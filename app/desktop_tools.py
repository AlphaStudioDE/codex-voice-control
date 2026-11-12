import ctypes
import io
import os
import struct
import time
from _ctypes import COMError
from urllib.parse import urlencode, urlsplit

import psutil
import pywintypes
import uiautomation as ui
import win32con
import win32gui
import win32process
from mcp.server.fastmcp import Image
from PIL import ImageGrab


BROWSERS = {
    "brave.exe": "Brave",
    "chrome.exe": "Chrome",
    "chromium.exe": "Chromium",
    "firefox.exe": "Firefox",
    "msedge.exe": "Edge",
    "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi",
}
SEARCH_PAGE = "https://www.google.com/"


def browser_open(url: str | None = None) -> str:
    """Otwórz podaną stronę HTTP lub HTTPS w domyślnej przeglądarce Windows."""
    address = SEARCH_PAGE if url is None else url.strip()
    parts = urlsplit(address)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or any(ch.isspace() or not ch.isprintable() or ch == "\\" for ch in address)):
        raise ValueError("Podaj pełny adres strony HTTP lub HTTPS.")
    os.startfile(address)
    return "Przekazano stronę do otwarcia domyślnej przeglądarce."


def browser_search(query: str) -> str:
    """Otwórz wyniki wyszukiwania podanej frazy w Google."""
    query = query.strip()
    if not query:
        raise ValueError("Podaj treść wyszukiwania.")
    browser_open(f"{SEARCH_PAGE}search?{urlencode({'q': query})}")
    return "Przekazano wyszukiwanie do przeglądarki."


def browser_youtube() -> str:
    """Otwórz stronę główną YouTube w domyślnej przeglądarce."""
    browser_open("https://www.youtube.com/")
    return "Przekazano YouTube do otwarcia w przeglądarce."


def browser_name(handle):
    if not handle or not win32gui.IsWindow(handle):
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(handle)
        return BROWSERS.get(psutil.Process(pid).name().casefold())
    except (OSError, psutil.Error, pywintypes.error):
        return None


def focus_browser(browser=None):
    if browser is not None:
        browser = browser.strip().casefold()
        if browser not in {name.casefold() for name in BROWSERS.values()}:
            raise ValueError("Wybierz Chrome, Edge, Firefox, Brave, Opera, Vivaldi lub Chromium.")
    foreground = win32gui.GetForegroundWindow()
    active_name = browser_name(foreground)
    if active_name and (browser is None or active_name.casefold() == browser):
        return foreground, active_name

    windows = []

    def collect(handle, _):
        if win32gui.IsWindowVisible(handle) and not win32gui.GetWindow(handle, win32con.GW_OWNER):
            name = browser_name(handle)
            if name and (browser is None or name.casefold() == browser):
                windows.append((handle, name))
        return True

    win32gui.EnumWindows(collect, None)
    if not windows:
        raise RuntimeError("Brak otwartego okna wybranej przeglądarki.")
    if len({name for _, name in windows}) > 1 and browser is None:
        choices = ", ".join(sorted({name for _, name in windows}))
        raise RuntimeError(f"Wskaż przeglądarkę spośród otwartych okien: {choices}.")
    handle, name = windows[0]
    if win32gui.IsIconic(handle):
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(handle)
    except (OSError, pywintypes.error):
        pass
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        if win32gui.GetForegroundWindow() == handle:
            return handle, name
        time.sleep(0.05)
    raise RuntimeError(f"Windows nie uaktywnił okna {name}. Wybierz je na pasku zadań i ponów polecenie.")


def browser_focus(browser: str | None = None) -> str:
    """Przełącz na otwarte okno wskazanej przeglądarki."""
    _, name = focus_browser(browser)
    return f"Aktywne okno: {name}."


def send_keys(handle, events):
    if win32gui.GetForegroundWindow() != handle:
        raise RuntimeError("Aktywne okno się zmieniło. Ponów polecenie w przeglądarce.")
    if any(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000 for key in (
        ui.Keys.VK_SHIFT, ui.Keys.VK_CONTROL, ui.Keys.VK_MENU,
        ui.Keys.VK_LWIN, ui.Keys.VK_RWIN,
    )):
        raise RuntimeError("Zwolnij klawisze modyfikujące i ponów polecenie.")
    inputs = (ui.INPUT * len(events))(*events)
    sent = ctypes.windll.user32.SendInput(len(inputs), inputs, ctypes.sizeof(ui.INPUT))
    if sent != len(inputs):
        raise RuntimeError("Windows nie przyjął wszystkich klawiszy. Sprawdź pole w przeglądarce.")


def browser_new_tab(browser: str | None = None) -> str:
    """Otwórz nową kartę w już działającej przeglądarce."""
    handle, name = focus_browser(browser)
    key_up = ui.KeyboardEventFlag.KeyUp
    ctrl = ui.Keys.VK_CONTROL
    tab_key = ord("T")
    send_keys(handle, [
        ui.KeyboardInput(ctrl, 0, 0),
        ui.KeyboardInput(tab_key, 0, 0),
        ui.KeyboardInput(tab_key, 0, key_up),
        ui.KeyboardInput(ctrl, 0, key_up),
    ])
    return f"Wysłano skrót otwarcia nowej karty do {name}."


def browser_type(text: str) -> str:
    """Wpisz dosłowny tekst do aktywnego pola edycji w przeglądarce, bez zatwierdzania."""
    if not text or not text.isprintable() or len(text) > 1500:
        raise ValueError("Podaj od 1 do 1500 znaków tekstu w jednym wierszu.")
    handle = win32gui.GetForegroundWindow()
    if not browser_name(handle):
        raise RuntimeError("Ustaw przeglądarkę na pierwszym planie i wybierz pole edycji.")
    control = ui.GetFocusedControl()
    if (not control or control.ControlType != ui.ControlType.EditControl
            or not control.IsEnabled or control.IsPassword):
        raise RuntimeError("Wybierz zwykłe pole tekstowe w przeglądarce.")
    encoded = text.encode("utf-16-le")
    units = struct.unpack(f"<{len(encoded) // 2}H", encoded)
    unicode_flag = ui.KeyboardEventFlag.KeyUnicode
    events = [
        ui.KeyboardInput(0, unit, flag)
        for unit in units
        for flag in (unicode_flag, unicode_flag | ui.KeyboardEventFlag.KeyUp)
    ]
    send_keys(handle, events)
    return "Wysłano tekst do wybranego pola."


def browser_click(label: str) -> str:
    """Kliknij widoczny przycisk albo odnośnik o podanej dokładnej nazwie w aktywnej przeglądarce."""
    name = label.strip().casefold()
    if not name:
        raise ValueError("Podaj dokładną nazwę przycisku albo odnośnika.")
    handle = win32gui.GetForegroundWindow()
    if not browser_name(handle):
        raise RuntimeError("Ustaw docelową przeglądarkę na pierwszym planie.")
    window = ui.ControlFromHandle(handle)
    if not window:
        raise RuntimeError("Windows nie udostępnił drzewa kontrolek przeglądarki.")
    matches = []
    kinds = {ui.ControlType.ButtonControl, ui.ControlType.HyperlinkControl}
    for control, _ in ui.WalkControl(window, maxDepth=40):
        try:
            if (control.ControlType in kinds and control.Name.casefold() == name
                    and control.IsEnabled and not control.IsOffscreen):
                matches.append(control)
                if len(matches) > 1:
                    raise ValueError("Ta nazwa pasuje do kilku elementów. Wybierz jednoznaczny element.")
        except COMError:
            continue
    if not matches or not (pattern := matches[0].GetPattern(ui.PatternId.InvokePattern)):
        raise RuntimeError("Nie znaleziono widocznego przycisku albo odnośnika z tą nazwą.")
    if win32gui.GetForegroundWindow() != handle:
        raise RuntimeError("Aktywne okno się zmieniło. Ponów polecenie w przeglądarce.")
    pattern.Invoke()
    return "Wywołano wskazany przycisk albo odnośnik."


def capture_screen(all_monitors: bool = False) -> Image:
    """Zrób jednorazowy zrzut głównego monitora lub całego pulpitu na wyraźne żądanie użytkownika."""
    with ImageGrab.grab(all_screens=all_monitors) as snapshot:
        snapshot.thumbnail((2560, 1600))
        with io.BytesIO() as buffer:
            snapshot.save(buffer, format="PNG")
            return Image(data=buffer.getvalue(), format="png")
