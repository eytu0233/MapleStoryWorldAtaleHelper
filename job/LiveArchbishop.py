import json
import os
import random
import threading

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from job.Archbishop import HolySymbol, AngelBlessing, MapleBlessing, InfiniteMana
from util.logger import MSLogger

_logger = MSLogger('LiveArchbishop')

_BUFF_INTERVAL = 270   # 秒
_MOVE_X_MIN    = 0.46
_MOVE_X_MAX    = 0.50
_MOVE_X_TOL    = 0.01
_MAP_CONFIG    = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')


class SitDownCommand(Command):
    def __init__(self):
        super().__init__(CommandType.CONDITION)

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info('[SitDown] 坐下')
        pyautogui.keyDown('0')
        self.interrupt_event.wait(0.5)
        pyautogui.keyUp('0')


class _SimpleSkyAngryCommand(Command):
    def __init__(self, q):
        super().__init__(CommandType.CONDITION)
        self._queue = q

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info('[SimpleSkyAngry] 天怒施放 4.5s')
        pyautogui.keyDown('d')
        self.interrupt_event.wait(4.5)
        pyautogui.keyUp('d')
        if self.interrupt_event.is_set():
            _logger.info('[SimpleSkyAngry] 被打斷')
        else:
            _logger.info('[SimpleSkyAngry] 完成')
        self._queue.put(SitDownCommand())


class _LiveMoveCommand(Command):
    def __init__(self, char, q):
        super().__init__(CommandType.CONDITION)
        self._char  = char
        self._queue = q

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        cur_x = self._char.map_x

        # 從 [0.46, 0.47, 0.48, 0.49, 0.50] 挑一個與當前位置不同的目標
        candidates = [round(x * 0.01 + _MOVE_X_MIN, 2) for x in range(5)]
        candidates = [x for x in candidates if abs(x - cur_x) > _MOVE_X_TOL]
        target_x = random.choice(candidates) if candidates else random.uniform(_MOVE_X_MIN, _MOVE_X_MAX)

        move_dir = 'left' if cur_x > target_x else 'right'
        _logger.info(f'[LiveMove] cur_x={cur_x:.2f} target_x={target_x:.2f} →{move_dir}')

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - target_x) <= _MOVE_X_TOL,
            callback=_on_reached,
            once=True,
        )
        pyautogui.keyDown(move_dir)
        self.interrupt_event.wait(5)
        pyautogui.keyUp(move_dir)
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached[0]:
            _logger.info('[LiveMove] 被打斷或超時')
            return

        _logger.info(f'[LiveMove] 到達 x={self._char.map_x:.2f}')
        self._char.priority_command_queue.put(InfiniteMana())
        self._queue.put(_SimpleSkyAngryCommand(self._queue))


class LiveArchbishop(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='LiveArchbishop')

    def _load_minimap_bounds(self):
        try:
            with open(_MAP_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data['minimap_bounds']
            self.minimap_task.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
            _logger.info(f'[LiveArchbishop] 小地圖邊界已載入: {mm}')
        except Exception as e:
            _logger.warning(f'[LiveArchbishop] 載入小地圖邊界失敗: {e}')

    def _enqueue_buffs(self):
        for cmd in (HolySymbol(), AngelBlessing(), MapleBlessing()):
            self.priority_command_queue.put(cmd)
        self.command_queue.put(_LiveMoveCommand(self, self.command_queue))
        self._buff_timer = threading.Timer(_BUFF_INTERVAL, self._enqueue_buffs)
        self._buff_timer.daemon = True
        self._buff_timer.start()

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        super().stop()
        for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break
        _logger.info('[LiveArchbishop] 已停止')

    def task_prepare(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        self._load_minimap_bounds()
        self._enqueue_buffs()
