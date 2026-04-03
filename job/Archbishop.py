import threading

from controller.CommandGameCharacter import CommandGameCharacter
from controller.GameCharacter import GameCharacter
from job.ArchbishopCommand import (HolySymbol, AngelBlessing, HolyLight, MapleBlessing,
                                   HealCommand, DragonCommand, SearchStepCommand,
                                   AttackCommand, SkyAngryCommand, sky_angry_position_ok)

_BUFF_INTERVAL      = 270  # 秒
_DRAGON_INTERVAL    = 90   # 秒
_SKY_ANGRY_COOLDOWN = 2.0  # 秒


class Archbishop(CommandGameCharacter):

    def __init__(self):
        super().__init__(name='Archbishop')
        self._sky_angry_eid: int | None = None

    def _enqueue_buffs(self):
        for cmd in (HolySymbol(), AngelBlessing(), HolyLight(), MapleBlessing()):
            self.priority_command_queue.put(cmd)
        self._buff_timer = threading.Timer(_BUFF_INTERVAL, self._enqueue_buffs)
        self._buff_timer.daemon = True
        self._buff_timer.start()

    def _enqueue_dragon(self):
        self.priority_command_queue.put(DragonCommand())
        self._dragon_timer = threading.Timer(_DRAGON_INTERVAL, self._enqueue_dragon)
        self._dragon_timer.daemon = True
        self._dragon_timer.start()

    def stop(self):
        if hasattr(self, '_buff_timer'):
            self._buff_timer.cancel()
        if hasattr(self, '_dragon_timer'):
            self._dragon_timer.cancel()
        if self._sky_angry_eid is not None:
            GameCharacter.unregister_composite_event(self._sky_angry_eid)
            self._sky_angry_eid = None
        super().stop()

    # ── 抽象方法實作 ─────────────────────────────────────────────

    def task_prepare(self):
        HealCommand(self.emerg_command_queue)
        self.command_queue.put(SearchStepCommand(self, self.command_queue))
        self._enqueue_buffs()
        self._enqueue_dragon()
        self._sky_angry_eid = GameCharacter.register_composite_event(
            condition=lambda: (
                GameCharacter._shared_hp >= 100.0 and
                GameCharacter._shared_mp > 50.0 and
                sky_angry_position_ok(self)
            ),
            callback=lambda: self.priority_command_queue.put(SkyAngryCommand(self)),
            cooldown=_SKY_ANGRY_COOLDOWN,
        )
        t = threading.Timer(2.0, self.priority_command_queue.put, args=(AttackCommand(self.priority_command_queue),))
        t.daemon = True
        t.start()

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 0.3)

    def normal_attack(self) -> bool:
        return self._hold_key('x', 0.1)
