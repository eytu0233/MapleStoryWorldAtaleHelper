import time

import cv2
import easyocr
import numpy as np
import pyautogui
import win32con
import win32gui

from MapleTask import MapleTask

template_base_width = 2576
template_base_height = 1416

WIDTH_SCALE = 0.2
HEIGHT_SCALE = 0.07
X_OFFSET_SCALE = 0.4
Y_OFFSET_SCALE = 0.25


class FindBossTask(MapleTask):
    def __init__(self, hwnd=None):
        super(FindBossTask, self).__init__()
        self.hwnd = hwnd if hwnd is not None else self.detect_hwnd()
        self.found_event = None
        self.boss_task_map = {}

    def set_found_event(self, callback):
        self.found_event = callback

    def register_boss_found_event(self, boss_keyword: str, task: MapleTask):
        self.boss_task_map[boss_keyword] = task

    def run_maple_task_by_keyword(self, input_str: str):
        for key, task in self.boss_task_map.items():
            if key in input_str:
                task.start()

    def get_actual_width_height(self):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = right - left
        height = bottom - top

        return width, height

    def find_and_click(self, img_file_name, delay=0, click=1, loop=False, threshold=0.8):
        global template_base_width
        global template_base_height

        actual_width, actual_height = self.get_actual_width_height()

        counter = 0

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

    def recognize_text(self, width_scale, height_scale, x_scale, y_scale):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = right - left
        height = bottom - top
        # print(f'left {left} top {top} right {right} bottom {bottom}')

        catch_width = int(width * width_scale)
        catch_height = int(height * height_scale)

        catch_left = int(left + width * x_scale)
        catch_top = int(top + height * y_scale)
        # print(f'catch_left {catch_left} catch_top {catch_top} catch_width {catch_width} catch_height {catch_height}')

        screenshot = pyautogui.screenshot(region=(catch_left, catch_top, catch_width, catch_height))
        img_np = np.array(screenshot)
        reader = easyocr.Reader(['ch_tra'], gpu=True)
        results = reader.readtext(img_np)

        return results

    def find_boss(self, delay=2):
        time.sleep(delay)
        results = self.recognize_text(WIDTH_SCALE, HEIGHT_SCALE, X_OFFSET_SCALE, Y_OFFSET_SCALE)
        print('辨識完成')

        for bbox, text, conf in results:
            print(f"找到關鍵字 ：{text}")
            return text

        print('未發現')
        return None

    def change_channel(self):
        while self.is_running:
            print('找目錄')
            self.find_and_click("img/directory.png", loop=True)
            print('找頻道')
            found = self.find_and_click("img/channel.png", loop=True)
            if not found:
                continue
            print('找隨機')
            found = self.find_and_click("img/random.png", loop=True)
            if not found:
                continue
            print('找確定')
            found = self.find_and_click("img/confirm.png", loop=True)
            if found:
                break

        while self.is_running:
            print('找登入')
            found = self.find_and_click("img/login_2.png", click=2)
            if found:
                pyautogui.move(-100, -100)
                pyautogui.click()
            print('找腳色')
            found = self.find_and_click("img/select_1.png")
            if found:
                break
            print('找重新連線')
            self.find_and_click("img/reconnect.png")

    def task(self):
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(self.hwnd)
        self.change_channel()
        found = self.find_boss()
        if found is not None:
            pyautogui.keyDown('home')
            time.sleep(0.5)
            pyautogui.keyUp('home')
            self.stop()
            if self.found_event is not None:
                self.found_event()
            self.run_maple_task_by_keyword(found)
