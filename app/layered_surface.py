import ctypes
from ctypes import wintypes

import win32con
import win32gui


class BitmapHeader(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("width", wintypes.LONG),
        ("height", wintypes.LONG),
        ("planes", wintypes.WORD),
        ("bits", wintypes.WORD),
        ("compression", wintypes.DWORD),
        ("image_size", wintypes.DWORD),
        ("x_resolution", wintypes.LONG),
        ("y_resolution", wintypes.LONG),
        ("colors_used", wintypes.DWORD),
        ("colors_important", wintypes.DWORD),
    ]


create_dib = ctypes.WinDLL("gdi32", use_last_error=True).CreateDIBSection
create_dib.argtypes = (wintypes.HDC, ctypes.POINTER(BitmapHeader), wintypes.UINT,
                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
create_dib.restype = wintypes.HBITMAP


class LayeredSurface:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.size = None
        self.bitmap = None
        self.dc = win32gui.CreateCompatibleDC(0)
        try:
            flags = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, flags | win32con.WS_EX_LAYERED)
        except Exception:
            win32gui.DeleteDC(self.dc)
            raise

    def paint(self, frame):
        if frame.size != self.size:
            width, height = frame.size
            header = BitmapHeader(ctypes.sizeof(BitmapHeader), width, -height, 1, 32)
            bits = ctypes.c_void_p()
            bitmap = create_dib(self.dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
            if not bitmap:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                previous = win32gui.SelectObject(self.dc, bitmap)
            except Exception:
                win32gui.DeleteObject(bitmap)
                raise
            if self.bitmap is None:
                self.stock_bitmap = previous
            else:
                win32gui.DeleteObject(previous)
            self.bitmap, self.bits, self.size = bitmap, bits, frame.size
        pixels = frame.convert("RGBa").tobytes("raw", "BGRa")
        ctypes.memmove(self.bits, pixels, len(pixels))
        x, y, _, _ = win32gui.GetWindowRect(self.hwnd)
        win32gui.UpdateLayeredWindow(self.hwnd, 0, (x, y), self.size, self.dc, (0, 0),
                                     0, (0, 0, 255, 1), win32con.ULW_ALPHA)

    def close(self):
        if self.bitmap is not None:
            win32gui.SelectObject(self.dc, self.stock_bitmap)
            win32gui.DeleteObject(self.bitmap)
        win32gui.DeleteDC(self.dc)
