"""Native frameless Win32 resizing by tracking a user-held left-button drag.

pywebview's WinForms frameless window has no resizable border. WM_NCLBUTTONDOWN
issued asynchronously from its JS bridge can return without resizing; instead
use screen-coordinate pointer movement and SetWindowPos on the actual HWND.
This module is only activated on Windows, after a real pointerdown on a resize
zone. It never modifies any folder or profile.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import threading
import time

MIN_WIDTH = 1000   # pywebview logical size; scaled by window DPI below
MIN_HEIGHT = 770
VALID_EDGES = frozenset({
    'north', 'south', 'east', 'west',
    'northeast', 'northwest', 'southeast', 'southwest',
})


def new_rect(rect, dx, dy, edge, minimum):
    """Return x,y,width,height after resize, preserving opposite edge at min."""
    left, top, right, bottom = rect
    min_w, min_h = minimum
    if 'west' in edge:
        left = min(left + dx, right - min_w)
    elif 'east' in edge:
        right = max(right + dx, left + min_w)
    if 'north' in edge:
        top = min(top + dy, bottom - min_h)
    elif 'south' in edge:
        bottom = max(bottom + dy, top + min_h)
    return (left, top, right - left, bottom - top)


class NativeDragResize:
    """One in-flight resize per window. All Win32 calls use native HWND pixels."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._last_error = None

    def start(self, hwnd, edge):
        if edge not in VALID_EDGES:
            raise ValueError('Unknown resize edge')
        if not isinstance(hwnd, int) or hwnd <= 0:
            raise OSError('Native window handle unavailable')
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._last_error = None
        try:
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.IsWindow.argtypes = [wintypes.HWND]
            user32.IsWindow.restype = wintypes.BOOL
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            user32.GetCursorPos.restype = wintypes.BOOL
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = ctypes.c_short
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.SetWindowPos.restype = wintypes.BOOL
            user32.IsZoomed.argtypes = [wintypes.HWND]
            user32.IsZoomed.restype = wintypes.BOOL
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT
            if not user32.IsWindow(hwnd):
                raise OSError('Invalid native window handle')
            if user32.IsZoomed(hwnd):
                raise OSError('Restore the maximized window before resizing')
            # The bridge callback runs on a worker thread. Do not assume
            # ReleaseCapture/SendMessage there will enter the GUI resize loop.
            rect = wintypes.RECT()
            point = wintypes.POINT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not user32.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            scale = max(1.0, user32.GetDpiForWindow(hwnd) / 96.0)
            minimum = (round(MIN_WIDTH * scale), round(MIN_HEIGHT * scale))
            initial = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            mouse = (int(point.x), int(point.y))
            # Work is scheduled once, then follows the OS cursor directly. No
            # JS round trips, CSS sizing, mouse capture or WebView reentrancy.
            thread = threading.Thread(
                target=self._drag_loop,
                args=(user32, hwnd, edge, initial, mouse, minimum),
                daemon=True,
                name='RepoSyncNativeResize',
            )
            thread.start()
            return True
        except Exception:
            with self._lock:
                self._active = False
            raise

    def _drag_loop(self, user32, hwnd, edge, initial, mouse, minimum):
        try:
            last = None
            # OS drag is bounded; fails closed if pointer release is missed.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and (user32.GetAsyncKeyState(0x01) & 0x8000):
                point = wintypes.POINT()
                if not user32.IsWindow(hwnd) or not user32.GetCursorPos(ctypes.byref(point)):
                    break
                desired = new_rect(initial, point.x - mouse[0], point.y - mouse[1], edge, minimum)
                if desired != last:
                    # SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
                    if not user32.SetWindowPos(hwnd, 0, *map(int, desired), 0x0214):
                        raise ctypes.WinError(ctypes.get_last_error())
                    last = desired
                time.sleep(1/60)
        except Exception as exc:
            self._last_error = str(exc)
            logging.getLogger('pywebview').exception('Native window resize failed')
        finally:
            with self._lock:
                self._active = False
