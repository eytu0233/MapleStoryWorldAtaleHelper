import datetime
import threading
from typing import Callable

import cv2
import numpy as np

from util.MapData import MapData
from util.logger import MSLogger

from .GameWindow import GameWindow
from .MapleTask import MapleTask

_logger = MSLogger('MinimapTask')

# ── 小地圖固定邊界預設值（遊戲視窗比例，0.0～1.0）────────────────
# 基準解析度 2576×1416，原像素 (66, 185, 319, 423)
_DEFAULT_RX0 = 66  / 2576   # ≈ 0.02562
_DEFAULT_RY0 = 185 / 1416   # ≈ 0.13065
_DEFAULT_RX1 = 319 / 2576   # ≈ 0.12384
_DEFAULT_RY1 = 423 / 1416   # ≈ 0.29873

# 黃點 HSV 範圍（H 26–38 為純黃；橘色隊友點 H ≈ 10–22，刻意排除）
_DOT_LOWER    = np.array([26, 150, 180])
_DOT_UPPER    = np.array([38, 255, 255])
_DOT_MIN_AREA = 3
_DOT_MAX_AREA = 300

SCAN_INTERVAL = 1 / 120  # 秒（~120fps）

# ── 地圖錄製參數 ──────────────────────────────────────────────
_RECORD_DECIMALS = 2
_CLIMB_X_TOL     = 0.04
_CLIMB_Y_STEP    = 0.008
_CLIMB_MIN_RUN   = 4


class MinimapTask(MapleTask):
    """
    持續偵測小地圖黃點位置的獨立 Task。

    邊界固定由 set_bounds() 設定（遊戲視窗比例座標，0.0～1.0），不再自動偵測。
    偵測結果：
        pos : 黃點相對於邊界區域的比例座標 tuple[float, float]（0.0～1.0）
    """

    def __init__(self, game_window: GameWindow):
        super().__init__()
        self.game_window = game_window
        self.pos: tuple[float, float] = (0.0, 0.0)

        # 固定邊界（遊戲視窗比例座標，0.0～1.0）
        self._rx0 = _DEFAULT_RX0
        self._ry0 = _DEFAULT_RY0
        self._rx1 = _DEFAULT_RX1
        self._ry1 = _DEFAULT_RY1

        # 地圖錄製
        self._map_points: list[tuple[float, float]] = []
        self._map_point_set: set[tuple[float, float]] = set()
        self._recording: bool = False

        # 位置事件
        self._pos_event_lock = threading.Lock()
        self._pos_events: list[tuple[int, Callable[[float, float], bool], bool, Callable[[], None]]] = []
        self._next_event_id: int = 0

        # 角色銀幕座標換算（由 load_char_pos_config 載入）
        self._layers: list[dict] = []
        self._screen_x_params: dict = {}
        self._screen_y_params: dict = {}
        self._char_facing: str = 'right'
        self._char_y_direction: str = 'down'

    # ── 角色銀幕座標換算 ─────────────────────────────────────────

    def load_char_pos_config(self, config: dict):
        """
        從地圖 JSON 載入角色銀幕座標換算參數。

        config 預期包含：
            layers         : list[{id, map_y, map_x_min, map_x_max}]
            char_screen_x  : {facing_left/facing_right: {base_x, left_transition, right_transition}}
            char_screen_y  : {default_direction, up, down}
        """
        self._layers         = config.get('layers', [])
        self._screen_x_params = config.get('char_screen_x', {})
        self._screen_y_params = config.get('char_screen_y', {})
        self._char_y_direction = self._screen_y_params.get('default_direction', 'down')
        _logger.info(f'[MinimapTask] 載入角色銀幕座標換算參數：{len(self._layers)} 層')

    @property
    def char_facing(self) -> str:
        return self._char_facing

    @char_facing.setter
    def char_facing(self, value: str):
        self._char_facing = value

    @property
    def char_y_direction(self) -> str:
        return self._char_y_direction

    @char_y_direction.setter
    def char_y_direction(self, value: str):
        """設定垂直移動方向：'up'（往高層移動）或 'down'（往低層移動）。"""
        self._char_y_direction = value

    def _get_current_layer(self, map_y: float) -> dict | None:
        """依目前 map_y 找最近的層。"""
        if not self._layers:
            return None
        return min(self._layers, key=lambda l: abs(l['map_y'] - map_y))

    def get_current_layer(self) -> dict | None:
        """回傳目前 pos 對應的層設定（公開介面）。"""
        return self._get_current_layer(self.pos[1])

    @property
    def char_screen_x(self) -> int:
        """
        依目前 pos、char_facing 與地圖換算參數計算角色銀幕 X（像素）。
        尚未載入 config 時回傳 0。

        換算公式（三段式）：
          [map_x_min, left_transition)  → base_x 的線性成長
          [left_transition, right_transition] → 固定 base_x
          (right_transition, map_x_max]  → base_x + (screen_w - base_x) 的線性成長
        """
        if not self._screen_x_params or not self.game_window or not self.game_window.is_valid:
            return 0
        map_x, map_y = self.pos
        layer = self._get_current_layer(map_y)
        if layer is None:
            return 0
        x_min       = layer['map_x_min']
        x_max       = layer['map_x_max']
        params      = self._screen_x_params.get('facing_' + self._char_facing, {})
        base_x      = params.get('base_x', 0)
        left_trans  = params.get('left_transition', x_min)
        right_trans = params.get('right_transition', x_max)
        screen_w    = self.game_window.width

        if map_x < left_trans:
            denom = left_trans - x_min
            if denom <= 0:
                return 0
            return int(base_x * (map_x - x_min) / denom)
        elif map_x <= right_trans:
            return base_x
        else:
            denom = x_max - right_trans
            if denom <= 0:
                return base_x
            t = (map_x - right_trans) / denom
            return int(base_x + (screen_w - base_x) * t)

    @property
    def char_screen_y(self) -> int:
        """
        依 char_y_direction 回傳角色銀幕 Y（像素）。
        尚未載入 config 時回傳 0。
        """
        if not self._screen_y_params:
            return 0
        return self._screen_y_params.get(self._char_y_direction, 0)

    # ── 邊界設定 ─────────────────────────────────────────────────

    def set_bounds(self, rx0: float, ry0: float, rx1: float, ry1: float):
        """設定小地圖邊界（遊戲視窗比例座標，0.0～1.0）。"""
        self._rx0, self._ry0 = rx0, ry0
        self._rx1, self._ry1 = rx1, ry1
        _logger.info(f"[MinimapTask] 邊界已更新：({rx0:.4f}, {ry0:.4f}) → ({rx1:.4f}, {ry1:.4f})")

    def get_bounds(self) -> tuple[float, float, float, float]:
        return self._rx0, self._ry0, self._rx1, self._ry1

    def bounds_as_window_region(self) -> tuple[float, float, float, float] | None:
        """回傳視窗比例座標 (x, y, w, h)，供 DebugOverlay 繪製。"""
        if not self.game_window.is_valid:
            return None
        return (self._rx0, self._ry0,
                self._rx1 - self._rx0,
                self._ry1 - self._ry0)

    # ── 位置事件 ─────────────────────────────────────────────────

    def register_pos_event(self,
                           condition: Callable[[float, float], bool],
                           callback: Callable[[], None],
                           once: bool = True) -> int:
        """
        註冊位置事件。每次 pos 更新時若 condition(x, y) 為 True 即呼叫 callback。

        Args:
            condition: 接受 (x, y) 回傳 bool 的判斷函式，例如 lambda x, y: x >= 0.98
            callback:  條件成立時呼叫的函式（應輕量，例如 event.set()）
            once:      True 表示觸發一次後自動移除（預設）

        Returns:
            event_id，可傳給 unregister_pos_event() 提前取消
        """
        with self._pos_event_lock:
            eid = self._next_event_id
            self._next_event_id += 1
            self._pos_events.append((eid, condition, once, callback))
        return eid

    def unregister_pos_event(self, event_id: int):
        """提前取消已註冊的位置事件。"""
        with self._pos_event_lock:
            self._pos_events = [e for e in self._pos_events if e[0] != event_id]

    def _check_pos_events(self, x: float, y: float):
        """由 task 迴圈每幀呼叫，檢查並觸發已達成條件的事件。"""
        with self._pos_event_lock:
            remaining = []
            to_fire = []
            for eid, condition, once, callback in self._pos_events:
                if condition(x, y):
                    to_fire.append(callback)
                    if not once:
                        remaining.append((eid, condition, once, callback))
                else:
                    remaining.append((eid, condition, once, callback))
            self._pos_events = remaining
        for cb in to_fire:
            cb()

    # ── 黃點偵測 ─────────────────────────────────────────────────

    @staticmethod
    def find_dot(img: np.ndarray) -> tuple[float, float] | None:
        """
        在圖像中偵測黃點。
        回傳相對於圖像的比例座標 (x_ratio, y_ratio)（0.0～1.0）；找不到回傳 None。
        """
        if img.size == 0:
            return None

        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, _DOT_LOWER, _DOT_UPPER)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best, best_area = None, 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if _DOT_MIN_AREA <= area <= _DOT_MAX_AREA and area > best_area:
                best_area = area
                best = cnt

        if best is None:
            return None

        M = cv2.moments(best)
        if M['m00'] == 0:
            return None

        h, w = img.shape[:2]
        return round(M['m10'] / M['m00'] / w, 3), round(M['m01'] / M['m00'] / h, 3)

    # ── 地圖錄製 ─────────────────────────────────────────────────

    @property
    def recording(self) -> bool:
        return self._recording

    def start_recording(self):
        """清空舊資料並開始錄製。"""
        self._map_points.clear()
        self._map_point_set.clear()
        self._recording = True
        _logger.info("[MinimapTask] 地圖錄製開始")

    def stop_recording(self):
        """停止錄製並將資料序列化輸出為 JSON。"""
        if not self._recording:
            return
        self._recording = False
        _logger.info("[MinimapTask] 地圖錄製停止")
        self._save_map()

    def save_recording_as(self, name: str) -> 'MapData | None':
        """將目前錄製資料以指定名稱儲存為 MapData，不影響錄製狀態。"""
        if not self._map_points:
            _logger.warning("[MinimapTask] 無地圖資料，跳過存檔")
            return None
        climb_indices = self._detect_climb_indices(self._map_points)
        md = MapData(
            name=name,
            points=list(self._map_points),
            climb_indices=climb_indices,
            bounds=(self._rx0, self._ry0, self._rx1, self._ry1),
            record_decimals=_RECORD_DECIMALS,
            climb_x_tol=_CLIMB_X_TOL,
            climb_y_step=_CLIMB_Y_STEP,
            climb_min_run=_CLIMB_MIN_RUN,
        )
        md.save()
        return md

    def _record_point(self, pos: tuple[float, float]):
        if not self._recording:
            return
        key = (round(pos[0], _RECORD_DECIMALS), round(pos[1], _RECORD_DECIMALS))
        if key not in self._map_point_set:
            self._map_point_set.add(key)
            self._map_points.append(key)

    @staticmethod
    def _detect_climb_indices(points: list[tuple[float, float]]) -> set[int]:
        n = len(points)
        is_climb_step = [False] * n
        for i in range(n - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            if abs(x1 - x0) < _CLIMB_X_TOL and (y0 - y1) > _CLIMB_Y_STEP:
                is_climb_step[i] = True

        climb: set[int] = set()
        i = 0
        while i < n - 1:
            if is_climb_step[i]:
                run_start = i
                while i < n - 1 and is_climb_step[i]:
                    i += 1
                if (i - run_start + 1) >= _CLIMB_MIN_RUN:
                    for idx in range(run_start, i + 1):
                        climb.add(idx)
            else:
                i += 1
        return climb

    def _save_map(self):
        if not self._map_points:
            _logger.warning("[MinimapTask] 無地圖資料，跳過存檔")
            return

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        climb_indices = self._detect_climb_indices(self._map_points)

        map_data = MapData(
            name=f"map_{ts}",
            points=list(self._map_points),
            climb_indices=climb_indices,
            bounds=(self._rx0, self._ry0, self._rx1, self._ry1),
            record_decimals=_RECORD_DECIMALS,
            climb_x_tol=_CLIMB_X_TOL,
            climb_y_step=_CLIMB_Y_STEP,
            climb_min_run=_CLIMB_MIN_RUN,
        )
        map_data.save()

    # ── Task 主迴圈 ──────────────────────────────────────────────

    def task(self):
        _logger.info("MinimapTask starting")
        while True:
            frame = self.game_window.get_latest_frame()
            if frame is not None:
                fh, fw = frame.shape[:2]
                rx = int(fw * self._rx0)
                ry = int(fh * self._ry0)
                rw = int(fw * (self._rx1 - self._rx0))
                rh = int(fh * (self._ry1 - self._ry0))
                img = frame[ry:ry + rh, rx:rx + rw]
                if img.size > 0:
                    result = self.find_dot(img)
                    if result is not None:
                        self.pos = result
                        self._record_point(result)
                        self._check_pos_events(result[0], result[1])

            if self.wait_stop_event(SCAN_INTERVAL):
                break

        _logger.info("MinimapTask end")
