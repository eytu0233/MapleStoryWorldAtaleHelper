import time
import pyautogui

from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class Righter(MapleTask):
    def __init__(self):
        super(Righter, self).__init__()

    def task(self):
        print("Righter starting")

        while not self.wait_stop_event(0.1):
            pyautogui.keyDown('x')
            if self.wait_stop_event(5):     # 吼五秒
                pyautogui.keyUp('x')
                break
            pyautogui.keyUp('x')
            pyautogui.keyDown('right')
            if self.wait_stop_event(5):     # 往右五秒
                pyautogui.keyUp('right')
                break
            pyautogui.keyUp('right')
            pyautogui.keyDown('x')
            if self.wait_stop_event(5):     # 吼五秒
                pyautogui.keyUp('x')
                break
            pyautogui.keyUp('x')
            pyautogui.keyDown('left')
            if self.wait_stop_event(5):     # 往左五秒
                pyautogui.keyUp('left')
                break
            pyautogui.keyUp('left')
        print("Righter end")
