import os
import sys
from pathlib import Path

import psutil
import win32con
import win32gui
import win32process
from win32com.client import Dispatch

from bar_art import save_tray_icon
from branding import APP_NAME, APP_ROOT, INSTALL_ROOT, LEGACY_APP_NAME, TASK_NAME, TRAY_CLASS_PREFIX
from listener_state import request_stop


ROOT = INSTALL_ROOT
LAUNCHER = ROOT / "windowed.pyw"
WINDOWED = Path(sys.base_prefix) / "pythonw.exe"
COMPILED = "__compiled__" in globals()
EXECUTABLE = APP_ROOT / "Cvc.exe" if COMPILED else WINDOWED


def app_arguments(role):
    return [role] if COMPILED else ["-s", "-B", str(LAUNCHER), role]


def create_shortcuts(programs=None):
    icon = ROOT / ".runtime" / "tray.ico"
    save_tray_icon(icon)
    shell = Dispatch("WScript.Shell")
    paths = [ROOT / f"{APP_NAME}.lnk"]
    if programs is not None:
        paths.append(programs / f"{APP_NAME}.lnk")
    for path in paths:
        shortcut = shell.CreateShortcut(str(path))
        shortcut.TargetPath = str(EXECUTABLE)
        shortcut.Arguments = "panel" if COMPILED else f'-s -B "{LAUNCHER}" panel'
        shortcut.WorkingDirectory = str(ROOT)
        shortcut.IconLocation = f"{icon},0"
        shortcut.Description = APP_NAME
        shortcut.Save()


def app_processes():
    executable = WINDOWED.resolve()
    launcher = os.path.normcase(str(LAUNCHER))
    for process in psutil.process_iter(("exe", "cmdline")):
        exe = process.info["exe"]
        args = process.info["cmdline"] or []
        if COMPILED and exe and len(args) == 2 and args[1] in {"panel", "listener"}:
            if Path(exe).resolve() == EXECUTABLE:
                yield process, args[1]
            continue
        if not exe or len(args) <= 2 or os.path.normcase(args[-2]) != launcher:
            continue
        if args[-1] in {"panel", "listener"} and Path(exe).resolve() == executable:
            yield process, args[-1]


def stop_installation():
    processes = list(app_processes())
    panels = {process.pid for process, role in processes if role == "panel"}

    def close_panel(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if (pid in panels and win32gui.GetWindowText(hwnd) in {APP_NAME, LEGACY_APP_NAME}
                and not win32gui.GetClassName(hwnd).startswith(TRAY_CLASS_PREFIX)):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return True

    win32gui.EnumWindows(close_panel, None)
    if any(role == "listener" for _, role in processes):
        request_stop()
    _, running = psutil.wait_procs([process for process, _ in processes], timeout=12)
    if running:
        raise RuntimeError(f"Zamknij {APP_NAME} w zasobniku i spróbuj ponownie.")


def remove_autostart():
    scheduler = Dispatch("Schedule.Service")
    scheduler.Connect()
    folder = scheduler.GetFolder("\\")
    for task in folder.GetTasks(0):
        if task.Name != TASK_NAME:
            continue
        actions = task.Definition.Actions
        if actions.Count == 1:
            action = actions.Item(1)
            if (Path(action.Path).resolve() == EXECUTABLE.resolve()
                    and action.Arguments == ("listener" if COMPILED else f'-s -B "{LAUNCHER}" listener')):
                folder.DeleteTask(TASK_NAME, 0)
        return


def migrate_autostart():
    scheduler = Dispatch("Schedule.Service")
    scheduler.Connect()
    folder = scheduler.GetFolder("\\")
    for task in folder.GetTasks(0):
        if task.Name != TASK_NAME:
            continue
        definition = task.Definition
        actions = definition.Actions
        if actions.Count != 1:
            return
        action = actions.Item(1)
        if Path(action.Path).name.casefold() != "pythonw.exe" or action.Arguments not in {
            f'-s -B "{LAUNCHER}" listener',
            f'-B "{ROOT / "friday.py"}" --background',
        }:
            return
        action.Path = str(EXECUTABLE)
        action.Arguments = "listener"
        action.WorkingDirectory = str(ROOT)
        definition.Settings.Enabled = task.Enabled
        folder.RegisterTaskDefinition(TASK_NAME, definition, 4, definition.Principal.UserId, None, 3)
        return


def main():
    operation = sys.argv[1]
    if operation == "install":
        create_shortcuts(Path(sys.argv[2]))
        if COMPILED:
            migrate_autostart()
    elif operation == "shortcut":
        create_shortcuts()
    elif operation == "stop":
        stop_installation()
    elif operation == "uninstall":
        stop_installation()
        remove_autostart()


if __name__ == "__main__":
    main()
