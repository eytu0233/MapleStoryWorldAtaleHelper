import random
import threading
import time
from collections import deque
from enum import Enum, auto

import pyautogui

from GameCharacter import GameCharacter, Job

SKILL1_INTERVAL = 270
SKILL2_INTERVAL = 270
SKILL3_INTERVAL = 270
SKILLX_INTERVAL_MIN = 10
SKILLX_INTERVAL_MAX = 30
STEP_INTERVAL = 10       # 攻擊開始後幾秒觸發一次移動

_STEP_X_LEFT  = 0.90    # 右邊界
_STEP_X_RIGHT = 0.02    # 左邊界
_STEP_POLL    = 0.1     # 移動按鍵間隔（秒）

AUX_INTERVAL  = 0.6

C_CHECK_CHUNK = 15


class State(Enum):
    ATTACK = auto()
    STEP = auto()
    AUX = auto()


class GhostWomen(GameCharacter):
    def __init__(self):
        super().__init__(name='GhostWomen', job=Job.GHOSTWOMEN)
        self.skill_ref_time = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self.last_skill3 = 0
        self._step_dir = 'left'
        self._first_stop_after_boundary = False   # 到達邊界後下次第一次停下多等 2 秒
        self._event_queue: deque = deque()
        self._timer_stop = threading.Event()
        self._step_gen = 0   # 用來取消舊的 step 計時器

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return self._hold_key('z', 1.0)

    def _pop_event(self):
        """Pop from event queue, prioritising AUX 1/2/3 over others."""
        for i, (s, sk) in enumerate(self._event_queue):
            if s == State.AUX and sk in (1, 2, 3):
                del self._event_queue[i]
                return s, sk
        return self._event_queue.popleft()

    # --- Timers ---

    def _start_aux_timers(self):
        """啟動輔助技能定時器（SKILL1/2/3 + 隨機 x）。不含移動計時器。"""
        self._timer_stop.clear()

        def timer_loop(interval, state, aux_skill):
            while not self._timer_stop.wait(interval):
                print(f"[GhostWomen] Timer fired: {state} aux_skill={aux_skill}")
                self._event_queue.append((state, aux_skill))

        def random_timer_loop():
            while True:
                interval = random.uniform(SKILLX_INTERVAL_MIN, SKILLX_INTERVAL_MAX)
                if self._timer_stop.wait(interval):
                    break
                print(f"[GhostWomen] Timer fired: {State.AUX} aux_skill=x")
                self._event_queue.append((State.AUX, 'x'))

        for interval, state, aux_skill in [
            (SKILL1_INTERVAL, State.AUX, 1),
            (SKILL2_INTERVAL, State.AUX, 2),
            (SKILL3_INTERVAL, State.AUX, 3),
        ]:
            threading.Thread(target=timer_loop, args=(interval, state, aux_skill), daemon=True).start()

        threading.Thread(target=random_timer_loop, daemon=True).start()

    def _schedule_step(self):
        """攻擊開始時呼叫，倒數 STEP_INTERVAL 秒後加入移動事件。"""
        self._step_gen += 1
        gen = self._step_gen
        timer_stop = self._timer_stop

        def fire():
            if not timer_stop.wait(STEP_INTERVAL) and self._step_gen == gen:
                print("[GhostWomen] Step timer fired")
                self._event_queue.append((State.STEP, None))

        threading.Thread(target=fire, daemon=True).start()

    def _cancel_timers(self):
        self._step_gen += 1   # 使所有待命的 step 計時器失效
        self._timer_stop.set()

    # --- InitState ---

    def _init_pre(self):
        print("[GhostWomen] InitState: pre")

    def _init_process(self) -> bool:
        print("[GhostWomen] InitState: process")
        if self._hold_key('1', AUX_INTERVAL):
            return True
        if self._hold_key('2', AUX_INTERVAL):
            return True
        if self._hold_key('3', AUX_INTERVAL):
            return True
        self.skill_ref_time = time.time()
        self.last_skill1 = self.skill_ref_time
        self.last_skill2 = self.skill_ref_time
        self.last_skill3 = self.skill_ref_time
        return False

    def _init_post(self) -> bool:
        print("[GhostWomen] InitState: post")
        return self.wait_stop_event(1)

    # --- AttackState ---

    def _attack_pre(self) -> bool:
        print("[GhostWomen] AttackState: pre")
        self._schedule_step()   # 攻擊開始，重新計時 10 秒
        if self.wait_stop_event(0.5):
            return True
        pyautogui.keyDown('z')
        return False

    def _attack_post(self):
        print("[GhostWomen] AttackState: post")
        pyautogui.keyUp('z')

    # --- StepState ---

    def _step_process(self) -> bool:
        """
        在 0.55 ~ 0.98 之間巡邏。
        - x >= 0.98 → 往左直到 x <= 0.55
        - x <= 0.55 → 往右直到 x >= 0.98
        - 其他      → 維持方向，直到碰到對應邊界
        到達邊界後反向移動 0.2 秒再回攻擊。

        Returns:
            True 表示收到停止訊號（task 應結束）。
        """
        x = self.map_x
        if x >= _STEP_X_LEFT:
            self._step_dir = 'left'
        elif x <= _STEP_X_RIGHT:
            self._step_dir = 'right'
        else:
            self._step_dir = 'right' if x < 0.5 else 'left'

        if self._step_dir == 'left':
            stop_condition = lambda cx, cy: cx <= _STEP_X_RIGHT
        else:
            stop_condition = lambda cx, cy: cx >= _STEP_X_LEFT

        stop_event = threading.Event()
        mt = self.minimap_task
        eid = mt.register_pos_event(stop_condition, stop_event.set, once=True)

        print(f"[GhostWomen] StepState: dir={self._step_dir} x={x:.3f}")
        try:
            while not stop_event.is_set():
                # 移動 1 秒
                elapsed = 0.0
                while elapsed < 1.0 and not stop_event.is_set():
                    if self._hold_key(self._step_dir, _STEP_POLL):
                        return True
                    elapsed += _STEP_POLL
                if stop_event.is_set():
                    break
                # 停下來釋放 x 技能
                if self.wait_stop_event(0.1):
                    return True
                self._hold_key('x', AUX_INTERVAL)
                # 邊界後第一次停下多等 2 秒撿道具
                if self._first_stop_after_boundary:
                    self._first_stop_after_boundary = False
                    if self.wait_stop_event(2.0):
                        return True
        finally:
            mt.unregister_pos_event(eid)

        end_x = self.map_x
        print(f"[GhostWomen] StepState: done x={end_x:.3f}")
        if end_x >= _STEP_X_LEFT or end_x <= _STEP_X_RIGHT:
            self._first_stop_after_boundary = True
            reverse_dir = 'right' if self._step_dir == 'left' else 'left'
            print(f"[GhostWomen] StepState: at boundary, reversing {reverse_dir} 0.2s")
            if self._hold_key(reverse_dir, 0.2):
                return True
        return False

    # --- AuxState ---

    def _aux_process(self, skill) -> bool:
        print(f"[GhostWomen] AuxState: process (skill={skill})")
        if self.wait_stop_event(0.5):
            return True
        if skill == 1:
            if self._hold_key('1', AUX_INTERVAL):
                return True
            self.last_skill1 = time.time()
        elif skill == 2:
            if self._hold_key('2', AUX_INTERVAL):
                return True
            self.last_skill2 = time.time()
        elif skill == 3:
            if self._hold_key('3', AUX_INTERVAL):
                return True
            self.last_skill3 = time.time()
        elif skill == 'x':
            if self.wait_stop_event(0):
                return True
            pyautogui.press('x')
        return False

    # --- State machine runner ---

    def task(self):
        print("GhostWomen starting")
        self._event_queue.clear()
        self._start_aux_timers()

        self._init_pre()
        if self._init_process():
            self._cancel_timers()
            print("GhostWomen end")
            return
        if self._init_post():
            self._cancel_timers()
            print("GhostWomen end")
            return

        state = State.ATTACK
        aux_skill = None

        while True:
            if state == State.ATTACK:
                if self._attack_pre():
                    break

                stopped = False
                while True:
                    if self.wait_stop_event(C_CHECK_CHUNK):
                        stopped = True
                        break
                    if self._event_queue:
                        state, aux_skill = self._pop_event()
                        print(f"[GhostWomen] AttackState: → {state} aux_skill={aux_skill}")
                        break

                self._attack_post()
                if stopped:
                    break

            elif state == State.STEP:
                if self._step_process():
                    break
                state, aux_skill = State.ATTACK, None   # 移動後一律回攻擊

            elif state == State.AUX:
                if self._aux_process(aux_skill):
                    break
                state, aux_skill = self._pop_event() if self._event_queue else (State.ATTACK, None)

        self._cancel_timers()
        print("GhostWomen end")
