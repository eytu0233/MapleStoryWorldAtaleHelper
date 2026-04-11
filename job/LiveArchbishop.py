import json
import os
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
        self.interrupt_event.wait(1)
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
        _logger.info('[SimpleSkyAngry] 天怒施放 7s')
        pyautogui.keyDown('d')
        self.interrupt_event.wait(7)
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

        dist_left = cur_x - _MOVE_X_MIN
        dist_right = _MOVE_X_MAX - cur_x
        move_dir = 'left' if dist_left >= dist_right else 'right'
        _logger.info(f'[LiveMove] cur_x={cur_x:.2f} →{move_dir} (dist_left={dist_left:.2f} dist_right={dist_right:.2f})')

        pyautogui.keyDown(move_dir)
        self.interrupt_event.wait(0.1)
        pyautogui.keyUp(move_dir)

        if self.interrupt_event.is_set():
            _logger.info('[LiveMove] 被打斷')
            return

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
        self.priority_command_queue.put(_LiveMoveCommand(self, self.command_queue))
        for cmd in (HolySymbol(), AngelBlessing(), MapleBlessing()):
            self.priority_command_queue.put(cmd)
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
