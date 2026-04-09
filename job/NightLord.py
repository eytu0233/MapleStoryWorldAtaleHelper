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
_PATROL_DELAY  = 30    # 秒（到達邊界後等待再移動）
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
        _logger.info('[AttackCommand] 攻擊開始 10s')
        pyautogui.keyDown('c')
        self.interrupt_event.wait(10)
        pyautogui.keyUp('c')
        if self.interrupt_event.is_set():
            _logger.info('[AttackCommand] 被打斷')
        else:
            _logger.info('[AttackCommand] 攻擊結束')
        if not self._cancelled and not self._char.stop_event.is_set():
            self._queue.put(self)


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
            direction = 'left'
            next_dir  = 'right'
        else:
            target_x = _RIGHT_X
            direction = 'right'
            next_dir  = 'left'

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

        _logger.info(f'[MoveToNearest] 到達 x={self._char.map_x:.2f}，{_PATROL_DELAY}s 後開始巡邏')
        t = threading.Timer(_PATROL_DELAY, self._queue.put,
                            args=(MoveCommand(self._char, self._queue, next_dir),))
        t.daemon = True
        t.start()


class MoveCommand(Command):
    """巡邏：移動到對面邊界，到達後 30 秒轉向繼續。"""

    def __init__(self, char, q, direction: str):
        super().__init__(CommandType.CONDITION)
        self._char      = char
        self._queue     = q
        self._direction = direction

    def release(self): pass

    def trigger_command(self):
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

        _logger.info(f'[MoveCommand] 到達 x={self._char.map_x:.2f} 轉向→{next_dir}，{_PATROL_DELAY}s 後繼續')
        t = threading.Timer(_PATROL_DELAY, self._queue.put,
                            args=(MoveCommand(self._char, self._queue, next_dir),))
        t.daemon = True
        t.start()


# ── NightLord ─────────────────────────────────────────────────────

class NightLord(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='NightLord')
        self._attack_cmd: AttackCommand | None = None

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
        for cmd in (Buff1(), Buff2()):
            self.priority_command_queue.put(cmd)
        self._buff_timer = threading.Timer(_BUFF_INTERVAL, self._enqueue_buffs)
        self._buff_timer.daemon = True
        self._buff_timer.start()

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        if self._attack_cmd is not None:
            self._attack_cmd.release()
            self._attack_cmd = None
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
        if self._attack_cmd is not None:
            self._attack_cmd.release()
            self._attack_cmd = None

        self._load_minimap_bounds()
        self._enqueue_buffs()
        self.priority_command_queue.put(MoveToNearestBoundaryCommand(self, self.command_queue))

        self._attack_cmd = AttackCommand(self, self.command_queue)
        self.command_queue.put(self._attack_cmd)
