import os

import pywintypes
import win32api
import win32con
import win32gui
from branding import APP_NAME, TRAY_CLASS_PREFIX


class Tray:
    def __init__(self, root, icon_path, entries):
        self.root = root
        self.entries = entries
        self.menu_point = None
        self.closed = False
        self.restart = win32gui.RegisterWindowMessage("TaskbarCreated")
        self.callback = win32con.WM_APP + 1
        self.instance = win32api.GetModuleHandle(None)
        self.class_name = f"{TRAY_CLASS_PREFIX}{os.getpid()}"
        window_class = win32gui.WNDCLASS()
        window_class.hInstance = self.instance
        window_class.lpszClassName = self.class_name
        window_class.lpfnWndProc = self.window_proc
        win32gui.RegisterClass(window_class)
        self.hwnd = win32gui.CreateWindowEx(win32con.WS_EX_TOOLWINDOW, self.class_name, APP_NAME,
                                           win32con.WS_POPUP, 0, 0, 0, 0, 0, 0, self.instance, None)
        self.icon = win32gui.LoadImage(0, str(icon_path), win32con.IMAGE_ICON, 0, 0,
                                       win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        self.added = False
        self.add_icon()
        self.job = self.root.after(60, self.poll)

    def add_icon(self):
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, 1, flags, self.callback,
                                                        self.icon, APP_NAME))
            self.added = True
        except pywintypes.error:
            self.added = False

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == self.restart:
            self.added = False
        elif message == self.callback and lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONUP,
                                                     win32con.WM_CONTEXTMENU):
            self.menu_point = win32gui.GetCursorPos()
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def poll(self):
        if not self.added:
            self.add_icon()
        point, self.menu_point = self.menu_point, None
        try:
            if point is not None:
                self.open_menu(point)
        finally:
            if not self.closed:
                self.job = self.root.after(60 if self.added else 1000, self.poll)

    def append_entries(self, menu, entries, commands):
        for entry in entries:
            if entry is None:
                win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
                continue
            label, action = entry
            if isinstance(action, list):
                child = win32gui.CreatePopupMenu()
                self.append_entries(child, action, commands)
                win32gui.AppendMenu(menu, win32con.MF_POPUP, child, label)
            elif action is None:
                win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, label)
            else:
                command = len(commands) + 1
                commands[command] = action
                win32gui.AppendMenu(menu, win32con.MF_STRING, command, label)

    def open_menu(self, point):
        menu = win32gui.CreatePopupMenu()
        commands = {}
        try:
            self.append_entries(menu, self.entries(), commands)
            try:
                win32gui.SetForegroundWindow(self.hwnd)
            except pywintypes.error:
                pass
            flags = (win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY | win32con.TPM_RIGHTBUTTON
                     | win32con.TPM_BOTTOMALIGN)
            command = win32gui.TrackPopupMenu(menu, flags, *point, 0, self.hwnd, None)
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(menu)
        if command in commands:
            commands[command]()

    def close(self):
        self.closed = True
        self.root.after_cancel(self.job)
        if self.added:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 1))
            except pywintypes.error:
                pass
        win32gui.DestroyWindow(self.hwnd)
        win32gui.DestroyIcon(self.icon)
        win32gui.UnregisterClass(self.class_name, self.instance)
