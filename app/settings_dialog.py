import ctypes
import time
import tkinter as tk
from tkinter import ttk

import pywintypes
from PIL import ImageTk

from bar_art import WAVE_HEIGHT, WAVE_PALETTES, wave_frame
from branding import APP_NAME
from chimes import DEFAULT_SOUNDS, TONES, play_chime
from localization import AUTO, CATALOG, RTL_LANGUAGES, SPEECH_LOCALES, strings
from settings_art import (
    ACCENT, BG, CARD, CYAN, FONT, INK, INPUT, MUTED, RoundedFrame, SettingsCombobox, style_settings,
)
from voice_settings import LAYOUTS, default_phrases, load_phrases, save_phrases


WIDTHS = {"split": 910, "sidebar": 840, "compact": 600}
SECTIONS = ("sounds", "phrases", "chat", "languages")


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_save, submit_check, wave_state, submit_chats=None):
        super().__init__(parent)
        self.check_job = self.chat_job = self.wave_job = self.size_job = None
        self.requested_width = None
        self.scroll_bounds = None
        self.canvas_width = None
        self.placements = {}
        self.grid_columns = None
        self.nav_narrow = None
        self.withdraw()
        self.configure(bg=BG)
        style_settings(self)
        try:
            self.current = load_phrases()
            self.notice = None
        except (OSError, ValueError):
            self.current = default_phrases()
            self.notice = "invalid"
        self.on_save = on_save
        self.submit_check = submit_check
        self.submit_chats = submit_chats
        self.wave_state = wave_state
        self.layout = self.current.layout
        self.section = "sounds"
        self.chat_id = self.current.chat_id
        self.chats = []
        self.chat_notice = None
        self.chat_controls_visible = False
        self.wave_photo = None
        self.locales = sorted(CATALOG, key=lambda code: CATALOG[code]["name"].casefold())
        self.languages = [AUTO, *sorted(SPEECH_LOCALES, key=lambda code:
                                        CATALOG[SPEECH_LOCALES[code]]["name"].casefold())]
        self.captions = {}
        self.groups = {}
        self.headings = {}
        self.editors = {}
        self.choices = {}

        self.chrome = tk.Frame(self, bg=BG, padx=20, pady=12)
        self.chrome.pack(fill="x")
        hero = tk.Frame(self.chrome, bg=BG)
        hero.pack(fill="x")
        title = tk.Frame(hero, bg=BG)
        title.pack(side="left")
        self.label(title, APP_NAME, bg=BG, color=ACCENT, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.title_label = self.label(title, bg=BG, color=INK, font=("Segoe UI Semibold", 22))
        self.title_label.pack(anchor="w")
        self.wave = tk.Canvas(hero, bg=BG, width=140, height=WAVE_HEIGHT, highlightthickness=0)
        self.wave.pack(side="right", fill="x", expand=True, padx=(14, 0))
        self.wave_item = self.wave.create_image(0, 0, anchor="nw")
        appearance = tk.Frame(self.chrome, bg=BG)
        appearance.pack(fill="x", pady=(9, 0))
        self.captions["appearance"] = self.label(appearance, bg=BG)
        self.captions["appearance"].pack(side="left", padx=(0, 10))
        self.layout_choice = self.combo(appearance, width=18, style="Chrome.Settings.TCombobox")
        self.layout_choice.pack(side="left", fill="x")
        self.layout_choice.bind("<<ComboboxSelected>>", self.change_layout)

        area = tk.Frame(self, bg=BG)
        area.pack(fill="both", expand=True, padx=(20, 13))
        self.canvas = tk.Canvas(area, bg=BG, highlightthickness=0, width=1, height=1)
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview,
                                  style="Settings.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.canvas.configure(yscrollcommand=lambda first, last: self.scroll_indicator(scrollbar, first, last))
        self.content = tk.Frame(self.canvas, bg=BG)
        self.content_id = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", self.update_scroll)
        self.canvas.bind("<Configure>", self.resize_content)

        self.navigation = RoundedFrame(self.content, outer=BG)
        self.navigation.configure(padx=8, pady=8)
        self.nav_buttons = {}
        self.fold_buttons = {}
        self.open_sections = {}
        for key in SECTIONS:
            self.groups[key] = RoundedFrame(self.content, outer=BG)
            self.groups[key].configure(padx=14, pady=11)
            self.headings[key] = self.label(self.groups[key], color=INK, font=("Segoe UI Semibold", 13))
            self.nav_buttons[key] = self.button(self.navigation, lambda item=key: self.show_section(item),
                                                style="Navigation")
            self.fold_buttons[key] = self.button(self.content, lambda item=key: self.toggle_section(item),
                                                 style="Fold")
            self.open_sections[key] = self.button(self.groups[key], lambda item=key: self.toggle_section(item),
                                                  style="OpenSection")
        self.build_languages()
        self.build_phrases()
        self.build_sounds()
        self.build_chat()

        self.bottom = tk.Frame(self, bg=BG, padx=20, pady=12)
        self.bottom.pack(fill="x")
        self.bottom.columnconfigure(1, weight=1)
        self.feedback = tk.StringVar(self)
        self.message = self.label(self.bottom, bg=BG, color=CYAN, textvariable=self.feedback, wraplength=510)
        self.message.grid(row=0, column=1, sticky="ew", padx=10)
        self.check_button = self.button(self.bottom, self.check)
        self.check_button.grid(row=0, column=0, sticky="w")
        self.save_button = self.button(self.bottom, self.save, style="Accent")
        self.save_button.grid(row=0, column=2, sticky="e")
        self.translate(self.languages.index(self.current.speech_language))
        self.interface.bind("<<ComboboxSelected>>", lambda _: self.translate(self.speech.current()))
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Control-s>", lambda _: self.save())
        self.bind("<MouseWheel>", self.scroll)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.resize_window()
        self.arrange()
        self.update_idletasks()
        self.set_dark_titlebar()
        self.deiconify()
        self.draw_wave()

    @staticmethod
    def label(parent, text="", *, bg=CARD, color=MUTED, font=FONT, **options):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=font, anchor="w", **options)

    @staticmethod
    def combo(parent, style="Settings.TCombobox", **options):
        return SettingsCombobox(parent, state="readonly", style=style, font=FONT, **options)

    @staticmethod
    def button(parent, command, style="Settings"):
        return ttk.Button(parent, command=command, style=f"{style}.TButton")

    def build_languages(self):
        group = self.groups["languages"]
        for column, key in enumerate(("interface", "speech")):
            group.columnconfigure(column, weight=1, uniform="language")
            caption = self.captions[key] = self.label(group, wraplength=205)
            caption.grid(row=1, column=column, sticky="ew", padx=(0, 9 * (column == 0)))
        self.interface = self.combo(group, width=15, values=[CATALOG[code]["name"] for code in self.locales])
        self.interface.grid(row=2, column=0, sticky="ew", padx=(0, 9))
        self.interface.current(self.locales.index(self.current.ui_locale))
        self.speech = self.combo(group, width=15)
        self.speech.grid(row=2, column=1, sticky="ew")

    def build_phrases(self):
        group = self.groups["phrases"]
        group.columnconfigure(0, weight=1)
        for index, (key, lines) in enumerate((("starts", self.current.starts), ("stop", self.current.stops))):
            row = 1 + index * 2
            caption = self.captions[key] = self.label(group, wraplength=250)
            caption.grid(row=row, columnspan=2, sticky="ew", pady=(8 * index, 4))
            well = RoundedFrame(group, outer=CARD, fill=INPUT, radius=9)
            well.grid(row=row + 1, columnspan=2, sticky="ew")
            well.columnconfigure(0, weight=1)
            editor = tk.Text(well, width=20, height=4 if index == 0 else 2, font=FONT, wrap="word",
                             bg=INPUT, fg=INK, insertbackground=CYAN, selectbackground="#3e4b81",
                             relief="flat", borderwidth=0, highlightthickness=0, padx=3, pady=3)
            editor.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=6)
            editor.bind("<FocusIn>", lambda _, frame=well: frame.focus_edge(True))
            editor.bind("<FocusOut>", lambda _, frame=well: frame.focus_edge(False))
            scroll = ttk.Scrollbar(well, orient="vertical", command=editor.yview,
                                   style="Text.Settings.Vertical.TScrollbar")
            scroll.grid(row=0, column=1, sticky="ns", padx=(2, 5), pady=7)
            editor.configure(yscrollcommand=lambda first, last, bar=scroll: self.text_scroll(bar, first, last))
            editor.insert("1.0", "\n".join(lines))
            self.editors[key] = editor

    def build_sounds(self):
        group = self.groups["sounds"]
        group.columnconfigure(0, weight=1)
        for index, event in enumerate(DEFAULT_SOUNDS):
            row = 1 + index * 2
            caption = self.captions[f"sound_{event}"] = self.label(group, wraplength=250)
            caption.grid(row=row, columnspan=2, sticky="ew", pady=(4 * (index > 0), 3))
            choice = self.combo(group, height=len(TONES), width=14)
            choice.grid(row=row + 1, column=0, sticky="ew", pady=(0, 5))
            preview = self.button(group, lambda box=choice: play_chime(TONES[box.current()], preview=True),
                                  style="Preview")
            preview.grid(row=row + 1, column=1, padx=(8, 0), pady=(0, 5))
            self.choices[event] = choice, preview

    def build_chat(self):
        group = self.groups["chat"]
        group.columnconfigure(0, weight=1)
        self.captions["chat_mode"] = self.label(group, wraplength=250)
        self.captions["chat_mode"].grid(row=1, columnspan=2, sticky="ew", pady=(0, 4))
        self.chat_mode = self.combo(group, width=16)
        self.chat_mode.grid(row=2, columnspan=2, sticky="ew")
        self.chat_mode.bind("<<ComboboxSelected>>", lambda _: self.update_chat_controls())
        self.chat_choice = self.combo(group, width=16)
        self.chat_choice.bind("<<ComboboxSelected>>", self.select_chat)
        self.chat_refresh = self.button(group, self.refresh_chats, style="Preview")
        self.chat_note = self.label(group, wraplength=320, color=CYAN)
        self.auto_replay = tk.BooleanVar(self, value=self.current.auto_replay)
        self.replay_check = tk.Checkbutton(
            group, variable=self.auto_replay, bg=CARD, fg=INK, selectcolor=BG,
            activebackground=CARD, activeforeground=INK, highlightthickness=0,
            anchor="w", justify="left", wraplength=270, font=FONT,
        )
        self.replay_check.grid(row=5, columnspan=2, sticky="ew", pady=(9, 0))

    @property
    def locale(self):
        return self.locales[self.interface.current()]

    def translate(self, language_index):
        labels = strings(self.locale)
        self.title(f'{APP_NAME} · {labels["settings"]}')
        self.title_label.configure(text=labels["settings"])
        rtl = CATALOG[self.locale]["speech"] in RTL_LANGUAGES
        for key, caption in self.captions.items():
            caption.configure(text=labels[key], anchor="e" if rtl else "w",
                              justify="right" if rtl else "left")
        self.message.configure(anchor="e" if rtl else "w", justify="right" if rtl else "left")
        self.speech.configure(values=[labels["auto"], *(
            CATALOG[SPEECH_LOCALES[language]]["name"] for language in self.languages[1:]
        )])
        self.speech.current(language_index)
        self.layout_choice.configure(values=[labels[f"style_{layout}"] for layout in LAYOUTS])
        self.layout_choice.current(LAYOUTS.index(self.layout))
        for event, (choice, preview) in self.choices.items():
            index = choice.current()
            choice.configure(values=[labels[f"tone_{tone}"] for tone in TONES])
            choice.current(TONES.index(self.current.sounds[event]) if index < 0 else index)
            preview.configure(text=labels["preview"])
        self.check_button.configure(text=labels["check"])
        self.save_button.configure(text=labels["save"])
        mode = self.chat_mode.current()
        self.chat_mode.configure(values=(labels["chat_last"], labels["chat_fixed"]))
        self.chat_mode.current(int(self.current.chat_id is not None) if mode < 0 else mode)
        self.chat_refresh.configure(text=labels["chat_refresh"])
        self.replay_check.configure(text=(
            "Rozłącz podczas pracy i odczytaj gotową odpowiedź"
            if self.locale == "pl-PL" else "Pause voice during work and replay the answer"
        ))
        self.update_chat_controls()
        self.report(self.notice)
        self.label_sections()

    def label_sections(self):
        labels = strings(self.locale)
        for key in SECTIONS:
            self.headings[key].configure(text=labels[key])
            self.nav_buttons[key].configure(text=labels[key])
            self.fold_buttons[key].configure(text=f"▸  {labels[key]}")
            self.open_sections[key].configure(text=f"▾  {labels[key]}")

    def update_chat_controls(self):
        fixed = self.chat_mode.current() == 1
        if fixed != self.chat_controls_visible:
            if fixed:
                self.chat_choice.grid(row=3, column=0, sticky="ew", pady=(8, 0))
                self.chat_refresh.grid(row=3, column=1, padx=(8, 0), pady=(8, 0))
                self.chat_note.grid(row=4, columnspan=2, sticky="ew", pady=(7, 0))
            else:
                for widget in (self.chat_choice, self.chat_refresh, self.chat_note):
                    widget.grid_remove()
            self.chat_controls_visible = fixed
        if not fixed:
            return
        notice = strings(self.locale)[self.chat_notice] if self.chat_notice else ""
        if notice != self.chat_note.cget("text"):
            self.chat_note.configure(text=notice)
        if self.chat_notice is None and not self.chats and self.groups["chat"] in self.placements:
            self.refresh_chats()

    def select_chat(self, _event=None):
        index = self.chat_choice.current()
        if index >= 0:
            self.chat_id = self.chats[index][0]
            self.chat_notice = None
            self.update_chat_controls()

    def refresh_chats(self):
        if self.submit_chats is None or self.chat_job is not None:
            return
        self.chat_notice = "chat_loading"
        self.update_chat_controls()
        self.chat_refresh.state(["disabled"])
        pending = self.submit_chats()

        def receive():
            if not pending.done():
                self.chat_job = self.after(80, receive)
                return
            self.chat_job = None
            self.chat_refresh.state(["!disabled"])
            try:
                self.chats = pending.result()
            except Exception:
                self.chat_notice = "chat_error"
            else:
                self.chat_choice.configure(values=[title for _, title in self.chats])
                index = next((i for i, (key, _) in enumerate(self.chats) if key == self.chat_id), None)
                if index is not None:
                    self.chat_choice.current(index)
                    self.chat_notice = None
                else:
                    self.chat_choice.set("")
                    self.chat_notice = ("chat_missing" if self.chat_id else
                                        "chat_choose" if self.chats else "chat_empty")
            self.update_chat_controls()

        self.chat_job = self.after(80, receive)

    def resize_window(self):
        self.requested_width = WIDTHS[self.layout]
        self.queue_fit()

    def queue_fit(self):
        if self.size_job is None:
            self.size_job = self.after_idle(self.fit_window)

    def fit_window(self):
        self.size_job = None
        available_width, available_height = self.work_area_size()
        width_limit, height_limit = max(1, available_width - 32), max(1, available_height - 64)
        preferred = self.requested_width or self.winfo_width()
        self.requested_width = None
        preferred = max(preferred, self.chrome.winfo_reqwidth())
        width = min(width_limit, max(390, preferred))
        content_height = self.chrome.winfo_reqheight() + self.content.winfo_reqheight() + self.bottom.winfo_reqheight()
        height = min(height_limit, content_height)
        minimum = (min(390, width), 1)
        if self.minsize() != minimum:
            self.minsize(*minimum)
        if (width, height) != (self.winfo_width(), self.winfo_height()):
            self.geometry(f"{width}x{height}")

    def work_area_size(self):
        try:
            import win32api
            import win32con

            monitor = win32api.MonitorFromWindow(self.winfo_id(), win32con.MONITOR_DEFAULTTONEAREST)
            left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
            return right - left, bottom - top
        except (OSError, pywintypes.error, tk.TclError):
            return self.winfo_screenwidth(), self.winfo_screenheight()

    def resize_content(self, event):
        if event.width == self.canvas_width:
            return
        self.canvas_width = event.width
        self.canvas.itemconfigure(self.content_id, width=event.width)
        self.message.configure(wraplength=max(110, event.width - 280))
        narrow = event.width < 640
        if narrow != getattr(self, "narrow", None):
            self.narrow = narrow
            self.arrange()

    def update_scroll(self, _event=None):
        bounds = self.canvas.bbox("all")
        if bounds and bounds != self.scroll_bounds:
            self.scroll_bounds = bounds
            self.canvas.configure(scrollregion=bounds)
            self.queue_fit()

    def scroll(self, event):
        if not isinstance(event.widget, (tk.Text, ttk.Combobox)):
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    @staticmethod
    def scroll_indicator(scrollbar, first, last):
        scrollbar.set(first, last)
        style = "Quiet.Vertical.TScrollbar" if float(first) == 0 and float(last) == 1 else "Settings.Vertical.TScrollbar"
        if scrollbar.cget("style") != style:
            scrollbar.configure(style=style)

    @staticmethod
    def text_scroll(scrollbar, first, last):
        scrollbar.set(first, last)
        if float(first) == 0 and float(last) == 1:
            scrollbar.grid_remove()
        elif not scrollbar.winfo_manager():
            scrollbar.grid()

    def change_layout(self, _event=None):
        self.layout = LAYOUTS[self.layout_choice.current()]
        self.section = "sounds"
        self.resize_window()
        self.arrange()
        self.canvas.yview_moveto(0)

    def show_section(self, section):
        self.section = section
        self.arrange()
        self.canvas.yview_moveto(0)

    def toggle_section(self, section):
        focused = self.focus_get()
        previous = self.open_sections[section] if section == self.section else self.fold_buttons[section]
        replacement = self.fold_buttons[section] if section == self.section else self.open_sections[section]
        self.show_section(None if section == self.section else section)
        if focused == previous:
            replacement.focus_set()

    def arrange(self):
        placements = {}
        columns = ((1, 0, ""), (0, 0, ""))
        narrow = getattr(self, "narrow", False)

        def place(widget, row, column=0, span=1, sticky="ew", padx=0, pady=0):
            placements[widget] = dict(row=row, column=column, columnspan=span,
                                      sticky=sticky, padx=padx, pady=pady)

        if self.layout == "split":
            for key in ("phrases", "sounds", "chat"):
                place(self.headings[key], 0, span=2, pady=(0, 8))
            place(self.groups["languages"], 0, span=2, pady=(0, 9))
            if narrow:
                place(self.groups["sounds"], 1, span=2, pady=(0, 9))
                place(self.groups["phrases"], 2, span=2, pady=(0, 9))
                place(self.groups["chat"], 3, span=2)
            else:
                columns = ((1, 0, "section"), (1, 0, "section"))
                place(self.groups["phrases"], 1, sticky="nsew", padx=(0, 6))
                place(self.groups["sounds"], 1, 1, sticky="nsew", padx=(6, 0))
                place(self.groups["chat"], 2, span=2, pady=(9, 0))
        elif self.layout == "sidebar":
            if narrow:
                place(self.navigation, 0, pady=(0, 8))
                row, column = 1, 0
            else:
                columns = ((0, 132, ""), (1, 0, ""))
                place(self.navigation, 0, sticky="nsw", padx=(0, 10))
                row, column = 0, 1
            if self.nav_narrow != narrow:
                self.navigation.columnconfigure(0, weight=1, uniform="nav" if narrow else "")
                self.navigation.columnconfigure(1, weight=int(narrow), uniform="nav" if narrow else "")
                for index, button in enumerate(self.nav_buttons.values()):
                    row_index, column_index = divmod(index, 2) if narrow else (index, 0)
                    button.grid(row=row_index, column=column_index, sticky="ew", padx=2, pady=2)
                self.nav_narrow = narrow
            for key, button in self.nav_buttons.items():
                button.state(["selected" if key == self.section else "!selected"])
            place(self.headings[self.section], 0, span=2, pady=(0, 7))
            place(self.groups[self.section], row, column, sticky="new")
        else:
            for index, key in enumerate(SECTIONS):
                if self.section == key:
                    place(self.open_sections[key], 0, span=2, pady=(0, 4))
                    place(self.groups[key], index, pady=(0, 7))
                else:
                    place(self.fold_buttons[key], index, pady=(0, 7))

        if columns != self.grid_columns:
            for column, (weight, minsize, uniform) in enumerate(columns):
                self.content.columnconfigure(column, weight=weight, minsize=minsize, uniform=uniform)
            self.grid_columns = columns
        chat_became_visible = self.groups["chat"] not in self.placements and self.groups["chat"] in placements
        for widget in self.placements.keys() - placements.keys():
            widget.grid_remove()
        for widget, position in placements.items():
            if self.placements.get(widget) != position:
                widget.grid(**position)
        self.placements = placements
        if chat_became_visible:
            self.update_chat_controls()

    def report(self, key):
        self.notice = key
        self.feedback.set(strings(self.locale)[key] if key else "")
        self.queue_fit()

    def save(self):
        starts, stops = (self.editors[key].get("1.0", "end-1c").splitlines() for key in ("starts", "stop"))
        sounds = {event: TONES[choice.current()] for event, (choice, _) in self.choices.items()}
        chat_id = self.chat_id if self.chat_mode.current() == 1 else None
        if self.chat_mode.current() == 1 and chat_id is None:
            self.report("chat_choose")
            return
        try:
            saved = save_phrases(starts, stops, self.locale, self.languages[self.speech.current()],
                                 sounds, self.layout, chat_id, self.auto_replay.get())
        except ValueError:
            self.report("invalid")
        except OSError as exc:
            self.feedback.set(str(exc))
        else:
            self.on_save(saved.ui_locale)
            self.report("saved")

    def check(self):
        self.check_button.state(["disabled"])
        self.report(None)
        pending = self.submit_check()

        def receive():
            if not pending.done():
                self.check_job = self.after(150, receive)
                return
            self.check_job = None
            try:
                self.report(pending.result())
            except Exception:
                self.report("check_failed")
            self.check_button.state(["!disabled"])

        self.check_job = self.after(150, receive)

    def draw_wave(self):
        width = self.wave.winfo_width()
        if width > 4 and self.winfo_viewable():
            level, palette = self.wave_state()
            if level < 0.02:
                palette = WAVE_PALETTES["ready"]
            frame = wave_frame(max(0.15, level), time.monotonic() * 1.4, width, palette)
            self.wave_photo = ImageTk.PhotoImage(frame, master=self)
            self.wave.itemconfigure(self.wave_item, image=self.wave_photo)
        self.wave_job = self.after(80, self.draw_wave)

    def set_dark_titlebar(self):
        try:
            import win32con
            import win32gui

            hwnd = win32gui.GetAncestor(self.winfo_id(), win32con.GA_ROOT)
            dark = ctypes.c_int(1)
            apply = ctypes.windll.dwmapi.DwmSetWindowAttribute
            apply.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint)
            for attribute in (20, 19):
                if apply(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                    break
            rounded = ctypes.c_int(2)
            apply(hwnd, 33, ctypes.byref(rounded), ctypes.sizeof(rounded))
        except (AttributeError, OSError):
            pass

    def destroy(self):
        for job in (self.check_job, self.chat_job, self.wave_job, self.size_job):
            if job is not None:
                self.after_cancel(job)
        super().destroy()
