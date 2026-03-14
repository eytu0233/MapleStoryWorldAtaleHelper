import threading
import time
from collections import deque
from enum import Enum, auto

import pyautogui

from MapleTask import MapleTask

AUX_INTERVAL = 270
Z_CHECK_CHUNK = 5


class State(Enum):
    INIT = auto()
    AUX = auto()
    ATTACK = auto()


class Priest(MapleTask):
    def __init__(self):
        super(Priest, self).__init__()
        self._event_queue: deque = deque()
        self._timer_stop = threading.Event()

    def _hold_key(self, key, duration) -> bool:
        """Hold key for duration seconds. Returns True if stop event fired."""
        pyautogui.keyDown(key)
        stopped = self.wait_stop_event(duration)
        pyautogui.keyUp(key)
        return stopped

    def _start_timers(self):
        self._timer_stop.clear()

        def timer_loop(interval, state):
            while not self._timer_stop.wait(interval):
                print(f"[Priest] Timer fired: {state}")
                self._event_queue.append((state, None))

        threading.Thread(target=timer_loop, args=(AUX_INTERVAL, State.AUX), daemon=True).start()

    def _cancel_timers(self):
        self._timer_stop.set()

    # --- InitState / AuxState (shared skills) ---

    def _release_skills(self) -> bool:
        """hold '5' → '1' → '2' each 1s. Returns True if stopped."""
        if self._hold_key('5', 1):
            return True
        if self._hold_key('1', 1):
            return True
        if self._hold_key('2', 1):
            return True
        return False

    def _init_process(self) -> bool:
        print("[Priest] InitState: process")
        return self._release_skills()

    def _aux_pre(self) -> bool:
        print("[Priest] AuxState: pre")
        return self.wait_stop_event(0.5)

    def _aux_process(self) -> bool:
        print("[Priest] AuxState: process")
        return self._release_skills()

    # --- AttackState ---

    def _attack_pre(self) -> bool:
        print("[Priest] AttackState: pre")
        if self.wait_stop_event(0.5):
            return True
        for _ in range(3):
            pyautogui.press('left')
        for _ in range(3):
            pyautogui.press('right')
        pyautogui.press('shift')
        return False

    def _attack_process(self) -> bool:
        print("[Priest] AttackState: process")
        return self._hold_key('d', 8)

    def _attack_post(self) -> bool:
        print("[Priest] AttackState: post")
        if self.wait_stop_event(1):
            return True
        pyautogui.press('0')
        return False

    # --- State machine runner ---

    def task(self):
        print("Priest starting")
        self._event_queue.clear()
        self._start_timers()

        # INIT
        if self._init_process():
            self._cancel_timers()
            print("Priest end")
            return

        state = State.ATTACK

        while True:
            if state == State.ATTACK:
                if self._attack_pre():
                    break
                if self._attack_process():
                    break
                if self._attack_post():
                    break

                # Idle-wait for next event
                print("[Priest] AttackState: idle, waiting for next event")
                while not self._event_queue:
                    if self.wait_stop_event(Z_CHECK_CHUNK):
                        self._cancel_timers()
                        print("Priest end")
                        return

                state, _ = self._event_queue.popleft()
                print(f"[Priest] → {state}")

            elif state == State.AUX:
                if self._aux_pre():
                    break
                if self._aux_process():
                    break
                state = State.ATTACK

        self._cancel_timers()
        print("Priest end")
