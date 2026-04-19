import json
import os
import queue
import threading

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from controller.ModelController import ModelController
from util.logger import MSLogger

_logger = MSLogger('BowmasterMapSeparate')

_BUFF1_INTERVAL       = 120    # 秒
_BUFF2_INTERVAL       = 60     # 秒
_START_X              = 0.85   # 初始 / 回歸位置
_LEFTMOST_X           = 0.70   # 向左追怪時的最左邊界
_SWEEP_X              = 0.58   # 定期巡邏最左點
_X_TOL                = 0.02
_SWEEP_INTERVAL       = 90     # 秒：定期掃地圖間隔
_CHASE_DURATION       = 0.5    # 秒：向左追怪移動時間
_MAP_CONFIG           = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')
_MONSTER_MODEL        = os.path.join(os.path.dirname(__file__), '..', 'model', 'egg_dragon.pt')
_MONSTER_DETECT_NAMES = {'eggDragon', 'eggDragon01'}
_ATTACK_RANGE_PX      = 850    # 方向前方怪物偵測距離（視窗像素）
_ATTACK_RANGE_Y       = 200    # 垂直方向誤差容許值（像素，±）


# ── Buff ──────────────────────────────────────────────────────────

class _Buff(Command):
    def __init__(self, key: str, hold: float = 1.0):
        super().__init__(CommandType.CONDITION)
        self._key  = key
        self._hold = hold

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[PRIORITY][{type(self).__name__}] 施放 key={self._key}')
        pyautogui.keyDown(self._key)
        interrupted = self.interrupt_event.wait(self._hold)
        pyautogui.keyUp(self._key)
        if interrupted:
            _logger.info(f'[PRIORITY][{type(self).__name__}] 被打斷')


class Buff1(_Buff):
    def __init__(self): super().__init__('1', 1.0)

class Buff2(_Buff):
    def __init__(self): super().__init__('2', 1.0)


# ── Attack ────────────────────────────────────────────────────────

class AttackCommand(Command):
    """
    向左攻擊。攻擊後若左側攻擊範圍內仍有怪物則繼續；否則結束等待下次偵測觸發。
    """

    _queued:     'AttackCommand | None' = None
    _is_running: bool                   = False

    @classmethod
    def _try_enqueue(cls, pq: queue.Queue, char: 'Bowmaster') -> bool:
        if cls._queued is not None or cls._is_running:
            return False
        obj = cls(pq, char)
        cls._queued = obj
        pq.put(obj)
        return True

    def __init__(self, pq: queue.Queue, char: 'Bowmaster'):
        super().__init__(CommandType.CONDITION)
        self._queue     = pq
        self._char      = char
        self._cancelled = False

    def release(self):
        self._cancelled = True

    def _has_monster_in_range(self) -> bool:
        cx = self._char.screen_x
        cy = self._char.screen_y
        if cx == 0:
            return False
        for d in self._char._monster_detections:
            x1, y1, x2, y2 = d['bbox']
            mcx = (x1 + x2) / 2
            mcy = (y1 + y2) / 2
            if abs(mcy - cy) > _ATTACK_RANGE_Y:
                continue
            if cx - _ATTACK_RANGE_PX <= mcx < cx:
                return True
        return False

    def trigger_command(self):
        AttackCommand._queued     = None
        AttackCommand._is_running = True
        try:
            if self._cancelled:
                return
            self.interrupt_event.clear()

            self._char.minimap_task.char_facing = 'left'
            pyautogui.keyDown('left')
            pyautogui.keyUp('left')

            _logger.info('[PRIORITY][AttackCommand] 攻擊 dir=left key=z')
            pyautogui.keyDown('z')
            self.interrupt_event.wait(1.0)
            pyautogui.keyUp('z')

            if self.interrupt_event.is_set():
                _logger.info('[PRIORITY][AttackCommand] 被中斷')
                return

            if not self._cancelled and self._has_monster_in_range():
                _logger.info('[PRIORITY][AttackCommand] 仍有怪物，繼續攻擊')
                AttackCommand._queued = self
                self._queue.put(self)
        finally:
            AttackCommand._is_running = False


# ── Chase ─────────────────────────────────────────────────────────

class MoveLeftChaseCommand(Command):
    """
    範圍外左側有怪物時，向左移動 _CHASE_DURATION 秒後重新偵測。
    僅在 map_x > _LEFTMOST_X 且無攻擊進行中時入隊。
    """

    _queued: 'MoveLeftChaseCommand | None' = None

    @classmethod
    def _try_enqueue(cls, pq: queue.Queue, char: 'Bowmaster'):
        if cls._queued is not None:
            return
        if AttackCommand._queued is not None or AttackCommand._is_running:
            return
        if char.map_x <= _LEFTMOST_X:
            return
        obj = cls(pq, char)
        cls._queued = obj
        pq.put(obj)

    def __init__(self, pq: queue.Queue, char: 'Bowmaster'):
        super().__init__(CommandType.CONDITION)
        self._queue = pq
        self._char  = char

    def release(self): pass

    def trigger_command(self):
        MoveLeftChaseCommand._queued = None
        try:
            if self._char.map_x <= _LEFTMOST_X:
                return
            self.interrupt_event.clear()
            _logger.info(f'[PRIORITY][MoveLeftChaseCommand] 向左追怪 {_CHASE_DURATION}s')
            self._char.minimap_task.char_facing = 'left'
            pyautogui.keyDown('left')
            self.interrupt_event.wait(_CHASE_DURATION)
            pyautogui.keyUp('left')
        finally:
            MoveLeftChaseCommand._queued = None


# ── Move ──────────────────────────────────────────────────────────

class MoveToStartCommand(Command):
    """移動到初始位置 _START_X（0.85）。"""

    _queued: 'MoveToStartCommand | None' = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char: 'Bowmaster'):
        if cls._queued is not None:
            return
        obj = cls(q, char)
        cls._queued = obj
        q.put(obj)

    def __init__(self, q: queue.Queue, char: 'Bowmaster'):
        super().__init__(CommandType.CONDITION)
        self._queue = q
        self._char  = char

    def release(self): pass

    def trigger_command(self):
        MoveToStartCommand._queued = None
        try:
            self.interrupt_event.clear()
            cur_x = self._char.map_x
            if abs(cur_x - _START_X) <= _X_TOL:
                _logger.info('[MoveToStartCommand] 已在初始位置')
                return

            direction = 'right' if cur_x < _START_X else 'left'
            _logger.info(f'[MoveToStartCommand] →{direction} cur={cur_x:.2f}')
            self._char.minimap_task.char_facing = direction

            reached = [False]

            def _on_reached():
                reached[0] = True
                self.interrupt_command()

            eid = self._char.minimap_task.register_pos_event(
                condition=lambda x, y: abs(x - _START_X) <= _X_TOL,
                callback=_on_reached,
                once=True,
            )
            pyautogui.keyDown(direction)
            self.interrupt_event.wait(15)
            pyautogui.keyUp(direction)
            self._char.minimap_task.unregister_pos_event(eid)

            if self._char.stop_event.is_set():
                return

            if not reached[0]:
                _logger.warning('[MoveToStartCommand] 超時，重試')
                MoveToStartCommand._try_enqueue(self._queue, self._char)
                return

            _logger.info(f'[MoveToStartCommand] 已到達 x={self._char.map_x:.2f}')
        finally:
            MoveToStartCommand._queued = None


class SweepCommand(Command):
    """每 _SWEEP_INTERVAL 秒觸發：移動到 _SWEEP_X（0.58）後回到 _START_X（0.85）。"""

    _queued: 'SweepCommand | None' = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char: 'Bowmaster'):
        if cls._queued is not None:
            return
        obj = cls(q, char)
        cls._queued = obj
        q.put(obj)

    def __init__(self, q: queue.Queue, char: 'Bowmaster'):
        super().__init__(CommandType.CONDITION)
        self._queue = q
        self._char  = char

    def release(self): pass

    def trigger_command(self):
        SweepCommand._queued = None
        try:
            self.interrupt_event.clear()
            _logger.info(f'[SweepCommand] 向左掃至 x={_SWEEP_X}')
            self._char.minimap_task.char_facing = 'left'

            reached = [False]

            def _on_reached():
                reached[0] = True
                self.interrupt_command()

            eid = self._char.minimap_task.register_pos_event(
                condition=lambda x, y: x <= _SWEEP_X + _X_TOL,
                callback=_on_reached,
                once=True,
            )
            pyautogui.keyDown('left')
            self.interrupt_event.wait(15)
            pyautogui.keyUp('left')
            self._char.minimap_task.unregister_pos_event(eid)

            if self._char.stop_event.is_set():
                return

            _logger.info(f'[SweepCommand] 到達 x={self._char.map_x:.2f}，回到初始位置')
            MoveToStartCommand._try_enqueue(self._queue, self._char)
        finally:
            SweepCommand._queued = None


# ── Bowmaster ─────────────────────────────────────────────────────

class Bowmaster(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='Bowmaster')
        self._monster_monitor:    ModelController | None = None
        self._monster_detections: list[dict]             = []

    # ── ModelController callback ───────────────────────────────────

    def _on_monster_detected(self, detections: list[dict]):
        filtered = [d for d in detections if d['name'] in _MONSTER_DETECT_NAMES]
        self._monster_detections = filtered

        cx = self.screen_x
        cy = self.screen_y
        if cx == 0:
            return

        in_range     = []
        out_of_range = []

        for d in filtered:
            x1, y1, x2, y2 = d['bbox']
            mcx = (x1 + x2) / 2
            mcy = (y1 + y2) / 2
            if abs(mcy - cy) > _ATTACK_RANGE_Y:
                continue
            if mcx < cx:  # 左側怪物
                if cx - mcx <= _ATTACK_RANGE_PX:
                    in_range.append(d)
                else:
                    out_of_range.append(d)

        if in_range:
            if AttackCommand._try_enqueue(self.priority_command_queue, self):
                _logger.info(f'[_on_monster_detected] 範圍內 {len(in_range)} 隻，觸發攻擊')
        elif out_of_range and self.map_x > _LEFTMOST_X:
            MoveLeftChaseCommand._try_enqueue(self.priority_command_queue, self)
            _logger.info(f'[_on_monster_detected] 範圍外左側 {len(out_of_range)} 隻，向左追怪')

    # ── 初始化 ────────────────────────────────────────────────────

    def _load_minimap_bounds(self):
        try:
            with open(_MAP_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data['minimap_bounds']
            self.minimap_task.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
            self.minimap_task.load_char_pos_config(data)
            _logger.info(f'[Bowmaster] 小地圖邊界已載入: {mm}')
        except Exception as e:
            _logger.warning(f'[Bowmaster] 載入小地圖邊界失敗: {e}')

    def _enqueue_buff1(self):
        for _ in range(2):
            self.priority_command_queue.put(Buff1())
        self._buff1_timer = threading.Timer(_BUFF1_INTERVAL, self._enqueue_buff1)
        self._buff1_timer.daemon = True
        self._buff1_timer.start()

    def _enqueue_buff2(self):
        self.priority_command_queue.put(Buff2())
        self._buff2_timer = threading.Timer(_BUFF2_INTERVAL, self._enqueue_buff2)
        self._buff2_timer.daemon = True
        self._buff2_timer.start()

    def _enqueue_sweep(self):
        if self.stop_event.is_set():
            return
        _logger.info(f'[Bowmaster] 定期掃地圖觸發')
        SweepCommand._try_enqueue(self.command_queue, self)
        self._sweep_timer = threading.Timer(_SWEEP_INTERVAL, self._enqueue_sweep)
        self._sweep_timer.daemon = True
        self._sweep_timer.start()

    # ── 生命週期 ──────────────────────────────────────────────────

    def stop(self):
        for attr in ('_buff1_timer', '_buff2_timer', '_sweep_timer'):
            if hasattr(self, attr):
                getattr(self, attr).cancel()
        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._monster_detections      = []
        AttackCommand._queued         = None
        AttackCommand._is_running     = False
        MoveLeftChaseCommand._queued  = None
        MoveToStartCommand._queued    = None
        SweepCommand._queued          = None
        super().stop()
        for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break
        _logger.info('[Bowmaster] 已停止')

    def task_prepare(self):
        for attr in ('_buff1_timer', '_buff2_timer', '_sweep_timer'):
            if hasattr(self, attr):
                getattr(self, attr).cancel()

        self._load_minimap_bounds()

        AttackCommand._queued         = None
        AttackCommand._is_running     = False
        MoveLeftChaseCommand._queued  = None
        MoveToStartCommand._queued    = None
        SweepCommand._queued          = None
        self.minimap_task.char_facing      = 'left'
        self.minimap_task.char_y_direction = 'down'

        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._monster_detections = []
        self._monster_monitor = ModelController(
            self.game_window, _MONSTER_MODEL, self._on_monster_detected
        )
        self._monster_monitor.start()

        self._enqueue_buff1()
        self._enqueue_buff2()

        # 90 秒後開始定期掃地圖
        self._sweep_timer = threading.Timer(_SWEEP_INTERVAL, self._enqueue_sweep)
        self._sweep_timer.daemon = True
        self._sweep_timer.start()

        # 移動到初始位置後開始向左搜尋怪物
        MoveToStartCommand._try_enqueue(self.command_queue, self)
