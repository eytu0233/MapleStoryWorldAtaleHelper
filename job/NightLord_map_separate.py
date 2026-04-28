import json
import os
import queue
import threading
import time

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from controller.ModelController import ModelController
from util.logger import MSLogger

_logger = MSLogger('NightLordMapSeparate')

_BUFF_INTERVAL        = 270   # 秒
_LEFT_X               = 0.46  # 左邊界
_RIGHT_X              = 0.86  # 右邊界
_X_TOL                = 0.02
_MAP_CONFIG           = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')
_MONSTER_MODEL        = os.path.join(os.path.dirname(__file__), '..', 'model', 'egg_dragon.pt')
_MONSTER_DETECT_NAMES = {'eggDragon', 'eggDragon01'}
_ATTACK_RANGE_PX          = 650   # 方向前方怪物偵測距離（視窗像素）
_ATTACK_RANGE_Y           = 200   # 垂直方向誤差容許值（像素，±）
_CONTINUOUS_ATTACK_LIMIT  = 20.0  # 秒：連續攻擊超過此時間後強制巡邏


# ── Buff ──────────────────────────────────────────────────────────

class _Buff(Command):
    def __init__(self, key: str):
        super().__init__(CommandType.CONDITION)
        self._key = key

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[{type(self).__name__}] 施放 key={self._key}')
        pyautogui.keyDown(self._key)
        interrupted = self.interrupt_event.wait(0.6)
        pyautogui.keyUp(self._key)
        if interrupted:
            _logger.info(f'[{type(self).__name__}] 被打斷')


class Buff1(_Buff):
    def __init__(self): super().__init__('1')

class Buff2(_Buff):
    def __init__(self): super().__init__('2')

class Buff3(_Buff):
    def __init__(self): super().__init__('3')


# ── Attack ────────────────────────────────────────────────────────


class AttackCommand(Command):
    """
    前方優先攻擊；前方無怪時後方有怪則轉向攻擊；
    完全無怪則立即觸發 MoveCommand 巡邏，自身不重入隊。
    MoveCommand 到達對面邊界後會重新排入 AttackCommand。
    """

    _queued:        'AttackCommand | None' = None
    _no_monster_streak: int                = 0
    _NO_MONSTER_THRESHOLD: int             = 10

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char: 'NightLord'):
        if cls._queued is not None:
            return
        obj = cls(q, char)
        cls._queued = obj
        q.put(obj)

    def __init__(self, q: queue.Queue, char: 'NightLord'):
        super().__init__(CommandType.CONDITION)
        self._queue            = q
        self._char             = char
        self._cancelled        = False
        self._attack_start_ts: float | None = None

    def release(self):
        self._cancelled = True

    def trigger_command(self):
        AttackCommand._queued = None
        if self._cancelled or self._char.stop_event.is_set():
            return
        self.interrupt_event.clear()

        facing      = self._char.minimap_task.char_facing or 'right'
        front_count = self._char._left_count if facing == 'left' else self._char._right_count

        if front_count > 0:
            AttackCommand._no_monster_streak = 0
            _logger.info(f'[AttackCommand] 前方攻擊 dir={facing} count={front_count}')
        else:
            AttackCommand._no_monster_streak += 1
            _logger.info(f'[AttackCommand] 無怪 streak={AttackCommand._no_monster_streak}/{AttackCommand._NO_MONSTER_THRESHOLD}')
            if AttackCommand._no_monster_streak < AttackCommand._NO_MONSTER_THRESHOLD:
                self.interrupt_event.wait(0.3)
                if not self._cancelled and not self._char.stop_event.is_set():
                    AttackCommand._queued = self
                    self._queue.put(self)
            else:
                AttackCommand._no_monster_streak = 0
                _logger.info(f'[AttackCommand] 連續 {AttackCommand._NO_MONSTER_THRESHOLD} 次無怪，觸發移動 dir={facing}')
                MoveCommand._try_enqueue(self._char.priority_command_queue, self._char, facing)
            return

        if self._attack_start_ts is None:
            self._attack_start_ts = time.time()

        pyautogui.keyDown('c')
        self.interrupt_event.wait(0.8)
        pyautogui.keyUp('c')

        if self.interrupt_event.is_set() or self._cancelled:
            return

        if time.time() - self._attack_start_ts >= _CONTINUOUS_ATTACK_LIMIT:
            _logger.info(f'[AttackCommand] 連續攻擊超過 {_CONTINUOUS_ATTACK_LIMIT}s，觸發巡邏 dir={facing}')
            MoveCommand._try_enqueue(self._char.priority_command_queue, self._char, facing)
            return

        if not self._char.stop_event.is_set():
            AttackCommand._queued = self
            self._queue.put(self)


# ── Move ──────────────────────────────────────────────────────────

class MoveToNearestBoundaryCommand(Command):
    """啟動時移動到最近的左/右邊界，到達後轉向，由 AttackCommand 接手後續邏輯。"""

    def __init__(self, char, q):
        super().__init__(CommandType.CONDITION)
        self._char  = char
        self._queue = q

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        cur_x = self._char.map_x
        if abs(cur_x - _LEFT_X) <= abs(cur_x - _RIGHT_X):
            target_x = _LEFT_X
            next_dir  = 'right'
        else:
            target_x = _RIGHT_X
            next_dir  = 'left'

        direction = 'right' if cur_x < target_x else 'left'
        self._char.minimap_task.char_facing = direction

        _logger.info(f'[MoveToNearest] cur={cur_x:.2f} →{direction}({target_x:.2f})')

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - target_x) <= _X_TOL,
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
            _logger.warning('[MoveToNearest] 未到達邊界（超時），重試')
            self._queue.put(MoveToNearestBoundaryCommand(self._char, self._queue))
            return

        self._char.minimap_task.char_facing = next_dir
        pyautogui.keyDown(next_dir)
        self.interrupt_event.wait(0.5)
        pyautogui.keyUp(next_dir)

        _logger.info(f'[MoveToNearest] 到達 x={self._char.map_x:.2f}，轉向→{next_dir}')


class MoveCommand(Command):
    """巡邏：移動到對面邊界，到達後轉向並排入 AttackCommand 繼續攻擊。"""

    _queued: 'MoveCommand | None' = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char: 'NightLord', direction: str):
        if cls._queued is not None:
            return
        obj = cls(q, char, direction)
        cls._queued = obj
        q.put(obj)

    def __init__(self, q: queue.Queue, char: 'NightLord', direction: str):
        super().__init__(CommandType.CONDITION)
        self._queue     = q
        self._char      = char
        self._direction = direction

    def release(self): pass

    def trigger_command(self):
        MoveCommand._queued = None
        try:
            self.interrupt_event.clear()
            target_x = _LEFT_X if self._direction == 'left' else _RIGHT_X
            next_dir  = 'right' if self._direction == 'left' else 'left'

            _logger.info(f'[MoveCommand] →{self._direction} target={target_x:.2f}')
            self._char.minimap_task.char_facing = self._direction

            reached = [False]

            def _on_reached():
                reached[0] = True
                self.interrupt_command()

            eid = self._char.minimap_task.register_pos_event(
                condition=lambda x, y: abs(x - target_x) <= _X_TOL,
                callback=_on_reached,
                once=True,
            )
            pyautogui.keyDown(self._direction)
            self.interrupt_event.wait(15)
            pyautogui.keyUp(self._direction)
            self._char.minimap_task.unregister_pos_event(eid)

            if self._char.stop_event.is_set():
                return

            if not reached[0]:
                _logger.warning('[MoveCommand] 被打斷或超時，重試')
                MoveCommand._try_enqueue(self._queue, self._char, self._direction)
                return

            self._char.minimap_task.char_facing = next_dir
            pyautogui.keyDown(next_dir)
            self.interrupt_event.wait(0.5)
            pyautogui.keyUp(next_dir)

            _logger.info(f'[MoveCommand] 到達 x={self._char.map_x:.2f}，轉向→{next_dir}，排入攻擊')
            AttackCommand._try_enqueue(self._char.command_queue, self._char)
        finally:
            MoveCommand._queued = None


# ── NightLord ─────────────────────────────────────────────────────

class NightLord(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='NightLord')
        self._monster_monitor: ModelController | None = None
        self._left_count:      int                    = 0
        self._right_count:     int                    = 0

    def _on_monster_detected(self, detections: list[dict]):
        filtered = [d for d in detections if d['name'] in _MONSTER_DETECT_NAMES]
        cx = self.screen_x
        cy = self.screen_y
        left_count = right_count = 0
        if cx != 0:
            for d in filtered:
                x1, y1, x2, y2 = d['bbox']
                mcx = (x1 + x2) / 2
                mcy = (y1 + y2) / 2
                if abs(mcy - cy) > _ATTACK_RANGE_Y:
                    continue
                if cx - _ATTACK_RANGE_PX <= mcx < cx:
                    left_count += 1
                elif cx < mcx <= cx + _ATTACK_RANGE_PX:
                    right_count += 1
        self._left_count  = left_count
        self._right_count = right_count

    def _load_minimap_bounds(self):
        try:
            with open(_MAP_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data['minimap_bounds']
            self.minimap_task.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
            self.minimap_task.load_char_pos_config(data)
            _logger.info(f'[NightLord] 小地圖邊界已載入: {mm}')
        except Exception as e:
            _logger.warning(f'[NightLord] 載入小地圖邊界失敗: {e}')

    def _enqueue_buffs(self):
        for cmd in (Buff1(), Buff2(), Buff3()):
            self.priority_command_queue.put(cmd)
        self._buff_timer = threading.Timer(_BUFF_INTERVAL, self._enqueue_buffs)
        self._buff_timer.daemon = True
        self._buff_timer.start()

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._left_count                  = 0
        self._right_count                 = 0
        AttackCommand._queued             = None
        AttackCommand._no_monster_streak  = 0
        MoveCommand._queued               = None
        super().stop()
        for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break
        _logger.info('[NightLord] 已停止')

    def task_prepare(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()

        self._load_minimap_bounds()

        AttackCommand._queued            = None
        AttackCommand._no_monster_streak = 0
        MoveCommand._queued              = None
        self.minimap_task.char_facing      = 'right'
        self.minimap_task.char_y_direction = 'down'

        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._left_count  = 0
        self._right_count = 0
        self._monster_monitor = ModelController(
            self.game_window, _MONSTER_MODEL, self._on_monster_detected
        )
        self._monster_monitor.start()

        self._enqueue_buffs()

        self.priority_command_queue.put(MoveToNearestBoundaryCommand(self, self.priority_command_queue))
        AttackCommand._try_enqueue(self.command_queue, self)
