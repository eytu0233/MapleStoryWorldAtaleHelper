import random
import time
import pyautogui

from MapleTask import MapleTask


class HelperTask(MapleTask):
    def __init__(self):
        super(HelperTask, self).__init__()

    def task(self):
        print(f"Helper thread started")
        while not self.wait_stop_event(0.1):
            pyautogui.press('=')
        print(f"Helper thread stopped")