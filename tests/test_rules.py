from g502hub import rules
from g502hub.context import Context, Game, Media
from g502hub.rules import Rule


def ctx(app="", title="", game=None, media=()):
    return Context(app=app, title=title, pid=None, game=game, media=tuple(media))


def media(title="", url="", status="Playing", identity="Firefox", artist=""):
    return Media(player="firefox", identity=identity, title=title, artist=artist, album="", url=url, status=status)


BRAWL = Game(appid=291550, name="Brawlhalla", pid=42, art=None)


def test_game_rules():
    assert Rule("b", "game", "291550").matches(ctx(game=BRAWL))
    assert Rule("any", "game", rules.ANY_GAME).matches(ctx(game=BRAWL))
    assert not Rule("cs", "game", "730").matches(ctx(game=BRAWL))
    assert not Rule("any", "game", rules.ANY_GAME).matches(ctx())


def test_app_and_title_rules():
    c = ctx(app="firefox", title="Lofi beats - YouTube — Mozilla Firefox")
    assert Rule("ff", "app", "Firefox").matches(c)
    assert not Rule("mpv", "app", "mpv").matches(c)
    assert Rule("yt", "title", "youtube").matches(c)


def test_media_rules_only_while_playing():
    playing = ctx(media=[media("One Piece - Episode 1100", "")])
    paused = ctx(media=[media("One Piece - Episode 1100", "", status="Paused")])
    assert Rule("op", "media", "one piece").matches(playing)
    assert not Rule("op", "media", "one piece").matches(paused)
    assert Rule("yt", "media", "youtube").matches(ctx(media=[media("x", "https://www.youtube.com/watch?v=1")]))


def test_disabled_and_empty_rules_never_match():
    assert not Rule("off", "app", "firefox", enabled=False).matches(ctx(app="firefox"))
    assert not Rule("empty", "title", "").matches(ctx(title="anything"))


def test_first_match_wins():
    rs = [Rule("anime", "media", "one piece"), Rule("yt", "media", "youtube")]
    c = ctx(media=[media("One Piece on YouTube", "https://youtube.com")])
    assert rules.first_match(rs, c).name == "anime"
    assert rules.first_match(rs, ctx()) is None


def test_round_trip_and_bad_entries():
    r = Rule("YouTube", "media", "youtube", lighting="color", color="#ff0000", slot=3)
    assert Rule.from_dict(r.to_dict()) == r
    loaded = rules.load([r.to_dict(), {"name": "x"}, {"name": "y", "trigger": "nope", "value": "z"}])
    assert loaded == [r]
    odd = Rule.from_dict({**r.to_dict(), "lighting": "laser-show"})
    assert odd.lighting is None


def test_descriptions():
    r = Rule("b", "game", "291550", lighting="color", color="#ff0000", slot=2)
    assert r.describe_trigger({"291550": "Brawlhalla"}) == "While Brawlhalla is running"
    assert r.describe_action() == "Color #ff0000, profile slot 2"
    assert Rule("n", "title", "x").describe_action() == "nothing yet"
