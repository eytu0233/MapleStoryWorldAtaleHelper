import time

import pyautogui

from MapleTask import MapleTask

SKILL_INTERVAL = 270
SKILL1_INTERVAL = 120
SKILL2_INTERVAL = 60
MOVE_INTERVAL = 180  # 每 180 秒執行移動
Z_CHECK_CHUNK = 5  # 每 5 秒檢查一次技能冷卻


class BowmasterTask(MapleTask):
    def __init__(self):
        super(BowmasterTask, self).__init__()

    def _press_skill(self, key):
        """按下並釋放技能，若收到停止訊號回傳 True"""
        pyautogui.keyDown(key)
        if self.wait_stop_event(0.5):
            pyautogui.keyUp(key)
            return True
        pyautogui.keyUp(key)
        return False

    def _do_move_routine(self):
        """按著左鍵3秒 → 按著右鍵7秒 → 按一下左鍵，若收到停止訊號回傳 True"""
        pyautogui.keyDown('left')
        if self.wait_stop_event(3):
            pyautogui.keyUp('left')
            return True
        pyautogui.keyUp('left')

        pyautogui.keyDown('right')
        if self.wait_stop_event(7):
            pyautogui.keyUp('right')
            return True
        pyautogui.keyUp('right')

        pyautogui.press('left')
        return False

    def task(self):
        print("BowmasterTask starting")
        last_skill1 = 0
        last_skill2 = 0
        last_move = 0

        while True:
            now = time.time()

            # 釋放技能 1（每 120 秒）
            if now - last_skill1 >= SKILL1_INTERVAL:
                if self._press_skill('1'):
                    break
                last_skill1 = time.time()

            # 釋放技能 2（每 60 秒）
            if now - last_skill2 >= SKILL2_INTERVAL:
                if self._press_skill('2'):
                    break
                last_skill2 = time.time()

            # 左鍵按一下
            pyautogui.press('left')

            # 等 0.5 秒
            if self.wait_stop_event(0.5):
                break

            # 按著 z 持續 270 秒，每 5 秒檢查技能冷卻
            pyautogui.keyDown('z')
            elapsed = 0
            stopped = False
            while elapsed < SKILL_INTERVAL:
                chunk = min(Z_CHECK_CHUNK, SKILL_INTERVAL - elapsed)
                if self.wait_stop_event(chunk):
                    stopped = True
                    break
                elapsed += chunk

                now = time.time()

                # 技能優先
                if now - last_skill1 >= SKILL1_INTERVAL:
                    pyautogui.keyUp('z')
                    if self._press_skill('1'):
                        stopped = True
                        break
                    last_skill1 = time.time()
                    pyautogui.keyDown('z')

                if now - last_skill2 >= SKILL2_INTERVAL:
                    pyautogui.keyUp('z')
                    if self._press_skill('2'):
                        stopped = True
                        break
                    last_skill2 = time.time()
                    pyautogui.keyDown('z')

                # 移動 routine（每 180 秒）
                if now - last_move >= MOVE_INTERVAL:
                    pyautogui.keyUp('z')
                    if self._do_move_routine():
                        stopped = True
                        break
                    last_move = time.time()
                    pyautogui.keyDown('z')

            pyautogui.keyUp('z')
            if stopped:
                break

        print("BowmasterTask end")
