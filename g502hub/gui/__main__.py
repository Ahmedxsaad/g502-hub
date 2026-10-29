"""Open settings, or start only the service for legacy --tray autostart."""

import sys

if "--tray" in sys.argv[1:]:
    from ..ipc import ensure_service
    ensure_service()
else:
    from .app import main
    main()
