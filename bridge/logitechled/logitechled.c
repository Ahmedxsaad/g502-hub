/* A stand-in for Logitech's LogitechLed.dll (LED SDK 9 surface plus the older
 * LGS names) for games running under Wine/Proton. Every lighting call is
 * forwarded to G502 Hub as one UDP datagram (protocol.h); the app turns them
 * into colors on the mouse. Per-key keyboard calls are accepted and ignored,
 * except that a per-key bitmap is averaged into one "ambient" color so games
 * that only light keyboards still light the mouse.
 *
 * Freestanding: no CRT and no Windows headers, see build.sh.
 */

#include "protocol.h"

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int i32;
typedef __SIZE_TYPE__ size_t;
typedef __UINTPTR_TYPE__ uptr;

#ifdef __i386__
#define WINAPI __attribute__((stdcall))
#else
#define WINAPI
#endif
#define IMPORT __attribute__((dllimport))

IMPORT u32 WINAPI GetCurrentProcessId(void);
IMPORT void WINAPI Sleep(u32 ms);
IMPORT void *WINAPI CreateThread(void *attributes, size_t stack, u32(WINAPI *start)(void *), void *param,
                                 u32 flags, u32 *id);
IMPORT int WINAPI CloseHandle(void *handle);
IMPORT int WINAPI GetModuleHandleExW(u32 flags, const u16 *name, void **module);
IMPORT __attribute__((noreturn)) void WINAPI FreeLibraryAndExitThread(void *module, u32 code);

IMPORT int WINAPI WSAStartup(u16 version, void *data);
IMPORT uptr WINAPI socket(int af, int type, int protocol);
IMPORT int WINAPI sendto(uptr s, const char *buf, int len, int flags, const void *to, int tolen);

#define AF_INET 2
#define SOCK_DGRAM 2
#define IPPROTO_UDP 17
#define INVALID_SOCKET ((uptr)~(uptr)0)
#define GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS 4

#define BITMAP_KEYS (21 * 6)
#define MAX_ARGS 6

struct sockaddr_in {
    u16 family;
    u16 port;  /* network order */
    u32 addr;  /* network order */
    u8 zero[8];
};

/* The compiler may emit calls to these even when freestanding */
void *memset(void *dst, int c, size_t n)
{
    volatile u8 *d = dst;
    while (n--)
        *d++ = (u8)c;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
    volatile u8 *d = dst;
    const u8 *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}

/* ------------------------------------------------------------ transport */

static volatile long g_socket_state;  /* 0 none, 1 opening, 2 ready, 3 failed */
static uptr g_socket;
static struct sockaddr_in g_addr;
static u8 g_wsadata[512] __attribute__((aligned(16)));  /* WSADATA is ~400 bytes */
static volatile long g_running;  /* between Init and Shutdown */
static volatile long g_pinger;   /* the ping thread is alive */

static int open_socket(void)
{
    long expected = 0;
    if (__atomic_load_n(&g_socket_state, __ATOMIC_ACQUIRE) == 2)
        return 1;
    if (__atomic_compare_exchange_n(&g_socket_state, &expected, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        int ok = WSAStartup(0x0202, g_wsadata) == 0;
        if (ok) {
            g_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
            ok = g_socket != INVALID_SOCKET;
        }
        g_addr.family = AF_INET;
        g_addr.port = (u16)(((LS_PORT & 0xff) << 8) | (LS_PORT >> 8));
        g_addr.addr = 0x0100007f;  /* 127.0.0.1 */
        __atomic_store_n(&g_socket_state, ok ? 2 : 3, __ATOMIC_RELEASE);
        return ok;
    }
    while (__atomic_load_n(&g_socket_state, __ATOMIC_ACQUIRE) == 1)
        Sleep(0);
    return __atomic_load_n(&g_socket_state, __ATOMIC_ACQUIRE) == 2;
}

static void put32(u8 *p, u32 v)
{
    p[0] = (u8)v;
    p[1] = (u8)(v >> 8);
    p[2] = (u8)(v >> 16);
    p[3] = (u8)(v >> 24);
}

static void send_op(int op, const i32 *args, int nargs, const char *text)
{
    u8 buf[8 + MAX_ARGS * 4 + LS_NAME_MAX];
    int n = 8, i;
    if (!open_socket())
        return;
    buf[0] = 'L';
    buf[1] = 'S';
    buf[2] = LS_VERSION;
    buf[3] = (u8)op;
    put32(buf + 4, GetCurrentProcessId());
    for (i = 0; i < nargs && i < MAX_ARGS; i++, n += 4)
        put32(buf + n, (u32)args[i]);
    for (i = 0; text && text[i] && i < LS_NAME_MAX; i++)
        buf[n++] = (u8)text[i];
    sendto(g_socket, (const char *)buf, n, 0, &g_addr, sizeof g_addr);
}

static void send0(int op)
{
    send_op(op, 0, 0, 0);
}

static void send3(int op, int a, int b, int c)
{
    i32 args[3] = {a, b, c};
    send_op(op, args, 3, 0);
}

static void send5(int op, int a, int b, int c, int d, int e)
{
    i32 args[5] = {a, b, c, d, e};
    send_op(op, args, 5, 0);
}

/* Pings tell the app the game is still there even when its colors don't change. */
static u32 WINAPI pinger(void *unused)
{
    void *self = 0;
    int ticks = 0;
    long expected;
    (void)unused;
    /* Hold a reference so the game unloading the DLL can't pull the code from under this thread */
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, (const u16 *)(void *)pinger, &self);
    for (;;) {
        while (__atomic_load_n(&g_running, __ATOMIC_ACQUIRE)) {
            Sleep(100);
            if (++ticks >= 10) {
                ticks = 0;
                if (__atomic_load_n(&g_running, __ATOMIC_ACQUIRE))
                    send0(LS_OP_PING);
            }
        }
        __atomic_store_n(&g_pinger, 0, __ATOMIC_RELEASE);
        expected = 0;
        /* Init again in the meantime: keep this thread instead of starting another */
        if (!__atomic_load_n(&g_running, __ATOMIC_ACQUIRE) ||
            !__atomic_compare_exchange_n(&g_pinger, &expected, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
            break;
    }
    if (self)
        FreeLibraryAndExitThread(self, 0);
    return 0;
}

static void start(const char *name)
{
    long expected = 0;
    __atomic_store_n(&g_running, 1, __ATOMIC_RELEASE);
    send_op(LS_OP_HELLO, 0, 0, name ? name : "");
    if (__atomic_compare_exchange_n(&g_pinger, &expected, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        void *thread = CreateThread(0, 0, pinger, 0, 0, 0);
        if (thread)
            CloseHandle(thread);
        else
            __atomic_store_n(&g_pinger, 0, __ATOMIC_RELEASE);
    }
}

int WINAPI DllMainCRTStartup(void *module, u32 reason, void *reserved)
{
    (void)module;
    (void)reason;
    (void)reserved;
    return 1;
}

/* ------------------------------------------------------------ SDK: setup */

_Bool LogiLedInit(void)
{
    start(0);
    return 1;
}

_Bool LogiLedInitWithName(const char name[])
{
    start(name);
    return 1;
}

_Bool LogiLedGetSdkVersion(int *major, int *minor, int *build)
{
    if (major)
        *major = 9;
    if (minor)
        *minor = 0;
    if (build)
        *build = 0;
    return 1;
}

/* Game settings exposed to G HUB: keep the game's defaults */
_Bool LogiLedGetConfigOptionNumber(const u16 *path, double *value) { (void)path; (void)value; return 1; }
_Bool LogiLedGetConfigOptionBool(const u16 *path, _Bool *value) { (void)path; (void)value; return 1; }
_Bool LogiLedGetConfigOptionColor(const u16 *path, int *r, int *g, int *b)
{
    (void)path; (void)r; (void)g; (void)b;
    return 1;
}
_Bool LogiLedGetConfigOptionRect(const u16 *path, int *x, int *y, int *w, int *h)
{
    (void)path; (void)x; (void)y; (void)w; (void)h;
    return 1;
}
_Bool LogiLedGetConfigOptionString(const u16 *path, u16 *value, int size) { (void)path; (void)value; (void)size; return 1; }
_Bool LogiLedGetConfigOptionKeyInput(const u16 *path, u16 *value, int size) { (void)path; (void)value; (void)size; return 1; }
_Bool LogiLedGetConfigOptionSelect(const u16 *path, u16 *value, int *size, const u16 *values, int buffer)
{
    (void)path; (void)value; (void)size; (void)values; (void)buffer;
    return 1;
}
_Bool LogiLedGetConfigOptionRange(const u16 *path, int *value, int min, int max)
{
    (void)path; (void)value; (void)min; (void)max;
    return 1;
}
_Bool LogiLedSetConfigOptionLabel(const u16 *path, const u16 *label) { (void)path; (void)label; return 1; }

/* The same, under the names Logitech Gaming Software's SDK used (with an extra
 * SDK-type argument, harmless with cdecl) */
_Bool LogiGetConfigOptionNumber(const u16 *path, double *value, int sdk) { (void)sdk; return LogiLedGetConfigOptionNumber(path, value); }
_Bool LogiGetConfigOptionBool(const u16 *path, _Bool *value, int sdk) { (void)sdk; return LogiLedGetConfigOptionBool(path, value); }
_Bool LogiGetConfigOptionColor(const u16 *path, int *r, int *g, int *b, int sdk) { (void)sdk; return LogiLedGetConfigOptionColor(path, r, g, b); }
_Bool LogiGetConfigOptionKeyInput(const u16 *path, u16 *value, int size, int sdk) { (void)sdk; return LogiLedGetConfigOptionKeyInput(path, value, size); }
_Bool LogiSetConfigOptionLabel(const u16 *path, const u16 *label, int sdk) { (void)sdk; return LogiLedSetConfigOptionLabel(path, label); }

/* ------------------------------------------------------------ SDK: whole-device lighting */

_Bool LogiLedSetTargetDevice(int target)
{
    i32 args[1] = {target};
    send_op(LS_OP_TARGET, args, 1, 0);
    return 1;
}

_Bool LogiLedSaveCurrentLighting(void)
{
    send0(LS_OP_SAVE);
    return 1;
}

_Bool LogiLedSetLighting(int r, int g, int b)
{
    send3(LS_OP_SET, r, g, b);
    return 1;
}

_Bool LogiLedRestoreLighting(void)
{
    send0(LS_OP_RESTORE);
    return 1;
}

_Bool LogiLedFlashLighting(int r, int g, int b, int duration_ms, int interval_ms)
{
    send5(LS_OP_FLASH, r, g, b, duration_ms, interval_ms);
    return 1;
}

_Bool LogiLedPulseLighting(int r, int g, int b, int duration_ms, int interval_ms)
{
    send5(LS_OP_PULSE, r, g, b, duration_ms, interval_ms);
    return 1;
}

_Bool LogiLedStopEffects(void)
{
    send0(LS_OP_STOP);
    return 1;
}

_Bool LogiLedSetLightingForTargetZone(int device_type, int zone, int r, int g, int b)
{
    send5(LS_OP_ZONE, device_type, zone, r, g, b);
    return 1;
}

void LogiLedShutdown(void)
{
    __atomic_store_n(&g_running, 0, __ATOMIC_RELEASE);
    send0(LS_OP_SHUTDOWN);
}

/* ------------------------------------------------------------ SDK: per-key (keyboards) */

/* bitmap: 21 x 6 keys, 4 bytes each in BGRA order. Averaged, weighting
 * brighter keys more so unlit keys don't just darken the result. */
_Bool LogiLedSetLightingFromBitmap(const u8 bitmap[])
{
    u32 weight = 0, r = 0, g = 0, b = 0;
    int i;
    if (!bitmap)
        return 0;
    for (i = 0; i < BITMAP_KEYS; i++) {
        u32 kb = bitmap[4 * i], kg = bitmap[4 * i + 1], kr = bitmap[4 * i + 2];
        u32 w = kr > kg ? (kr > kb ? kr : kb) : (kg > kb ? kg : kb);
        weight += w;
        r += kr * w;
        g += kg * w;
        b += kb * w;
    }
    if (weight) {
        /* percent = sum * 100 / (weight * 255), rounded; at most ~820M, fits 32 bits */
        u32 scale = weight * 255;
        send3(LS_OP_AMBIENT, (int)((r * 100 + scale / 2) / scale), (int)((g * 100 + scale / 2) / scale),
              (int)((b * 100 + scale / 2) / scale));
    } else {
        send3(LS_OP_AMBIENT, 0, 0, 0);
    }
    return 1;
}

_Bool LogiLedSetLightingForKeyWithScanCode(int key, int r, int g, int b) { (void)key; (void)r; (void)g; (void)b; return 1; }
_Bool LogiLedSetLightingForKeyWithHidCode(int key, int r, int g, int b) { (void)key; (void)r; (void)g; (void)b; return 1; }
_Bool LogiLedSetLightingForKeyWithQuartzCode(int key, int r, int g, int b) { (void)key; (void)r; (void)g; (void)b; return 1; }
_Bool LogiLedSetLightingForKeyWithKeyName(int key, int r, int g, int b) { (void)key; (void)r; (void)g; (void)b; return 1; }
_Bool LogiLedSaveLightingForKey(int key) { (void)key; return 1; }
_Bool LogiLedRestoreLightingForKey(int key) { (void)key; return 1; }
_Bool LogiLedExcludeKeysFromBitmap(const int *keys, int count) { (void)keys; (void)count; return 1; }
_Bool LogiLedFlashSingleKey(int key, int r, int g, int b, int duration_ms, int interval_ms)
{
    (void)key; (void)r; (void)g; (void)b; (void)duration_ms; (void)interval_ms;
    return 1;
}
_Bool LogiLedPulseSingleKey(int key, int r0, int g0, int b0, int r1, int g1, int b1, int duration_ms, _Bool infinite)
{
    (void)key; (void)r0; (void)g0; (void)b0; (void)r1; (void)g1; (void)b1; (void)duration_ms; (void)infinite;
    return 1;
}
_Bool LogiLedStopEffectsOnKey(int key) { (void)key; return 1; }
