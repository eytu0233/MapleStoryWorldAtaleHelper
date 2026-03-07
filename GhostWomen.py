import time
import pyautogui

from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class GhostWomen(MapleTask):
    def __init__(self, hwnd):
        super(GhostWomen, self).__init__()
        self.hwnd = hwnd

    def task(self):
        print("GhostWomen starting")

        while not self.wait_stop_event(0.1):
            print("GhostWomen end")
        print("GhostWomen end")
