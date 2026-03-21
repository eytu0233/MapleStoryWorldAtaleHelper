import abc
from dataclasses import dataclass, field
from enum import Enum, auto

import pyautogui

from MapleTask import MapleTask
from character_control import ArtaleController


class Job(Enum):
    BOWMASTER = auto()
    PRIEST = auto()
    SCHOLAR = auto()


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0


class GameCharacter(MapleTask, abc.ABC):
    def __init__(self, name: str, job: Job, hp: int = 100, mp: int = 100,
                 position: Position = None, config_path: str = "board_config.json"):
        super().__init__()
        self.name = name
        self.job = job
        self.hp = hp
        self.mp = mp
        self.position = position if position is not None else Position()
        self.controller = ArtaleController(config_path)

    def _hold_key(self, key: str, duration: float) -> bool:
        """Hold key for duration seconds. Returns True if stop event fired."""
        pyautogui.keyDown(key)
        stopped = self.wait_stop_event(duration)
        pyautogui.keyUp(key)
        return stopped

    def update_position(self, x: float, y: float):
        self.position.x = x
        self.position.y = y

    @abc.abstractmethod
    def move(self, direction: str) -> bool:
        """Move in the given direction ('left'/'right'/'up'/'down'). Returns True if stopped."""
        ...

    @abc.abstractmethod
    def normal_attack(self) -> bool:
        """Perform a normal attack. Returns True if stopped."""
        ...

    @abc.abstractmethod
    def task(self):
        """Main automation loop. Must be implemented by subclasses."""
        ...

    def __repr__(self):
        return (f"{self.__class__.__name__}(name={self.name!r}, job={self.job.name}, "
                f"hp={self.hp}, mp={self.mp}, pos={self.position!r})")
