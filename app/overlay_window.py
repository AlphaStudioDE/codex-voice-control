import win32api
import win32con
import win32gui


class OverlayWindow:
    def __init__(self, root):
        self.root = root
        self.hwnd = win32gui.GetAncestor(root.winfo_id(), win32con.GA_ROOT)
        self.position = None
        self.poll_job = None
        self.visible = False
        style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
        style |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, style)

    def show(self):
        if self.visible:
            return
        self.visible = True
        self.fit()
        self.root.deiconify()
        self.root.update_idletasks()
        self.fit()

    def hide(self):
        self.visible = False
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        self.root.withdraw()

    def fit(self):
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
        monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
        left, top, right, _ = win32api.GetMonitorInfo(monitor)["Monitor"]
        height = self.root.winfo_reqheight()
        position = (left, top, right, top + height)
        if self.position != position:
            self.position = position
            self.root.geometry(f"{right - left}x{height}")
        if (win32gui.GetWindowRect(self.hwnd) != position
                or not win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST):
            win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, left, top, right - left, height,
                                  win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER)
        self.poll_job = self.root.after(500, self.fit)
