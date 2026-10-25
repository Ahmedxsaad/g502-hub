from types import SimpleNamespace

import numpy as np

from g502hub import lightfx


def frame(color, h=36, w=64):
    f = np.zeros((h, w, 3), np.uint8)
    f[:] = color
    return f


def levels(**kw):
    base = dict(level=0.0, bass=0.0, mid=0.0, treble=0.0, centroid=0.5, beat=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_average_of_solid_frame():
    r, g, b = lightfx.sample(frame((255, 0, 0)), vivid=False)
    assert (round(r, 3), g, b) == (1.0, 0.0, 0.0)


def test_vivid_picks_colored_light_over_grey():
    f = frame((60, 60, 60))
    f[:6, :8] = (0, 200, 255)  # a small cyan highlight in a grey scene
    r, g, b = lightfx.sample(f, vivid=True)
    assert b > 0.4 and b > r * 3 and g > r * 3


def test_vivid_black_is_off():
    assert lightfx.sample(frame((0, 0, 0))) == lightfx.OFF


def test_vivid_dark_scene_stays_dim():
    dark = lightfx.sample(frame((20, 0, 0)))
    bright = lightfx.sample(frame((240, 0, 0)))
    assert max(dark) < max(bright) * 0.5


def test_areas_sample_their_part():
    f = frame((0, 0, 0))
    f[:, :21] = (255, 0, 0)      # left third red
    f[:, 43:] = (0, 0, 255)      # right third blue
    assert lightfx.sample(f, "left", vivid=False)[0] > 0.9
    assert lightfx.sample(f, "right", vivid=False)[2] > 0.9


def test_adjust_and_smooth():
    h = lightfx.adjust((0.5, 0.25, 0.25), saturation=2.0)
    assert h[1] < 0.05 and abs(h[0] - 0.5) < 1e-6
    assert lightfx.smooth(None, (1, 1, 1), 0.2) == (1, 1, 1)
    assert lightfx.smooth((0, 0, 0), (1, 1, 1), 0.25) == (0.25, 0.25, 0.25)


def test_wave_zones_are_offset():
    assert lightfx.wave(0, 4, 0) != lightfx.wave(0, 4, 1)
    assert np.allclose(lightfx.wave(4, 4, 0), lightfx.wave(0, 4, 0))


def test_audio_pulse_silence_is_off_and_bass_lights():
    assert lightfx.audio_pulse(levels(), (1, 0, 0)) == {0: (0, 0, 0), 1: (0, 0, 0)}
    loud = lightfx.audio_pulse(levels(bass=1.0, level=1.0), (1, 0, 0))
    assert loud[1][0] > 0.9


def test_audio_spectrum_bass_on_logo_treble_on_dpi():
    out = lightfx.audio_spectrum(levels(bass=1.0, treble=0.0))
    assert max(out[1]) > 0.9 and max(out[0]) < 0.05


def test_beat_rainbow_moves_on_beats():
    fx = lightfx.BeatRainbow()
    a = fx(levels(level=1.0))
    b = fx(levels(level=1.0, beat=True))
    assert a[1] != b[1]


def test_to_rgb8():
    assert lightfx.to_rgb8((1.0, 0.5, -1)) == (255, 128, 0)
    assert lightfx.hex_to_rgb("#ff8000") == (1.0, 128 / 255, 0.0)
