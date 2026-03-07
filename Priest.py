import random
import time
import pyautogui

from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class Priest(MapleTask):
    def __init__(self, hwnd):
        super(Priest, self).__init__()

    def active_skill(self):
        pyautogui.keyDown('1')
        time.sleep(0.5)
        pyautogui.keyUp('1')
        pyautogui.keyDown('2')
        time.sleep(0.5)
        pyautogui.keyUp('2')
        pyautogui.keyDown('3')
        time.sleep(0.5)
        pyautogui.keyUp('3')

    def task(self):
        print(f"Priest thread started")

        support_time_start = time.time()
        self.active_skill()

        while True:
            if time.time() - support_time_start > 250:
                support_time_start = time.time()
                self.active_skill()
            pyautogui.keyDown('x')
            if self.wait_stop_event(random.randint(4, 6)):
                pyautogui.keyUp('x')
                break
            pyautogui.keyUp('x')
            pyautogui.keyDown('right')
            pyautogui.keyDown('c')
            if self.wait_stop_event(random.randint(1, 3)):
                pyautogui.keyUp('right')
                pyautogui.keyUp('c')
                break
            pyautogui.keyUp('c')
            pyautogui.keyUp('right')
            pyautogui.keyDown('x')
            if self.wait_stop_event(random.randint(3, 6)):
                pyautogui.keyUp('x')
                break
            pyautogui.keyUp('x')
            pyautogui.keyDown('left')
            pyautogui.keyDown('c')
            if self.wait_stop_event(random.randint(1, 3)):
                pyautogui.keyUp('left')
                pyautogui.keyUp('c')
                break
            pyautogui.keyUp('left')
            pyautogui.keyUp('c')
        print(f"Priest thread stopped")
