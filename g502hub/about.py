"""Who made this, and where to find it. Shown on the About page."""

from . import __version__

APP_NAME = "G502 Hub"
TAGLINE = "The G HUB experience for the Logitech G502 HERO, on Linux"
VERSION = __version__
AUTHOR = "Ahmed Saad"
LICENSE = "GPL-3.0-or-later"

# Fill these in before publishing (tools/set-github-user.sh sets GITHUB); empty ones are hidden.
GITHUB = "Ahmedxsaad"   # GitHub username that hosts the g502-hub repository
REDDIT = ""   # Reddit username, without u/
DONATE = ""   # a Ko-fi, PayPal or GitHub Sponsors link

DISCLAIMER = ("An unofficial, independent project. Not affiliated with, endorsed or supported by "
              "Logitech. Logitech, Logitech G, G HUB, LIGHTSYNC, HERO and G502 are trademarks of "
              "Logitech Europe S.A.; Counter-Strike 2, Dota 2 and Steam are trademarks of Valve "
              "Corporation. The mouse photo is Logitech's, downloaded from logitechg.com on first start.")

# Projects whose public code and notes on Logitech's HID++ protocol helped map the mouse
# (see docs/protocol.md for the exact references)
CREDITS = [
    ("libratbag", "https://github.com/libratbag/libratbag"),
    ("Solaar", "https://github.com/pwr-Solaar/Solaar"),
    ("cvuchener/hidpp", "https://github.com/cvuchener/hidpp"),
    ("OpenRGB", "https://gitlab.com/CalcProgrammer1/OpenRGB"),
    ("Linux hid-logitech-hidpp", "https://github.com/torvalds/linux"),
]


def repo_url():
    return f"https://github.com/{GITHUB}/g502-hub" if GITHUB else ""


def links():
    """(label, url) for the About page, only the ones that are set."""
    out = []
    if GITHUB:
        out += [("GitHub", repo_url()), ("Report a bug", repo_url() + "/issues")]
    if REDDIT:
        out.append(("Reddit", f"https://www.reddit.com/user/{REDDIT}"))
    if DONATE:
        out.append(("Support the project", DONATE))
    return out
