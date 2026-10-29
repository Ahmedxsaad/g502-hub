"""Rules: "while this is happening, use this lighting / profile".

A rule's trigger looks at a context.Context (active window, running Steam
game, playing media); the first enabled rule that matches wins.
"""

import uuid
from dataclasses import asdict, dataclass, field


def QT_TRANSLATE_NOOP(context, text):
    return text


TRIGGERS = {
    "game": QT_TRANSLATE_NOOP("GamesPage", "A game is running"),
    "app": QT_TRANSLATE_NOOP("GamesPage", "This app is in front"),
    "title": QT_TRANSLATE_NOOP("GamesPage", "The window title contains"),
    "media": QT_TRANSLATE_NOOP("GamesPage", "Playing media contains"),
}
ANY_GAME = "any"

# Lighting a rule can apply; None in a rule means "leave the lighting alone"
LIGHTING = {
    "color": QT_TRANSLATE_NOOP("GamesPage", "Color"),
    "breathing": QT_TRANSLATE_NOOP("GamesPage", "Breathing"),
    "art": QT_TRANSLATE_NOOP("GamesPage", "Cover art colors"),
    "game": QT_TRANSLATE_NOOP("GamesPage", "Game-driven"),
    "screen": QT_TRANSLATE_NOOP("GamesPage", "Screen sampler"),
    "audio": QT_TRANSLATE_NOOP("GamesPage", "Audio visualizer"),
    "wave": QT_TRANSLATE_NOOP("GamesPage", "Color wave"),
    "dpi": QT_TRANSLATE_NOOP("GamesPage", "DPI colors"),
}


@dataclass
class Rule:
    name: str
    trigger: str              # a TRIGGERS key
    value: str                # game: appid or ANY_GAME; app: window class; title/media: text to find
    lighting: str | None = None
    color: str = "#14b4ff"    # for color / breathing
    period_ms: int = 4000     # for breathing
    slot: int | None = None   # onboard profile slot to switch to (its DPI levels, buttons...)
    enabled: bool = True
    id: str = field(default_factory=lambda: new_id())

    def matches(self, ctx):
        if not self.enabled or not self.value:
            return False
        want = self.value.strip().lower()
        if self.trigger == "game":
            return ctx.game is not None and (want == ANY_GAME or want == str(ctx.game.appid))
        if self.trigger == "app":
            return ctx.app.lower() == want
        if self.trigger == "title":
            return want in ctx.title.lower()
        if self.trigger == "media":
            return any(m.status == "Playing" and want in media_text(m) for m in ctx.media)
        return False

    def describe_trigger(self, game_names=None):
        if self.trigger == "game":
            if self.value == ANY_GAME:
                return "While any game is running"
            name = (game_names or {}).get(self.value, f"Steam app {self.value}")
            return f"While {name} is running"
        if self.trigger == "app":
            return f"While {self.value} is in front"
        if self.trigger == "title":
            return f"While a window title contains “{self.value}”"
        return f"While playing media contains “{self.value}”"

    def describe_action(self):
        parts = []
        if self.lighting in ("color", "breathing"):
            parts.append(f"{LIGHTING[self.lighting]} {self.color}")
        elif self.lighting:
            parts.append(LIGHTING[self.lighting])
        if self.slot:
            parts.append(f"profile slot {self.slot}")
        return ", ".join(parts) or "nothing yet"

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        known = {k: d[k] for k in Rule.__dataclass_fields__ if k in d}
        rule = Rule(**known)
        if rule.trigger not in TRIGGERS:
            raise ValueError(f"unknown trigger {rule.trigger!r}")
        if rule.lighting is not None and rule.lighting not in LIGHTING:
            rule.lighting = None
        return rule


def new_id():
    return uuid.uuid4().hex[:8]


def media_text(m):
    return " ".join((m.title, m.artist, m.album, m.url, m.identity)).lower()


def first_match(rules, ctx):
    return next((r for r in rules if r.matches(ctx)), None)


def load(items):
    """Rules from settings, skipping any that are malformed."""
    out = []
    for d in items or []:
        try:
            out.append(Rule.from_dict(d))
        except (TypeError, ValueError):
            continue
    return out


# Ready-made rules offered in the "Add rule" menu
TEMPLATES = [
    Rule("YouTube", "media", "youtube", lighting="color", color="#ff0000"),
    Rule("Netflix", "media", "netflix", lighting="color", color="#e50914"),
    Rule("Twitch", "media", "twitch", lighting="color", color="#9146ff"),
    Rule("Spotify", "media", "spotify", lighting="audio"),
    Rule("Any Steam game", "game", ANY_GAME, lighting="art"),
    Rule("Counter-Strike 2", "game", "730", lighting="game"),
    Rule("Dota 2", "game", "570", lighting="game"),
]
