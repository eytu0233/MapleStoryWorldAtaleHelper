import pyautogui

from MapleTask import MapleTask

SKILL_INTERVAL = 270


class BowmasterTask(MapleTask):
    def __init__(self):
        super(BowmasterTask, self).__init__()

    def task(self):
        print("BowmasterTask starting")
        while True:
            # 釋放技能 1、2
            pyautogui.press('1')
            if self.wait_stop_event(0.5):
                break
            pyautogui.press('2')
            if self.wait_stop_event(0.5):
                break

            # 左鍵按一下
            pyautogui.press('left')

            # 等 0.5 秒
            if self.wait_stop_event(0.5):
                break

            # 按著 z 持續 270 秒
            pyautogui.keyDown('z')
            if self.wait_stop_event(SKILL_INTERVAL):
                pyautogui.keyUp('z')
                break
            pyautogui.keyUp('z')

        print("BowmasterTask end")
