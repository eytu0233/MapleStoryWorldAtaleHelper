import json
import os
import threading

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from util.logger import MSLogger

_logger = MSLogger('NightLord')

_BUFF_INTERVAL = 270   # 秒
_LEFT_X        = 0.48
_RIGHT_X       = 0.85
_X_TOL         = 0.02
_PATROL_DELAY  = 10    # 秒（到達邊界後等待再移動）
_MAP_CONFIG    = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')


# ── Buff ──────────────────────────────────────────────────────────

class _Buff(Command):
    def __init__(self, key: str):
        super().__init__(CommandType.CONDITION)
        self._key = key

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[PRIORITY][{type(self).__name__}] 施放 key={self._key}')
        pyautogui.keyDown(self._key)
        interrupted = self.interrupt_event.wait(0.6)
        pyautogui.keyUp(self._key)
        if interrupted:
            _logger.info(f'[PRIORITY][{type(self).__name__}] 被打斷')


class Buff1(_Buff):
    def __init__(self): super().__init__('1')

class Buff2(_Buff):
    def __init__(self): super().__init__('2')

class Buff3(_Buff):
    def __init__(self): super().__init__('3')


# ── Attack ────────────────────────────────────────────────────────

class AttackCommand(Command):
    """按著 c 10 秒，完成後自動重新入隊。"""

    def __init__(self, char, q):
        super().__init__(CommandType.CONDITION)
        self._char      = char
        self._queue     = q
        self._cancelled = False

    def release(self):
        self._cancelled = True

    def trigger_command(self):
        if self._cancelled:
            return
        self.interrupt_event.clear()
        _logger.info('[AttackCommand] 攻擊開始 3s')
        pyautogui.keyDown('c')
        self.interrupt_event.wait(3)
        pyautogui.keyUp('c')
        if self.interrupt_event.is_set():
            _logger.info('[AttackCommand] 被打斷')
        else:
            _logger.info('[AttackCommand] 攻擊結束')
        if not self._cancelled and not self._char.stop_event.is_set():
            self._queue.put(ConditionalAttackCommand(self._char, self._queue))


class DrainAttackCommand(Command):
    """按 a 1 秒（吸血攻擊），完成後排入 ConditionalAttackCommand。"""

    def __init__(self, char, q):
        super().__init__(CommandType.CONDITION)
        self._char  = char
        self._queue = q

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info('[DrainAttackCommand] 吸血攻擊 1s')
        pyautogui.keyDown('a')
        interrupted = self.interrupt_event.wait(1)
        pyautogui.keyUp('a')
        if interrupted:
            _logger.info('[DrainAttackCommand] 被打斷')
        if not self._char.stop_event.is_set():
            self._queue.put(ConditionalAttackCommand(self._char, self._queue))


class ConditionalAttackCommand(Command):
    """判斷 HP：< 100% 先排入吸血攻擊，否則直接排入一般攻擊。"""

    def __init__(self, char, q):
        super().__init__(CommandType.CONDITION)
        self._char  = char
        self._queue = q

    def release(self): pass

    def trigger_command(self):
        if self._char.stop_event.is_set():
            return
        hp = self._char.hp
        if hp < 80.0:
            _logger.info(f'[ConditionalAttack] HP={hp:.1f}% < 80%，先吸血')
            self._queue.put(DrainAttackCommand(self._char, self._queue))
        else:
            _logger.info(f'[ConditionalAttack] HP={hp:.1f}% 滿血，一般攻擊')
            self._queue.put(AttackCommand(self._char, self._queue))


# ── Move ──────────────────────────────────────────────────────────

class MoveToNearestBoundaryCommand(Command):
    """移動到最近的左/右邊界，到達後 30 秒排入 MoveCommand 開始巡邏。"""

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
            _logger.warning(f'[MoveToNearest] 未到達邊界（超時），重試')
            self._queue.put(MoveToNearestBoundaryCommand(self._char, self._queue))
            return

        if direction != next_dir:
            pyautogui.keyDown(next_dir)
            self.interrupt_event.wait(0.5)
            pyautogui.keyUp(next_dir)

        _logger.info(f'[MoveToNearest] 到達 x={self._char.map_x:.2f}，轉向→{next_dir}，{_PATROL_DELAY}s 後開始巡邏')
        MoveCommand._schedule(self._queue, self._char, next_dir)


class MoveCommand(Command):
    """巡邏：移動到對面邊界，到達後 _PATROL_DELAY 秒轉向繼續。"""

    _queued:        'MoveCommand | None'    = None
    _pending_timer: 'threading.Timer | None' = None

    @classmethod
    def _try_enqueue(cls, q, char, direction: str):
        if cls._queued is not None:
            return
        obj = cls(char, q, direction)
        cls._queued = obj
        q.put(obj)

    @classmethod
    def _schedule(cls, q, char, direction: str):
        if cls._pending_timer is not None:
            cls._pending_timer.cancel()
        t = threading.Timer(_PATROL_DELAY, cls._try_enqueue, args=(q, char, direction))
        t.daemon = True
        t.start()
        cls._pending_timer = t

    @classmethod
    def cancel_pending(cls):
        if cls._pending_timer is not None:
            cls._pending_timer.cancel()
            cls._pending_timer = None
        cls._queued = None

    def __init__(self, char, q, direction: str):
        super().__init__(CommandType.CONDITION)
        self._char      = char
        self._queue     = q
        self._direction = direction

    def release(self): pass

    def trigger_command(self):
        MoveCommand._queued = None
        MoveCommand._pending_timer = None
        try:
            self.interrupt_event.clear()
            target_x = _LEFT_X if self._direction == 'left' else _RIGHT_X
            next_dir  = 'right' if self._direction == 'left' else 'left'

            _logger.info(f'[MoveCommand] →{self._direction} target={target_x:.2f}')

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

            pyautogui.keyDown(next_dir)
            self.interrupt_event.wait(0.5)
            pyautogui.keyUp(next_dir)

            _logger.info(f'[MoveCommand] 到達 x={self._char.map_x:.2f} 轉向→{next_dir}，{_PATROL_DELAY}s 後繼續')
            MoveCommand._schedule(self._queue, self._char, next_dir)
        finally:
            MoveCommand._queued = None


# ── NightLord ─────────────────────────────────────────────────────

class NightLord(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='NightLord')

    def _load_minimap_bounds(self):
        try:
            with open(_MAP_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data['minimap_bounds']
            self.minimap_task.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
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
        MoveCommand.cancel_pending()
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
        self._enqueue_buffs()
        self.priority_command_queue.put(MoveToNearestBoundaryCommand(self, self.priority_command_queue))

        self.command_queue.put(ConditionalAttackCommand(self, self.command_queue))
