import abc
import queue

from Command import Command
from controller.GameCharacter import GameCharacter, Position


class CommandGameCharacter(GameCharacter, abc.ABC):
    """
    以 Command 佇列驅動的角色基底類別。
    task() 迴圈依 emerg > priority > normal 優先順序取出 Command，
    依序執行 trigger_command → post_command。
    """

    def __init__(self, name: str,
                 position: Position = None):
        super().__init__(name, position)
        self.command_queue: queue.Queue[Command] = queue.Queue()
        self.priority_command_queue: queue.Queue[Command] = queue.Queue()
        self.emerg_command_queue: queue.Queue[Command] = queue.Queue()
        self.current_command: Command | None = None

    @abc.abstractmethod
    def task_prepare(self):
        ...

    def start_event_notify(self):
        self.task_prepare()

    def _next_command(self) -> Command | None:
        for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
            try:
                return q.get_nowait()
            except queue.Empty:
                continue
        return None

    def task(self):
        while True:
            cmd = self._next_command()
            if cmd is None:
                if self.wait_stop_event(0.05):
                    return
                continue
            self.current_command = cmd
            cmd.trigger_command()
            cmd.post_command()
            self.current_command = None
            if self.stop_event.is_set():
                return
