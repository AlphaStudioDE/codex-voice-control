import io
import threading
import wave
import winsound
from dataclasses import dataclass
from functools import lru_cache
from queue import Full, Queue

import numpy as np


@dataclass(frozen=True)
class Note:
    frequency: float
    start: float = 0
    duration: float = 0.20
    gain: float = 0.11
    overtone: float = 2.0
    overtone_gain: float = 0.12
    end_frequency: float | None = None


NOTES = {
    "rise": (Note(523.25), Note(659.25, start=0.20)),
    "fall": (Note(523.25), Note(392.0, start=0.20)),
    "soft": (Note(440.0, gain=0.08), Note(523.25, start=0.20, gain=0.08)),
    "tap": (Note(554.37, duration=0.13, gain=0.09),),
    "wood": (Note(293.66, duration=0.17, gain=0.09, overtone=2.73, overtone_gain=0.20),),
    "glass": (Note(783.99, duration=0.36, gain=0.075, overtone=2.76, overtone_gain=0.17),),
    "drop": (Note(698.46, duration=0.24, gain=0.086, end_frequency=415.30),),
    "echo": (Note(587.33, duration=0.21, gain=0.082),
             Note(587.33, start=0.17, duration=0.20, gain=0.041)),
    "double": (Note(493.88, duration=0.12, gain=0.085),
               Note(493.88, start=0.145, duration=0.12, gain=0.075)),
    "chord": (Note(392.0, duration=0.35, gain=0.044),
              Note(493.88, start=0.025, duration=0.32, gain=0.035),
              Note(587.33, start=0.052, duration=0.29, gain=0.031)),
    "three": (Note(392.0, duration=0.14, gain=0.07),
              Note(493.88, start=0.10, duration=0.15, gain=0.075),
              Note(659.25, start=0.20, duration=0.20, gain=0.079)),
}
TONES = (*NOTES, "system", "mute")
DEFAULT_SOUNDS = {"connected": "rise", "disconnected": "fall", "spoken": "soft", "ready": "chord"}
playback_queue = Queue(maxsize=8)
playback_lock = threading.Lock()
preview_pending = threading.Event()
playback_worker = None


@lru_cache(maxsize=len(NOTES))
def chime_wave(tone):
    rate = 24_000
    notes = NOTES[tone]
    samples = np.zeros(max(round(rate * note.start) + round(rate * note.duration) for note in notes))
    for note in notes:
        start = round(rate * note.start)
        timeline = np.arange(round(rate * note.duration)) / rate
        envelope = np.minimum(timeline / 0.018, 1) * (1 - timeline / note.duration) ** 2
        end_frequency = note.frequency if note.end_frequency is None else note.end_frequency
        sweep = (end_frequency - note.frequency) / (2 * note.duration)
        phase = 2 * np.pi * (note.frequency * timeline + sweep * timeline ** 2)
        signal = np.sin(phase) + note.overtone_gain * np.sin(phase * note.overtone)
        samples[start:start + len(timeline)] += note.gain * envelope * signal
    pcm = (samples * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())
    return buffer.getvalue()


def play_queued_chimes():
    while True:
        tone, preview = playback_queue.get()
        try:
            if tone == "system":
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                winsound.PlaySound(chime_wave(tone), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except RuntimeError as exc:
            print(f"Could not play notification sound: {exc}", flush=True)
        finally:
            if preview:
                preview_pending.clear()
            playback_queue.task_done()


def play_chime(tone, *, preview=False):
    global playback_worker
    if tone == "mute":
        return
    if tone not in TONES:
        raise ValueError(f"Unknown notification sound: {tone}")
    with playback_lock:
        if preview and preview_pending.is_set():
            return
        if preview:
            preview_pending.set()
        try:
            playback_queue.put_nowait((tone, preview))
        except Full:
            if preview:
                preview_pending.clear()
            else:
                print("Notification sound queue is full.", flush=True)
            return
        if playback_worker is None or not playback_worker.is_alive():
            playback_worker = threading.Thread(target=play_queued_chimes, name="codex-voice-chimes", daemon=True)
            playback_worker.start()
