import json
import queue
import random
import threading

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from controller.GameCharacter import GameCharacter
from util.logger import MSLogger

_CONFIG_FILE      = 'support.json'
_FREE_MARKET_FILE = 'free_market.json'

_MINIMAP_Y_TOLERANCE   = 0.05   # 確認進入自由市場的 y 容差
_FREE_MARKET_WAIT_SECS = 2.0    # 按下按鈕後等待確認的秒數
_BUTTON_JITTER_PX      = 5      # 按鈕 x 隨機位移（像素）

_logger = MSLogger('SupportBot')


def _load_configs() -> tuple[dict, dict]:
    with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
        support_cfg = json.load(f)['support']
    with open(_FREE_MARKET_FILE, 'r', encoding='utf-8') as f:
        fm_cfg = json.load(f)
    return support_cfg, fm_cfg


# ── Buff 施放 ──────────────────────────────────────────────────────

class CastBuffsCommand(Command):
    """依序施放所有 buff 技能，完成後進入自由市場。"""

    def __init__(self, char: 'SupportBot', q: queue.Queue,
                 buff_skills: list[str], fm_cfg: dict):
        super().__init__(CommandType.CONDITION)
        self._char       = char
        self._queue      = q
        self._skills     = buff_skills
        self._fm_cfg     = fm_cfg

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        for key in self._skills:
            if self.interrupt_event.is_set():
                _logger.info('[CastBuffs] 被打斷，停止施放')
                return
            _logger.info(f'[CastBuffs] 施放技能 key={key}')
            pyautogui.keyDown(key)
            interrupted = self.interrupt_event.wait(0.6)
            pyautogui.keyUp(key)
            if interrupted:
                _logger.info('[CastBuffs] 被打斷')
                return
        _logger.info('[CastBuffs] buff 施放完畢，準備進入自由市場')
        self._queue.put(EnterFreeMarketCommand(
            self._char, self._queue, self._fm_cfg, jitter_x=0
        ))


# ── 進入自由市場 ───────────────────────────────────────────────────

class EnterFreeMarketCommand(Command):
    """點擊自由市場按鈕，等待確認後設定小地圖邊界。"""

    def __init__(self, char: 'SupportBot', q: queue.Queue,
                 fm_cfg: dict, jitter_x: int = 0):
        super().__init__(CommandType.CONDITION)
        self._char     = char
        self._queue    = q
        self._fm_cfg   = fm_cfg
        self._jitter_x = jitter_x

    def release(self): pass

    def _click_button(self):
        gw = GameCharacter.shared_game_window()
        if gw is None or not gw.is_valid:
            _logger.warning('[EnterFM] 遊戲視窗不可用')
            return
        btn = self._fm_cfg['free_market_button_pos']
        abs_x = int(gw.left + gw.width  * btn['x']) + self._jitter_x
        abs_y = int(gw.top  + gw.height * btn['y'])
        _logger.info(f'[EnterFM] 點擊自由市場按鈕 ({abs_x}, {abs_y}) jitter={self._jitter_x}')
        pyautogui.click(abs_x, abs_y)

    def trigger_command(self):
        self.interrupt_event.clear()

        # 套用自由市場小地圖邊界
        mm = self._fm_cfg['minimap_bounds']
        mt = self._char.minimap_task
        mt.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
        _logger.info(f'[EnterFM] 套用自由市場小地圖邊界 {mm}')

        self._click_button()

        # 等待 ~2 秒讓畫面切換
        interrupted = self.interrupt_event.wait(_FREE_MARKET_WAIT_SECS)
        if interrupted:
            _logger.info('[EnterFM] 被打斷')
            return

        # 確認是否進入自由市場（依 minimap_y）
        target_y = self._fm_cfg['free_market_exit']['minimap_y']
        actual_y = self._char.map_y
        _logger.info(f'[EnterFM] 確認位置 map_y={actual_y:.3f} target_y={target_y:.3f}')

        if abs(actual_y - target_y) <= _MINIMAP_Y_TOLERANCE:
            _logger.info('[EnterFM] 確認進入自由市場')
            self._queue.put(MoveToExitCommand(
                self._char, self._queue, self._fm_cfg
            ))
        else:
            new_jitter = random.choice([-_BUTTON_JITTER_PX, _BUTTON_JITTER_PX])
            _logger.warning(f'[EnterFM] 未確認進入，重試 jitter={new_jitter}')
            self._queue.put(EnterFreeMarketCommand(
                self._char, self._queue, self._fm_cfg, jitter_x=new_jitter
            ))


# ── 移動到出口位置 ─────────────────────────────────────────────────

class MoveToExitCommand(Command):
    """在自由市場內移動到 free_market_exit 指定的小地圖位置。"""

    _TOLERANCE = 0.04

    def __init__(self, char: 'SupportBot', q: queue.Queue, fm_cfg: dict):
        super().__init__(CommandType.CONDITION)
        self._char   = char
        self._queue  = q
        self._fm_cfg = fm_cfg

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        target_x = self._fm_cfg['free_market_exit']['minimap_x']

        dist = abs(self._char.map_x - target_x)
        if dist <= self._TOLERANCE:
            _logger.info(f'[MoveToExit] 已在目標位置 x={self._char.map_x:.3f}')
            self._queue.put(WaitInFreeMarketCommand(
                self._char, self._queue, self._fm_cfg
            ))
            return

        direction = 'left' if self._char.map_x > target_x else 'right'
        _logger.info(f'[MoveToExit] 移動 →{direction} target_x={target_x:.3f}')

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - target_x) <= self._TOLERANCE,
            callback=_on_reached,
            once=True,
        )
        pyautogui.keyDown(direction)
        self.interrupt_event.wait(10)
        pyautogui.keyUp(direction)
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached[0]:
            _logger.warning('[MoveToExit] 被打斷，重試')
            self._queue.put(self)
            return

        _logger.info(f'[MoveToExit] 到達目標位置 x={self._char.map_x:.3f}')
        self._queue.put(WaitInFreeMarketCommand(
            self._char, self._queue, self._fm_cfg
        ))


# ── 在自由市場等待 ─────────────────────────────────────────────────

class WaitInFreeMarketCommand(Command):
    """等待 interval 秒後離開自由市場。"""

    def __init__(self, char: 'SupportBot', q: queue.Queue, fm_cfg: dict):
        super().__init__(CommandType.CONDITION)
        self._char   = char
        self._queue  = q
        self._fm_cfg = fm_cfg

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        interval = self._char.interval
        _logger.info(f'[Wait] 在自由市場等待 {interval}s')
        interrupted = self.interrupt_event.wait(interval)
        if interrupted:
            _logger.info('[Wait] 被打斷')
            return
        _logger.info('[Wait] 等待完畢，準備離開自由市場')
        self._queue.put(ExitFreeMarketCommand(
            self._char, self._queue, self._fm_cfg
        ))


# ── 離開自由市場 ───────────────────────────────────────────────────

class ExitFreeMarketCommand(Command):
    """按上方向鍵離開自由市場，還原小地圖邊界，重新施放 buff。"""

    def __init__(self, char: 'SupportBot', q: queue.Queue, fm_cfg: dict):
        super().__init__(CommandType.CONDITION)
        self._char   = char
        self._queue  = q
        self._fm_cfg = fm_cfg

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info('[ExitFM] 按上方向鍵離開自由市場')
        pyautogui.keyDown('up')
        interrupted = self.interrupt_event.wait(0.5)
        pyautogui.keyUp('up')

        if interrupted:
            _logger.info('[ExitFM] 被打斷')
            return

        # 還原原始小地圖邊界
        self._char.restore_minimap_bounds()
        _logger.info('[ExitFM] 已還原小地圖邊界，重新施放 buff')

        self._queue.put(CastBuffsCommand(
            self._char, self._queue,
            self._char.buff_skills, self._fm_cfg
        ))


# ── SupportBot 主類別 ──────────────────────────────────────────────

class SupportBot(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='SupportBot')
        support_cfg, fm_cfg = _load_configs()
        self.buff_skills: list[str] = support_cfg['buff_skills']
        self.interval: int          = support_cfg['interval']
        self._fm_cfg: dict          = fm_cfg
        self._original_bounds: tuple | None = None
        self._buff_timer: threading.Timer | None = None

    def restore_minimap_bounds(self):
        """還原進入自由市場前的小地圖邊界。"""
        if self._original_bounds is not None:
            x, y, x2, y2 = self._original_bounds
            self.minimap_task.set_bounds(x, y, x2, y2)
            _logger.info(f'還原小地圖邊界 ({x},{y})-({x2},{y2})')

    def stop(self):
        if self._buff_timer is not None:
            self._buff_timer.cancel()
            self._buff_timer = None
        super().stop()
        for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break

    # ── 抽象方法實作 ───────────────────────────────────────────────

    def task_prepare(self):
        # 記錄目前小地圖邊界，供離開自由市場時還原
        mt = self.minimap_task
        if mt is not None:
            self._original_bounds = mt.get_bounds()
        else:
            self._original_bounds = None

        self.command_queue.put(CastBuffsCommand(
            self, self.command_queue, self.buff_skills, self._fm_cfg
        ))

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 0.3)

    def normal_attack(self) -> bool:
        return False
