import time
import pyautogui

from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class ScholarTask(MapleTask):
    def __init__(self, finder, hwnd=None):
        super(ScholarTask, self).__init__()
        hwnd = hwnd if hwnd is not None else self.detect_hwnd()
        self.monitor = MonitorBossAliveTask(hwnd, self.boss_killed_event)
        self.finder = finder
        self.is_boss_event = False

    def boss_killed_event(self):
        self.is_boss_event = True
        self.stop()

    def boss_killed_after_event(self):
        if self.is_boss_event:
            self.is_boss_event = False
            time.sleep(0.5)
            pyautogui.keyDown('down')
            time.sleep(0.1)
            pyautogui.keyDown('alt')
            time.sleep(0.1)
            pyautogui.keyUp('down')
            pyautogui.keyUp('alt')
            pyautogui.keyDown('right')
            time.sleep(0.1)
            pyautogui.keyUp('right')
            pyautogui.keyDown('left')
            time.sleep(0.2)
            pyautogui.keyUp('left')
            self.finder.start()

    def task(self):
        self.monitor.start()
        print("ScholarTask starting")

        is_right = False
        while True:
            print("keyDown x")
            pyautogui.keyDown('x')
            if self.wait_stop_event(20):
                pyautogui.keyUp('x')
                self.boss_killed_after_event()
                break
            print("keyUp x")
            pyautogui.keyUp('x')
            if self.wait_stop_event(1):
                self.boss_killed_after_event()
                break
            if is_right is True:
                print("right")
                pyautogui.keyDown('right')
                time.sleep(0.05)
                pyautogui.keyUp('right')
                is_right = not is_right
            else:
                print("left")
                pyautogui.keyDown('left')
                time.sleep(0.05)
                pyautogui.keyUp('left')
                is_right = not is_right
        print("ScholarTask end")
        self.monitor.stop()
