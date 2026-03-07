import random
import time
import pyautogui

from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class KingKongTask(MapleTask):
    def __init__(self, hwnd, finder):
        super(KingKongTask, self).__init__()
        self.monitor = MonitorBossAliveTask(hwnd, self.boss_killed_event)
        self.finder = finder
        self.is_boss_event = False

    def boss_killed_event(self):
        self.is_boss_event = True
        self.stop()

    def boss_killed_after_event(self):
        if self.is_boss_event:
            self.is_boss_event = False
            pyautogui.keyDown('left')
            time.sleep(4)
            pyautogui.press('alt')
            time.sleep(1)
            pyautogui.press('alt')
            time.sleep(1)
            pyautogui.keyUp('left')
            self.finder.start()

    def task(self):
        self.monitor.start()
        print(f"KingKong thread started")

        while True:
            pyautogui.keyDown('space')
            time.sleep(0.2)
            pyautogui.keyUp('space')
            pyautogui.keyDown('x')
            if self.wait_stop_event(12):
                pyautogui.keyUp('x')
                self.boss_killed_after_event()
                self.stop()
                break
            pyautogui.keyUp('x')
            time.sleep(1)
            n = random.randint(5, 10)
            for i in range(1, n + 1):
                pyautogui.press('right')
                time.sleep(0.1)
            for i in range(1, n - 3):
                pyautogui.press('left')
                time.sleep(0.1)
        print(f"KingKong thread stopped")
        self.monitor.stop()
