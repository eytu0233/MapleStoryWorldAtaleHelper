import time

import cv2
import numpy as np
import pyautogui
import win32con
import win32gui

from MapleTask import MapleTask

template_base_width = 2576
template_base_height = 1416

save_x = -1
save_y = -1

class SupportTask(MapleTask):
    def __init__(self, hwnd):
        super(SupportTask, self).__init__()
        self.hwnd = hwnd
        self.back_time = 1.5

    def get_actual_width_height(self):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = right - left
        height = bottom - top

        return width, height

    def find_and_click(self, img_file_name, delay=0, click=1, loop=False, threshold=0.8, use_last=False):
        global template_base_width
        global template_base_height
        global save_x
        global save_y

        actual_width, actual_height = self.get_actual_width_height()

        counter = 0

        if use_last is False:
            save_x = -1
            save_y = -1
        else:
            if save_x >= 0 or save_y >= 0:
                pyautogui.click(save_x, save_y, clicks=click)
                print(f"點擊位置: {save_x}, {save_y}")
                return True

        while True:
            template = cv2.imread(img_file_name, cv2.IMREAD_GRAYSCALE)
            w, h = template.shape[::-1]
            screenshot = pyautogui.screenshot()
            screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

            scale_x = actual_width / template_base_width
            scale_y = actual_height / template_base_height

            # 6. 縮放 template
            new_w = int(template.shape[1] * scale_x)
            new_h = int(template.shape[0] * scale_y)
            resized_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

            result = cv2.matchTemplate(screenshot, resized_template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= threshold)

            if not self.is_running:
                return False
            for pt in zip(*loc[::-1]):
                x, y = pt[0] + w // 2, pt[1] + h // 2
                if delay > 0:
                    time.sleep(delay)
                if click > 0:
                    save_x = x
                    save_y = y
                    pyautogui.click(x, y, clicks=click)
                    print(f"點擊位置: {x}, {y}")
                    return True
            if loop:
                counter += 1
                if threshold == 0.1:
                    return False
                if counter >= 10:
                    counter = 0
                    threshold -= 0.1
                time.sleep(0.5)
                continue
            return False

    def set_back_time(self, time):
        self.back_time = time

    def task(self):
        # if win32gui.IsIconic(self.hwnd):
        #     win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        # win32gui.SetForegroundWindow(self.hwnd)
        # pyautogui.keyDown('1')
        # time.sleep(0.5)
        # pyautogui.keyUp('1')
        # pyautogui.keyDown('2')
        # time.sleep(0.5)
        # pyautogui.keyUp('2')
        while self.is_running:
            if self.find_and_click("img/market1.png", loop=True, use_last=True):
                break
        time.sleep(1)
        pyautogui.keyDown('left')
        time.sleep(5)
        pyautogui.keyUp('left')

        # 施放技能間隔時間
        if self.wait_stop_event(250):
            return

        pyautogui.keyDown('right')
        time.sleep(self.back_time)
        pyautogui.keyUp('right')
        pyautogui.keyDown('up')
        time.sleep(0.5)
        pyautogui.keyUp('up')

        time.sleep(5)
        pyautogui.keyDown('1')
        time.sleep(0.5)
        pyautogui.keyUp('1')
        pyautogui.keyDown('2')
        time.sleep(0.5)
        pyautogui.keyUp('2')
