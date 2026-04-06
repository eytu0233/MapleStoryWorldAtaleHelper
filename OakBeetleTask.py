import json
import time

from controller.GameCharacter import GameCharacter
from util.logger import MSLogger

_logger = MSLogger('OakBeetleTask')

_CONFIG_PATH = 'OakBeetle.json'


class OakBeetleTask(GameCharacter):
    def __init__(self):
        super().__init__(name='OakBeetle')
        # 以下屬性由 _load_config() 填入，task() 每次啟動時重新載入
        self._layers:          list  = []
        self._attack_interval: float = 1.2
        self._aux_interval:    float = 270
        self._aux_hold:        float = 0.6
        self._move_poll:       float = 0.1
        self._move_poll_near:  float = 0.03
        self._near_threshold:  float = 0.05
        self._y_detect_max:    float = 0.15
        self._last_attack:     float = 0.0

    # ── 設定載入 ─────────────────────────────────────────────────

    def _load_config(self):
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        t = cfg.get('timing', {})
        self._attack_interval = t.get('attack_interval', 1.2)
        self._aux_interval    = t.get('aux_interval',    270)
        self._aux_hold        = t.get('aux_hold',        0.6)
        self._move_poll       = t.get('move_poll',       0.1)
        self._move_poll_near  = t.get('move_poll_near',  0.03)
        self._near_threshold  = t.get('near_threshold',  0.05)
        self._y_detect_max    = t.get('y_detect_max',    0.15)
        # 依 y 值由小到大排序（最上層優先），方便 _detect_layer 最近鄰搜尋
        self._layers = sorted(cfg.get('layers', []), key=lambda l: l['y'])
        _logger.info(f"[OakBeetleTask] 設定載入完成，共 {len(self._layers)} 層")

    # ── 抽象方法實作 ──────────────────────────────────────────────

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return self._hold_key('z', 1.0)

    # ── 內部輔助 ─────────────────────────────────────────────────

    def _cast_aux(self) -> bool:
        """釋放輔助技能 1、2。回傳 True 表示收到停止訊號。"""
        for key in ('1', '2'):
            if self._hold_key(key, self._aux_hold):
                return True
        return False

    def _detect_layer(self) -> dict | None:
        """以最近鄰方式找出目前所在層；超出 y_detect_max 則回傳 None（過渡中）。"""
        y = self.map_y
        best, best_dist = None, float('inf')
        for layer in self._layers:
            d = abs(y - layer['y'])
            if d < best_dist:
                best_dist, best = d, layer
        return best if best_dist <= self._y_detect_max else None

    def _walk_to_x(self, target_x: float) -> bool:
        """
        向 target_x 移動，途中若攻擊冷卻到期則插入攻擊。
        回傳 True 表示收到停止訊號。
        """
        while True:
            x = self.map_x
            if abs(x - target_x) < self._near_threshold:
                break
            direction = 'right' if target_x > x else 'left'
            if time.time() - self._last_attack >= self._attack_interval:
                if self._hold_key('z', 0.5):
                    return True
                self._last_attack = time.time()
            else:
                near = abs(x - target_x) < self._near_threshold * 2
                poll = self._move_poll_near if near else self._move_poll
                if self._hold_key(direction, poll):
                    return True
        return False

    # ── 主 Task ──────────────────────────────────────────────────

    def task(self):
        _logger.info("OakBeetleTask starting")
        self._load_config()

        if self._cast_aux():
            _logger.info("OakBeetleTask end")
            return

        self._last_attack = time.time()
        last_aux = time.time()

        while True:
            # ── 輔助技能計時 ──────────────────────────────────────
            if time.time() - last_aux >= self._aux_interval:
                if self._cast_aux():
                    break
                last_aux = time.time()
                self._last_attack = time.time()
                continue

            # ── 偵測當前層 ────────────────────────────────────────
            layer = self._detect_layer()
            if layer is None:
                # 正在爬升／下跳的過渡期，稍候再偵測
                if self.wait_stop_event(0.1):
                    break
                continue

            climb_points = layer.get('climb_points', [])
            name = layer.get('name', f"id={layer['id']}")

            if not climb_points:
                # ── 頂層：左右巡邏後下跳 ──────────────────────────
                x_ranges = layer.get('x_ranges', [[0.0, 1.0]])
                x_min = x_ranges[0][0]
                x_max = x_ranges[-1][1]
                _logger.info(f"[OakBeetleTask] {name}，巡邏 x={x_min:.2f}~{x_max:.2f}")
                if self._walk_to_x(x_max):
                    break
                if self._walk_to_x(x_min):
                    break
                _logger.info(f"[OakBeetleTask] {name} 巡邏完，下跳")
                if self.move_down():
                    break
                if self.wait_stop_event(0.8):
                    break
            else:
                # ── 非頂層：走向最近爬升點後往上爬 ──────────────────
                nearest_cp = min(climb_points, key=lambda cp: abs(cp - self.map_x))
                _logger.info(f"[OakBeetleTask] {name}，爬升點 x={nearest_cp:.2f}")
                if self._walk_to_x(nearest_cp):
                    break
                _logger.info(f"[OakBeetleTask] {name}，開始爬升")
                if self.move_up():
                    break
                if self.wait_stop_event(0.3):
                    break

        _logger.info("OakBeetleTask end")
