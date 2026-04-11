import json
import os
import queue
import random
import threading
import time
from typing import Optional

import pyautogui

from controller.Command import Command, CommandType
from controller.CommandGameCharacter import CommandGameCharacter
from controller.GameCharacter import GameCharacter
from discord_bot.discord_bot import DiscordBot
from util.logger import MSLogger

_logger = MSLogger('NightLord101')

_BUFF_INTERVAL           = 270   # 秒
_HP_DEAD_NOTIFY_INTERVAL = 300   # 秒（5 分鐘）
_MAP_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_cd_101.json')

# ── 地圖常數 ──────────────────────────────────────────────────────
_LEFT_BOUNDARY  = 0.05
_RIGHT_BOUNDARY = 0.98

_TOP_Y = 0.41
_MID_Y = 0.68
_BOT_Y = 0.94

_TOP_MID_THRESH = (_TOP_Y + _MID_Y) / 2   # 0.545
_MID_BOT_THRESH = (_MID_Y + _BOT_Y) / 2   # 0.81

_MID_TELEPORT_X = 0.06
_BOT_TELEPORT_X = 0.33

_TELEPORT_X = {
    'mid': _MID_TELEPORT_X,
    'bot': _BOT_TELEPORT_X,
}

_TELEPORT_TOLERANCE = 0.01


def _get_layer(char) -> str:
    y = char.map_y
    if y < _TOP_MID_THRESH:
        return 'top'
    elif y < _MID_BOT_THRESH:
        return 'mid'
    else:
        return 'bot'


# ── Buff / Heal ───────────────────────────────────────────────────

class _BuffCommand(Command):
    def __init__(self, key: str):
        super().__init__(CommandType.CONDITION)
        self._key = key

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        name = type(self).__name__
        _logger.info(f'[PRIORITY][{name}] 施放 key={self._key}')
        pyautogui.keyDown(self._key)
        interrupted = self.interrupt_event.wait(0.6)
        pyautogui.keyUp(self._key)
        if interrupted:
            _logger.info(f'[PRIORITY][{name}] 被打斷')


class SpeedBoost(_BuffCommand):
    def __init__(self): super().__init__('1')

class LuckSpell(_BuffCommand):
    def __init__(self): super().__init__('2')



# ── Search Commands ───────────────────────────────────────────────
#
# 鏈式結構：
#   SearchStepCommand          ← 分派器（無 wait）
#     ├─ TeleportStepCommand   ← 瞬移一步（interrupt_event.wait）→ SearchStepCommand
#     └─ WalkToBoundaryCommand ← 步行至邊界（done.wait）
#           ├─ SearchStepCommand（未到換層）
#           └─ LayerChangeCommand（bounce >= 2，無 wait）
#                 ├─ MoveToXCommand → DropDownCommand → SearchStepCommand
#                 └─ GoUpApproachCommand（無 wait）
#                       ├─ GoUpTeleportCommand（interrupt_event.wait）→ GoUpApproachCommand
#                       └─ GoUpWalkCommand（done.wait）→ GoUpPressCommand
#                                                          └─（interrupt_event.wait）
#                                                               ├─ 換層成功 → SearchStepCommand
#                                                               └─ 換層失敗 → GoUpApproachCommand


class SearchStepCommand(Command):
    """位置評估分派器：距邊界 > 0.3 用二段跳，否則步行。無 wait。"""

    def __init__(self, char, q: queue.Queue,
                 direction: str | None = None, bounce_count: int = 0):
        super().__init__(CommandType.CONDITION)
        self._char         = char
        self._queue        = q
        self._direction    = direction
        self._bounce_count = bounce_count

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        direction = self._direction or ('right' if self._char.map_x <= 0.5 else 'left')
        boundary  = _LEFT_BOUNDARY if direction == 'left' else _RIGHT_BOUNDARY
        dist      = abs(self._char.map_x - boundary)
        _logger.info(f'[NORMAL][SearchStep] dir={direction} pos=({self._char.map_x:.2f},{self._char.map_y:.2f}) dist={dist:.2f} bounce={self._bounce_count}')

        if dist > 0.3 and _get_layer(self._char) != 'top':
            self._queue.put(DoubleJumpStepCommand(self._char, self._queue, direction, self._bounce_count))
        else:
            self._queue.put(WalkToBoundaryCommand(self._char, self._queue, direction, self._bounce_count))


class DoubleJumpStepCommand(Command):
    """單次二段跳步驟：按住方向鍵並按一次 alt，完成後重新評估位置。"""

    def __init__(self, char, q: queue.Queue, direction: str, bounce_count: int):
        super().__init__(CommandType.CONDITION)
        self._char         = char
        self._queue        = q
        self._direction    = direction
        self._bounce_count = bounce_count

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[NORMAL][DoubleJumpStep] →{self._direction}')
        pyautogui.keyDown(self._direction)
        pyautogui.keyDown('alt')
        self.interrupt_event.wait(0.3)
        pyautogui.keyUp('alt')
        pyautogui.keyUp(self._direction)
        # 無論是否被打斷，重新評估位置（任務停止中則不入列，避免殘留污染下一輪）
        if not self._char.stop_event.is_set():
            self._queue.put(SearchStepCommand(self._char, self._queue, self._direction, self._bounce_count))


class WalkToBoundaryCommand(Command):
    """步行直到碰到左/右邊界。"""

    def __init__(self, char, q: queue.Queue, direction: str, bounce_count: int):
        super().__init__(CommandType.CONDITION)
        self._char         = char
        self._queue        = q
        self._direction    = direction
        self._bounce_count = bounce_count

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[NORMAL][WalkToBoundary] →{self._direction} pos=({self._char.map_x:.2f},{self._char.map_y:.2f})')
        condition = (lambda x, y: x <= _LEFT_BOUNDARY) if self._direction == 'left' \
                    else (lambda x, y: x >= _RIGHT_BOUNDARY)

        reached = [False]

        def _on_boundary():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(condition, _on_boundary, once=True)
        pyautogui.keyDown(self._direction)
        self.interrupt_event.wait(10)
        pyautogui.keyUp(self._direction)
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached[0]:
            _logger.info(f'[NORMAL][WalkToBoundary] 被打斷 重試')
            if not self._char.stop_event.is_set():
                self._queue.put(SearchStepCommand(self._char, self._queue, self._direction, self._bounce_count))
            return

        new_dir    = 'right' if self._direction == 'left' else 'left'
        new_bounce = self._bounce_count + 1
        _logger.info(f'[NORMAL][WalkToBoundary] 到達邊界 翻轉→{new_dir} bounce={new_bounce}')

        if new_bounce >= 2:
            self._queue.put(LayerChangeCommand(self._char, self._queue, new_dir))
        else:
            self._queue.put(SearchStepCommand(self._char, self._queue, new_dir, new_bounce))


class LayerChangeCommand(Command):
    """換層分派器：判斷往上或往下。無 wait。"""

    def __init__(self, char, q: queue.Queue, direction: str):
        super().__init__(CommandType.CONDITION)
        self._char      = char
        self._queue     = q
        self._direction = direction

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        layer = _get_layer(self._char)
        _logger.info(f'[NORMAL][LayerChange] layer={layer} dir={self._direction}')

        if layer == 'top':
            offset   = random.uniform(0.25, 0.65)
            target_x = _LEFT_BOUNDARY + offset if self._char.map_x < 0.5 else _RIGHT_BOUNDARY - offset
            _logger.info(f'[NORMAL][LayerChange] top → 下降 先移至 x={target_x:.2f}')
            drop_cmd = DropDownCommand(self._char, self._queue, self._direction)
            self._queue.put(MoveToXCommand(self._char, self._queue, target_x, drop_cmd))
        else:
            teleport_x = _TELEPORT_X[layer]
            self._queue.put(GoUpApproachCommand(self._char, self._queue, teleport_x, self._direction, layer))


class MoveToXCommand(Command):
    """步行移動到目標 x，到達後執行 next_cmd。"""

    def __init__(self, char, q: queue.Queue, target_x: float, next_cmd: Command):
        super().__init__(CommandType.CONDITION)
        self._char     = char
        self._queue    = q
        self._target_x = target_x
        self._next_cmd = next_cmd

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        dist = abs(self._char.map_x - self._target_x)
        if dist <= _TELEPORT_TOLERANCE:
            _logger.info(f'[NORMAL][MoveToX] 已到達 x={self._target_x:.2f}')
            self._queue.put(self._next_cmd)
            return

        move_dir = 'left' if self._char.map_x > self._target_x else 'right'
        _logger.info(f'[NORMAL][MoveToX] →{move_dir} target={self._target_x:.2f} dist={dist:.2f}')

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - self._target_x) <= _TELEPORT_TOLERANCE,
            callback=_on_reached, once=True,
        )
        pyautogui.keyDown(move_dir)
        self.interrupt_event.wait(10)
        pyautogui.keyUp(move_dir)
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached[0]:
            _logger.info(f'[NORMAL][MoveToX] 被打斷 重試')
            if not self._char.stop_event.is_set():
                self._queue.put(self)
            return

        self._queue.put(self._next_cmd)


class DropDownCommand(Command):
    """按住 down+alt 直到 y >= 0.9 落至底層。"""

    def __init__(self, char, q: queue.Queue, direction: str):
        super().__init__(CommandType.CONDITION)
        self._char      = char
        self._queue     = q
        self._direction = direction

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[NORMAL][DropDown] 開始下降')

        reached_bottom = [False]

        def _on_bottom():
            reached_bottom[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: y >= 0.9, callback=_on_bottom, once=True,
        )
        pyautogui.keyDown('down')
        pyautogui.keyDown('alt')
        self.interrupt_event.wait(10)
        pyautogui.keyUp('alt')
        pyautogui.keyUp('down')
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached_bottom[0]:
            if self._char.map_y >= 0.9:
                _logger.info(f'[NORMAL][DropDown] 被打斷 但已在底層 繼續')
            else:
                _logger.info(f'[NORMAL][DropDown] 被打斷 重試')
                if not self._char.stop_event.is_set():
                    self._queue.put(self)
                return

        _logger.info(f'[NORMAL][DropDown] 到達底層 pos=({self._char.map_x:.2f},{self._char.map_y:.2f})')
        if not self._char.stop_event.is_set():
            self._queue.put(SearchStepCommand(self._char, self._queue, self._direction, 0))


class GoUpApproachCommand(Command):
    """換層前靠近傳送點的分派器：距離 > 0.3 用二段跳，近則步行。無 wait。"""

    def __init__(self, char, q: queue.Queue, teleport_x: float, direction: str, layer: str):
        super().__init__(CommandType.CONDITION)
        self._char       = char
        self._queue      = q
        self._teleport_x = teleport_x
        self._direction  = direction
        self._layer      = layer

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        dist = abs(self._char.map_x - self._teleport_x)
        _logger.info(f'[NORMAL][GoUpApproach] teleport_x={self._teleport_x:.2f} dist={dist:.2f}')

        if dist <= _TELEPORT_TOLERANCE:
            self._queue.put(GoUpPressCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))
        elif dist > 0.3:
            self._queue.put(DoubleJumpGoUpCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))
        else:
            self._queue.put(GoUpWalkCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))


class DoubleJumpGoUpCommand(Command):
    """二段跳靠近換層傳送點：按住方向鍵並按一次 alt，完成後重新評估距離。"""

    def __init__(self, char, q: queue.Queue, teleport_x: float, direction: str, layer: str):
        super().__init__(CommandType.CONDITION)
        self._char       = char
        self._queue      = q
        self._teleport_x = teleport_x
        self._direction  = direction
        self._layer      = layer

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        move_dir = 'left' if self._char.map_x > self._teleport_x else 'right'
        _logger.info(f'[NORMAL][DoubleJumpGoUp] →{move_dir}')
        pyautogui.keyDown(move_dir)
        pyautogui.press('alt')
        pyautogui.press('alt')
        pyautogui.keyUp(move_dir)
        # 重新評估距離（任務停止中則不入列）
        if not self._char.stop_event.is_set():
            self._queue.put(GoUpApproachCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))


class GoUpWalkCommand(Command):
    """步行到換層傳送點。"""

    def __init__(self, char, q: queue.Queue, teleport_x: float, direction: str, layer: str):
        super().__init__(CommandType.CONDITION)
        self._char       = char
        self._queue      = q
        self._teleport_x = teleport_x
        self._direction  = direction
        self._layer      = layer

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        move_dir = 'left' if self._char.map_x > self._teleport_x else 'right'
        _logger.info(f'[NORMAL][GoUpWalk] →{move_dir} target={self._teleport_x:.2f}')

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - self._teleport_x) <= _TELEPORT_TOLERANCE,
            callback=_on_reached, once=True,
        )
        pyautogui.keyDown(move_dir)
        self.interrupt_event.wait(10)
        pyautogui.keyUp(move_dir)
        self._char.minimap_task.unregister_pos_event(eid)

        if not reached[0]:
            _logger.info(f'[NORMAL][GoUpWalk] 被打斷 重試')
            if not self._char.stop_event.is_set():
                self._queue.put(GoUpApproachCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))
            return

        self._queue.put(GoUpPressCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))


class GoUpPressCommand(Command):
    """在傳送點按上方向鍵嘗試換層。"""

    def __init__(self, char, q: queue.Queue, teleport_x: float, direction: str, layer: str):
        super().__init__(CommandType.CONDITION)
        self._char       = char
        self._queue      = q
        self._teleport_x = teleport_x
        self._direction  = direction
        self._layer      = layer

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        prev_layer = _get_layer(self._char)
        _logger.info(f'[NORMAL][GoUpPress] 按上 layer={prev_layer} pos=({self._char.map_x:.2f},{self._char.map_y:.2f})')

        pyautogui.keyDown('up')
        self.interrupt_event.wait(0.3)
        pyautogui.keyUp('up')

        if self.interrupt_event.is_set():
            _logger.info(f'[NORMAL][GoUpPress] 被打斷')
            if not self._char.stop_event.is_set():
                self._queue.put(SearchStepCommand(self._char, self._queue, self._direction, 0))
            return

        new_layer = _get_layer(self._char)
        if new_layer != prev_layer:
            _logger.info(f'[NORMAL][GoUpPress] 換層成功 {prev_layer} → {new_layer}')
            self._queue.put(SearchStepCommand(self._char, self._queue, self._direction, 0))
        else:
            _logger.info(f'[NORMAL][GoUpPress] 換層失敗 重試')
            self._queue.put(GoUpApproachCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))


# ── Attack ────────────────────────────────────────────────────────

class AttackCommand(Command):

    def __init__(self, priority_queue: queue.Queue):
        super().__init__(CommandType.CONDITION)
        self._queue      = priority_queue
        self._counter    = 0
        self._cancelled  = False
        self._pending_timer: threading.Timer | None = None

    def release(self):
        self._cancelled = True
        if self._pending_timer is not None:
            self._pending_timer.cancel()
            self._pending_timer = None

    def trigger_command(self):
        if self._cancelled:
            return
        self.interrupt_event.clear()
        _logger.info('[PRIORITY][AttackCommand] 攻擊開始')
        pyautogui.keyDown('z')
        self.interrupt_event.wait(2)
        pyautogui.keyUp('z')

        if self.interrupt_event.is_set():
            _logger.info('[PRIORITY][AttackCommand] 攻擊被中斷')
        else:
            _logger.info('[PRIORITY][AttackCommand] 攻擊結束')

        if self._cancelled:
            return
        delay = random.randint(1500, 3000) / 1000
        t = threading.Timer(delay, self._queue.put, args=(self,))
        t.daemon = True
        self._pending_timer = t
        t.start()



# ── NightLord101 ──────────────────────────────────────────────────

class NightLord101(CommandGameCharacter):

    def __init__(self, discord_bot: Optional[DiscordBot] = None):
        super().__init__(name='NightLord101')
        self._discord_bot                                   = discord_bot
        self._attack_cmd: AttackCommand | None             = None
        self._attack_initial_timer: threading.Timer | None = None
        self._hp_dead_callback                             = None
        self._hp_notify_timer: threading.Timer | None      = None

    def _on_hp_dead(self):
        """HP 歸零初次觸發：立即通知，並啟動每 5 分鐘的重複通知。"""
        if self._discord_bot is None:
            return
        self._discord_bot.notify('⚠️ NightLord101 HP 歸零！角色可能已死亡。')
        self._schedule_hp_dead_repeat()

    def _schedule_hp_dead_repeat(self):
        """若 HP 仍 < 1%，每 5 分鐘再次通知。"""
        self._hp_notify_timer = threading.Timer(_HP_DEAD_NOTIFY_INTERVAL, self._hp_dead_repeat_check)
        self._hp_notify_timer.daemon = True
        self._hp_notify_timer.start()

    def _hp_dead_repeat_check(self):
        if GameCharacter._shared_hp < 1.0:
            self._discord_bot.notify('⚠️ NightLord101 HP 仍為 0！角色可能仍在死亡狀態。')
            self._schedule_hp_dead_repeat()
        # HP 已恢復，不再重複

    def _load_minimap_bounds(self):
        try:
            with open(_MAP_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data['minimap_bounds']
            self.minimap_task.set_bounds(mm['x'], mm['y'], mm['x'] + mm['w'], mm['y'] + mm['h'])
            _logger.info(f'[NightLord101] 小地圖邊界已載入: {mm}')
        except Exception as e:
            _logger.warning(f'[NightLord101] 載入小地圖邊界失敗: {e}')

    def _enqueue_buffs(self):
        for cmd in (SpeedBoost(), LuckSpell()):
            self.priority_command_queue.put(cmd)
        self._buff_timer = threading.Timer(_BUFF_INTERVAL, self._enqueue_buffs)
        self._buff_timer.daemon = True
        self._buff_timer.start()

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        if self._attack_initial_timer is not None:
            self._attack_initial_timer.cancel()
            self._attack_initial_timer = None
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
        if self._hp_dead_callback is not None:
            GameCharacter.unregister_hp_callback(self._hp_dead_callback)
            self._hp_dead_callback = None
        if self._hp_notify_timer is not None:
            self._hp_notify_timer.cancel()
            self._hp_notify_timer = None
        _logger.info("Clear queue")

    # ── 抽象方法實作 ─────────────────────────────────────────────

    def task_prepare(self):
        self._load_minimap_bounds()
        # ── 重置所有 Command 類別狀態，確保重新啟動時乾淨 ──────────
        if self._hp_dead_callback is not None:
            GameCharacter.unregister_hp_callback(self._hp_dead_callback)
            self._hp_dead_callback = None
        if self._hp_notify_timer is not None:
            self._hp_notify_timer.cancel()
            self._hp_notify_timer = None
        if self._attack_initial_timer is not None:
            self._attack_initial_timer.cancel()
            self._attack_initial_timer = None
        if self._attack_cmd is not None:
            self._attack_cmd.release()
            self._attack_cmd = None

        # ── 建立全新 Command 實例並初始化 ───────────────────────────
        if self._discord_bot is not None:
            _logger.info("Register dead monitor")
            cb = self._on_hp_dead
            self._hp_dead_callback = cb
            GameCharacter.register_hp_callback(1.0, cb, condition='below')
        self.command_queue.put(SearchStepCommand(self, self.command_queue))
        self._enqueue_buffs()
        self._attack_cmd = AttackCommand(self.priority_command_queue)
        self._attack_initial_timer = threading.Timer(2.0, self.priority_command_queue.put, args=(self._attack_cmd,))
        self._attack_initial_timer.daemon = True
        self._attack_initial_timer.start()

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 0.3)

    def normal_attack(self) -> bool:
        return self._hold_key('x', 0.1)
