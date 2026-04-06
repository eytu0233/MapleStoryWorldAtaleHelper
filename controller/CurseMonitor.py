"""
CurseMonitor — 偵測遊戲詛咒狀態通知框，並透過 notify_fn 發送通知。

偵測策略（純色彩篩選）：
  HSV 深紫背景 + 亮紫文字 + 面積條件

觸發後啟動 _NOTIFY_COOLDOWN 秒冷卻，期間不重複通知。

使用方式：
  monitor = CurseMonitor(game_window, discord_bot.notify)
  monitor.start()
"""

import time
from typing import Callable

import cv2
import numpy as np

from util.logger import MSLogger
from .GameWindow import GameWindow
from .MapleTask import MapleTask

_logger = MSLogger('CurseMonitor')

# ── 截圖區域（比例座標：x, y, w, h）────────────────────────────
_SCAN_REGION = (0.30, 0.20, 0.50, 0.25)

# ── 深紫背景 HSV 範圍（OpenCV H: 0-179）────────────────────────
_BG_LOWER = np.array([125, 100, 10])
_BG_UPPER = np.array([160, 255, 90])

# ── 亮紫文字 HSV 範圍 ───────────────────────────────────────────
_TXT_LOWER = np.array([130,  40, 140])
_TXT_UPPER = np.array([160, 210, 255])

# ── 幾何條件 ────────────────────────────────────────────────────
_MIN_BG_AREA   = 3000   # 背景連通塊最小像素面積（px²）
_TXT_RATIO_MIN = 0.01   # 亮紫文字佔背景框面積的最小比例

# ── 冷卻與輪詢間隔 ──────────────────────────────────────────────
_NOTIFY_COOLDOWN = 60.0   # 秒，通知後的冷卻時間（防洗版）
_POLL_INTERVAL   = 1.5    # 秒，正常輪詢間隔


class CurseMonitor(MapleTask):
    """偵測詛咒狀態並發送通知。"""

    def __init__(self, game_window: GameWindow,
                 notify_fn: Callable[[str], None] = print):
        super().__init__()
        self._gw = game_window
        self._notify_fn = notify_fn
        self._last_notified: float = 0.0

    # ── 色彩篩選 ─────────────────────────────────────────────────

    def _color_detect(self, frame: np.ndarray) -> bool:
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)

        # 深紫背景遮罩
        bg_mask = cv2.inRange(hsv, _BG_LOWER, _BG_UPPER)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        bg_mask = cv2.morphologyEx(bg_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(bg_mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < _MIN_BG_AREA:
            return False

        x, y, w, h = cv2.boundingRect(largest)

        # 確認亮紫文字存在
        txt_mask = cv2.inRange(hsv, _TXT_LOWER, _TXT_UPPER)
        roi_txt = txt_mask[y:y + h, x:x + w]
        if np.count_nonzero(roi_txt) / (w * h) < _TXT_RATIO_MIN:
            return False

        return True

    # ── 主迴圈 ───────────────────────────────────────────────────

    def task(self):
        _logger.info("[CurseMonitor] 啟動")
        while True:
            if self.wait_stop_event(_POLL_INTERVAL):
                break

            gw = self._gw
            if gw is None or not gw.is_valid:
                continue

            frame = gw.capture(*_SCAN_REGION)
            if frame is None:
                continue

            try:
                if not self._color_detect(frame):
                    continue

                now = time.monotonic()
                if now - self._last_notified < _NOTIFY_COOLDOWN:
                    continue

                self._last_notified = now
                self._notify_fn("⚠️ 詛咒狀態！必須解放符文才能解除詛咒！")
                _logger.info("[CurseMonitor] 詛咒偵測，已發送通知")

            except Exception as e:
                _logger.error(f"[CurseMonitor] 偵測異常: {e}")

        _logger.info("[CurseMonitor] 停止")
