import threading
import time
from _ctypes import COMError

import comtypes
import psutil
from pycaw.pycaw import (
    AudioUtilities,
    DEVICE_STATE,
    EDataFlow,
    IAudioMeterInformation,
    IAudioSessionControl2,
    IAudioSessionManager2,
)


CODEX_PROCESSES = {"chatgpt.exe", "codex.exe"}


def codex_meters(flow=EDataFlow.eRender.value):
    meters = []
    devices = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(
        flow, DEVICE_STATE.ACTIVE.value
    )
    for device_index in range(devices.GetCount()):
        try:
            device = devices.Item(device_index)
            interface = device.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None)
            manager = interface.QueryInterface(IAudioSessionManager2)
            sessions = manager.GetSessionEnumerator()
            count = sessions.GetCount()
        except COMError:
            continue
        for index in range(count):
            try:
                session = sessions.GetSession(index)
                pid = session.QueryInterface(IAudioSessionControl2).GetProcessId()
                if pid and psutil.Process(pid).name().casefold() in CODEX_PROCESSES:
                    if flow == EDataFlow.eCapture.value and session.GetState() != 1:
                        continue
                    meters.append(session.QueryInterface(IAudioMeterInformation))
            except (COMError, psutil.Error):
                continue
    return meters


def peak_level(meters):
    level = 0.0
    for meter in meters:
        try:
            level = max(level, meter.GetPeakValue())
        except COMError:
            continue
    return level


class SpeechActivity:
    def __init__(self):
        self.noise = 0.008
        self.frames = 0
        self.until = 0.0

    def update(self, peak, now):
        if peak >= max(0.023, self.noise * 2.8):
            self.frames += 1
            if self.frames >= 2:
                self.until = now + 0.23
        else:
            self.frames = 0
            self.noise += (peak - self.noise) * 0.06
        return now < self.until


class ReplyPlayback:
    """Allow one reply chime per user turn using Codex input and output levels."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.user_started = None
        self.armed = False
        self.first_audio = None
        self.last_audio = None
        self.ignore_input_until = 0.0

    def ignore_input(self, now, duration=0.9):
        self.user_started = None
        self.ignore_input_until = max(self.ignore_input_until, now + duration)

    def update(self, level, now, connected, user_speaking):
        if not connected:
            self.reset()
            return False

        if level >= 0.012:
            self.ignore_input(now, duration=0.45)
            if self.armed and (self.first_audio is not None or not user_speaking):
                if self.first_audio is None:
                    self.first_audio = now
                self.last_audio = now
            return False

        if user_speaking and now >= self.ignore_input_until:
            if self.user_started is None:
                self.user_started = now
            if now - self.user_started >= 0.3:
                # A new user turn replaces a pending chime from the previous reply.
                self.armed = True
                self.first_audio = self.last_audio = None
        else:
            self.user_started = None

        if user_speaking or self.last_audio is None or now - self.last_audio < 2.5:
            return False
        finished = self.last_audio - self.first_audio >= 0.25
        self.first_audio = self.last_audio = None
        if finished:
            self.armed = False
            self.ignore_input(now)
        return finished


class CodexAudioMeter:
    def __init__(self, monitor_capture=True):
        self.level = 0.0
        self.capturing = False
        self.user_speaking = False
        self.stop = threading.Event()
        threading.Thread(target=self.monitor, args=(monitor_capture,),
                         name="friday-codex-audio", daemon=True).start()

    def monitor(self, monitor_capture):
        comtypes.CoInitialize()
        meters = []
        capture = []
        activity = SpeechActivity()
        try:
            refresh_at = 0.0
            while not self.stop.is_set():
                now = time.monotonic()
                if now >= refresh_at:
                    try:
                        meters = codex_meters()
                    except COMError:
                        meters = []
                    if monitor_capture:
                        try:
                            capture = codex_meters(EDataFlow.eCapture.value)
                        except COMError:
                            capture = []
                        if not capture:
                            activity = SpeechActivity()
                        self.capturing = bool(capture)
                    refresh_at = time.monotonic() + 0.45
                self.level = peak_level(meters)
                self.user_speaking = self.capturing and activity.update(peak_level(capture), now)
                self.stop.wait(0.04)
        finally:
            self.level = 0.0
            self.capturing = self.user_speaking = False
            meters.clear()
            capture.clear()
            comtypes.CoUninitialize()

    def close(self):
        self.stop.set()
