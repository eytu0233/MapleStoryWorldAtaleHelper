import threading
from typing import Optional

from controller.CommandGameCharacter import CommandGameCharacter
from controller.GameCharacter import GameCharacter
from discord_bot.discord_bot import DiscordBot
from job.ArchbishopCommand import (HolySymbol, AngelBlessing, HolyLight, MapleBlessing,
                                   HealCommand, DragonCommand, SearchStepCommand,
                                   AttackCommand, SkyAngryCommand, sky_angry_position_ok)

_BUFF_INTERVAL           = 270   # 秒
_DRAGON_INTERVAL         = 90    # 秒
_SKY_ANGRY_COOLDOWN      = 15.0  # 秒
_HP_DEAD_NOTIFY_INTERVAL = 300   # 秒（5 分鐘）


class Archbishop(CommandGameCharacter):

    def __init__(self, discord_bot: Optional[DiscordBot] = None):
        super().__init__(name='Archbishop')
        self._discord_bot                                   = discord_bot
        self._sky_angry_eid: int | None                    = None
        self._attack_cmd: AttackCommand | None             = None
        self._attack_initial_timer: threading.Timer | None = None
        self._hp_dead_callback                             = None
        self._hp_notify_timer: threading.Timer | None      = None

    def _on_hp_dead(self):
        """HP 歸零初次觸發：立即通知，並啟動每 5 分鐘的重複通知。"""
        if self._discord_bot is None:
            return
        self._discord_bot.notify('⚠️ Archbishop HP 歸零！角色可能已死亡。')
        self._schedule_hp_dead_repeat()

    def _schedule_hp_dead_repeat(self):
        """若 HP 仍 < 1%，每 5 分鐘再次通知。"""
        self._hp_notify_timer = threading.Timer(_HP_DEAD_NOTIFY_INTERVAL, self._hp_dead_repeat_check)
        self._hp_notify_timer.daemon = True
        self._hp_notify_timer.start()

    def _hp_dead_repeat_check(self):
        if GameCharacter._shared_hp < 1.0:
            self._discord_bot.notify('⚠️ Archbishop HP 仍為 0！角色可能仍在死亡狀態。')
            self._schedule_hp_dead_repeat()
        # HP 已恢復，不再重複

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
        HealCommand.release()
        SkyAngryCommand.release()
        if self._hp_dead_callback is not None:
            GameCharacter.unregister_hp_callback(self._hp_dead_callback)
            self._hp_dead_callback = None
        if self._hp_notify_timer is not None:
            self._hp_notify_timer.cancel()
            self._hp_notify_timer = None
        print("Clear queue")

    # ── 抽象方法實作 ─────────────────────────────────────────────

    def task_prepare(self):
        # ── 重置所有 Command 類別狀態，確保重新啟動時乾淨 ──────────
        HealCommand.release()
        SkyAngryCommand.release()
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
        if self._sky_angry_eid is not None:
            GameCharacter.unregister_composite_event(self._sky_angry_eid)
            self._sky_angry_eid = None

        # ── 建立全新 Command 實例並初始化 ───────────────────────────
        if self._discord_bot is not None:
            print("Register dead monitor")
            cb = self._on_hp_dead
            self._hp_dead_callback = cb
            GameCharacter.register_hp_callback(1.0, cb, condition='below')
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
            callback=lambda: SkyAngryCommand._try_enqueue(self.priority_command_queue, self),
            cooldown=_SKY_ANGRY_COOLDOWN,
        )
        self._attack_cmd = AttackCommand(self.priority_command_queue)
        self._attack_initial_timer = threading.Timer(2.0, self.priority_command_queue.put, args=(self._attack_cmd,))
        self._attack_initial_timer.daemon = True
        self._attack_initial_timer.start()

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 0.3)

    def normal_attack(self) -> bool:
        return self._hold_key('x', 0.1)
