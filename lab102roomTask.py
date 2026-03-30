import time

import pyautogui

from controller.GameCharacter import GameCharacter

# ── 地圖座標（百分比，0~100）─────────────────────────────────────
_Y_UPPER_THRESH   = 25    # y < 此值 → 在2樓（可跳躍）

_X_CENTER         = 50    # 起始方向判斷中心
_X_TRIGGER_RIGHT  = 65    # 向右前進到此 x% 時上樓
_X_TRIGGER_LEFT   = 40    # 向左前進到此 x% 時上樓
_X_RIGHT_BOUNDARY = 98    # 2樓向右走到此 x% 後下跳
_X_LEFT_BOUNDARY  = 2     # 2樓向左走到此 x% 後下跳

_ATTACK_INTERVAL  = 1.2   # 平地攻擊間隔（秒）
_AUX_INTERVAL     = 270   # 輔助技能釋放間隔（秒）
_AUX_HOLD         = 0.6   # 輔助技能按住時間（秒）
_MOVE_POLL        = 0.1   # 移動輪詢間隔（秒）
_MOVE_POLL_NEAR   = 0.03  # 接近目標點時的步長（秒）
_NEAR_THRESHOLD   = 8     # 距觸發點幾% 內視為「接近」


class Lab102RoomTask(GameCharacter):
    def __init__(self):
        super().__init__(name='Lab102Room')

    @property
    def _px(self) -> float:
        return self.map_x * 100

    @property
    def _py(self) -> float:
        return self.map_y * 100

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return self._hold_key('z', 1.0)

    def _cast_aux(self) -> bool:
        """釋放輔助技能 1、2，回傳 True 表示收到停止訊號。"""
        for key in ('1', '2'):
            if self._hold_key(key, _AUX_HOLD):
                return True
        return False

    def _climb_to_upper(self) -> bool:
        """按住 alt+up 爬升，一旦 y < _Y_UPPER_THRESH 立刻放開按鍵。
        回傳 True 表示收到 stop 訊號。"""
        _CHECK_INTERVAL = 0.03
        _STALL_TIMEOUT  = 0.5

        pyautogui.keyDown('alt')
        pyautogui.keyDown('up')

        last_decrease_time = time.monotonic()
        last_y = self._py
        stopped = False

        try:
            while True:
                if self.wait_stop_event(_CHECK_INTERVAL):
                    stopped = True
                    break
                y = self._py
                if y < _Y_UPPER_THRESH:
                    break
                if y < last_y:
                    last_y = y
                    last_decrease_time = time.monotonic()
                elif time.monotonic() - last_decrease_time >= _STALL_TIMEOUT:
                    break
        finally:
            pyautogui.keyUp('up')
            pyautogui.keyUp('alt')

        return stopped

    # ── 上樓序列 ─────────────────────────────────────────────────

    def _ascend_right(self) -> bool:
        """停止 → 上樓 → 右跳 → 攻擊 → 走到 x>=98 → 下跳"""
        print("[Lab102RoomTask] 上樓序列（右）")
        if self.wait_stop_event(0.2):       # 先確保停止
            return True
        if self._climb_to_upper():
            return True
        if self.jump('right'):
            return True
        if self._hold_key('z', 1.0):
            return True
        if self.wait_stop_event(0.3):
            return True
        while self._px < _X_RIGHT_BOUNDARY:
            poll = _MOVE_POLL_NEAR if self._px >= _X_RIGHT_BOUNDARY - _NEAR_THRESHOLD else _MOVE_POLL
            if self._hold_key('right', poll):
                return True
        if self.move_down():
            return True
        return self.wait_stop_event(0.5)

    def _ascend_left(self) -> bool:
        """停止 → 上樓 → 左跳 → 攻擊 → 走到 x<=2 → 下跳"""
        print("[Lab102RoomTask] 上樓序列（左）")
        if self.wait_stop_event(0.2):       # 先確保停止
            return True
        if self._climb_to_upper():
            return True
        if self.jump('left'):
            return True
        if self._hold_key('z', 1.0):
            return True
        if self.wait_stop_event(0.3):
            return True
        while self._px > _X_LEFT_BOUNDARY:
            poll = _MOVE_POLL_NEAR if self._px <= _X_LEFT_BOUNDARY + _NEAR_THRESHOLD else _MOVE_POLL
            if self._hold_key('left', poll):
                return True
        if self.move_down():
            return True
        return self.wait_stop_event(0.5)

    # ── 主 Task ──────────────────────────────────────────────────

    def task(self):
        print("Lab102RoomTask starting")

        # 若不在平地，先下跳
        if self._py < _Y_UPPER_THRESH:
            print(f"[Lab102RoomTask] 不在平地（y={self._py:.1f}%），先下跳")
            if self.move_down():
                print("Lab102RoomTask end")
                return
            if self.wait_stop_event(0.5):
                print("Lab102RoomTask end")
                return

        # 起始釋放輔助技能
        if self._cast_aux():
            print("Lab102RoomTask end")
            return

        direction = 'left' if self._px > _X_CENTER else 'right'
        print(f"[Lab102RoomTask] 起始方向: {direction}，x={self._px:.1f}%")

        last_attack = time.time()
        last_aux    = time.time()

        while True:
            # 每 270 秒釋放輔助技能
            if time.time() - last_aux >= _AUX_INTERVAL:
                if self._cast_aux():
                    break
                last_aux = time.time()
                last_attack = time.time()
                continue

            x = self._px

            if direction == 'right' and x >= _X_TRIGGER_RIGHT:
                if self._ascend_right():
                    break
                direction = 'left'
                if self._hold_key(direction, poll):
                    break
                if self._hold_key('z', 1.0):
                    break
                last_attack = time.time()

            elif direction == 'left' and x <= _X_TRIGGER_LEFT:
                if self._ascend_left():
                    break
                direction = 'right'
                if self._hold_key(direction, poll):
                    break
                if self._hold_key('z', 1.0):
                    break
                last_attack = time.time()

            else:
                # 平地移動：每 1 秒攻擊一次
                if time.time() - last_attack >= _ATTACK_INTERVAL:
                    if self._hold_key('z', 0.5):
                        break
                    last_attack = time.time()
                else:
                    near = (direction == 'right' and x >= _X_TRIGGER_RIGHT - _NEAR_THRESHOLD) or \
                           (direction == 'left'  and x <= _X_TRIGGER_LEFT  + _NEAR_THRESHOLD)
                    poll = _MOVE_POLL_NEAR if near else _MOVE_POLL
                    if self._hold_key(direction, poll):
                        breakㄏㄏ

        print("Lab102RoomTask end")
