import threading
import time
from collections import deque
from enum import Enum, auto

import pyautogui

from controller.GameCharacter import GameCharacter

SKILL1_INTERVAL = 120
SKILL2_INTERVAL = 60
MOVE_INTERVAL   = 90
STEP_INTERVAL   = 15     # 攻擊開始後幾秒觸發一次移動

_STEP_X_LEFT  = 0.98    # 右邊界
_STEP_X_RIGHT = 0.66    # 左邊界
_STEP_POLL    = 0.1     # 移動按鍵間隔（秒）

Z_CHECK_CHUNK = 5


class State(Enum):
    ATTACK = auto()
    MOVE = auto()
    STEP = auto()
    AUX = auto()


class BowmasterTask(GameCharacter):
    def __init__(self):
        super().__init__(name='Bowmaster')
        self.skill_ref_time = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self._step_dir = 'left'
        self._event_queue: deque = deque()
        self._timer_stop = threading.Event()
        self._step_gen = 0

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return self._hold_key('z', 1.0)

    def _start_aux_timers(self):
        self._timer_stop.clear()

        def timer_loop(interval, state, aux_skill):
            while not self._timer_stop.wait(interval):
                print(f"[BowmasterTask] Timer fired: {state} aux_skill={aux_skill}")
                self._event_queue.append((state, aux_skill))

        for interval, state, aux_skill in [
            (SKILL1_INTERVAL, State.AUX,  1),
            (SKILL2_INTERVAL, State.AUX,  2),
            (MOVE_INTERVAL,   State.MOVE, None),
        ]:
            threading.Thread(target=timer_loop, args=(interval, state, aux_skill), daemon=True).start()

    def _schedule_step(self):
        """攻擊開始時呼叫，倒數 STEP_INTERVAL 秒後加入移動事件。"""
        self._step_gen += 1
        gen = self._step_gen
        timer_stop = self._timer_stop

        def fire():
            if not timer_stop.wait(STEP_INTERVAL) and self._step_gen == gen:
                print("[BowmasterTask] Step timer fired")
                self._event_queue.append((State.STEP, None))

        threading.Thread(target=fire, daemon=True).start()

    def _cancel_timers(self):
        self._step_gen += 1
        self._timer_stop.set()

    # --- InitState ---

    def _init_pre(self):
        print("[BowmasterTask] InitState: pre")

    def _init_process(self) -> bool:
        print("[BowmasterTask] InitState: process")
        if self._hold_key('1', 1):
            return True
        if self._hold_key('2', 1):
            return True
        self.skill_ref_time = time.time()
        self.last_skill1 = self.skill_ref_time
        self.last_skill2 = self.skill_ref_time
        return False

    def _init_post(self) -> bool:
        print("[BowmasterTask] InitState: post")
        return self.wait_stop_event(1)

    # --- AttackState ---

    def _attack_pre(self) -> bool:
        print("[BowmasterTask] AttackState: pre")
        self._schedule_step()
        if self.wait_stop_event(0.5):
            return True
        pyautogui.keyDown('z')
        return False

    def _attack_post(self):
        print("[BowmasterTask] AttackState: post")
        pyautogui.keyUp('z')

    # --- MoveState ---

    def _move_pre(self) -> bool:
        print("[BowmasterTask] MoveState: pre")
        return self.wait_stop_event(0.5)

    def _move_process(self) -> bool:
        print("[BowmasterTask] MoveState: process")
        if self._hold_key('left', 1.5):
            return True
        if self._hold_key('right', 3):
            return True
        return False

    def _move_post(self):
        print("[BowmasterTask] MoveState: post")
        for _ in range(3):
            pyautogui.press('left')

    # --- StepState ---

    def _step_process(self) -> bool:
        """
        在 0.66 ~ 0.98 之間巡邏。
        - x >= 0.98 → 往左直到 x <= 0.66
        - x <= 0.66 → 往右直到 x >= 0.98
        - 其他      → 維持方向，直到碰到對應邊界
        到達右邊界（x >= 0.98）後往左 0.2 秒再回攻擊。

        Returns:
            True 表示收到停止訊號（task 應結束）。
        """
        x = self.map_x
        if x >= _STEP_X_LEFT:
            self._step_dir = 'left'
        elif x <= _STEP_X_RIGHT:
            self._step_dir = 'right'

        if self._step_dir == 'left':
            stop_condition = lambda cx, cy: cx <= _STEP_X_RIGHT
        else:
            stop_condition = lambda cx, cy: cx >= _STEP_X_LEFT

        stop_event = threading.Event()
        mt = self.minimap_task
        eid = mt.register_pos_event(stop_condition, stop_event.set, once=True)

        print(f"[BowmasterTask] StepState: dir={self._step_dir} x={x:.3f}")
        try:
            while not stop_event.is_set():
                if self._hold_key(self._step_dir, _STEP_POLL):
                    return True
        finally:
            mt.unregister_pos_event(eid)

        end_x = self.map_x
        print(f"[BowmasterTask] StepState: done x={end_x:.3f}")
        if end_x >= _STEP_X_LEFT:
            print("[BowmasterTask] StepState: at right boundary, reversing left 0.2s")
            if self._hold_key('left', 0.2):
                return True
        return False

    # --- AuxState ---

    def _aux_process(self, skill: int) -> bool:
        print(f"[BowmasterTask] AuxState: process (skill={skill})")
        if skill == 1:
            if self._hold_key('1', 1):
                return True
            if self._hold_key('1', 1):
                return True
            self.last_skill1 = time.time()
        else:
            if self._hold_key('2', 1):
                return True
            self.last_skill2 = time.time()
        return False

    # --- State machine runner ---

    def task(self):
        print("BowmasterTask starting")
        self._event_queue.clear()
        self._start_aux_timers()

        self._init_pre()
        if self._init_process():
            self._cancel_timers()
            print("BowmasterTask end")
            return
        if self._init_post():
            self._cancel_timers()
            print("BowmasterTask end")
            return

        state = State.ATTACK
        aux_skill = None

        while True:
            if state == State.ATTACK:
                if self._attack_pre():
                    break

                stopped = False
                while True:
                    if self.wait_stop_event(Z_CHECK_CHUNK):
                        stopped = True
                        break
                    if self._event_queue:
                        state, aux_skill = self._event_queue.popleft()
                        print(f"[BowmasterTask] AttackState: → {state} aux_skill={aux_skill}")
                        break

                self._attack_post()
                if stopped:
                    break

            elif state == State.MOVE:
                if self._move_pre():
                    break
                if self._move_process():
                    break
                self._move_post()
                state, aux_skill = self._event_queue.popleft() if self._event_queue else (State.ATTACK, None)

            elif state == State.STEP:
                if self._step_process():
                    break
                state, aux_skill = State.ATTACK, None

            elif state == State.AUX:
                if self._aux_process(aux_skill):
                    break
                state, aux_skill = self._event_queue.popleft() if self._event_queue else (State.ATTACK, None)

        self._cancel_timers()
        print("BowmasterTask end")
