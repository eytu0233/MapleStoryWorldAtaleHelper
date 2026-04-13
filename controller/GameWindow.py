import threading
import time
from ctypes import windll

import numpy as np
import pyautogui
import win32gui
import win32ui

from util.GameDetector import get_artale_hwnd
from util.logger import MSLogger

_logger = MSLogger('GameWindow')
_POLL_INTERVAL = 0.5         # 視窗幾何輪詢間隔（秒）
_FRAME_CAPTURE_FPS = 120    # 全幀緩衝擷取速率
_FRAME_INTERVAL = 1.0 / _FRAME_CAPTURE_FPS


class GameWindow:
    """
    即時追蹤 Artale 遊戲視窗的句柄與幾何資訊。

    背景執行緒每 poll_interval 秒更新一次視窗位置與大小；
    視窗消失時自動重新偵測。所有屬性存取皆為執行緒安全。

    主要功能：
        - hwnd / left / top / width / height / is_valid 屬性
        - abs_region()：將視窗比例座標轉換為絕對像素區域
        - get_latest_frame()：回傳最新完整視窗畫面（_FRAME_CAPTURE_FPS 緩衝，RGB numpy array）
        - capture()：從緩衝幀裁切指定比例區域（不再直接呼叫 PrintWindow）
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

        # 全幀緩衝
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._frame_thread = threading.Thread(target=self._frame_loop, daemon=True)
        self._frame_thread.start()

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
                        _logger.info(f"[GameWindow] 視窗大小變更：{prev_w}x{prev_h} → {self._width}x{self._height}")
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
                    _logger.info(f"[GameWindow] 偵測到視窗：hwnd={hex(hwnd)}  {self._width}x{self._height}")
                except Exception:
                    self._hwnd = 0
                    self._width = self._height = 0
            else:
                if self._hwnd:
                    _logger.warning("[GameWindow] 遊戲視窗已關閉，等待重新偵測…")
                self._hwnd = 0
                self._width = self._height = 0

    def _poll_loop(self):
        while True:
            time.sleep(self._poll_interval)
            try:
                self._refresh()
            except Exception:
                pass

    # ── 全幀緩衝 ────────────────────────────────────────────────

    def _capture_full(self) -> np.ndarray | None:
        """擷取完整視窗畫面（不裁切），回傳 RGB numpy array 或 None。"""
        if not self.is_valid:
            return None

        with self._lock:
            hwnd = self._hwnd
            ww = self._width
            wh = self._height
            left = self._left
            top = self._top

        if ww <= 0 or wh <= 0:
            return None

        img = None
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if hwnd_dc == 0:
            return np.array(pyautogui.screenshot(region=(left, top, ww, wh)))

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
            win32gui.ReleaseDC(hwnd, hwnd_dc)

        if img is None:
            return np.array(pyautogui.screenshot(region=(left, top, ww, wh)))

        return img

    def _frame_loop(self):
        while True:
            start = time.perf_counter()
            try:
                frame = self._capture_full()
            except Exception:
                frame = None
            with self._frame_lock:
                self._latest_frame = frame
            elapsed = time.perf_counter() - start
            sleep_time = _FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_latest_frame(self) -> np.ndarray | None:
        """回傳最新完整視窗畫面（RGB numpy array）；視窗不可用時回傳 None。"""
        with self._frame_lock:
            return self._latest_frame

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
        從全幀緩衝裁切指定比例區域的畫面。

        Args:
            x_ratio, y_ratio, w_ratio, h_ratio: 同 abs_region()

        Returns:
            RGB numpy array (H×W×3)；視窗不可用或緩衝尚未就緒時回傳 None。
        """
        frame = self.get_latest_frame()
        if frame is None:
            return None
        fh, fw = frame.shape[:2]
        rx = int(fw * x_ratio)
        ry = int(fh * y_ratio)
        rw = int(fw * w_ratio)
        rh = int(fh * h_ratio)
        cropped = frame[ry:ry + rh, rx:rx + rw]
        return cropped if cropped.size > 0 else None

    def __repr__(self) -> str:
        with self._lock:
            if not self._hwnd:
                return "GameWindow(未偵測到視窗)"
            return (f"GameWindow(hwnd={hex(self._hwnd)}, "
                    f"pos=({self._left},{self._top}), "
                    f"size={self._width}x{self._height})")
