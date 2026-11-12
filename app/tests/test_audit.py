import ctypes
import asyncio
import io
import json
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
import wave
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import chimes
from codex_chats import chat_link, codex_cli
import desktop_tools
import friday
import voice_settings as settings
from bar_art import WAVE_HEIGHT, WAVE_PALETTES, wave_frame
from branding import APP_NAME
from codex_audio import ReplyPlayback
from localization import CATALOG, normalize_control_name, strings
from settings_art import BG, CARD, rounded_surface, style_settings
from settings_dialog import SettingsDialog
from setup_support import app_processes, LAUNCHER, WINDOWED
from voice_replay import AutomaticReplay, PendingAnswer, REPLAY_REQUESTS, completed_answer, is_replay_request


class PreferencesTests(unittest.TestCase):
    def test_legacy_to_new_name_and_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "old.json"
            current = root / "new.json"
            previous.write_text(json.dumps({
                "starts": ["Friday, słuchaj"], "stop": "bez odbioru",
                "sounds": {"ready": "system"},
            }), encoding="utf-8")
            with patch.multiple(settings, SETTINGS_PATH=current, LEGACY_SETTINGS_PATH=previous):
                old = settings.load_phrases()
                self.assertEqual(old.layout, "compact")
                self.assertEqual(old.stops, ("bez odbioru",))
                self.assertEqual(old.sounds["ready"], "system")
                self.assertEqual(settings.phrase_revision()[0], previous)
                for layout in settings.LAYOUTS:
                    saved = settings.save_phrases(old.starts, old.stops, old.ui_locale,
                                                  old.speech_language, old.sounds, layout)
                    self.assertEqual(settings.load_phrases(), saved)
                    self.assertEqual(settings.phrase_revision()[0], current)
                self.assertIn('"stop":', previous.read_text(encoding="utf-8"))

    def test_every_locale_has_distinct_options_and_valid_defaults(self):
        for code in CATALOG:
            with self.subTest(locale=code):
                labels = strings(code)
                self.assertEqual(labels.keys(), strings("pl-PL").keys())
                self.assertEqual(len({labels[f"style_{key}"] for key in settings.LAYOUTS}), 3)
                self.assertEqual(len({labels[f"tone_{tone}"] for tone in chimes.TONES}), len(chimes.TONES))
                value = settings.default_phrases(code)
                self.assertEqual(value, settings.validate_phrases(
                    value.starts, value.stops, code, value.speech_language, value.sounds, value.layout,
                ))

    def test_invalid_data_and_normalized_commands(self):
        for kwargs in ({"layout": "unknown"}, {"sounds": {"ready": []}}, {"ui_locale": []}):
            with self.assertRaises(ValueError):
                settings.validate_phrases(["start"], ["stop"], **kwargs)
        with self.assertRaises(ValueError):
            settings.validate_phrases(["Friday"], ["frajdej!"])
        self.assertEqual(friday.command_for("FAJNE?", ["fajne"], ["stop"]), "start")
        self.assertEqual(friday.command_for("結束 會話", ["開始會話"], ["结束会话"], "zh"), "stop")
        self.assertIsNone(friday.command_for("Proszę zakończ", ["start"], ["zakończ"]))
        self.assertEqual(normalize_control_name("  \u200eStart   voice chat "), "Start voice chat")


class SettingsWindowTests(unittest.TestCase):
    def test_hover_survives_native_active_state_reset(self):
        root = tk.Tk()
        root.withdraw()
        try:
            from settings_art import SettingsCombobox

            combo = SettingsCombobox(root)
            combo.event_generate("<Enter>")
            combo.state(["!active"])
            self.assertTrue(combo.instate(["alternate"]))
            combo.event_generate("<Leave>")
            self.assertFalse(combo.instate(["alternate"]))
        finally:
            root.destroy()

    def test_control_corners_keep_parent_color_in_interactive_states(self):
        root = tk.Tk()
        root.withdraw()
        try:
            style_settings(root)
            style = ttk.Style(root)
            for name, outer in (
                ("Fold.TButton", BG), ("Accent.TButton", BG), ("Settings.TButton", BG),
                ("Navigation.TButton", CARD), ("OpenSection.TButton", CARD), ("Preview.TButton", CARD),
                ("Settings.TCombobox", CARD), ("Chrome.Settings.TCombobox", BG),
            ):
                for states in ((), ("active",), ("pressed", "active"), ("focus", "active"),
                               ("selected",), ("disabled",)):
                    with self.subTest(style=name, states=states):
                        self.assertEqual(style.lookup(name, "background", states), outer)
        finally:
            root.destroy()

    def test_rounded_plate_has_transparent_corners(self):
        image = rounded_surface(128, 36, 9, "#141d32", "#344461")
        self.assertLess(image.getpixel((0, 0))[3], 15)
        self.assertEqual(image.getpixel((64, 18)), (20, 29, 50, 255))

    def test_window_fits_content_and_caps_size_to_monitor(self):
        heights = {"chrome": 110, "content": 280, "bottom": 56}
        size = []

        def widget(key):
            return SimpleNamespace(winfo_reqheight=lambda: heights[key], winfo_reqwidth=lambda: 280)

        dialog = SimpleNamespace(
            size_job="pending", requested_width=600, work_area_size=lambda: (530, 470),
            chrome=widget("chrome"), content=widget("content"), bottom=widget("bottom"),
            winfo_width=lambda: 498, winfo_height=lambda: 200,
            minsize=lambda *_: None, geometry=size.append,
        )
        SettingsDialog.fit_window(dialog)
        self.assertEqual(size[-1], "498x406")
        heights["content"] = 88
        SettingsDialog.fit_window(dialog)
        self.assertEqual(size[-1], "498x254")

    def test_hidden_window_layouts_preserve_unsaved_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            config = root_path / "settings.json"
            with (
                patch.multiple(settings, SETTINGS_PATH=config, LEGACY_SETTINGS_PATH=root_path / "old.json",
                               LEGACY_PHRASES=root_path / "phrases.txt"),
                patch.object(SettingsDialog, "deiconify"),
                patch.object(SettingsDialog, "set_dark_titlebar"),
                patch("settings_dialog.play_chime") as play,
            ):
                settings.save_phrases(["start"], ["stop"], "pl-PL", "pl")
                root = tk.Tk()
                root.withdraw()
                future = Future()
                future.set_result("voice_ready")
                chat_id = "019a0000-0000-7000-8000-000000000001"
                chats = Future()
                submit_chats = Mock(return_value=chats)
                applied = []
                try:
                    dialog = SettingsDialog(root, applied.append, lambda: future,
                                            lambda: (0, WAVE_PALETTES["ready"]), submit_chats)
                    self.assertEqual(dialog.layout, "compact")
                    self.assertEqual(dialog.title(), f"{APP_NAME} · Ustawienia")
                    self.assertEqual(dialog.groups["sounds"].winfo_manager(), "grid")
                    self.assertFalse(dialog.groups["phrases"].winfo_manager())
                    dialog.fold_buttons["phrases"].invoke()
                    dialog.editors["stop"].insert("end", "\nfinish")
                    dialog.fold_buttons["chat"].invoke()
                    self.assertTrue(dialog.auto_replay.get())
                    dialog.replay_check.invoke()
                    self.assertFalse(dialog.auto_replay.get())
                    dialog.chat_mode.current(1)
                    dialog.update_chat_controls()
                    submit_chats.assert_called_once()
                    chats.set_result([(chat_id, "Mój czat")])
                    limit = time.monotonic() + 2
                    while dialog.chat_job is not None and time.monotonic() < limit:
                        root.update()
                        time.sleep(.02)
                    self.assertEqual(dialog.chat_choice.cget("values"), ("Mój czat",))
                    dialog.chat_choice.current(0)
                    dialog.select_chat()
                    choice, preview = dialog.choices["ready"]
                    choice.current(chimes.TONES.index("drop"))
                    for index, layout in enumerate(settings.LAYOUTS):
                        dialog.layout_choice.current(index)
                        dialog.change_layout()
                        dialog.update_idletasks()
                        self.assertEqual(dialog.layout, layout)
                        self.assertEqual(choice.current(), chimes.TONES.index("drop"))
                        self.assertEqual(dialog.editors["stop"].get("1.0", "end-1c"), "stop\nfinish")
                        self.assertEqual(dialog.groups["sounds"].winfo_manager(), "grid")
                    dialog.layout_choice.current(1)
                    dialog.change_layout()
                    dialog.resize_content(SimpleNamespace(width=440))
                    self.assertEqual(int(dialog.navigation.grid_info()["row"]), 0)
                    self.assertEqual(int(dialog.groups["sounds"].grid_info()["row"]), 1)
                    dialog.nav_buttons["languages"].invoke()
                    self.assertEqual(dialog.groups["languages"].winfo_manager(), "grid")
                    dialog.interface.current(dialog.locales.index("ar"))
                    dialog.translate(dialog.speech.current())
                    self.assertEqual(dialog.layout_choice.current(), 1)
                    self.assertEqual(dialog.captions["starts"]["justify"], "right")
                    preview.invoke()
                    play.assert_called_once_with("drop", preview=True)
                    dialog.save()
                    saved = settings.load_phrases()
                    self.assertEqual((saved.layout, saved.stops, saved.ui_locale), ("sidebar", ("stop", "finish"), "ar"))
                    self.assertEqual(saved.sounds["ready"], "drop")
                    self.assertEqual(saved.chat_id, chat_id)
                    self.assertFalse(saved.auto_replay)
                    self.assertEqual(applied, ["ar"])
                    dialog.chat_mode.current(0)
                    dialog.update_chat_controls()
                    dialog.save()
                    self.assertIsNone(settings.load_phrases().chat_id)
                    dialog.check()
                    limit = time.monotonic() + 2
                    while dialog.check_button.instate(["disabled"]) and time.monotonic() < limit:
                        root.update()
                        time.sleep(.02)
                    self.assertEqual(dialog.feedback.get(), strings("ar")["voice_ready"])
                    dialog.destroy()
                    root.update()
                finally:
                    root.destroy()


class AudioTests(unittest.TestCase):
    def test_chime_samples_and_wave_strokes(self):
        sounds = [chimes.chime_wave(tone) for tone in chimes.NOTES]
        self.assertEqual(len(set(sounds)), 11)
        for content in sounds:
            with wave.open(io.BytesIO(content)) as stream:
                samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
                self.assertLessEqual(len(samples) / stream.getframerate(), 0.40)
                self.assertLess(np.abs(samples).max(), 4500)
                self.assertEqual(samples[0], 0)
                self.assertEqual(samples[-1], 0)
        for width in (96, 400, 1920, 3840):
            for state, palette in WAVE_PALETTES.items():
                with self.subTest(width=width, state=state):
                    result = wave_frame(.5, .75, width, palette, .8)
                    self.assertEqual(result.size, (width, WAVE_HEIGHT))
                    self.assertEqual(result.mode, "RGBA")
                    self.assertGreater(result.getchannel("A").getextrema()[1], 0)

    def test_preview_coalesces_without_losing_notification(self):
        playing, release = threading.Event(), threading.Event()
        played = []

        def sound(data, _flags):
            played.append(data)
            playing.set()
            release.wait(2)

        with patch.object(chimes.winsound, "PlaySound", side_effect=sound):
            try:
                chimes.play_chime("tap", preview=True)
                self.assertTrue(playing.wait(2))
                for _ in range(80):
                    chimes.play_chime("echo", preview=True)
                chimes.play_chime("chord")
                chimes.play_chime("mute")
                self.assertEqual(chimes.playback_queue.qsize(), 1)
            finally:
                release.set()
                chimes.playback_queue.join()
        self.assertEqual(played, [chimes.chime_wave("tap"), chimes.chime_wave("chord")])

    def test_one_signal_per_spoken_reply(self):
        tracker = ReplyPlayback()
        events = []
        for step in range(600):
            now = step / 50
            user = .3 <= now < 1.3 or 6.3 <= now < 7.1
            output = .1 if 2 <= now < 3 or 7.5 <= now < 8.5 else 0
            if tracker.update(output, now, True, user):
                events.append(now)
        self.assertEqual(events, [5.48, 10.98])
        self.assertFalse(tracker.update(.5, 14, True, False))
        self.assertFalse(tracker.update(0, 17, True, False))


class WindowsIntegrationTests(unittest.TestCase):
    def test_replay_resumes_and_requests_the_answer_in_the_same_chat(self):
        chat = "019a0000-0000-7000-8000-000000000001"
        turn = {"id": "new", "status": "completed", "items": [
            {"type": "agentMessage", "phase": "commentary", "text": "Progress"},
            {"type": "agentMessage", "phase": "final_answer", "text": "The answer."},
        ]}
        self.assertIsNone(completed_answer(turn, "old"))
        self.assertIsNone(completed_answer(dict(turn, status="interrupted"), "new"))
        self.assertEqual(completed_answer(turn, "new"), "The answer.")
        self.assertTrue(is_replay_request({"items": [{"type": "userMessage", "content": [
            {"type": "text", "text": REPLAY_REQUESTS["pl"]},
        ]}]}))
        controller = AutomaticReplay()
        try:
            desktop = Mock()
            desktop.find_active_call.return_value = False
            controller.ticket = PendingAnswer(chat, "Test", "new")
            controller.phase = "wait"
            controller.future = Future()
            controller.future.set_result(True)
            self.assertEqual(controller.check(desktop, False, 0), "resumed")
            desktop.open_call.assert_called_once_with(chat)
            desktop.request_replay.assert_called_once_with("Test")
        finally:
            controller.close()

    def test_manual_stop_cancels_pending_voice_replay(self):
        controller = AutomaticReplay()
        try:
            desktop = Mock()
            desktop.voice_chat_title.return_value = "Selected"
            desktop.suspend_for_replay.return_value = True
            candidate, waiting = Future(), Future()
            with patch.object(controller.executor, "submit", side_effect=[candidate, waiting]):
                controller.check(desktop, True, 0)
                candidate.set_result(PendingAnswer("chat", "Selected", "turn"))
                self.assertEqual(controller.check(desktop, True, 0), "suspended")
                cancelled = controller.cancelled
                controller.cancel()
                self.assertTrue(cancelled.is_set())
                self.assertTrue(waiting.cancelled())
                controller.check(desktop, False, 0)
            desktop.open_fixed_chat.assert_not_called()
        finally:
            controller.close()

    def test_codex_cli_finds_running_store_install_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "OpenAI.Codex_test" / "app"
            cli = app / "resources" / "codex.exe"
            cli.parent.mkdir(parents=True)
            cli.touch()
            desktop = SimpleNamespace(info={"name": "ChatGPT.exe", "exe": str(app / "ChatGPT.exe")})
            with patch("codex_chats.psutil.process_iter", return_value=[desktop]), \
                    patch("codex_chats.shutil.which", return_value=None) as search_path:
                self.assertEqual(codex_cli(), str(cli))
                search_path.assert_not_called()

    def test_fixed_chat_opens_by_id_and_checks_current_title(self):
        chat_id = "019a0000-0000-7000-8000-000000000001"
        desktop = friday.Desktop.__new__(friday.Desktop)
        desktop.select_call_window = Mock(return_value=True)
        desktop.bind_chat_document = Mock(return_value=True)
        with patch("friday.list_chats", return_value=[(chat_id, "Nowa nazwa")]), \
                patch("friday.os.startfile") as open_url:
            self.assertEqual(desktop.open_fixed_chat(chat_id), "Nowa nazwa")
            open_url.assert_called_once_with(f"codex://threads/{chat_id}")
            desktop.bind_chat_document.assert_called_once_with("Nowa nazwa")
        with self.assertRaises(ValueError):
            chat_link(f"{chat_id}/other")

    def test_fixed_chat_requires_current_document_before_starting_voice(self):
        desktop = friday.Desktop.__new__(friday.Desktop)
        desktop.open_fixed_chat = Mock(side_effect=[None, "Mój czat", "Mój czat"])
        desktop.select_call_window = Mock()
        button = Mock()
        desktop.wait_for = Mock(return_value=button)
        desktop.controls = Mock(side_effect=lambda names: [button] if names == friday.START_BUTTONS else [])
        desktop.refresh_window = Mock(return_value=True)
        desktop.bind_chat_document = Mock(side_effect=[False, True])
        with patch("builtins.print"):
            self.assertFalse(desktop.open_call("missing"))
            self.assertFalse(desktop.open_call("different"))
            button.GetInvokePattern.assert_not_called()
            self.assertTrue(desktop.open_call("target"))
        button.GetInvokePattern.return_value.Invoke.assert_called_once()
        desktop.select_call_window.assert_not_called()

    def test_window_state_needs_enabled_start_button(self):
        desktop = friday.Desktop.__new__(friday.Desktop)
        label = next(iter(friday.START_BUTTONS))
        desktop.controls = lambda *args, **kwargs: [label] if kwargs.get("names_only") else []
        self.assertEqual(desktop.call_state(), "unavailable")
        desktop.controls = lambda *_args, **_kwargs: [label]
        self.assertEqual(desktop.call_state(), "closed")

    def test_process_matching_uses_resolved_executable_and_owned_launcher(self):
        owned = SimpleNamespace(info={"exe": str(WINDOWED.resolve()),
                                     "cmdline": [str(WINDOWED), "-B", str(LAUNCHER), "panel"]})
        other = SimpleNamespace(info={"exe": str(WINDOWED),
                                     "cmdline": [str(WINDOWED), "-B", "C:/other/windowed.pyw", "panel"]})
        with patch("setup_support.psutil.process_iter", return_value=[owned, other]):
            self.assertEqual(list(app_processes()), [(owned, "panel")])

    def test_queue_handles_expired_corrupt_and_valid_records(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory)
            (inbox / "damaged.json").write_bytes(b"\xff\x00broken")
            (inbox / "stale.json").write_text(
                json.dumps({"time": time.time() - 610, "summary": "stale"}), encoding="utf-8")
            (inbox / "bad-type.json").write_text(
                json.dumps({"time": time.time(), "summary": []}), encoding="utf-8")
            with patch.object(friday, "INBOX", inbox):
                friday.notify_ready("  gotowy   wynik ")
                self.assertEqual(friday.take_notification(), "gotowy wynik")
                self.assertIsNone(friday.take_notification())
                self.assertFalse(list(inbox.glob("*.json")))

    def test_reacquiring_same_call_does_not_repeat_connected_chime(self):
        steps = iter(range(1, 12))
        clock = SimpleNamespace(now=0)

        class Blocks:
            def get(self, timeout):
                clock.now = next(steps)
                return 0, b""

            def get_nowait(self):
                raise queue.Empty

        meter = SimpleNamespace(level=0, user_speaking=False, close=lambda: None)
        mic = SimpleNamespace(name="synthetic", add=lambda _: (), reset=lambda: None)
        desktop = SimpleNamespace(
            window_handle=42, remember_window=lambda: None, find_active_call=lambda: clock.now < 10,
            call_window_disappeared=lambda: False,
            call_state=lambda: ("unavailable" if 2 <= clock.now <= 5 else
                                "closed" if clock.now >= 10 else "open"),
        )
        initial = replace(settings.default_phrases("pl-PL"), auto_replay=False)
        with patch.multiple(
            friday, queue=SimpleNamespace(Queue=lambda **_: Blocks(), Empty=queue.Empty),
            time=SimpleNamespace(monotonic=lambda: clock.now, time=lambda: clock.now), Desktop=lambda: desktop,
            open_microphones=lambda *args: {0: mic}, CodexAudioMeter=lambda: meter,
            phrase_revision=lambda: None, load_phrases=lambda: initial, take_notification=lambda: None,
        ), patch.object(friday, "play_chime") as play:
            friday.listen(None, initial, False, None, lambda: clock.now >= 11)
        self.assertEqual([call.args[0] for call in play.call_args_list], ["rise", "fall"])

    def test_browser_address_validation_without_opening_a_window(self):
        with patch.object(desktop_tools.os, "startfile") as open_url:
            for invalid in ("file:///C:/file", "https://name:secret@example.com", "https://a b",
                            "https://example.com\\other", "javascript:alert(1)"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    desktop_tools.browser_open(invalid)
            open_url.assert_not_called()
            desktop_tools.browser_search("polskie frazy")
            self.assertTrue(open_url.call_args.args[0].endswith("q=polskie+frazy"))

    def test_overlay_releases_bitmap_if_select_fails(self):
        from PIL import Image
        from layered_surface import BitmapHeader, LayeredSurface

        self.assertEqual(ctypes.sizeof(BitmapHeader), 40)
        with patch("layered_surface.win32gui") as gui, patch("layered_surface.create_dib", return_value=57):
            gui.CreateCompatibleDC.return_value = 11
            gui.GetWindowLong.return_value = 0
            gui.SelectObject.side_effect = OSError("test SelectObject")
            surface = LayeredSurface(42)
            with self.assertRaises(OSError):
                surface.paint(Image.new("RGBA", (16, 4)))
            gui.DeleteObject.assert_called_once_with(57)
            surface.close()
            gui.DeleteDC.assert_called_once_with(11)

    def test_mcp_stdio_with_temporary_notification_queue(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                inbox = Path(directory)
                command = (
                    "import friday; from pathlib import Path; "
                    f"friday.INBOX=Path({str(inbox)!r}); friday.run_mcp()"
                )
                parameters = StdioServerParameters(
                    command=sys.executable, args=["-B", "-c", command],
                    cwd=str(Path(friday.__file__).resolve().parent),
                )
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as session:
                        hello = await session.initialize()
                        self.assertEqual(hello.serverInfo.name, APP_NAME)
                        names = {tool.name for tool in (await session.list_tools()).tools}
                        self.assertEqual(names, {
                            "notify_answer_ready", "browser_open", "browser_focus", "browser_new_tab",
                            "browser_search", "browser_type", "browser_click", "browser_youtube",
                            "capture_screen",
                        })
                        result = await session.call_tool("notify_answer_ready", {"summary": "test result"})
                        self.assertFalse(result.isError)
                        message = json.loads(next(inbox.glob("*.json")).read_text(encoding="utf-8"))
                        self.assertEqual(message["summary"], "test result")
                        invalid = await session.call_tool("browser_open", {"url": "file:///C:/test.txt"})
                        self.assertTrue(invalid.isError)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
