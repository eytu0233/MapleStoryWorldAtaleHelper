import abc
import queue

from .Command import Command
from .GameCharacter import GameCharacter, Position

_LEVEL_NORMAL   = 0
_LEVEL_PRIORITY = 1
_LEVEL_EMERG    = 2


class _NotifyQueue(queue.Queue):
    """在 put / put_nowait 時通知 CommandGameCharacter 嘗試打斷 current command。"""

    def __init__(self, owner: 'CommandGameCharacter', level: int):
        super().__init__()
        self._owner = owner
        self._level = level

    def _notify(self):
        cmd = self._owner.current_command
        if cmd is not None and self._owner._current_command_level < self._level:
            cmd.interrupt_command()

    def put(self, item, block=True, timeout=None):
        super().put(item, block, timeout)
        self._notify()

    def put_nowait(self, item):
        super().put_nowait(item)
        self._notify()


class CommandGameCharacter(GameCharacter, abc.ABC):
    """
    以 Command 佇列驅動的角色基底類別。
    task() 迴圈依 emerg > priority > normal 優先順序取出 Command，
    依序執行 trigger_command → post_command。

    打斷規則：
    - emerg 入隊   → 打斷任何 current command
    - priority 入隊 → 只打斷 normal current command
    - normal 入隊  → 不打斷
    """

    def __init__(self, name: str,
                 position: Position = None):
        super().__init__(name, position)
        self.command_queue          = _NotifyQueue(self, _LEVEL_NORMAL)
        self.priority_command_queue = _NotifyQueue(self, _LEVEL_PRIORITY)
        self.emerg_command_queue    = _NotifyQueue(self, _LEVEL_EMERG)
        self.current_command: Command | None = None
        self._current_command_level: int = _LEVEL_NORMAL

    @abc.abstractmethod
    def task_prepare(self):
        ...

    def start_event_notify(self):
        GameCharacter._active_instance = self
        self.task_prepare()

    def stop_event_notify(self):
        if GameCharacter._active_instance is self:
            GameCharacter._active_instance = None
        if self.current_command is not None:
            self.current_command.interrupt_command()

    def _next_command(self) -> tuple[Command, int] | tuple[None, None]:
        for q, level in (
            (self.emerg_command_queue,    _LEVEL_EMERG),
            (self.priority_command_queue, _LEVEL_PRIORITY),
            (self.command_queue,          _LEVEL_NORMAL),
        ):
            try:
                return q.get_nowait(), level
            except queue.Empty:
                continue
        return None, None

    def task(self):
        while True:
            cmd, level = self._next_command()
            if cmd is None:
                if self.wait_stop_event(0.05):
                    return
                continue
            self.current_command = cmd
            self._current_command_level = level
            cmd.trigger_command()
            self.current_command = None
            self._current_command_level = _LEVEL_NORMAL
            if self.stop_event.is_set():
                return
