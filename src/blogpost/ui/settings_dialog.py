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
