/* Wire format between the LogitechLed.dll stand-in and G502 Hub.
 *
 * One UDP datagram per SDK call, sent to 127.0.0.1:LS_PORT.
 * Little endian. Header: 'L' 'S' LS_VERSION op, then the caller's process id
 * (uint32), then the op's int32 arguments. HELLO carries the game's name as
 * bytes after the header (as the game passed it, up to LS_NAME_MAX).
 * Colors are the SDK's percentages, 0-100.
 *
 * g502hub/effects/lightsync.py mirrors these values; a test checks they match.
 */

#define LS_PORT 41503
#define LS_VERSION 1
#define LS_NAME_MAX 64

#define LS_OP_HELLO 1     /* (name bytes) */
#define LS_OP_SHUTDOWN 2  /* () */
#define LS_OP_TARGET 3    /* (target device flags) */
#define LS_OP_SET 4       /* (r, g, b) */
#define LS_OP_FLASH 5     /* (r, g, b, duration ms, interval ms) */
#define LS_OP_PULSE 6     /* (r, g, b, duration ms, interval ms) */
#define LS_OP_STOP 7      /* () */
#define LS_OP_SAVE 8      /* () */
#define LS_OP_RESTORE 9   /* () */
#define LS_OP_ZONE 10     /* (device type, zone, r, g, b) */
#define LS_OP_AMBIENT 11  /* (r, g, b): average of a per-key bitmap */
#define LS_OP_PING 12     /* () once a second while initialised */
