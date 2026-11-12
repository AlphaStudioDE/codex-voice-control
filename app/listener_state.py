import pywintypes
import win32con
import win32event
import winerror


LISTENER_MUTEX = r"Local\FridayVoiceListener"
STOP_EVENT = r"Local\FridayVoiceStop"


def listener_running():
    try:
        handle = win32event.OpenMutex(win32con.SYNCHRONIZE, False, LISTENER_MUTEX)
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_FILE_NOT_FOUND:
            return False
        raise
    handle.Close()
    return True


def request_stop():
    try:
        handle = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, STOP_EVENT)
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_FILE_NOT_FOUND:
            return False
        raise
    try:
        win32event.SetEvent(handle)
    finally:
        handle.Close()
    return True
