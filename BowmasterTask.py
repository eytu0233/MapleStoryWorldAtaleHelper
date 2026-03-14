import threading
import time
from collections import deque
from enum import Enum, auto

import pyautogui

from DetectMarkerTask import DetectMarkerTask
from MapleTask import MapleTask

SKILL1_INTERVAL = 120
SKILL2_INTERVAL = 60
MOVE_INTERVAL = 90
STEP_INTERVAL = 15
Z_CHECK_CHUNK = 5


class State(Enum):
    ATTACK = auto()
    MOVE = auto()
    STEP = auto()
    AUX = auto()


class BowmasterTask(MapleTask):
    def __init__(self):
        super(BowmasterTask, self).__init__()
        self.detect_arrow_task = DetectMarkerTask()
        self.skill_ref_time = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self._event_queue: deque = deque()
        self._timer_stop = threading.Event()

    def start_event_notify(self):
        self.detect_arrow_task.start()

    def stop_event_notify(self):
        self.detect_arrow_task.stop()
        self.send_marker()

    def send_marker(self):
        time.sleep(0.5)
        pyautogui.press('enter')
        time.sleep(0.1)
        pyautogui.typewrite('/marker', interval=0.05)
        pyautogui.press('enter')

    def _hold_key(self, key, duration) -> bool:
        """Hold key for duration seconds. Returns True if stop event fired."""
        pyautogui.keyDown(key)
        stopped = self.wait_stop_event(duration)
        pyautogui.keyUp(key)
        return stopped

    def _start_timers(self):
        self._timer_stop.clear()

        def timer_loop(interval, state, aux_skill):
            while not self._timer_stop.wait(interval):
                print(f"[BowmasterTask] Timer fired: {state} aux_skill={aux_skill}")
                self._event_queue.append((state, aux_skill))

        for interval, state, aux_skill in [
            (SKILL1_INTERVAL, State.AUX,  1),
            (SKILL2_INTERVAL, State.AUX,  2),
            (MOVE_INTERVAL,   State.MOVE, None),
            (STEP_INTERVAL,   State.STEP, None),
        ]:
            threading.Thread(target=timer_loop, args=(interval, state, aux_skill), daemon=True).start()

    def _cancel_timers(self):
        self._timer_stop.set()

    # --- InitState ---

    def _init_pre(self):
        print("[BowmasterTask] InitState: pre")
        self.send_marker()
        time.sleep(0.1)

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

    def _step_process(self):
        print("[BowmasterTask] StepState: process")
        for _ in range(3):
            pyautogui.press('left')

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
        self._start_timers()

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

                # Hold z, yield to event queue each chunk
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
                self._step_process()
                state, aux_skill = self._event_queue.popleft() if self._event_queue else (State.ATTACK, None)

            elif state == State.AUX:
                if self._aux_process(aux_skill):
                    break
                state, aux_skill = self._event_queue.popleft() if self._event_queue else (State.ATTACK, None)

        self._cancel_timers()
        print("BowmasterTask end")
