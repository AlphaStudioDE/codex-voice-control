import os
import subprocess
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import exp
from pathlib import Path

import pythoncom
import pywintypes
import win32api
import win32com.client
import win32event
from bar_art import (
    BACKGROUND, WAVE_HEIGHT, WAVE_PALETTES, bar_shadow, save_tray_icon, wave_frame,
)
from branding import APP_NAME, INSTALL_ROOT as ROOT, TASK_NAME
from codex_audio import CodexAudioMeter
from codex_chats import list_chats
from layered_surface import LayeredSurface
from listener_state import listener_running, request_stop
from localization import strings, windows_locale
from overlay_window import OverlayWindow
from tray import Tray
from settings_dialog import SettingsDialog
from voice_settings import load_phrases
from setup_support import COMPILED, EXECUTABLE, LAUNCHER, app_arguments


PYTHON = EXECUTABLE
LOG = ROOT / ".runtime" / "listener.log"
LISTENER_ARGUMENTS = "listener" if COMPILED else f'-s -B "{LAUNCHER}" listener'
TASK_LOGON_INTERACTIVE_TOKEN = 3
TASK_TRIGGER_LOGON = 9
TASK_ACTION_EXEC = 0
TASK_CREATE = 2
TASK_INSTANCES_IGNORE_NEW = 2
IDLE_WAVE_OPACITY = 0.65


@dataclass
class Status:
    listening: bool
    autostart: bool
    connected: bool = False


def scheduled_listener(folder):
    try:
        task = folder.GetTask(TASK_NAME)
    except pywintypes.com_error as exc:
        if any(isinstance(code, int) and code & 0xFFFFFFFF == 0x80070002
               for code in (exc.hresult, (exc.excepinfo or (None,))[-1])):
            return None
        raise
    actions = task.Definition.Actions
    if actions.Count != 1:
        raise RuntimeError(f"Zadanie o tej nazwie wskazuje na inną instalację {APP_NAME}.")
    action = actions.Item(1)
    launch = (Path(action.Path).resolve(), action.Arguments)
    accepted = {
        (PYTHON.resolve(), LISTENER_ARGUMENTS),
        ((ROOT / ".venv" / "Scripts" / "pythonw.exe").resolve(),
         f'-B "{ROOT / "friday.py"}" --background'),
    }
    if launch not in accepted:
        raise RuntimeError(f"Zadanie o tej nazwie wskazuje na inną instalację {APP_NAME}.")
    return task


def register_autostart(scheduler, folder):
    user = win32api.GetUserNameEx(2)
    definition = scheduler.NewTask(0)
    definition.RegistrationInfo.Description = f"Lokalny nasłuch komend {APP_NAME}"
    definition.Principal.UserId = user
    definition.Principal.LogonType = TASK_LOGON_INTERACTIVE_TOKEN
    definition.Triggers.Create(TASK_TRIGGER_LOGON).UserId = user
    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str(PYTHON)
    action.Arguments = LISTENER_ARGUMENTS
    action.WorkingDirectory = str(ROOT)
    settings = definition.Settings
    settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    settings.ExecutionTimeLimit = "PT0S"
    settings.StartWhenAvailable = True
    settings.DisallowStartIfOnBatteries = False
    settings.StopIfGoingOnBatteries = False
    settings.RestartInterval = "PT1M"
    settings.RestartCount = 3
    return folder.RegisterTaskDefinition(TASK_NAME, definition, TASK_CREATE, user, None,
                                         TASK_LOGON_INTERACTIVE_TOKEN)


def listener_connected():
    try:
        with LOG.open("rb") as stream:
            stream.seek(max(0, LOG.stat().st_size - 8192))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        if line.startswith(("Nasłuch lokalny: ", "Uruchomienie nasłuchu: ")):
            break
        if line.startswith(("Połączono.", "Wykryto rozmowę włączoną ręcznie.")):
            return True
        if line.startswith(("Rozłączono.", "Rozmowa zamknięta w Codexie.",
                            "Okno rozmowy Codexa zostało zamknięte.",
                            "Brak przycisków rozmowy w Codexie.")):
            break
    return False


def manage_listener(action=None):
    pythoncom.CoInitialize()
    task = None
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        folder = scheduler.GetFolder("\\")
        task = scheduled_listener(folder)
        if action == "start" and not listener_running():
            if task is not None and task.Enabled:
                task.Run("")
            else:
                subprocess.Popen([str(PYTHON), *app_arguments("listener")], cwd=ROOT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        elif action == "stop" and listener_running():
            if not request_stop():
                if task is None or not task.GetInstances(0).Count:
                    raise RuntimeError("Zamknij wcześniejszy nasłuch w jego oknie konsoli.")
                task.Stop(0)
        elif action == "autostart":
            if task is not None:
                task.Enabled = not task.Enabled
            else:
                task = register_autostart(scheduler, folder)
                if not listener_running():
                    task.Run("")
        listening = listener_running()
        return Status(listening, bool(task is not None and task.Enabled), listening and listener_connected())
    finally:
        task = None
        pythoncom.CoUninitialize()


def check_codex():
    pythoncom.CoInitialize()
    try:
        from friday import Desktop, VOICE_BUTTONS

        desktop = Desktop()
        if not desktop.select_call_window():
            return "open_chat"
        if not desktop.controls(VOICE_BUTTONS, require_enabled=False):
            return "voice_missing"
        return "voice_ready"
    finally:
        pythoncom.CoUninitialize()


class Panel:
    def __init__(self, root, poll=True):
        self.root = root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="friday-panel")
        self.pending = None
        self.pending_action = None
        self.status = None
        self.last_error = ""
        self.bar = None
        self.surface = None
        self.tray = None
        self.settings_window = None
        try:
            self.ui_locale = load_phrases().ui_locale
        except (OSError, ValueError):
            self.ui_locale = windows_locale()
        self.wave_level = 0.0
        self.wave_phase = 0.0
        self.wave_palette = WAVE_PALETTES["closed"]
        self.wave_opacity = IDLE_WAVE_OPACITY
        root.title(APP_NAME)
        root.configure(background=BACKGROUND)
        root.overrideredirect(True)
        root.columnconfigure(0, weight=1)
        tk.Canvas(root, width=1, height=WAVE_HEIGHT, bg=BACKGROUND,
                  borderwidth=0, highlightthickness=0).grid(row=0, column=0, sticky="ew")
        self.audio_meter = CodexAudioMeter()
        self.wave_frame_at = time.monotonic()
        self.draw_wave()
        root.protocol("WM_DELETE_WINDOW", self.close)
        if poll:
            self.refresh()

    def menu_entries(self):
        status = self.status
        ready = status is not None and self.pending_action is None
        labels = strings(self.ui_locale)
        entries = [
            (labels["pause" if status and status.listening else "resume"],
             self.toggle_listener if ready else None),
            (labels["hide" if self.bar.visible else "show"], self.toggle_animation),
            None,
            (labels["disable_auto" if status and status.autostart else "enable_auto"],
             (lambda: self.submit("autostart")) if ready else None),
            (labels["settings"], self.open_settings),
            (labels["log"], lambda: self.open_file(LOG)),
        ]
        if self.last_error:
            entries.extend((None, (self.last_error, None)))
        return [*entries, None, (labels["exit"], self.close)]

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_set()
            return
        self.settings_window = SettingsDialog(
            self.root, self.apply_locale, lambda: self.executor.submit(check_codex),
            lambda: (self.wave_level, self.wave_palette),
            submit_chats=lambda: self.executor.submit(list_chats),
        )

    def apply_locale(self, locale):
        self.ui_locale = locale

    def toggle_animation(self):
        if self.bar.visible:
            self.bar.hide()
        else:
            self.bar.show()

    def compose_frame(self):
        width = self.root.winfo_width()
        frame = bar_shadow(width).copy()
        frame.alpha_composite(wave_frame(self.wave_level, self.wave_phase, width, self.wave_palette,
                                         opacity=self.wave_opacity))
        return frame

    def draw_wave(self):
        now = time.monotonic()
        elapsed = min(now - self.wave_frame_at, 0.08)
        self.wave_frame_at = now
        peak = self.audio_meter.level
        target = min(1.0, max(0.0, peak - 0.008) ** 0.55 * 1.8)
        rate = 21 if target > self.wave_level else 8
        self.wave_level += (target - self.wave_level) * (1 - exp(-rate * elapsed))
        if target == 0 and self.wave_level < 0.012:
            self.wave_level = 0
        if target or self.wave_level > 0.06:
            state = "speaking"
        elif self.audio_meter.capturing and self.audio_meter.user_speaking:
            state = "listening"
        elif self.audio_meter.capturing or (self.status and self.status.connected):
            state = "ready"
        else:
            state = "closed"
        blend = 1 - exp(-elapsed * 14)
        opacity = 1.0 if state in ("speaking", "listening") else IDLE_WAVE_OPACITY
        self.wave_opacity += (opacity - self.wave_opacity) * blend
        self.wave_palette = tuple(
            tuple(current + (desired - current) * blend for current, desired in zip(source, dest))
            for source, dest in zip(self.wave_palette, WAVE_PALETTES[state])
        )
        self.wave_phase += elapsed * (1.0 + 4.0 * self.wave_level)
        visible = self.bar is not None and self.bar.visible
        if visible:
            self.surface.paint(self.compose_frame())
        self.wave_job = self.root.after(120 if not visible else 45 if self.wave_level == 0 else 25,
                                        self.draw_wave)

    def submit(self, action):
        if self.pending_action is not None:
            return
        self.last_error = ""
        self.pending_action = action
        self.pending = self.executor.submit(manage_listener, action)

    def refresh(self):
        if self.pending is not None and self.pending.done():
            try:
                self.status = self.pending.result()
            except Exception as exc:
                self.last_error = str(exc)
            self.pending = self.pending_action = None
        if self.pending is None:
            self.pending = self.executor.submit(manage_listener)
        self.root.after(650, self.refresh)

    def toggle_listener(self):
        if self.status:
            self.submit("stop" if self.status.listening else "start")

    def open_file(self, path):
        try:
            os.startfile(path)
        except OSError as exc:
            self.last_error = "Brak logu nasłuchu. Uruchom program, żeby powstał." if path == LOG else str(exc)

    def close(self):
        self.root.after_cancel(self.wave_job)
        self.audio_meter.close()
        if self.tray is not None:
            self.tray.close()
        if self.bar is not None:
            self.bar.hide()
        if self.surface is not None:
            self.surface.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    mutex = win32event.CreateMutex(None, False, r"Local\FridayVoicePanel")
    try:
        if win32event.WaitForSingleObject(mutex, 0) == win32event.WAIT_TIMEOUT:
            return
        try:
            app = tk.Tk()
            app.withdraw()
            panel = Panel(app)
            app.update_idletasks()
            panel.bar = OverlayWindow(app)
            panel.surface = LayeredSurface(panel.bar.hwnd)
            icon = ROOT / ".runtime" / "tray.ico"
            save_tray_icon(icon)
            app.iconbitmap(default=str(icon))
            panel.tray = Tray(app, icon, panel.menu_entries)
            panel.bar.show()
            app.mainloop()
        finally:
            win32event.ReleaseMutex(mutex)
    finally:
        mutex.Close()


if __name__ == "__main__":
    main()
