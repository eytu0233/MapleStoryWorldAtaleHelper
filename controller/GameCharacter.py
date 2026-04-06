import abc
import re
import threading
import time
from dataclasses import dataclass
from typing import ClassVar, Callable

import cv2
import easyocr
import numpy as np
import pyautogui

from util.logger import MSLogger
from .GameWindow import GameWindow

_logger = MSLogger('GameCharacter')
from .MapleTask import MapleTask
from .MinimapTask import MinimapTask

# ── 共用 OCR reader（English-only，辨識數字最快）────────────────
_ocr_reader: easyocr.Reader | None = None
_ocr_lock = threading.Lock()


def _get_ocr_reader() -> easyocr.Reader:
    global _ocr_reader
    with _ocr_lock:
        if _ocr_reader is None:
            _ocr_reader = easyocr.Reader(['en'], gpu=True)
        return _ocr_reader


# ── HP / MP 狀態列在視窗中的比例座標 ────────────────────────────
_HP_REGION = (0.25, 0.922, 0.105, 0.042)   # (x, y, w, h) 比例
_MP_REGION = (0.38, 0.922, 0.105, 0.042)

# ── 角色名字邊框顏色偵測設定 ─────────────────────────────────────
_CHAR_COLOR_RGB       = (199, 168, 214)     # 名字邊框 RGB
_CHAR_COLOR_TOLERANCE = 20                  # 每通道容差（±20）
_CHAR_MIN_AREA        = 30                  # 最小輪廓面積（px²）
_CHAR_SEARCH_X_MIN    = 0
_CHAR_SEARCH_X_MAX    = 1
_CHAR_SEARCH_Y_MIN    = 0.6               # 排除小地圖（上方 60%）
_CHAR_SEARCH_Y_MAX    = 0.80               # 排除 HP/MP bar（下方 20%）

@dataclass
class Position:
    x: float = 0.0       # 相對於小地圖邊框的水平比例 0.0（左）～1.0（右）
    y: float = 0.0       # 相對於小地圖邊框的垂直比例 0.0（上）～1.0（下）
    screen_x: int = 0    # 視窗像素座標（角色名字邊框左上角 x）
    screen_y: int = 0    # 視窗像素座標（角色名字邊框左上角 y）
    screen_w: int = 0    # 偵測到的名字邊框寬度（px）
    screen_h: int = 0    # 偵測到的名字邊框高度（px）


class GameCharacter(MapleTask, abc.ABC):
    # ── 類別共用資源（所有子類別共享同一份）────────────────────────
    _shared_gw: ClassVar[GameWindow | None] = None
    _shared_mt: ClassVar[MinimapTask | None] = None
    _shared_hp: ClassVar[float] = 100.0
    _shared_mp: ClassVar[float] = 100.0
    _shared_screen_x: ClassVar[int] = 0
    _shared_screen_y: ClassVar[int] = 0
    _shared_screen_w: ClassVar[int] = 0
    _shared_screen_h: ClassVar[int] = 0
    _shared_screen_center_x: ClassVar[int] = 0
    _shared_screen_center_y: ClassVar[int] = 0
    _shared_stat_stop: ClassVar[threading.Event] = threading.Event()
    _shared_init_lock: ClassVar[threading.Lock] = threading.Lock()
    _shared_monitors_running: ClassVar[bool] = False
    _shared_curse_monitor: ClassVar['CurseMonitor | None'] = None
    # callback 格式：(threshold, condition, callback, fired)
    # condition: 'below' 或 'above'；fired 為 list[bool] 以支援 mutable 邊緣觸發狀態
    _hp_callbacks: ClassVar[list] = []
    _mp_callbacks: ClassVar[list] = []
    # composite event 格式：{'id', 'condition', 'callback', 'cooldown', 'last_fired'}
    # condition: Callable[[], bool]；cooldown: 秒；last_fired: monotonic 時間戳（初值 0.0）
    _composite_events: ClassVar[list] = []
    _composite_event_counter: ClassVar[int] = 0
    _composite_events_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _init_shared(cls):
        """確保 GameWindow、MinimapTask 與 HP/MP monitor 只建立一次。"""
        with cls._shared_init_lock:
            if cls._shared_gw is None:
                cls._shared_gw = GameWindow()
                cls._shared_mt = MinimapTask(cls._shared_gw)
                cls._shared_mt.start()
                from .CurseMonitor import CurseMonitor
                cls._shared_curse_monitor = CurseMonitor(cls._shared_gw)
            if not cls._shared_monitors_running:
                cls._shared_monitors_running = True
                threading.Thread(target=cls._hp_monitor_loop, daemon=True).start()
                threading.Thread(target=cls._mp_monitor_loop, daemon=True).start()
                threading.Thread(target=cls._screen_detect_loop, daemon=True).start()
                threading.Thread(target=cls._composite_monitor_loop, daemon=True).start()

    @classmethod
    def _fire_callbacks(cls, callbacks: list, value: float):
        for entry in callbacks:
            threshold, condition, cb, fired = entry
            triggered = value < threshold if condition == 'below' else value > threshold
            if triggered and not fired[0]:
                fired[0] = True
                threading.Thread(target=cb, daemon=True).start()
            elif not triggered:
                fired[0] = False

    @classmethod
    def _hp_monitor_loop(cls):
        while not cls._shared_stat_stop.wait(0.1):
            try:
                pct = cls._read_stat(_HP_REGION)
                if pct is not None:
                    cls._shared_hp = pct
                    cls._fire_callbacks(cls._hp_callbacks, pct)
            except Exception as e:
                _logger.error(f"[GameCharacter] HP monitor 異常: {e}")

    @classmethod
    def _mp_monitor_loop(cls):
        while not cls._shared_stat_stop.wait(0.1):
            try:
                pct = cls._read_stat(_MP_REGION)
                if pct is not None:
                    cls._shared_mp = pct
                    cls._fire_callbacks(cls._mp_callbacks, pct)
            except Exception as e:
                _logger.error(f"[GameCharacter] MP monitor 異常: {e}")

    @classmethod
    def _screen_detect_loop(cls):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        r0, g0, b0 = _CHAR_COLOR_RGB
        tol = _CHAR_COLOR_TOLERANCE
        while not cls._shared_stat_stop.wait(0.1):
            try:
                gw = cls._shared_gw
                if gw is None or not gw.is_valid:
                    continue
                frame = gw.capture(0.0, 0.0, 1.0, 1.0)
                if frame is None:
                    continue
                h, w = frame.shape[:2]
                x0 = int(w * _CHAR_SEARCH_X_MIN)
                x1 = int(w * _CHAR_SEARCH_X_MAX)
                y0 = int(h * _CHAR_SEARCH_Y_MIN)
                y1 = int(h * _CHAR_SEARCH_Y_MAX)
                roi = frame[y0:y1, x0:x1]
                mask = (
                    (roi[:, :, 0] >= r0 - tol) & (roi[:, :, 0] <= r0 + tol) &
                    (roi[:, :, 1] >= g0 - tol) & (roi[:, :, 1] <= g0 + tol) &
                    (roi[:, :, 2] >= b0 - tol) & (roi[:, :, 2] <= b0 + tol)
                ).astype(np.uint8) * 255
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(largest) >= _CHAR_MIN_AREA:
                        cx, cy, cw, ch = cv2.boundingRect(largest)
                        cls._shared_screen_x = cx + x0
                        cls._shared_screen_y = cy + y0
                        cls._shared_screen_w = cw
                        cls._shared_screen_h = ch
                        cls._shared_screen_center_x = cx + x0 + cw // 2
                        cls._shared_screen_center_y = cy + y0 + ch // 2
            except Exception as e:
                _logger.error(f"[GameCharacter] screen detect 異常: {e}")

    @classmethod
    def register_hp_callback(cls, threshold: float, callback: Callable[[], None],
                             condition: str = 'below'):
        """
        當 HP 滿足條件時觸發 callback（邊緣觸發，條件解除後才能再次觸發）。

        :param threshold: HP 百分比閾值（0.0 ~ 100.0）
        :param callback:  無參數的 callable，將於獨立執行緒中呼叫
        :param condition: 'below'（低於）或 'above'（高於）
        """
        cls._hp_callbacks.append((threshold, condition, callback, [False]))

    @classmethod
    def unregister_hp_callback(cls, callback: Callable[[], None]):
        cls._hp_callbacks = [e for e in cls._hp_callbacks if e[2] is not callback]

    @classmethod
    def register_mp_callback(cls, threshold: float, callback: Callable[[], None],
                             condition: str = 'below'):
        """
        當 MP 滿足條件時觸發 callback（邊緣觸發，條件解除後才能再次觸發）。

        :param threshold: MP 百分比閾值（0.0 ~ 100.0）
        :param callback:  無參數的 callable，將於獨立執行緒中呼叫
        :param condition: 'below'（低於）或 'above'（高於）
        """
        cls._mp_callbacks.append((threshold, condition, callback, [False]))

    @classmethod
    def _composite_monitor_loop(cls):
        """每 0.1 s 輪詢所有 composite event；條件成立且冷卻已過則觸發 callback。"""
        while not cls._shared_stat_stop.wait(0.1):
            now = time.monotonic()
            with cls._composite_events_lock:
                entries = list(cls._composite_events)
            for entry in entries:
                try:
                    triggered = entry['condition']()
                except Exception:
                    continue
                if triggered and (now - entry['last_fired']) >= entry['cooldown']:
                    entry['last_fired'] = now
                    threading.Thread(target=entry['callback'], daemon=True).start()

    @classmethod
    def register_composite_event(
        cls,
        condition: Callable[[], bool],
        callback: Callable[[], None],
        cooldown: float = 1.0,
    ) -> int:
        """
        當 condition() 為 True 且距上次觸發超過 cooldown 秒時呼叫 callback。

        :param condition: 無參數，回傳 bool；可同時檢查 HP、MP、位置等任意組合
        :param callback:  無參數的 callable，將於獨立 daemon thread 中呼叫
        :param cooldown:  兩次觸發的最短間隔（秒）
        :return:          event ID，可傳入 unregister_composite_event 取消
        """
        with cls._composite_events_lock:
            eid = cls._composite_event_counter
            cls._composite_event_counter += 1
            cls._composite_events.append({
                'id':         eid,
                'condition':  condition,
                'callback':   callback,
                'cooldown':   cooldown,
                'last_fired': 0.0,
            })
        return eid

    @classmethod
    def unregister_composite_event(cls, eid: int) -> None:
        """取消以 register_composite_event 註冊的 event。"""
        with cls._composite_events_lock:
            cls._composite_events = [e for e in cls._composite_events if e['id'] != eid]

    @classmethod
    def shared_minimap(cls) -> MinimapTask | None:
        """回傳類別共用的 MinimapTask 實例。"""
        return cls._shared_mt

    @classmethod
    def shared_game_window(cls) -> GameWindow | None:
        """回傳類別共用的 GameWindow 實例。"""
        return cls._shared_gw

    @classmethod
    def shared_curse_monitor(cls) -> 'CurseMonitor | None':
        """回傳類別共用的 CurseMonitor 實例。"""
        return cls._shared_curse_monitor

    @classmethod
    def _read_stat(cls, region: tuple) -> float | None:
        if cls._shared_gw is None:
            return None
        img = cls._shared_gw.capture(*region)
        if img is None:
            return None
        processed = cls._preprocess(img)
        reader = _get_ocr_reader()
        with _ocr_lock:
            results = reader.readtext(processed, detail=0)
        return cls._parse_ratio(" ".join(results))

    def __init__(self, name: str,
                 position: Position = None):
        super().__init__()
        self.name = name
        self.position = position if position is not None else Position()

        GameCharacter._init_shared()
        self.game_window = GameCharacter._shared_gw
        self.minimap_task = GameCharacter._shared_mt

    # ── HP / MP 屬性（讀取類別共用值）───────────────────────────

    @property
    def hp(self) -> float:
        return GameCharacter._shared_hp

    @property
    def mp(self) -> float:
        return GameCharacter._shared_mp

    # ── position 便捷屬性（從 minimap_task 同步）────────────────

    @property
    def map_x(self) -> float:
        return self.minimap_task.pos[0]

    @property
    def map_y(self) -> float:
        return self.minimap_task.pos[1]

    @property
    def screen_x(self) -> int:
        return GameCharacter._shared_screen_x

    @property
    def screen_y(self) -> int:
        return GameCharacter._shared_screen_y

    @property
    def screen_w(self) -> int:
        return GameCharacter._shared_screen_w

    @property
    def screen_h(self) -> int:
        return GameCharacter._shared_screen_h

    @property
    def screen_center_x(self) -> int:
        return GameCharacter._shared_screen_center_x

    @property
    def screen_center_y(self) -> int:
        return GameCharacter._shared_screen_center_y

    # ── HP / MP 辨識（靜態輔助）────────────────────────────────

    @staticmethod
    def _preprocess(img: np.ndarray) -> np.ndarray:
        img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def _parse_ratio(text: str) -> float | None:
        m = re.search(r'(\d+)\s*/\s*(\d+)', text)
        if m:
            current, total = int(m.group(1)), int(m.group(2))
            if total > 0:
                return round(current / total * 100.0, 1)
        return None

    @classmethod
    def stop_monitors(cls):
        """停止 HP/MP 背景監控與小地圖 Task（全域，影響所有子類別）。"""
        cls._shared_stat_stop.set()
        if cls._shared_mt is not None:
            cls._shared_mt.stop()

    # ── 按鍵控制 ─────────────────────────────────────────────────

    def _hold_key(self, key: str, duration: float) -> bool:
        pyautogui.keyDown(key)
        stopped = self.wait_stop_event(duration)
        pyautogui.keyUp(key)
        return stopped

    def move_up(self) -> bool:
        """
        同時按住 alt（跳躍）+ 上方向鍵，使角色往上爬升。
        停止條件：pos_y 連續 500 ms 未再減少，或收到 stop 訊號。
        回傳 True 表示收到 stop 訊號。
        """
        import time
        _CHECK_INTERVAL = 0.05   # 每 50 ms 取樣一次
        _STALL_TIMEOUT  = 0.5    # pos_y 不再減少超過此秒數則停止

        pyautogui.keyDown('alt')
        pyautogui.keyDown('up')

        last_decrease_time = time.monotonic()
        last_y = self.minimap_task.pos[1]
        stopped = False

        try:
            while True:
                if self.wait_stop_event(_CHECK_INTERVAL):
                    stopped = True
                    break
                y = self.minimap_task.pos[1]
                if y < last_y:
                    last_y = y
                    last_decrease_time = time.monotonic()
                elif time.monotonic() - last_decrease_time >= _STALL_TIMEOUT:
                    break
        finally:
            pyautogui.keyUp('up')
            pyautogui.keyUp('alt')

        return stopped

    def jump(self, direction: str) -> bool:
        """按住 alt + 左/右方向鍵進行方向跳躍。回傳 True 表示收到 stop 訊號。"""
        pyautogui.keyDown('alt')
        stopped = self._hold_key(direction, 0.2)
        pyautogui.keyUp('alt')
        return stopped

    def move_down(self) -> bool:
        """先按住下方向鍵再按 alt，持續 0.5 秒後放開，讓角色穿越平台往下跳。"""
        pyautogui.keyDown('down')
        pyautogui.keyDown('alt')
        stopped = self.wait_stop_event(1)
        pyautogui.keyUp('alt')
        pyautogui.keyUp('down')
        return stopped

    def update_position(self, x: float, y: float):
        self.position.x = x
        self.position.y = y

    # ── 抽象方法 ─────────────────────────────────────────────────

    @abc.abstractmethod
    def move(self, direction: str) -> bool:
        ...

    @abc.abstractmethod
    def normal_attack(self) -> bool:
        ...

    @abc.abstractmethod
    def task(self):
        ...

    def __repr__(self):
        return (f"{self.__class__.__name__}(name={self.name!r}, "
                f"hp={self.hp:.1f}%, mp={self.mp:.1f}%, "
                f"pos=({self.map_x:.2f}, {self.map_y:.2f}))")
