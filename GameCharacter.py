import abc
import re
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar

import cv2
import easyocr
import numpy as np
import pyautogui

from GameWindow import GameWindow
from MapleTask import MapleTask
from MinimapTask import MinimapTask
from character_control import ArtaleController

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
_MP_REGION = (0.365, 0.922, 0.105, 0.042)


class Job(Enum):
    BOWMASTER = auto()
    PRIEST = auto()
    SCHOLAR = auto()
    NIGHTLORD = auto()
    GHOSTWOMEN = auto()
    MAPTEST = auto()


@dataclass
class Position:
    x: float = 0.0   # 相對於小地圖邊框的水平比例 0.0（左）～1.0（右）
    y: float = 0.0   # 相對於小地圖邊框的垂直比例 0.0（上）～1.0（下）


class GameCharacter(MapleTask, abc.ABC):
    # ── 類別共用資源（所有子類別共享同一份）────────────────────────
    _shared_gw: ClassVar[GameWindow | None] = None
    _shared_mt: ClassVar[MinimapTask | None] = None
    _shared_hp: ClassVar[float] = 100.0
    _shared_mp: ClassVar[float] = 100.0
    _shared_stat_stop: ClassVar[threading.Event] = threading.Event()
    _shared_init_lock: ClassVar[threading.Lock] = threading.Lock()
    _shared_monitors_running: ClassVar[bool] = False

    @classmethod
    def _init_shared(cls):
        """確保 GameWindow、MinimapTask 與 HP/MP monitor 只建立一次。"""
        with cls._shared_init_lock:
            if cls._shared_gw is None:
                cls._shared_gw = GameWindow()
                cls._shared_mt = MinimapTask(cls._shared_gw)
                cls._shared_mt.start()
            if not cls._shared_monitors_running:
                cls._shared_monitors_running = True
                threading.Thread(target=cls._hp_monitor_loop, daemon=True).start()
                threading.Thread(target=cls._mp_monitor_loop, daemon=True).start()

    @classmethod
    def _hp_monitor_loop(cls):
        while not cls._shared_stat_stop.wait(1.0):
            try:
                pct = cls._read_stat(_HP_REGION)
                if pct is not None:
                    cls._shared_hp = pct
            except Exception as e:
                print(f"[GameCharacter] HP monitor 異常: {e}")

    @classmethod
    def _mp_monitor_loop(cls):
        while not cls._shared_stat_stop.wait(1.0):
            try:
                pct = cls._read_stat(_MP_REGION)
                if pct is not None:
                    cls._shared_mp = pct
            except Exception as e:
                print(f"[GameCharacter] MP monitor 異常: {e}")

    @classmethod
    def shared_minimap(cls) -> MinimapTask | None:
        """回傳類別共用的 MinimapTask 實例。"""
        return cls._shared_mt

    @classmethod
    def shared_game_window(cls) -> GameWindow | None:
        """回傳類別共用的 GameWindow 實例。"""
        return cls._shared_gw

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

    def __init__(self, name: str, job: Job,
                 position: Position = None, config_path: str = "board_config.json"):
        super().__init__()
        self.name = name
        self.job = job
        self.position = position if position is not None else Position()
        self.controller = ArtaleController(config_path)

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
        return (f"{self.__class__.__name__}(name={self.name!r}, job={self.job.name}, "
                f"hp={self.hp:.1f}%, mp={self.mp:.1f}%, "
                f"pos=({self.map_x:.2f}, {self.map_y:.2f}))")
