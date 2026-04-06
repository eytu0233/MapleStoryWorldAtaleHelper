import abc
import threading
from enum import Enum, auto


class CommandType(Enum):
    NORMAL    = auto()
    CONDITION = auto()


class Command(abc.ABC):
    def __init__(self, command_type: CommandType):
        self.command_type = command_type
        if command_type == CommandType.CONDITION:
            self.interrupt_event = threading.Event()
        else:
            self.interrupt_event = None

    def interrupt_command(self):
        if self.interrupt_event is not None:
            self.interrupt_event.set()

    @abc.abstractmethod
    def trigger_command(self):
        ...

    @abc.abstractmethod
    def release(self):
        """釋放此 Command 持有的所有外部資源（callback、timer、class 追蹤變數等）。
        Archbishop 停止時統一呼叫。無外部資源者實作為 pass。"""
        ...

