"""Screen frames for lighting, via the xdg-desktop-portal ScreenCast and a PipeWire stream.

The portal asks the user once which screen to share; with a restore token it
reuses that choice silently next time. Frames are scaled down in GStreamer so
only a tiny RGB image reaches Python.
"""

import asyncio
import os
import secrets
import threading

import numpy as np

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
SOURCE_MONITOR = 1
CURSOR_HIDDEN, CURSOR_EMBEDDED = 1, 2
PERSIST_UNTIL_REVOKED = 2
CALL_TIMEOUT = 30.0


class PortalError(Exception):
    pass


class Cancelled(Exception):
    pass


def sender_part(unique_name):
    """':1.42' -> '1_42', as the portal spells a caller in object paths."""
    return unique_name.lstrip(":").replace(".", "_")


def request_path(unique_name, token):
    return f"{PORTAL_PATH}/request/{sender_part(unique_name)}/{token}"


def session_path(unique_name, token):
    return f"{PORTAL_PATH}/session/{sender_part(unique_name)}/{token}"


def rgb_from_buffer(data, width, height, stride):
    """Copy a packed RGB image with `stride` bytes per row into an (h, w, 3) array."""
    rows = np.frombuffer(data, dtype=np.uint8, count=stride * height).reshape(height, stride)
    return rows[:, :width * 3].reshape(height, width, 3).copy()


def pipeline_description(source, size, fps):
    w, h = size
    return (f"{source} ! videorate ! video/x-raw,framerate={fps}/1 "
            f"! videoscale add-borders=false ! video/x-raw,width={w},height={h} "
            f"! videoconvert ! video/x-raw,format=RGB "
            f"! appsink name=sink max-buffers=1 drop=true sync=false emit-signals=false")


class FramePump:
    """Runs a GStreamer pipeline ending in an appsink and keeps the latest RGB frame."""

    def __init__(self, description, on_error=None):
        self.description = description
        self.on_error = on_error
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None
        self._pipeline = None

    def start(self):
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstApp", "1.0")
        gi.require_version("GstVideo", "1.0")
        from gi.repository import Gst, GstApp  # noqa: F401  (GstApp adds the appsink methods)
        Gst.init(None)
        self._pipeline = Gst.parse_launch(self.description)
        self._sink = self._pipeline.get_by_name("sink")
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._pipeline.set_state(Gst.State.NULL)
            raise PortalError("Could not start the screen capture pipeline")
        self._running = True
        self._thread = threading.Thread(target=self._pull, daemon=True, name="g502hub-screen")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        if self._pipeline is not None:
            from gi.repository import Gst
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

    def frame(self):
        with self._lock:
            return self._frame

    def _pull(self):
        try:
            self._pull_frames()
        except Exception as e:
            self._running = False
            if self.on_error:
                self.on_error(f"Screen capture failed: {e}")

    def _pull_frames(self):
        from gi.repository import Gst, GstVideo
        bus = self._pipeline.get_bus()
        while self._running:
            msg = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg is not None:
                if msg.type == Gst.MessageType.ERROR:
                    err, _ = msg.parse_error()
                    text = err.message
                else:
                    text = "The screen capture stream ended"
                self._running = False
                if self.on_error:
                    self.on_error(text)
                return
            sample = self._sink.try_pull_sample(100 * Gst.MSECOND)
            if sample is None:
                continue
            info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
            buf = sample.get_buffer()
            meta = GstVideo.buffer_get_video_meta(buf)
            stride = meta.stride[0] if meta is not None else info.stride[0]
            ok, mapped = buf.map(Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                frame = rgb_from_buffer(mapped.data, info.width, info.height, stride)
            finally:
                buf.unmap(mapped)
            with self._lock:
                self._frame = frame


class ScreenCapture:
    """A downscaled live view of one monitor. Safe to poll from any thread; never raises."""

    _bus_address = None  # tests: a private bus with a fake portal
    _pipeline_source = None  # tests: replaces pipewiresrc

    def __init__(self, restore_token=None, size=(64, 36), fps=30):
        self.restore_token = restore_token
        self.size, self.fps = size, fps
        self.state = "idle"
        self.error = None
        self.source_size = None
        self._lock = threading.Lock()
        self._thread = None
        self._loop = None
        self._task = None
        self._pump = None
        self._fd = None
        self._stopping = False

    def start(self):
        with self._lock:
            if self.state in ("starting", "running"):
                return
            self.state, self.error = "starting", None
            self._stopping = False
            self._thread = threading.Thread(target=self._run, daemon=True, name="g502hub-portal")
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stopping = True  # in case the thread hasn't created its task yet
            loop, task, thread = self._loop, self._task, self._thread
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:  # loop already closed
                pass
        if thread is not None:
            thread.join(timeout=2)
        with self._lock:
            if self.state in ("starting", "running"):
                self.state = "idle"

    def frame(self):
        pump = self._pump
        return pump.frame() if pump is not None else None

    # ------------------------------------------------------------ portal thread

    def _run(self):
        loop = asyncio.new_event_loop()
        try:
            with self._lock:
                if self._stopping:
                    return
                self._loop = loop
                self._task = loop.create_task(self._main())
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # never let the thread die silently
            self._fail(str(e) or type(e).__name__)
        finally:
            with self._lock:
                self._loop = self._task = None
            loop.close()

    def _fail(self, text, state="error"):
        with self._lock:
            self.state, self.error = state, text

    async def _main(self):
        try:
            from dbus_fast.aio import MessageBus
        except ImportError:
            self._fail("python-dbus-fast is not installed")
            return
        bus = None
        session = None
        current_request = [None]
        try:
            bus = await MessageBus(self._bus_address, negotiate_unix_fd=True).connect()
            session = await self._open(bus, current_request)
            await asyncio.get_running_loop().create_future()  # capture until cancelled
        except asyncio.CancelledError:
            pass
        except Cancelled:
            self._fail(None, "cancelled")
        except PortalError as e:
            self._fail(str(e))
        except Exception as e:
            self._fail(f"Screen capture failed: {e}")
        finally:
            pump, self._pump = self._pump, None
            if pump is not None:
                pump.stop()
            fd, self._fd = self._fd, None
            if fd is not None:  # pipewiresrc works on its own copy
                try:
                    os.close(fd)
                except OSError:
                    pass
            if bus is not None:
                await self._close(bus, session, current_request[0])
                bus.disconnect()

    async def _close(self, bus, session, request):
        from dbus_fast import Message
        for path, iface in ((request, REQUEST), (session, SESSION)):
            if path is None:
                continue
            try:
                await asyncio.wait_for(bus.call(Message(
                    destination=PORTAL, path=path, interface=iface, member="Close")), 2)
            except Exception:
                pass

    async def _open(self, bus, current_request):
        from dbus_fast import Message, MessageType, Variant

        version = await self._property(bus, "version", 1)
        cursor_modes = await self._property(bus, "AvailableCursorModes", 0)

        async def request(method, signature, body, options):
            token = "g502hub_" + secrets.token_hex(6)
            path = request_path(bus.unique_name, token)
            options = dict(options, handle_token=Variant("s", token))
            done = asyncio.get_running_loop().create_future()
            paths = {path}

            def on_message(msg):
                if (msg.message_type == MessageType.SIGNAL and msg.interface == REQUEST
                        and msg.member == "Response" and msg.path in paths and not done.done()):
                    done.set_result(msg.body)

            bus.add_message_handler(on_message)
            try:
                await self._add_match(bus, path)
                current_request[0] = path
                reply = await asyncio.wait_for(bus.call(Message(
                    destination=PORTAL, path=PORTAL_PATH, interface=SCREENCAST, member=method,
                    signature=signature, body=body + [options])), CALL_TIMEOUT)
                if reply.message_type == MessageType.ERROR:
                    raise PortalError(f"{method}: {reply.body[0] if reply.body else reply.error_name}")
                handle = reply.body[0]
                if handle != path:  # very old portals pick their own path
                    paths.add(handle)
                    current_request[0] = handle
                    await self._add_match(bus, handle)
                code, results = await done  # Start waits for the user, so no timeout
            finally:
                bus.remove_message_handler(on_message)
                if done.done() and not done.cancelled():  # else still pending: closed on the way out
                    current_request[0] = None
            if code == 1:
                raise Cancelled()
            if code != 0:
                raise PortalError(f"The screen share request failed ({method})")
            return results

        session_token = "g502hub_" + secrets.token_hex(6)
        results = await request("CreateSession", "a{sv}", [],
                                {"session_handle_token": Variant("s", session_token)})
        session = results["session_handle"].value
        try:
            options = {"types": Variant("u", SOURCE_MONITOR), "multiple": Variant("b", False)}
            if cursor_modes & CURSOR_HIDDEN:
                options["cursor_mode"] = Variant("u", CURSOR_HIDDEN)
            if version >= 4:
                options["persist_mode"] = Variant("u", PERSIST_UNTIL_REVOKED)
                if self.restore_token:
                    options["restore_token"] = Variant("s", self.restore_token)
            await request("SelectSources", "oa{sv}", [session], options)
            results = await request("Start", "osa{sv}", [session, ""], {})
            if "restore_token" in results:
                self.restore_token = results["restore_token"].value
            streams = results["streams"].value if "streams" in results else []
            if not streams:
                raise PortalError("No screen was shared")
            node, props = streams[0]
            if "size" in props:
                w, h = props["size"].value
                self.source_size = (int(w), int(h))

            reply = await asyncio.wait_for(bus.call(Message(
                destination=PORTAL, path=PORTAL_PATH, interface=SCREENCAST,
                member="OpenPipeWireRemote", signature="oa{sv}", body=[session, {}])), CALL_TIMEOUT)
            if reply.message_type == MessageType.ERROR:
                raise PortalError(f"OpenPipeWireRemote: {reply.body[0] if reply.body else reply.error_name}")
            index = reply.body[0]
            fd = self._fd = reply.unix_fds[index] if reply.unix_fds else index

            source = self._pipeline_source or \
                f"pipewiresrc fd={fd} path={node} do-timestamp=true keepalive-time=1000"
            pump = FramePump(pipeline_description(source, self.size, self.fps),
                             on_error=lambda text: self._fail(text))
            await asyncio.get_running_loop().run_in_executor(None, pump.start)
            self._pump = pump
            await self._watch_session(bus, session)
            with self._lock:
                if self.state == "starting":
                    self.state = "running"
            return session
        except BaseException:
            await self._close(bus, session, current_request[0])
            current_request[0] = None
            raise

    async def _watch_session(self, bus, session):
        """The user can stop sharing from the desktop; the portal then closes the session."""
        from dbus_fast import MessageType

        def on_message(msg):
            if (msg.message_type == MessageType.SIGNAL and msg.interface == SESSION
                    and msg.member == "Closed" and msg.path == session):
                self._fail("Screen sharing was stopped")

        bus.add_message_handler(on_message)
        await self._add_match(bus, session, SESSION, "Closed")

    @staticmethod
    async def _add_match(bus, path, interface=REQUEST, member="Response"):
        from dbus_fast import Message
        rule = f"type='signal',interface='{interface}',member='{member}',path='{path}'"
        await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                               interface="org.freedesktop.DBus", member="AddMatch",
                               signature="s", body=[rule]))

    @staticmethod
    async def _property(bus, name, default):
        from dbus_fast import Message, MessageType
        reply = await asyncio.wait_for(bus.call(Message(
            destination=PORTAL, path=PORTAL_PATH, interface="org.freedesktop.DBus.Properties",
            member="Get", signature="ss", body=[SCREENCAST, name])), CALL_TIMEOUT)
        if reply.message_type == MessageType.ERROR:
            return default
        return reply.body[0].value
