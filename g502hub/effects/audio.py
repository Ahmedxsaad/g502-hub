"""System audio levels for lighting: parec on the default sink monitor, analysed with numpy."""

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

import numpy as np

BANDS = {"level": (20, 10000), "bass": (20, 150), "mid": (150, 2000), "treble": (2000, 10000)}
NOISE_FLOOR_DB = -50.0  # band amplitude (dBFS) below which a band reads 0
BAND_RANGE_DB = 24.0  # a band is never gained up more than this relative to overall loudness
GATE_DB = 6.0  # soft gate width above the floor
PEAK_HALF_LIFE = 5.0  # seconds for the auto-gain peak to fall by half
RELEASE = 0.12  # seconds for an output level to fall back after a hit
CENTROID_RANGE = (50.0, 8000.0)
BEAT_RATIO = 2.0  # bass energy vs its ~1 s average
BEAT_REFRACTORY = 0.15  # seconds
STALE_AFTER = 0.3  # seconds without audio data before levels read 0


@dataclass(frozen=True)
class Levels:
    level: float  # overall loudness 0..1 (auto-gained)
    bass: float  # ~20-150 Hz energy 0..1 (auto-gained per band)
    mid: float  # ~150-2000 Hz
    treble: float  # ~2000-10000 Hz
    centroid: float  # spectral centroid mapped to 0..1 (log scale, ~50 Hz..8 kHz)
    beat: bool  # a bass onset was detected


SILENT = Levels(0.0, 0.0, 0.0, 0.0, 0.0, False)


class Analyzer:
    """Hann-windowed FFT over a sliding window; feed it mono samples, get Levels."""

    def __init__(self, rate=44100, size=1024, hop=512):
        self.rate, self.size, self.hop = rate, size, hop
        self.window = np.hanning(size)
        self._norm = self.window.sum() / 2  # a full-scale sine peaks at ~1.0
        freqs = np.fft.rfftfreq(size, 1 / rate)
        self._bins = {name: (freqs >= lo) & (freqs < hi) for name, (lo, hi) in BANDS.items()}
        lo, hi = CENTROID_RANGE
        self._centroid_bins = (freqs >= lo) & (freqs <= hi)
        self._freqs = freqs[self._centroid_bins]
        hops_per_s = rate / hop
        self._peak_decay = 0.5 ** (1 / (PEAK_HALF_LIFE * hops_per_s))
        self._release = np.exp(-1 / (RELEASE * hops_per_s))
        self._floor = 10 ** (NOISE_FLOOR_DB / 20)
        self._band_range = 10 ** (-BAND_RANGE_DB / 20)
        self._peaks = {name: self._floor for name in BANDS}
        self._out = {name: 0.0 for name in BANDS}
        self._centroid = 0.0
        self._bass_history = np.zeros(max(1, int(hops_per_s)))  # ~1 s of bass energy
        self._history_i = 0
        self._history_full = False
        self._since_beat = BEAT_REFRACTORY
        self._buf = np.zeros(0)

    def feed(self, samples):
        """Add samples (int16 or float -1..1); returns the latest Levels, or None if no new window."""
        samples = np.asarray(samples)
        if samples.dtype == np.int16:
            samples = samples.astype(np.float64) / 32768.0
        self._buf = np.concatenate([self._buf, samples.astype(np.float64, copy=False)])
        result = None
        beat = False
        while len(self._buf) >= self.size:
            levels = self._analyse(self._buf[:self.size])
            beat = beat or levels.beat
            result = levels
            self._buf = self._buf[self.hop:]
        if result is not None and beat and not result.beat:
            result = Levels(result.level, result.bass, result.mid, result.treble, result.centroid, True)
        return result

    def _analyse(self, chunk):
        power = (np.abs(np.fft.rfft(chunk * self.window)) / self._norm) ** 2
        values = {}
        for name, bins in self._bins.items():
            amp = np.sqrt(power[bins].sum())
            # The overall peak (computed first) keeps quiet bands, e.g. leakage, from being blown up
            relative = self._peaks["level"] * self._band_range if name != "level" else 0.0
            peak = max(amp, self._peaks[name] * self._peak_decay, self._floor, relative)
            self._peaks[name] = peak
            db = 20 * np.log10(max(amp, 1e-12))
            gate = min(max((db - NOISE_FLOOR_DB) / GATE_DB, 0.0), 1.0)
            target = min(amp / peak, 1.0) * gate
            self._out[name] = max(target, self._out[name] * self._release)
            values[name] = amp

        cpow = power[self._centroid_bins]
        if values["level"] > self._floor and cpow.sum() > 0:
            c = (self._freqs * cpow).sum() / cpow.sum()
            lo, hi = CENTROID_RANGE
            c = min(max(np.log(c / lo) / np.log(hi / lo), 0.0), 1.0)
            self._centroid += (c - self._centroid) * 0.3

        energy = values["bass"] ** 2
        history = self._bass_history if self._history_full else self._bass_history[:self._history_i]
        average = history.mean() if len(history) else 0.0
        self._since_beat += self.hop / self.rate
        beat = (len(history) >= 4 and values["bass"] > self._floor * 2
                and energy > BEAT_RATIO * average and self._since_beat >= BEAT_REFRACTORY)
        if beat:
            self._since_beat = 0.0
        self._bass_history[self._history_i] = energy
        self._history_i = (self._history_i + 1) % len(self._bass_history)
        self._history_full = self._history_full or self._history_i == 0

        o = self._out
        return Levels(float(o["level"]), float(o["bass"]), float(o["mid"]), float(o["treble"]),
                      float(self._centroid), bool(beat))


class AudioMonitor:
    """Levels of whatever is playing, from `parec` on a PulseAudio/PipeWire monitor source.

    Safe to poll from any thread. A beat stays reported until the next levels() call reads it.
    """

    def __init__(self, source="@DEFAULT_MONITOR@", rate=44100):
        self.source, self.rate = source, rate
        self.state = "idle"
        self.error = None
        self._lock = threading.Lock()
        self._levels = None
        self._beat = False
        self._updated = 0.0
        self._proc = None
        self._thread = None
        self._stopping = False

    def start(self):
        with self._lock:
            if self.state == "running":
                return
            parec = shutil.which("parec")
            if parec is None:
                self.state, self.error = "error", "parec not found (install libpulse)"
                return
            cmd = [parec, "-d", self.source, "--raw", "--format=s16le", f"--rate={self.rate}",
                   "--channels=1", "--latency-msec=20"]
            try:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as e:
                self.state, self.error = "error", f"Could not start parec: {e}"
                return
            self._stopping = False
            self._levels, self._beat = None, False
            self.state, self.error = "running", None
            self._thread = threading.Thread(target=self._read, args=(self._proc,), daemon=True,
                                            name="g502hub-audio")
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stopping = True
            proc, thread = self._proc, self._thread
            self._proc = self._thread = None
            if self.state == "running":
                self.state = "idle"
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        if thread is not None:
            thread.join(timeout=1)

    def levels(self):
        with self._lock:
            levels, beat = self._levels, self._beat
            self._beat = False
            if levels is None:
                return None
            if time.monotonic() - self._updated > STALE_AFTER:
                return SILENT
        if beat != levels.beat:
            levels = Levels(levels.level, levels.bass, levels.mid, levels.treble, levels.centroid, beat)
        return levels

    def _read(self, proc):
        analyzer = Analyzer(self.rate)
        fd = proc.stdout.fileno()
        leftover = b""
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                data = b""
            if not data:
                break
            data = leftover + data
            usable = len(data) - len(data) % 2
            leftover = data[usable:]
            levels = analyzer.feed(np.frombuffer(data[:usable], dtype="<i2"))
            if levels is not None:
                with self._lock:
                    self._levels = levels
                    self._beat = self._beat or levels.beat
                    self._updated = time.monotonic()
        with self._lock:
            if self._stopping:
                return
            try:
                message = proc.stderr.read().decode(errors="replace").strip()
            except (OSError, ValueError):
                message = ""
            self.state = "error"
            self.error = f"parec exited ({proc.poll()}): {message}" if message else f"parec exited ({proc.poll()})"
