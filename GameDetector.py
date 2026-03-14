import win32gui
import win32process

ARTALE_WINDOW_TITLE = "MapleStory Worlds-Artale"


def get_artale_hwnd():
    """
    透過視窗標題枚舉找到 Artale 視窗句柄。
    回傳 hwnd (int)，找不到時回傳 0。
    """
    result = []

    def callback(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and ARTALE_WINDOW_TITLE in title:
                    result.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return result[0] if result else 0
