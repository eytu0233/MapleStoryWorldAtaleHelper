import threading
import time
from ctypes import windll

import numpy as np
import pyautogui
import win32gui
import win32ui

from util.GameDetector import get_artale_hwnd

_POLL_INTERVAL = 0.5  # 視窗幾何輪詢間隔（秒）


class GameWindow:
    """
    即時追蹤 Artale 遊戲視窗的句柄與幾何資訊。

    背景執行緒每 poll_interval 秒更新一次視窗位置與大小；
    視窗消失時自動重新偵測。所有屬性存取皆為執行緒安全。

    主要功能：
        - hwnd / left / top / width / height / is_valid 屬性
        - abs_region()：將視窗比例座標轉換為絕對像素區域
        - capture()：截取視窗內指定比例區域的畫面（RGB numpy array）
    """

    def __init__(self, poll_interval: float = _POLL_INTERVAL):
        self._lock = threading.RLock()
        self._hwnd: int = 0
        self._left: int = 0
        self._top: int = 0
        self._width: int = 0
        self._height: int = 0

        self._poll_interval = poll_interval
        self._refresh()  # 同步初始化，確保啟動時即有資料

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    # ── 內部更新 ────────────────────────────────────────────────

    def _refresh(self):
        with self._lock:
            # 若現有 hwnd 仍有效，直接更新幾何即可
            if self._hwnd and win32gui.IsWindow(self._hwnd):
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(self._hwnd)
                    prev_w, prev_h = self._width, self._height
                    self._left, self._top = left, top
                    self._width, self._height = right - left, bottom - top
                    if (self._width, self._height) != (prev_w, prev_h):
                        print(f"[GameWindow] 視窗大小變更：{prev_w}x{prev_h} → {self._width}x{self._height}")
                    return
                except Exception:
                    pass  # 視窗失效，往下重新偵測

            # 重新搜尋遊戲視窗
            hwnd = get_artale_hwnd()
            if hwnd:
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    self._hwnd = hwnd
                    self._left, self._top = left, top
                    self._width, self._height = right - left, bottom - top
                    print(f"[GameWindow] 偵測到視窗：hwnd={hex(hwnd)}  {self._width}x{self._height}")
                except Exception:
                    self._hwnd = 0
                    self._width = self._height = 0
            else:
                if self._hwnd:
                    print("[GameWindow] 遊戲視窗已關閉，等待重新偵測…")
                self._hwnd = 0
                self._width = self._height = 0

    def _poll_loop(self):
        while True:
            time.sleep(self._poll_interval)
            try:
                self._refresh()
            except Exception:
                pass

    # ── 公開屬性 ────────────────────────────────────────────────

    @property
    def hwnd(self) -> int:
        with self._lock:
            return self._hwnd

    @property
    def left(self) -> int:
        with self._lock:
            return self._left

    @property
    def top(self) -> int:
        with self._lock:
            return self._top

    @property
    def width(self) -> int:
        with self._lock:
            return self._width

    @property
    def height(self) -> int:
        with self._lock:
            return self._height

    @property
    def is_valid(self) -> bool:
        with self._lock:
            return self._hwnd != 0 and self._width > 0 and self._height > 0

    # ── 畫面辨識輔助 ────────────────────────────────────────────

    def abs_region(self,
                   x_ratio: float, y_ratio: float,
                   w_ratio: float, h_ratio: float
                   ) -> tuple[int, int, int, int]:
        """
        將視窗相對比例座標轉換為螢幕絕對像素區域。

        Args:
            x_ratio: 區域左緣距視窗左緣的比例 (0.0～1.0)
            y_ratio: 區域上緣距視窗上緣的比例 (0.0～1.0)
            w_ratio: 區域寬度佔視窗寬度的比例
            h_ratio: 區域高度佔視窗高度的比例

        Returns:
            (left, top, width, height) 絕對像素座標，
            可直接傳給 pyautogui.screenshot(region=...)。
        """
        with self._lock:
            left = int(self._left + self._width * x_ratio)
            top = int(self._top + self._height * y_ratio)
            w = int(self._width * w_ratio)
            h = int(self._height * h_ratio)
        return left, top, w, h

    def capture(self,
                x_ratio: float, y_ratio: float,
                w_ratio: float, h_ratio: float
                ) -> np.ndarray | None:
        """
        截取視窗內指定比例區域的畫面（直接從視窗 DC 擷取，不含疊加視窗）。

        Args:
            x_ratio, y_ratio, w_ratio, h_ratio: 同 abs_region()

        Returns:
            RGB numpy array (H×W×3)；視窗不可用時回傳 None。
        """
        if not self.is_valid:
            return None

        with self._lock:
            hwnd = self._hwnd
            ww = self._width
            wh = self._height

        if ww <= 0 or wh <= 0:
            return None

        # 用 PrintWindow(PW_RENDERFULLCONTENT=2) 直接從視窗 DC 擷取，
        # 不含任何疊加在上方的視窗（例如 DebugOverlay）
        img = None
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if hwnd_dc == 0:
            # DC 無效（視窗最小化或暫時不可用）→ 退回 pyautogui
            region = self.abs_region(x_ratio, y_ratio, w_ratio, h_ratio)
            return np.array(pyautogui.screenshot(region=region))

        mfc_dc = save_dc = bmp = None
        try:
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(mfc_dc, ww, wh)
            save_dc.SelectObject(bmp)

            if windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2):
                raw = bmp.GetBitmapBits(True)
                img = np.frombuffer(raw, dtype=np.uint8).reshape(wh, ww, 4)
                img = img[:, :, 2::-1].copy()  # BGRA → RGB
        except Exception:
            img = None
        finally:
            if bmp is not None:
                handle = bmp.GetHandle()
                if handle:
                    win32gui.DeleteObject(handle)
            if save_dc is not None:
                save_dc.DeleteDC()
            # mfc_dc 只是包裝 hwnd_dc，不擁有它；由 ReleaseDC 釋放，此處不呼叫 DeleteDC
            win32gui.ReleaseDC(hwnd, hwnd_dc)

        if img is None:
            # PrintWindow 失敗時退回 pyautogui（仍可能含 DebugOverlay）
            region = self.abs_region(x_ratio, y_ratio, w_ratio, h_ratio)
            return np.array(pyautogui.screenshot(region=region))

        # 裁切到要求的比例區域
        rx = int(ww * x_ratio)
        ry = int(wh * y_ratio)
        rw = int(ww * w_ratio)
        rh = int(wh * h_ratio)
        return img[ry:ry + rh, rx:rx + rw]

    def __repr__(self) -> str:
        with self._lock:
            if not self._hwnd:
                return "GameWindow(未偵測到視窗)"
            return (f"GameWindow(hwnd={hex(self._hwnd)}, "
                    f"pos=({self._left},{self._top}), "
                    f"size={self._width}x{self._height})")
