import json
from pathlib import Path

import pytest

from g502hub import backup, onboard, sharing

FIXTURE = Path(__file__).parent / "fixtures" / "onboard-c08b.json"


def profiles():
    data = backup.load(FIXTURE)
    return [onboard.Profile.decode(data["sectors"][n]) for n in range(1, 6)]


def test_round_trip_is_byte_exact():
    for p in profiles():
        loaded, notes = sharing.load(sharing.export(p))
        assert loaded.encode() == p.encode()
        assert notes == []


def test_summary_is_readable():
    doc = json.loads(sharing.export(profiles()[1]))
    assert doc["summary"]["dpi"] and doc["summary"]["report_rate_hz"] in (125, 250, 500, 1000)
    assert len(doc["summary"]["buttons"]) == 11


def test_macros_are_disabled_with_a_note():
    p = profiles()[0]
    p.buttons[3] = onboard.Macro(page=7, offset=0, head=0)
    p.raw = p.encode()
    loaded, notes = sharing.load(sharing.export(p))
    assert isinstance(loaded.buttons[3], onboard.Disabled)
    assert notes and "button 4" in notes[0]


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(format="other"), "not a G502 Hub"),
    (lambda d: d.update(device="046d:c332"), "another device"),
    (lambda d: d.update(version=99), "newer version"),
    (lambda d: d.update(sector=d["sector"][:-4] + "0000"), "damaged"),
    (lambda d: d.update(sector="zz"), "damaged"),
])
def test_rejects_bad_files(change, message):
    doc = json.loads(sharing.export(profiles()[0]))
    change(doc)
    with pytest.raises(sharing.ShareError, match=message):
        sharing.load(json.dumps(doc))


def test_rejects_non_json():
    with pytest.raises(sharing.ShareError, match="not a profile file"):
        sharing.load("hello")
