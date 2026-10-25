#!/usr/bin/env python3
"""Download Logitech's top-down product photo of the G502 HERO for the app.

The photo is Logitech's, so it isn't part of this repository: it is saved to
~/.local/share/g502-hub/ for your own copy of the app. Without it the app
shows its built-in drawing of the mouse.
"""

import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from g502hub.gui.photo import PHOTO_PATH, PHOTO_SIZE  # noqa: E402

URL = ("https://resource.logitechg.com/f_png,q_auto/content/dam/gaming/en/non-braid/"
       "hyjal-g502-hero/2025/g502-hero-mouse-top-angle-gallery-1.png")
# The mouse inside Logitech's 2500x2160 picture, with a short stub of cable
CROP = QRect(730, 130, 1030, 1850)


def main():
    print(f"Downloading {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    image = QImage.fromData(data)
    if image.isNull() or (image.width(), image.height()) != (2500, 2160):
        sys.exit(f"Unexpected image ({image.width()}x{image.height()}); Logitech may have changed it.")
    image = image.convertToFormat(QImage.Format.Format_ARGB32).copy(CROP)
    image = image.scaled(*PHOTO_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    PHOTO_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(PHOTO_PATH))
    print(f"Saved {PHOTO_PATH}")


if __name__ == "__main__":
    main()
