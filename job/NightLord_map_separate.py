import json
import os
import queue
import threading

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from controller.ModelController import ModelController
from util.logger import MSLogger

_logger = MSLogger('NightLordMapSeparate')

_BUFF_INTERVAL          = 270   # 秒
_LEFT_X                 = 0.46  # 左邊界
_CENTER_X               = 0.63  # 中間觀察點
_RIGHT_X                = 0.80  # 右邊界
_X_TOL                  = 0.02
_MAP_CONFIG             = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')
_MONSTER_MODEL          = os.path.join(os.path.dirname(__file__), '..', 'model', 'egg_dragon.pt')
_MONSTER_DETECT_NAMES   = {'eggDragon', 'eggDragon01'}
_ATTACK_RANGE_PX        = 600   # 方向前方怪物偵測距離（視窗像素）
_ATTACK_RANGE_Y         = 200   # 垂直方向誤差容許值（像素，±）
_MULTI_ATTACK_THRESHOLD = 2     # 怪物數量 >= 此值時改用多體攻擊（z 鍵）
_NO_MONSTER_TIMEOUT     = 3.0   # 秒：優先方向無怪後移往對應邊界
_FORCE_MOVE_INTERVAL    = 60    # 秒：強制移往邊界（不論有無怪）


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
    """
    攻擊指令。方向由中間點決定後鎖定，不在此處更改。
    每次 0.4 秒攻擊後自我重入隊，直到被外部打斷為止。
    """

    _queued:     'AttackCommand | None' = None
    _is_running: bool                   = False

    @classmethod
    def _try_enqueue(cls, priority_queue: queue.Queue,
                     char: 'NightLord', direction: str, attack_key: str):
        if cls._queued is not None or cls._is_running:
            return False
        obj = cls(priority_queue, char, direction, attack_key)
        cls._queued = obj
        priority_queue.put(obj)
        return True

    def __init__(self, priority_queue: queue.Queue, char: 'NightLord',
                 direction: str, attack_key: str):
        super().__init__(CommandType.CONDITION)
        self._queue      = priority_queue
        self._char       = char
        self._direction  = direction
        self._attack_key = attack_key
        self._cancelled  = False

    def release(self):
        self._cancelled = True

    def _decide_attack_key(self) -> str:
        cx = self._char.screen_x
        cy = self._char.screen_y
        if cx == 0:
            return self._attack_key
        total = 0
        for d in self._char._monster_detections:
            x1, y1, x2, y2 = d['bbox']
            mcx = (x1 + x2) / 2
            mcy = (y1 + y2) / 2
            if abs(mcy - cy) <= _ATTACK_RANGE_Y:
                if cx - _ATTACK_RANGE_PX <= mcx <= cx + _ATTACK_RANGE_PX:
                    total += 1
        return 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'

    def trigger_command(self):
        AttackCommand._queued     = None
        AttackCommand._is_running = True
        try:
            if self._cancelled:
                return
            self.interrupt_event.clear()

            self._char.minimap_task.char_facing = self._direction
            pyautogui.keyDown(self._direction)
            pyautogui.keyUp(self._direction)

            _logger.info(f'[PRIORITY][AttackCommand] 攻擊 dir={self._direction} key={self._attack_key}')
            pyautogui.keyDown(self._attack_key)
            self.interrupt_event.wait(0.4)
            pyautogui.keyUp(self._attack_key)

            if self.interrupt_event.is_set() or self._cancelled:
                _logger.info('[PRIORITY][AttackCommand] 被中斷，停止攻擊')
                return

            self._attack_key = self._decide_attack_key()
            AttackCommand._queued = self
            self._queue.put(self)
        finally:
            AttackCommand._is_running = False


# ── Move ──────────────────────────────────────────────────────────

class MoveToCenterCommand(Command):
    """
    移動到中間觀察點（_CENTER_X）。
    到達後結束；被攻擊打斷則重新入隊繼續移動。
    """

    _queued: 'MoveToCenterCommand | None' = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char: 'NightLord'):
        if cls._queued is not None:
            return
        obj = cls(q, char)
        cls._queued = obj
        q.put(obj)

    def __init__(self, q: queue.Queue, char: 'NightLord'):
        super().__init__(CommandType.CONDITION)
        self._queue = q
        self._char  = char

    def release(self): pass

    def _start_attack(self):
        cx = self._char.screen_x
        cy = self._char.screen_y
        counts = {'left': 0, 'right': 0}
        total = 0
        if cx != 0:
            for d in self._char._monster_detections:
                x1, y1, x2, y2 = d['bbox']
                mcx = (x1 + x2) / 2
                mcy = (y1 + y2) / 2
                if abs(mcy - cy) > _ATTACK_RANGE_Y:
                    continue
                if cx - _ATTACK_RANGE_PX <= mcx < cx:
                    counts['left'] += 1
                    total += 1
                elif cx < mcx <= cx + _ATTACK_RANGE_PX:
                    counts['right'] += 1
                    total += 1

        if counts['left'] > counts['right']:
            direction = 'left'
        elif counts['right'] > counts['left']:
            direction = 'right'
        else:
            direction = self._char._preferred_dir or 'right'

        self._char._preferred_dir = direction
        attack_key = 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'

        _logger.info(
            f'[MoveToCenterCommand] 攻擊方向={direction} key={attack_key} '
            f'L={counts["left"]} R={counts["right"]}'
        )

        self._char._reset_no_monster_timer(direction)
        self._char._reset_force_move_timer()
        AttackCommand._try_enqueue(
            self._char.priority_command_queue, self._char, direction, attack_key
        )

    def trigger_command(self):
        MoveToCenterCommand._queued = None
        try:
            self.interrupt_event.clear()
            cur_x = self._char.map_x
            if abs(cur_x - _CENTER_X) <= _X_TOL:
                _logger.info('[MoveToCenterCommand] 已在中間位置')
                self._start_attack()
                return

            direction = 'right' if cur_x < _CENTER_X else 'left'
            _logger.info(f'[MoveToCenterCommand] →{direction} cur={cur_x:.2f}')
            self._char.minimap_task.char_facing = direction

            reached = [False]

            def _on_reached():
                reached[0] = True
                self.interrupt_command()

            eid = self._char.minimap_task.register_pos_event(
                condition=lambda x, y: abs(x - _CENTER_X) <= _X_TOL,
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
                _logger.warning('[MoveToCenterCommand] 被打斷或超時，重試')
                MoveToCenterCommand._try_enqueue(self._queue, self._char)
                return

            _logger.info(f'[MoveToCenterCommand] 到達中間 x={self._char.map_x:.2f}，決定攻擊方向')
            self._start_attack()
        finally:
            MoveToCenterCommand._queued = None


class MoveToSideCommand(Command):
    """
    移動到指定邊界（_LEFT_X 或 _RIGHT_X）後回到中間觀察點。
    被攻擊打斷則重新入隊繼續移動。
    """

    _queued: 'MoveToSideCommand | None' = None

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
        MoveToSideCommand._queued = None
        try:
            self.interrupt_event.clear()
            target_x = _LEFT_X if self._direction == 'left' else _RIGHT_X
            _logger.info(f'[MoveToSideCommand] →{self._direction} target={target_x:.2f}')
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
                _logger.warning(f'[MoveToSideCommand] 被打斷或超時，重試')
                MoveToSideCommand._try_enqueue(self._queue, self._char, self._direction)
                return

            _logger.info(f'[MoveToSideCommand] 到達邊界 x={self._char.map_x:.2f}，回中間')
            MoveToCenterCommand._try_enqueue(self._queue, self._char)
        finally:
            MoveToSideCommand._queued = None


# ── NightLord ─────────────────────────────────────────────────────

class NightLord(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='NightLord')
        self._monster_monitor:    ModelController | None     = None
        self._monster_detections: list[dict]                 = []
        self._preferred_dir:      str | None                 = None
        self._no_monster_timer:   threading.Timer | None     = None
        self._force_move_timer:   threading.Timer | None     = None

    # ── 怪物方向偏好 & 無怪計時器 ─────────────────────────────────

    def _reset_no_monster_timer(self, direction: str):
        """每次在 direction 方向偵測到怪物時呼叫，重設 5 秒倒數。"""
        if self._no_monster_timer is not None:
            self._no_monster_timer.cancel()
        if self.stop_event.is_set():
            return
        t = threading.Timer(_NO_MONSTER_TIMEOUT, self._on_no_monster_timeout, args=(direction,))
        t.daemon = True
        t.start()
        self._no_monster_timer = t

    def _reset_force_move_timer(self):
        if self._force_move_timer is not None:
            self._force_move_timer.cancel()
        if self.stop_event.is_set():
            return
        t = threading.Timer(_FORCE_MOVE_INTERVAL, self._on_force_move_timeout)
        t.daemon = True
        t.start()
        self._force_move_timer = t

    def _interrupt_attack_and_move(self, direction: str):
        if AttackCommand._queued is not None:
            AttackCommand._queued._cancelled = True
            AttackCommand._queued = None
        if (self.current_command is not None
                and isinstance(self.current_command, AttackCommand)):
            self.current_command.interrupt_command()
        MoveToSideCommand._try_enqueue(self.command_queue, self, direction)

    def _on_force_move_timeout(self):
        self._force_move_timer = None
        if self.stop_event.is_set():
            return
        direction = self._preferred_dir or 'right'
        _logger.info(f'[NightLord] 1 分鐘強制移動，方向={direction}')
        self._interrupt_attack_and_move(direction)

    def _on_no_monster_timeout(self, direction: str):
        """_NO_MONSTER_TIMEOUT 秒後仍未見 direction 方向的怪：移往對應邊界。"""
        self._no_monster_timer = None
        if self.stop_event.is_set():
            return
        if self._preferred_dir != direction:
            return
        _logger.info(f'[NightLord] {direction} 方向 {_NO_MONSTER_TIMEOUT}s 無怪，移往邊界')
        self._interrupt_attack_and_move(direction)

    # ── ModelController callback ───────────────────────────────────

    def _on_monster_detected(self, detections: list[dict]):
        filtered = [d for d in detections if d['name'] in _MONSTER_DETECT_NAMES]
        self._monster_detections = filtered

        if not filtered or self._preferred_dir is None:
            return

        cx = self.screen_x
        cy = self.screen_y
        if cx == 0:
            return

        # 只統計鎖定方向的怪物數量，有怪才重置計時器
        preferred_count = 0
        for d in filtered:
            x1, y1, x2, y2 = d['bbox']
            mcx = (x1 + x2) / 2
            mcy = (y1 + y2) / 2
            if abs(mcy - cy) > _ATTACK_RANGE_Y:
                continue
            if self._preferred_dir == 'left' and cx - _ATTACK_RANGE_PX <= mcx < cx:
                preferred_count += 1
            elif self._preferred_dir == 'right' and cx < mcx <= cx + _ATTACK_RANGE_PX:
                preferred_count += 1

        if preferred_count > 0:
            self._reset_no_monster_timer(self._preferred_dir)

    # ── 初始化 ────────────────────────────────────────────────────

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

    # ── 生命週期 ──────────────────────────────────────────────────

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        if self._no_monster_timer is not None:
            self._no_monster_timer.cancel()
            self._no_monster_timer = None
        if self._force_move_timer is not None:
            self._force_move_timer.cancel()
            self._force_move_timer = None
        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._monster_detections = []
        self._preferred_dir       = None
        AttackCommand._queued     = None
        AttackCommand._is_running = False
        MoveToCenterCommand._queued = None
        MoveToSideCommand._queued   = None
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
        if self._no_monster_timer is not None:
            self._no_monster_timer.cancel()
            self._no_monster_timer = None
        if self._force_move_timer is not None:
            self._force_move_timer.cancel()
            self._force_move_timer = None

        self._load_minimap_bounds()

        # 重置所有狀態
        AttackCommand._queued       = None
        AttackCommand._is_running   = False
        MoveToCenterCommand._queued = None
        MoveToSideCommand._queued   = None
        self._preferred_dir         = None
        self.minimap_task.char_facing      = 'right'
        self.minimap_task.char_y_direction = 'down'

        # 啟動怪物偵測
        if self._monster_monitor is not None:
            self._monster_monitor.stop()
            self._monster_monitor = None
        self._monster_detections = []
        self._monster_monitor = ModelController(
            self.game_window, _MONSTER_MODEL, self._on_monster_detected
        )
        self._monster_monitor.start()

        self._enqueue_buffs()
        # 初始移動到中間觀察點
        MoveToCenterCommand._try_enqueue(self.command_queue, self)
