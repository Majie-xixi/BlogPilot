from __future__ import annotations

from ctypes import Structure, c_long


def fit_dialog_geometry(
    parent: tuple[int, int, int, int],
    work_area: tuple[int, int, int, int],
    preferred: tuple[int, int] = (650, 760),
    margin: int = 16,
) -> tuple[int, int, int, int]:
    """Return width, height, x and y fully contained in the usable desktop."""
    parent_x, parent_y, parent_width, parent_height = parent
    left, top, right, bottom = work_area
    available_width = max(1, right - left - margin * 2)
    available_height = max(1, bottom - top - margin * 2)
    width = min(preferred[0], available_width)
    height = min(preferred[1], available_height)
    x = parent_x + (parent_width - width) // 2
    y = parent_y + (parent_height - height) // 2
    x = min(max(x, left + margin), right - margin - width)
    y = min(max(y, top + margin), bottom - margin - height)
    return width, height, x, y


class _Rect(Structure):
    _fields_ = (("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long))


def monitor_work_area(parent) -> tuple[int, int, int, int]:
    import sys
    if sys.platform == 'win32':
        from ctypes import byref, sizeof, windll
        from ctypes import wintypes

        class MonitorInfo(Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', _Rect),
                        ('rcWork', _Rect), ('dwFlags', wintypes.DWORD)]

        user32 = windll.user32
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, wintypes.LPVOID]
        monitor = user32.MonitorFromWindow(parent.winfo_id(), 2)
        info = MonitorInfo()
        info.cbSize = sizeof(info)
        if monitor and user32.GetMonitorInfoW(monitor, byref(info)):
            area = info.rcWork
            return area.left, area.top, area.right, area.bottom
    return 0, 0, parent.winfo_screenwidth(), parent.winfo_screenheight()


def place_dialog(dialog, parent, preferred: tuple[int, int]) -> tuple[int, int, int, int]:
    parent.update_idletasks()
    dialog.update_idletasks()
    bounds = (parent.winfo_rootx(), parent.winfo_rooty(), parent.winfo_width(), parent.winfo_height())
    width, height, x, y = fit_dialog_geometry(bounds, monitor_work_area(parent), preferred)
    dialog.geometry(f'{width}x{height}{x:+d}{y:+d}')
    return width, height, x, y
