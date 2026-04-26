import threading
import time
from collections import deque
from enum import Enum, auto

import pyautogui

from controller.GameCharacter import GameCharacter
from util.logger import MSLogger

_logger = MSLogger('BowmasterTask')

SKILL1_INTERVAL = 300
SKILL2_INTERVAL = 60
SKILL3_INTERVAL = 300
SKILL4_INTERVAL = 180
MOVE_INTERVAL   = 90
STEP_INTERVAL   = 16     # 每幾秒強制巡邏一次（週期計時）
DRIFT_INTERVAL  = 8      # 攻擊開始後幾秒往左飄移
DRIFT_DURATION  = 0.4    # 往左飄移持續秒數

_STEP_X_LEFT  = 0.84    # 右邊界
_STEP_X_RIGHT = 0.66    # 左邊界
_STEP_POLL    = 0.1     # 移動按鍵間隔（秒）

Z_CHECK_CHUNK = 5


class State(Enum):
    ATTACK = auto()
    MOVE = auto()
    STEP = auto()
    AUX = auto()
    DRIFT = auto()


class BowmasterTask(GameCharacter):
    def __init__(self):
        super().__init__(name='Bowmaster')
        self.skill_ref_time = 0
        self.last_skill1 = 0
        self.last_skill2 = 0
        self._event_queue: deque = deque()
        self._timer_stop = threading.Event()
        self._step_pending = False
        self._step_gen = 0
        self._drift_gen = 0

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return self._hold_key('z', 1.0)

    def _start_aux_timers(self):
        self._timer_stop.clear()
        self._step_pending = False

        def timer_loop(interval, state, aux_skill):
            while not self._timer_stop.wait(interval):
                _logger.info(f"[BowmasterTask] Timer fired: {state} aux_skill={aux_skill}")
                self._event_queue.append((state, aux_skill))

        for interval, state, aux_skill in [
            (SKILL1_INTERVAL, State.AUX,  1),
            (SKILL2_INTERVAL, State.AUX,  2),
            (SKILL3_INTERVAL, State.AUX,  3),
            (SKILL4_INTERVAL, State.AUX,  4),
            (MOVE_INTERVAL,   State.MOVE, None),
        ]:
            threading.Thread(target=timer_loop, args=(interval, state, aux_skill), daemon=True).start()

    def _schedule_step(self):
        """巡邏完成後呼叫，倒數 STEP_INTERVAL 秒後觸發下一次巡邏。"""
        self._step_gen += 1
        gen = self._step_gen
        timer_stop = self._timer_stop

        def fire():
            if not timer_stop.wait(STEP_INTERVAL) and self._step_gen == gen:
                _logger.info("[BowmasterTask] Step timer fired")
                self._step_pending = True

        threading.Thread(target=fire, daemon=True).start()

    def _schedule_drift(self):
        """攻擊開始時呼叫，倒數 DRIFT_INTERVAL 秒後加入往左飄移事件。"""
        self._drift_gen += 1
        gen = self._drift_gen
        timer_stop = self._timer_stop

        def fire():
            if not timer_stop.wait(DRIFT_INTERVAL) and self._drift_gen == gen:
                _logger.info("[BowmasterTask] Drift timer fired")
                self._event_queue.append((State.DRIFT, None))

        threading.Thread(target=fire, daemon=True).start()

    def _cancel_timers(self):
        self._step_gen += 1
        self._drift_gen += 1
        self._step_pending = False
        self._timer_stop.set()

    # --- InitState ---

    def _init_pre(self):
        _logger.info("[BowmasterTask] InitState: pre")

    def _init_process(self) -> bool:
        _logger.info("[BowmasterTask] InitState: process")
        if self._hold_key('1', 1):
            return True
        if self._hold_key('2', 1):
            return True
        self.skill_ref_time = time.time()
        self.last_skill1 = self.skill_ref_time
        self.last_skill2 = self.skill_ref_time
        return False

    def _init_post(self) -> bool:
        _logger.info("[BowmasterTask] InitState: post")
        return self.wait_stop_event(1)

    # --- AttackState ---

    def _attack_pre(self, arm_drift: bool = False) -> bool:
        _logger.info("[BowmasterTask] AttackState: pre")
        if arm_drift:
            self._schedule_drift()
        if self._hold_key('left', 0.05):
            return True
        if self.wait_stop_event(0.5):
            return True
        pyautogui.keyDown('z')
        return False

    def _attack_post(self):
        _logger.info("[BowmasterTask] AttackState: post")
        pyautogui.keyUp('z')

    # --- MoveState ---

    def _move_pre(self) -> bool:
        _logger.info("[BowmasterTask] MoveState: pre")
        return self.wait_stop_event(0.5)

    def _move_process(self) -> bool:
        _logger.info("[BowmasterTask] MoveState: process")
        if self._hold_key('left', 1.5):
            return True
        if self._hold_key('right', 3):
            return True
        return False

    def _move_post(self):
        _logger.info("[BowmasterTask] MoveState: post")
        for _ in range(3):
            pyautogui.press('left')

    # --- StepState ---

    def _step_move_to(self, direction: str, condition) -> bool:
        """
        持續按住 direction 直到 condition(x, y) 成立或收到停止訊號。
        Returns True 表示收到停止訊號。
        """
        stop_event = threading.Event()
        mt = self.minimap_task
        eid = mt.register_pos_event(condition, stop_event.set, once=True)
        try:
            while not stop_event.is_set():
                if self._hold_key(direction, _STEP_POLL):
                    return True
        finally:
            mt.unregister_pos_event(eid)
        return False

    def _step_process(self) -> bool:
        """
        巡邏：先往左走到左邊界，再往右走到右邊界。

        Returns:
            True 表示收到停止訊號（task 應結束）。
        """
        x = self.map_x
        _logger.info(f"[BowmasterTask] StepState: start x={x:.3f}")

        if x > _STEP_X_RIGHT:
            _logger.info("[BowmasterTask] StepState: move left to left boundary")
            if self._step_move_to('left', lambda cx, cy: cx <= _STEP_X_RIGHT):
                return True
            _logger.info(f"[BowmasterTask] StepState: reached left boundary x={self.map_x:.3f}")

        _logger.info("[BowmasterTask] StepState: move right to right boundary")
        if self._step_move_to('right', lambda cx, cy: cx >= _STEP_X_LEFT):
            return True
        _logger.info(f"[BowmasterTask] StepState: done x={self.map_x:.3f}")
        return False

    # --- DriftState ---

    def _drift_process(self) -> bool:
        _logger.info("[BowmasterTask] DriftState: move left 1s")
        return self._hold_key('left', DRIFT_DURATION)

    # --- AuxState ---

    def _aux_process(self, skill: int) -> bool:
        _logger.info(f"[BowmasterTask] AuxState: process (skill={skill})")
        if skill == 1:
            if self._hold_key('1', 1):
                return True
            if self._hold_key('1', 1):
                return True
            self.last_skill1 = time.time()
        elif skill == 2:
            if self._hold_key('2', 1):
                return True
            self.last_skill2 = time.time()
        elif skill == 3:
            if self._hold_key('3', 1):
                return True
        else:
            if self._hold_key('alt', 1):
                return True
        return False

    # --- State machine runner ---

    def task(self):
        _logger.info("BowmasterTask starting")
        self._event_queue.clear()
        self._start_aux_timers()

        self._init_pre()
        if self._init_process():
            self._cancel_timers()
            _logger.info("BowmasterTask end")
            return
        if self._init_post():
            self._cancel_timers()
            _logger.info("BowmasterTask end")
            return

        self._schedule_step()   # 任務啟動後 16 秒觸發首次巡邏

        state = State.ATTACK
        aux_skill = None
        arm_drift = True   # 首次進入 ATTACK 時排程 drift；STEP 完成後重新啟用

        while True:
            if state == State.ATTACK:
                if self._attack_pre(arm_drift=arm_drift):
                    break
                arm_drift = False   # 排程後關閉，直到下次 STEP 完成

                stopped = False
                while True:
                    if self.wait_stop_event(Z_CHECK_CHUNK):
                        stopped = True
                        break
                    if self._step_pending:
                        self._step_pending = False
                        state, aux_skill = State.STEP, None
                        _logger.info("[BowmasterTask] AttackState: → STEP (forced)")
                        break
                    if self._event_queue:
                        state, aux_skill = self._event_queue.popleft()
                        _logger.info(f"[BowmasterTask] AttackState: → {state} aux_skill={aux_skill}")
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
                self._schedule_step()  # 巡邏完成後才開始計算下一次
                state, aux_skill = State.ATTACK, None
                arm_drift = True   # 巡邏完成，下次 ATTACK 重新排程 drift

            elif state == State.DRIFT:
                if self._drift_process():
                    break
                state, aux_skill = State.ATTACK, None
                # arm_drift 不重設，drift 在下次巡邏前不再觸發

            elif state == State.AUX:
                if self._aux_process(aux_skill):
                    break
                state, aux_skill = self._event_queue.popleft() if self._event_queue else (State.ATTACK, None)

        self._cancel_timers()
        _logger.info("BowmasterTask end")
