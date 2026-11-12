import argparse
import json
import os
import queue
import sys
import time
import wave
from _ctypes import COMError
from uuid import uuid4
from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from branding import APP_NAME, INSTALL_ROOT as HERE


def enable_background_log():
    log = HERE / ".runtime" / "listener.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.is_file() and log.stat().st_size > 1_000_000:
        log.replace(log.with_suffix(".previous.log"))
    sys.stdout = sys.stderr = log.open("a", encoding="utf-8", buffering=1)
    print(f"\nUruchomienie nasłuchu: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

import numpy as np
import sounddevice as sd
import soxr
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model
from chimes import play_chime
from codex_audio import CodexAudioMeter, ReplyPlayback
from codex_chats import ChatAccessError, chat_link, list_chats
from localization import AUTO, normalize_control_name, voice_control_labels
from voice_settings import DEFAULT_STOP, load_phrases, phrase_revision, phrase_words
from voice_replay import AutomaticReplay, REPLAY_REQUESTS


MODEL = HERE / ".models" / "whisper-base"
INBOX = HERE / ".runtime" / "notifications"
RATE = 16_000
FRAME_BYTES = RATE * 30 // 1000 * 2
MIN_RMS = 10 ** (-62 / 20)
ABOVE_BACKGROUND = 10 ** (10 / 20)
VOICE_LABELS = voice_control_labels()
START_BUTTONS = VOICE_LABELS["start"] | {"Start voice chat", "Rozpocznij czat głosowy"}
END_BUTTONS = VOICE_LABELS["end"] | {
    "Stop voice chat", "End voice chat", "Zatrzymaj czat głosowy",
    "Zakończ czat głosowy",
}
CANCEL_BUTTONS = VOICE_LABELS["cancel"] | {"Cancel voice chat", "Anuluj czat głosowy"}
ENDING_BUTTONS = VOICE_LABELS["ending"] | {"Ending voice chat", "Kończenie czatu głosowego"}
VOICE_BUTTONS = START_BUTTONS | END_BUTTONS | CANCEL_BUTTONS | ENDING_BUTTONS
MICROPHONE_BUTTONS = {
    "Wycisz mikrofon", "Wyłącz mikrofon", "Włącz mikrofon", "Mute microphone", "Unmute microphone",
}
COMPOSER_NAMES = {"Pracuj z Codex", "Work with Codex"}
SEND_BUTTONS = {"Wyślij", "Wyślij wiadomość", "Send", "Send message"}


class CloseResult(Enum):
    REQUESTED_AND_CONFIRMED = "program wysłał polecenie i Codex potwierdził zamknięcie"
    ALREADY_CLOSED = "Codex już zakończył rozmowę przed poleceniem programu"
    CONTROLS_GONE = "program wysłał polecenie, ale zniknęły przyciski głosu i brakuje potwierdzenia"
    UNCONFIRMED = "nie udało się potwierdzić zamknięcia"


def notify_ready(summary):
    clean = " ".join(summary.split())[:200]
    if not clean:
        raise ValueError("Podaj krótki opis gotowej odpowiedzi.")
    INBOX.mkdir(parents=True, exist_ok=True)
    target = INBOX / f"{uuid4().hex}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"summary": clean, "time": time.time()}), encoding="utf-8")
    temporary.replace(target)


def take_notification():
    for path in INBOX.glob("*.json"):
        try:
            payload = path.read_bytes()
            path.unlink()
        except OSError:
            continue
        try:
            data = json.loads(payload)
            summary = data["summary"]
            if isinstance(summary, str) and summary and 0 <= time.time() - data["time"] < 600:
                return summary
        except (ValueError, TypeError, KeyError):
            continue
    return None


def run_mcp():
    from mcp.server.fastmcp import FastMCP
    import desktop_tools

    server = FastMCP(
        APP_NAME,
        instructions="Wykonuj akcje Windows zgodnie z poleceniem użytkownika. "
                     "Zrzut ekranu rób na jego wyraźne żądanie. "
                     "Gdy użytkownik chce sygnału po ukończeniu zadania, wywołaj "
                     "notify_answer_ready tuż przed przekazaniem gotowego wyniku.",
    )

    @server.tool()
    def notify_answer_ready(summary: str) -> str:
        """Wyślij do działającego lokalnie Codex Voice Control sygnał o gotowym wyniku."""
        notify_ready(summary)
        return f"Sygnał zapisany w kolejce aplikacji {APP_NAME}."

    for action in (
        desktop_tools.browser_open,
        desktop_tools.browser_focus,
        desktop_tools.browser_new_tab,
        desktop_tools.browser_search,
        desktop_tools.browser_type,
        desktop_tools.browser_click,
        desktop_tools.browser_youtube,
        desktop_tools.capture_screen,
    ):
        server.add_tool(action)

    server.run(transport="stdio")


def command_for(text, start_phrases, stop_phrases=(DEFAULT_STOP,), language="pl"):
    words = phrase_words(text, language)
    if any(words == phrase_words(phrase, language) for phrase in start_phrases):
        return "start"
    if isinstance(stop_phrases, str):
        stop_phrases = (stop_phrases,)
    if any(words == phrase_words(phrase, language) for phrase in stop_phrases):
        return "stop"
    return None


def recognize(model, audio, start_phrases, stop_phrases=(DEFAULT_STOP,), language="pl"):
    if len(audio) < RATE // 5:
        return None, ""
    if isinstance(stop_phrases, str):
        stop_phrases = (stop_phrases,)
    segments, info = model.transcribe(
        audio, language=None if language == AUTO else language, beam_size=2, temperature=0,
        condition_on_previous_text=False, hotwords=" ".join((*start_phrases, *stop_phrases)),
        no_speech_threshold=0.45, log_prob_threshold=-0.8,
    )
    text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.55)
    match_language = "zh" if language == AUTO and info.language == "zh" else language
    return command_for(text, start_phrases, stop_phrases, match_language), text


def read_wave(path):
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2:
            raise ValueError("Próbka musi być plikiem WAV PCM 16-bit.")
        rate = source.getframerate()
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
        audio = audio.reshape(-1, source.getnchannels()).mean(axis=1).astype(np.float32)
    return soxr.resample(audio / 32768, rate, RATE)


class Utterances:
    def __init__(self, rate):
        self.resampler = soxr.ResampleStream(rate, RATE, 1, dtype="int16")
        self.background = MIN_RMS / ABOVE_BACKGROUND
        self.pending = bytearray()
        self.leading = deque(maxlen=9)
        self.frames = []
        self.quiet = 0
        self.discard = False

    def add(self, block):
        samples = np.frombuffer(block, dtype=np.int16)
        self.pending.extend(self.resampler.resample_chunk(samples).tobytes())
        complete = []
        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
            samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768
            rms = float(np.sqrt(np.mean(samples * samples)))
            voiced = rms >= max(MIN_RMS, self.background * ABOVE_BACKGROUND)
            if not voiced or self.discard:
                self.background = 0.97 * self.background + 0.03 * rms
            if voiced and not self.frames and not self.discard:
                self.frames = list(self.leading)
            self.leading.append(frame)
            if (voiced or self.frames) and not self.discard:
                self.frames.append(frame)
                if len(self.frames) > 125:
                    self.frames.clear()
                    self.discard = True
            self.quiet = 0 if voiced else self.quiet + 1
            if self.quiet >= 12:
                if self.frames:
                    complete.append(np.frombuffer(
                        b"".join(self.frames), dtype=np.int16
                    ).astype(np.float32) / 32768)
                    self.frames.clear()
                self.discard = False
        return complete


@dataclass
class Microphone:
    name: str
    rate: int
    channels: int
    detector: Utterances

    def add(self, block):
        if self.channels == 1:
            return self.detector.add(block)
        samples = np.frombuffer(block, dtype=np.int16).reshape(-1, self.channels)
        strength = np.mean(samples.astype(np.float32) ** 2, axis=0)
        return self.detector.add(samples[:, int(np.argmax(strength))].tobytes())

    def score(self, audio):
        return float(np.percentile(np.abs(audio), 90)) / max(self.detector.background, 0.0001)

    def reset(self):
        background = self.detector.background
        self.detector = Utterances(self.rate)
        self.detector.background = background


def open_microphones(stack, selected, blocks):
    devices = sd.query_devices()
    hosts = sd.query_hostapis()
    wasapi = next((i for i, host in enumerate(hosts) if host["name"] == "Windows WASAPI"), None)
    fallback = None
    if selected is None:
        candidates = [
            i for i, device in enumerate(devices)
            if device["hostapi"] == wasapi and device["max_input_channels"] > 0
            and not device["name"].casefold().startswith(("miks stereo", "stereo mix"))
        ]
        default_input = int(sd.default.device[0])
        if default_input >= 0 and default_input not in candidates:
            fallback = default_input
            candidates.append(fallback)
    else:
        candidates = [selected]

    microphones = {}
    for index in candidates:
        if index == fallback and microphones:
            continue
        info = sd.query_devices(index, "input")
        rate = int(info["default_samplerate"])
        channels = min(2, int(info["max_input_channels"]))
        settings = sd.WasapiSettings(auto_convert=True) if info["hostapi"] == wasapi else None

        def receive(data, frames, timing, status, device_index=index):
            try:
                blocks.put_nowait((device_index, bytes(data)))
            except queue.Full:
                pass

        try:
            stack.enter_context(sd.RawInputStream(
                device=index, samplerate=rate, channels=channels, dtype="int16",
                blocksize=rate // 20, callback=receive, extra_settings=settings,
            ))
        except sd.PortAudioError as exc:
            print(f"Pomijam niedostępne wejście {info['name']}: {exc}", flush=True)
            continue
        microphones[index] = Microphone(info["name"], rate, channels, Utterances(rate))
    if not microphones:
        raise RuntimeError("Nie udało się otworzyć żadnego mikrofonu.")
    return microphones


class Desktop:
    def __init__(self):
        import uiautomation as ui
        import psutil
        import win32gui
        import win32process
        from pywintypes import error as window_error

        self.ui = ui
        self.psutil = psutil
        self.win32gui = win32gui
        self.win32process = win32process
        self.window_error = window_error
        self.window = None
        self.window_handle = None
        self.window_pid = None
        self.last_codex_handle = None
        self.foreground_handle = None

    def controls(self, names, require_enabled=True, names_only=False):
        if self.window is None:
            return []
        matches = []
        try:
            for control, _ in self.ui.WalkControl(self.window, maxDepth=40):
                try:
                    if control.ControlType != self.ui.ControlType.ButtonControl:
                        continue
                    name = normalize_control_name(control.Name)
                    if (name in names and (not require_enabled or control.IsEnabled)
                            and not control.IsOffscreen):
                        matches.append(name if names_only else control)
                except COMError:
                    continue
        except (COMError, OSError, LookupError):
            pass
        return matches

    def codex_window(self, handle):
        if not handle:
            return None
        try:
            _, pid = self.win32process.GetWindowThreadProcessId(handle)
            if self.psutil.Process(pid).name().casefold() not in {"chatgpt.exe", "codex.exe"}:
                return None
            window = self.ui.ControlFromHandle(handle)
            if window and (window.ControlType == self.ui.ControlType.WindowControl
                           or window.ClassName == "Chrome_WidgetWin_1") and window.Name:
                return window
        except (self.psutil.Error, self.window_error, COMError, OSError, LookupError):
            pass
        return None

    def remember_window(self):
        handle = self.ui.GetForegroundWindow()
        if handle != self.foreground_handle:
            self.foreground_handle = handle
            if self.codex_window(handle):
                self.last_codex_handle = handle

    def select_window(self):
        self.remember_window()
        if self.codex_window(self.last_codex_handle):
            return self.last_codex_handle

        # When settings or the tray has focus, use the topmost visible Codex window.
        # Native window enumeration preserves stacking order, unlike the UIA tree.
        candidate = None

        def find_window(handle, _):
            nonlocal candidate
            if candidate is None and self.win32gui.IsWindowVisible(handle) and self.codex_window(handle):
                candidate = handle
            return True

        try:
            self.win32gui.EnumWindows(find_window, None)
        except (self.window_error, OSError):
            return None
        return candidate

    def refresh_window(self, restore=False):
        self.window = self.codex_window(self.window_handle)
        if self.window is None:
            return False
        try:
            _, pid = self.win32process.GetWindowThreadProcessId(self.window_handle)
        except self.window_error:
            self.window = None
            return False
        if self.window_pid is not None and self.window_pid != pid:
            self.window = None
            return False
        self.window_pid = pid
        if restore and self.ui.IsIconic(self.window_handle):
            self.ui.ShowWindow(self.window_handle, self.ui.SW.Restore)
        return True

    def call_window_disappeared(self):
        if not self.window_handle or not self.win32gui.IsWindow(self.window_handle):
            return True
        try:
            _, pid = self.win32process.GetWindowThreadProcessId(self.window_handle)
            return pid != self.window_pid
        except self.window_error:
            return True

    def call_state(self):
        names = set(self.controls(VOICE_BUTTONS, require_enabled=False, names_only=True))
        if names & (END_BUTTONS | CANCEL_BUTTONS | ENDING_BUTTONS):
            return "open"
        if names & START_BUTTONS and self.controls(START_BUTTONS):
            return "closed"
        return "unavailable"

    def wait_for(self, names, timeout=8, require_enabled=True):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            buttons = self.controls(names, require_enabled)
            if buttons:
                return buttons[0]
            time.sleep(0.2)
        return None

    def select_call_window(self, restore=False):
        self.window_handle = self.select_window()
        self.window_pid = None
        return self.refresh_window(restore=restore)

    def find_active_call(self):
        return self.select_call_window() and bool(self.controls(END_BUTTONS))

    def bind_chat_document(self, title):
        if self.window is None:
            return False
        expected = normalize_control_name(title).casefold()
        try:
            for control, _ in self.ui.WalkControl(self.window, maxDepth=16):
                try:
                    if (control.ControlType == self.ui.ControlType.DocumentControl
                            and not control.IsOffscreen
                            and normalize_control_name(control.Name).casefold() == expected):
                        self.window = control
                        return True
                except COMError:
                    continue
        except (COMError, OSError, LookupError):
            pass
        return False

    def open_fixed_chat(self, chat_id):
        try:
            title = dict(list_chats()).get(chat_id)
            if title is None:
                print("Wybrany czat jest niedostępny lub nie ma unikatowej nazwy.", flush=True)
                return None
            os.startfile(chat_link(chat_id))
        except (ChatAccessError, OSError, ValueError) as exc:
            print(f"Nie udało się otworzyć wybranego czatu: {exc}", flush=True)
            return None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.select_call_window() and self.bind_chat_document(title):
                return title
            time.sleep(0.2)
        print("Codex nie potwierdził otwarcia wybranego czatu.", flush=True)
        return None

    def open_call(self, chat_id=None):
        title = None
        if chat_id:
            title = self.open_fixed_chat(chat_id)
            if title is None:
                return False
        elif not self.select_call_window(restore=True):
            print("Otwórz docelowy czat w oknie Codexa i powtórz frazę startową.", flush=True)
            return False
        if not self.wait_for(VOICE_BUTTONS, timeout=2, require_enabled=False):
            print("W wybranym oknie otwórz istniejący czat z przyciskiem rozmowy głosowej.",
                  flush=True)
            return False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.controls(END_BUTTONS):
                return True
            button = self.wait_for(START_BUTTONS, timeout=2)
            if button:
                if title:
                    if not self.refresh_window() or not self.bind_chat_document(title):
                        return False
                    button = next(iter(self.controls(START_BUTTONS)), None)
                    if button is None:
                        return False
                try:
                    button.GetInvokePattern().Invoke()
                except (COMError, OSError, LookupError):
                    pass
                else:
                    if self.wait_for(END_BUTTONS, timeout=8):
                        return True
            if not self.refresh_window() or (title and not self.bind_chat_document(title)):
                break
            time.sleep(0.3)
        return False

    def close_call(self):
        if self.call_window_disappeared():
            return CloseResult.ALREADY_CLOSED
        button = next(iter(self.controls(END_BUTTONS | CANCEL_BUTTONS)), None)
        if button is None:
            if self.call_state() == "closed":
                return CloseResult.ALREADY_CLOSED
            if not self.refresh_window():
                return CloseResult.UNCONFIRMED
            button = self.wait_for(END_BUTTONS | CANCEL_BUTTONS, timeout=2)
            if button is None:
                return CloseResult.ALREADY_CLOSED if self.call_state() == "closed" else CloseResult.UNCONFIRMED
        for _ in range(3):
            try:
                button.GetInvokePattern().Invoke()
                break
            except (COMError, OSError, LookupError):
                button = self.wait_for(END_BUTTONS | CANCEL_BUTTONS, timeout=2)
                if button is None:
                    return CloseResult.ALREADY_CLOSED if self.call_state() == "closed" else CloseResult.UNCONFIRMED
        else:
            return CloseResult.UNCONFIRMED
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.call_window_disappeared() or self.call_state() == "closed":
                return CloseResult.REQUESTED_AND_CONFIRMED
            time.sleep(0.2)
        if self.call_state() == "unavailable":
            return CloseResult.CONTROLS_GONE
        return CloseResult.UNCONFIRMED

    def voice_chat_title(self):
        if not self.refresh_window():
            return None
        try:
            documents = [
                control for control, _ in self.ui.WalkControl(self.window, maxDepth=16)
                if control.ControlType == self.ui.ControlType.DocumentControl and not control.IsOffscreen
            ]
            if len(documents) != 1 or not documents[0].Name:
                return None
            self.window = documents[0]
            if self.controls(END_BUTTONS):
                return documents[0].Name
        except (COMError, LookupError, OSError):
            return None
        return None

    def suspend_for_replay(self):
        button = next(iter(self.controls(END_BUTTONS)), None)
        if button is None:
            return False
        try:
            button.GetInvokePattern().Invoke()
            return True
        except (COMError, LookupError, OSError):
            return False

    def request_replay(self, title):
        if not (self.refresh_window() and self.bind_chat_document(title) and self.controls(END_BUTTONS)):
            return False
        language = "pl" if self.controls({"Zatrzymaj czat głosowy"}, names_only=True) else "en"
        return self.send_voice_prompt(title, REPLAY_REQUESTS[language])

    def voice_composer(self):
        edits = [
            control for control, _ in self.ui.WalkControl(self.window, maxDepth=40)
            if control.ControlType == self.ui.ControlType.EditControl
            and control.IsEnabled and not control.IsOffscreen and control.Name in COMPOSER_NAMES
        ]
        if len(edits) == 1:
            return edits[0]
        return None

    def send_voice_prompt(self, title, prompt):
        if not (self.refresh_window() and self.bind_chat_document(title) and self.controls(END_BUTTONS)):
            return False
        value = None
        sent = False
        expected = normalize_control_name(prompt)
        try:
            edit = self.voice_composer()
            if edit is None:
                return False
            value = edit.GetValuePattern()
            if value is None or value.IsReadOnly or normalize_control_name(value.Value) not in {"", edit.Name}:
                return False
            value.SetValue(prompt)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if not self.refresh_window() or not self.bind_chat_document(title):
                    return False
                edit = self.voice_composer()
                if edit is not None and (current := edit.GetValuePattern()) is not None:
                    if normalize_control_name(current.Value) == expected:
                        buttons = [b for b in self.controls(SEND_BUTTONS) if "composer" in b.ClassName]
                        if len(buttons) == 1 and self.controls(END_BUTTONS | MICROPHONE_BUTTONS):
                            buttons[0].GetInvokePattern().Invoke()
                            sent = True
                            return True
                time.sleep(0.15)
            return False
        except (COMError, LookupError, OSError):
            return False
        finally:
            if value is not None and not sent:
                try:
                    if normalize_control_name(value.Value) == expected:
                        value.SetValue("")
                except (COMError, LookupError, OSError):
                    pass

    def close_reopened_chat(self, title):
        if self.refresh_window() and self.bind_chat_document(title):
            self.close_call()


def listen(model, settings, listen_only, device, should_stop):
    desktop = None if listen_only else Desktop()
    call_active = False
    controls_missing_since = None
    unconfirmed_window = None
    check_status_at = 0
    check_background_at = 0
    check_replay_at = 0
    call_started_at = 0
    blocks = queue.Queue(maxsize=300)
    candidates = []
    recognize_at = 0
    settings_revision = object()

    def reset_audio(microphones):
        candidates.clear()
        for microphone in microphones.values():
            microphone.reset()
        while True:
            try:
                blocks.get_nowait()
            except queue.Empty:
                return

    with ExitStack() as stack:
        microphones = open_microphones(stack, device, blocks)
        audio_meter = None if listen_only else CodexAudioMeter()
        reply = ReplyPlayback()
        automatic_replay = None if listen_only else AutomaticReplay()
        if audio_meter is not None:
            stack.callback(audio_meter.close)
            stack.callback(automatic_replay.close)
        names = ", ".join(microphone.name for microphone in microphones.values())
        print(f"Nasłuch lokalny: {names}. Ctrl+C wyłącza program.", flush=True)
        print("Frazy startowe: " + " | ".join(settings.starts), flush=True)
        last_block_at = time.monotonic()
        while not should_stop():
            try:
                index, block = blocks.get(timeout=0.25)
            except queue.Empty:
                if time.monotonic() - last_block_at >= 5:
                    raise RuntimeError("Mikrofon przestał przekazywać dźwięk.")
                continue
            last_block_at = time.monotonic()
            microphone = microphones.get(index)
            if microphone is None:
                continue
            phrases = microphone.add(block)
            now = time.monotonic()
            if now >= check_background_at:
                check_background_at = now + 0.5
                try:
                    revision = phrase_revision()
                    if revision != settings_revision:
                        settings_revision = revision
                        settings = load_phrases()
                except (OSError, ValueError) as exc:
                    print(f"Nie można wczytać ustawień fraz: {exc}", flush=True)
                if not listen_only:
                    desktop.remember_window()
                    if notice := take_notification():
                        print(f"Wynik gotowy: {notice}", flush=True)
                        if settings.sounds["ready"] != "mute":
                            reply.ignore_input(now)
                        play_chime(settings.sounds["ready"])
            if phrases:
                if not candidates:
                    recognize_at = now + (0.18 if len(microphones) > 1 else 0)
                candidates.extend((microphone.score(audio), microphone.name, audio) for audio in phrases)
            command = None
            if candidates and now >= recognize_at:
                ranked = sorted(candidates, key=lambda candidate: candidate[0], reverse=True)
                candidates.clear()
                for _, name, audio in ranked:
                    command, _ = recognize(
                        model, audio, settings.starts, settings.stops, settings.speech_language,
                    )
                    if command:
                        print(f"Wykryto: {command} ({name})", flush=True)
                        break
                if listen_only and command is None:
                    print(f"Odebrano dźwięk bez komendy ({ranked[0][1]}).", flush=True)
            if listen_only:
                continue
            if command or not settings.auto_replay:
                if command == "stop" and automatic_replay.phase in {"wait", "speak"}:
                    print("Anulowano automatyczny odczyt poleceniem głosowym.", flush=True)
                automatic_replay.cancel()
            elif now >= check_replay_at:
                check_replay_at = now + 1
                replay_result = automatic_replay.check(desktop, call_active, call_started_at)
                if replay_result == "suspended":
                    call_active = False
                    reset_audio(microphones)
                elif replay_result == "resumed":
                    call_active = True
                    call_started_at = time.time()
                    controls_missing_since = None
                    check_status_at = time.monotonic() + 1
            if reply.update(audio_meter.level, time.monotonic(), call_active and command != "stop",
                            audio_meter.user_speaking):
                if settings.sounds["spoken"] != "mute":
                    print("Koniec odpowiedzi głosowej.", flush=True)
                    play_chime(settings.sounds["spoken"])
            if not call_active:
                if automatic_replay.phase == "wait":
                    continue
                if command == "start":
                    print("Uruchamiam głos w wybranym czacie Codexa.", flush=True)
                    if not desktop.open_call(settings.chat_id):
                        print("Nie udało się potwierdzić połączenia.", flush=True)
                        reset_audio(microphones)
                        continue
                    print("Połączono. Możesz mówić.", flush=True)
                    unconfirmed_window = None
                    reset_audio(microphones)
                elif command == "stop" or now >= check_status_at:
                    active = desktop.find_active_call()
                    check_status_at = time.monotonic() + 1
                    if not active:
                        continue
                    print("Wykryto rozmowę włączoną ręcznie.", flush=True)
                else:
                    continue
                call_active = True
                call_started_at = time.time()
                controls_missing_since = None
                check_status_at = time.monotonic() + 1
                if desktop.window_handle != unconfirmed_window:
                    if settings.sounds["connected"] != "mute":
                        reply.ignore_input(time.monotonic())
                    play_chime(settings.sounds["connected"])
                unconfirmed_window = None
            requested_stop = command == "stop"
            if not requested_stop and now >= check_status_at:
                window_gone = desktop.call_window_disappeared()
                state = "closed" if window_gone else desktop.call_state()
                checked_at = time.monotonic()
                check_status_at = checked_at + 1
                if state == "unavailable":
                    if controls_missing_since is None:
                        controls_missing_since = checked_at
                    if checked_at - controls_missing_since >= 3:
                        print("Brak przycisków rozmowy w Codexie. Nasłuch lokalny.", flush=True)
                        unconfirmed_window = desktop.window_handle
                        call_active = False
                        if automatic_replay.phase == "identify":
                            automatic_replay.cancel()
                        reset_audio(microphones)
                    continue
                controls_missing_since = None
                if state == "closed":
                    call_active = False
                    if automatic_replay.phase == "identify":
                        automatic_replay.cancel()
                    if window_gone:
                        print("Okno rozmowy Codexa zostało zamknięte. Nasłuch lokalny.", flush=True)
                    else:
                        print("Rozmowa zamknięta w Codexie. Nasłuch lokalny.", flush=True)
                    play_chime(settings.sounds["disconnected"])
                    reset_audio(microphones)
                    continue
            if requested_stop:
                closing_started = time.monotonic()
                result = desktop.close_call()
                elapsed = time.monotonic() - closing_started
                print(f"Zamknięcie (komenda głosowa; czas próby {elapsed:.1f} s): {result.value}.",
                      flush=True)
                if result is not CloseResult.UNCONFIRMED:
                    call_active = False
                    if result is CloseResult.CONTROLS_GONE:
                        unconfirmed_window = desktop.window_handle
                        print("Brak przycisków rozmowy w Codexie. Nasłuch lokalny.", flush=True)
                    else:
                        print("Rozłączono. Nasłuch lokalny.", flush=True)
                        play_chime(settings.sounds["disconnected"])
                else:
                    print("Nie udało się potwierdzić rozłączenia. Sprawdź okno Codexa.", flush=True)
                reset_audio(microphones)


def main():
    parser = argparse.ArgumentParser(description="Lokalne sterowanie rozmową głosową w Codexie.")
    parser.add_argument("--model-dir", type=Path, default=MODEL)
    parser.add_argument("--prepare", action="store_true", help="Pobierz model, bez użycia mikrofonu.")
    parser.add_argument("--listen-only", action="store_true", help="Rozpoznawaj frazy bez sterowania Codexem.")
    parser.add_argument("--from-wav", type=Path, help="Rozpoznaj próbkę lokalną, bez sterowania Codexem.")
    parser.add_argument("--device", type=int, help="Numer mikrofonu widoczny w --list-devices.")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--mcp", action="store_true", help="Uruchom lokalny interfejs MCP.")
    parser.add_argument("--notify", metavar="TEKST", help="Dodaj lokalny sygnał testowy.")
    parser.add_argument("--background", action="store_true", help="Zapisuj stan nasłuchu do lokalnego logu.")
    args = parser.parse_args()
    if args.background and not args.mcp:
        enable_background_log()
    if args.mcp:
        run_mcp()
        return
    if args.notify is not None:
        notify_ready(args.notify)
        return
    if args.list_devices:
        print(sd.query_devices())
        return
    if args.prepare:
        download_model("base", output_dir=str(args.model_dir))
        return
    if not (args.model_dir / "model.bin").is_file():
        parser.error("Brakuje modelu. Uruchom najpierw Przygotuj.cmd.")
    try:
        settings = load_phrases()
    except (OSError, ValueError) as exc:
        parser.error(f"Nie można wczytać fraz startowych: {exc}")
    with ExitStack() as cleanup:
        stop_event = None
        if not args.from_wav and not args.listen_only:
            import win32event
            from listener_state import LISTENER_MUTEX, STOP_EVENT

            mutex = win32event.CreateMutex(None, False, LISTENER_MUTEX)
            cleanup.callback(mutex.Close)
            if win32event.WaitForSingleObject(mutex, 0) == win32event.WAIT_TIMEOUT:
                print(f"Nasłuch {APP_NAME} jest już uruchomiony.", flush=True)
                return
            cleanup.callback(win32event.ReleaseMutex, mutex)
            stop_event = win32event.CreateEvent(None, True, False, STOP_EVENT)
            cleanup.callback(stop_event.Close)
            win32event.ResetEvent(stop_event)
        model = WhisperModel(str(args.model_dir), device="cpu", compute_type="int8",
                             cpu_threads=4, local_files_only=True)
        if args.from_wav:
            command, text = recognize(
                model, read_wave(args.from_wav), settings.starts, settings.stops, settings.speech_language,
            )
            print(f"{command or 'brak'}: {text}")
            return
        try:
            def should_stop():
                return (stop_event is not None and
                        win32event.WaitForSingleObject(stop_event, 0) == win32event.WAIT_OBJECT_0)

            listen(model, settings, args.listen_only, args.device, should_stop)
            print("Wyłączono lokalny nasłuch.", flush=True)
        except KeyboardInterrupt:
            print("\nWyłączono lokalny nasłuch.")
        except (COMError, OSError, RuntimeError, queue.Empty) as exc:
            parser.exit(1, f"Błąd nasłuchu lub sterowania: {exc}\n")


if __name__ == "__main__":
    main()
