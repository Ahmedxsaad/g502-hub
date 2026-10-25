// Reports the active window to G502 Hub over D-Bus.
// Loaded at runtime by g502hub/context.py, which fills in SERVICE.
const SERVICE = "%SERVICE%";
let watched = null;

function report(window) {
    callDBus(SERVICE, "/Context", "io.github.g502hub.Context", "ActiveWindow",
             window ? String(window.resourceClass || "") : "",
             window ? String(window.caption || "") : "",
             window && window.pid ? String(window.pid) : "");
}

function captionChanged() {
    report(workspace.activeWindow);
}

function activated(window) {
    if (watched) {
        try {
            watched.captionChanged.disconnect(captionChanged);
        } catch (e) {
            // the previous window is already gone
        }
    }
    watched = window;
    if (window) {
        window.captionChanged.connect(captionChanged);
    }
    report(window);
}

workspace.windowActivated.connect(activated);
activated(workspace.activeWindow);
