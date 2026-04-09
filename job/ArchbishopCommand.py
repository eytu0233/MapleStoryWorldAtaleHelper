import queue
import random
import threading
import pyautogui
import time

from controller.Command import Command, CommandType
from controller.GameCharacter import GameCharacter
from util.logger import MSLogger

_logger = MSLogger('ArchbishopCommand')

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


class HolySymbol(_BuffCommand):
    def __init__(self): super().__init__('1')

class AngelBlessing(_BuffCommand):
    def __init__(self): super().__init__('2')

class HolyLight(_BuffCommand):
    def __init__(self): super().__init__('3')

class MapleBlessing(_BuffCommand):
    def __init__(self): super().__init__('5')

class DragonCommand(_BuffCommand):
    def __init__(self): super().__init__('a')


class HealCommand(Command):
    _queued: 'HealCommand | None' = None  # 追蹤 queue 中的實例，防止重複入隊
    _hp_callback = None                    # 記錄已註冊的 callback 以便解除

    def __init__(self, q: queue.Queue):
        super().__init__(CommandType.NORMAL)
        cb = lambda: HealCommand._try_enqueue(q)
        HealCommand._hp_callback = cb
        GameCharacter.register_hp_callback(80.0, cb)

    @classmethod
    def release(cls):
        if cls._hp_callback is not None:
            GameCharacter.unregister_hp_callback(cls._hp_callback)
            cls._hp_callback = None
        cls._queued = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue):
        if cls._queued is not None:
            _logger.info('[EMERG][HealCommand] 已在 queue 中，略過')
            return
        obj = cls.__new__(cls)
        Command.__init__(obj, CommandType.NORMAL)
        cls._queued = obj
        q.put(obj)

    def trigger_command(self):
        _logger.info(f'[EMERG][HealCommand] 治療開始 HP={GameCharacter._shared_hp:.1f}%')
        while GameCharacter._shared_hp < 90.0:
            pyautogui.keyDown('z')
            time.sleep(0.3)
            pyautogui.keyUp('z')
            _logger.info(f'[EMERG][HealCommand] 治療中 HP={GameCharacter._shared_hp:.1f}%')
        _logger.info(f'[EMERG][HealCommand] 治療完成 HP={GameCharacter._shared_hp:.1f}%')
        HealCommand._queued = None


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
    """位置評估分派器：根據距邊界距離決定瞬移或步行。無 wait。"""

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

        if dist > 0.1:
            self._queue.put(TeleportStepCommand(self._char, self._queue, direction, self._bounce_count))
        else:
            self._queue.put(WalkToBoundaryCommand(self._char, self._queue, direction, self._bounce_count))


class TeleportStepCommand(Command):
    """單次瞬移步驟（方向鍵 + c）。"""

    def __init__(self, char, q: queue.Queue, direction: str, bounce_count: int):
        super().__init__(CommandType.CONDITION)
        self._char         = char
        self._queue        = q
        self._direction    = direction
        self._bounce_count = bounce_count

    def release(self): pass

    def trigger_command(self):
        self.interrupt_event.clear()
        _logger.info(f'[NORMAL][TeleportStep] →{self._direction}')
        pyautogui.keyDown(self._direction)
        pyautogui.keyDown('c')
        self.interrupt_event.wait(0.3)
        pyautogui.keyUp('c')
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
    """換層前靠近傳送點的分派器：遠則瞬移，近則步行。無 wait。"""

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
        elif dist > 0.1:
            self._queue.put(GoUpTeleportCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))
        else:
            self._queue.put(GoUpWalkCommand(self._char, self._queue, self._teleport_x, self._direction, self._layer))


class GoUpTeleportCommand(Command):
    """瞬移靠近換層傳送點。"""

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
        _logger.info(f'[NORMAL][GoUpTeleport] →{move_dir}')
        pyautogui.keyDown(move_dir)
        pyautogui.keyDown('c')
        self.interrupt_event.wait(0.3)
        pyautogui.keyUp('c')
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
        pyautogui.keyDown('x')
        self.interrupt_event.wait(0.4)
        pyautogui.keyUp('x')

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


# ── SkyAngry ──────────────────────────────────────────────────────

_SKY_ANGRY_X_CENTER = 0.40
_SKY_ANGRY_X_TOL    = 0.05


def sky_angry_position_ok(char) -> bool:
    """角色是否在天怒可施放位置（mid/bot 層，x ∈ [0.35, 0.45]）。"""
    return (_get_layer(char) in ('mid', 'bot') and
            _SKY_ANGRY_X_CENTER - _SKY_ANGRY_X_TOL
            <= char.map_x <=
            _SKY_ANGRY_X_CENTER + _SKY_ANGRY_X_TOL)


class SkyAngryCommand(Command):
    """
    天怒（攻擊技能）：施放條件如下，任一不符則靜默跳過：
      - HP 滿血（>= 100%）
      - MP > 50%
      - 位於第二層（mid）或第三層（bot）
      - 小地圖 x 在 0.35 ~ 0.45
    施放方式：按住 d 1 秒（priority，可被更高優先中斷）。
    """
    _queued: 'SkyAngryCommand | None' = None  # 追蹤 queue 中的實例，防止重複入隊

    def __init__(self, char):
        super().__init__(CommandType.CONDITION)
        self._char = char

    @classmethod
    def release(cls):
        cls._queued = None

    @classmethod
    def _try_enqueue(cls, q: queue.Queue, char):
        if cls._queued is not None:
            _logger.info('[PRIORITY][SkyAngry] 已在 queue 中，略過')
            return
        obj = cls(char)
        cls._queued = obj
        q.put(obj)

    def trigger_command(self):
        self.interrupt_event.clear()

        hp    = GameCharacter._shared_hp
        mp    = GameCharacter._shared_mp
        layer = _get_layer(self._char)
        x     = self._char.map_x

        if (hp < 100.0 or mp <= 50.0 or
                layer not in ('mid', 'bot') or
                not (_SKY_ANGRY_X_CENTER - _SKY_ANGRY_X_TOL
                     <= x <=
                     _SKY_ANGRY_X_CENTER + _SKY_ANGRY_X_TOL)):
            _logger.info(f'[PRIORITY][SkyAngry] 條件不足，跳過 '
                  f'hp={hp:.1f}% mp={mp:.1f}% layer={layer} x={x:.2f}')
            SkyAngryCommand._queued = None
            return

        _logger.info(f'[PRIORITY][SkyAngry] 天怒施放 '
              f'hp={hp:.1f}% mp={mp:.1f}% layer={layer} x={x:.2f}')
        pyautogui.keyDown('d')
        self.interrupt_event.wait(1.0)
        pyautogui.keyUp('d')

        if self.interrupt_event.is_set():
            _logger.info('[PRIORITY][SkyAngry] 被打斷')
        else:
            _logger.info('[PRIORITY][SkyAngry] 完成')
        SkyAngryCommand._queued = None
