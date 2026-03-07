import random
import time
import pyautogui

import Utility
from FindBossTask import FindBossTask
from MapleTask import MapleTask
from MonitorBossAliveTask import MonitorBossAliveTask


class ZombieMushKingTask(MapleTask):
    def __init__(self, hwnd):
        super(ZombieMushKingTask, self).__init__()
        self.monitor = MonitorBossAliveTask(hwnd, self.boss_killed_event)
        self.finder = FindBossTask(hwnd)
        self.finder.set_found_event(self.start)
        self.hwnd = hwnd
        self.is_boss_event = False

    def stop_event_notify(self):
        self.finder.stop()

    def boss_killed_event(self):
        self.is_boss_event = True
        self.stop()

    def boss_killed_after_event(self):
        if self.is_boss_event:
            self.is_boss_event = False
            pyautogui.keyDown('left')
            time.sleep(4)
            pyautogui.keyUp('left')
            self.finder.start()

    def find_boss_flow(self):
        results = Utility.recognize_text(self.hwnd, 0.11, 0.03, 0.19, 0.03)
        if len(results) > 0:
            return False

        is_left = False

        pyautogui.keyDown('right')
        if self.wait_stop_event(5):
            pyautogui.keyUp('right')
            return False
        pyautogui.keyUp('right')
        time.sleep(0.1)
        pyautogui.keyDown('down')
        time.sleep(0.1)
        pyautogui.keyDown('alt')
        pyautogui.keyUp('down')
        pyautogui.keyUp('alt')
        time.sleep(2)
        for i in range(1, 10):
            pyautogui.press('left')
            time.sleep(0.1)
        counter = 0
        while not self.wait_stop_event(1):
            pyautogui.keyDown('x')
            time.sleep(0.1)
            pyautogui.keyUp('x')
            results = Utility.recognize_text(self.hwnd, 0.11, 0.03, 0.19, 0.03)

            if len(results) > 0:
                return True

            counter += 1
            if counter >= 10:
                time.sleep(0.1)
                pyautogui.keyDown('right')
                time.sleep(0.5)
                pyautogui.keyUp('right')
                time.sleep(0.1)
                if is_left:
                    print("0.05")
                    for i in range(1, 3):
                        pyautogui.press('left')
                        time.sleep(0.05)
                    is_left = False
                else:
                    print("0.2")
                    pyautogui.keyDown('left')
                    time.sleep(0.2)
                    pyautogui.keyUp('left')
                    is_left = True
                counter = 0
                # n = random.randint(5, 10)
                # for i in range(1, n + 1):
                #     pyautogui.press('right')
                #     time.sleep(0.1)
                # for i in range(1, n - 3):
                #     pyautogui.press('left')
                #     time.sleep(0.1)

        return False

    def task(self):
        print(f"ZombieMushKing thread started")

        found = self.find_boss_flow()
        if not found:
            self.stop()
            self.finder.start()
            return

        self.monitor.start()

        n = 3
        counter = 0
        while True:
            pyautogui.keyDown('space')
            time.sleep(0.2)
            pyautogui.keyUp('space')
            pyautogui.keyDown('x')
            if self.wait_stop_event(15):
                pyautogui.keyUp('x')
                self.boss_killed_after_event()
                self.stop()
                break
            pyautogui.keyUp('x')
            time.sleep(0.1)
            pyautogui.keyDown('right')
            time.sleep(0.5)
            pyautogui.keyUp('right')
            time.sleep(0.1)
            # if n < 15:
            #     n += 15
            # else:
            #     n -= 15
            # for i in range(1, n):
            #     pyautogui.press('left')
            #     time.sleep(0.1)
            counter += 1
            if counter % 2 == 0:
                for i in range(1, 2):
                    pyautogui.press('left')
                    time.sleep(0.05)
            else:
                pyautogui.keyDown('left')
                time.sleep(0.25)
                pyautogui.keyUp('left')
        print(f"ZombieMushKing thread stopped")
        self.monitor.stop()
