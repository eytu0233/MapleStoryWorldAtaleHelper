import time

import cv2
import numpy as np
import pyautogui
import win32con
import win32gui

from MapleTask import MapleTask

MARKER_COMMAND_COOLDOWN = 10  # 重新發送 /marker 指令的冷卻秒數

# 搜尋範圍：視窗水平全寬，垂直僅中間一半（25%～75%）
SEARCH_LEFT_RATIO   = 0.0
SEARCH_RIGHT_RATIO  = 1.0
SEARCH_TOP_RATIO    = 0.25
SEARCH_BOTTOM_RATIO = 0.75

# 黃色箭頭 HSV 範圍
YELLOW_H_LOW, YELLOW_H_HIGH = 20, 40
YELLOW_S_LOW, YELLOW_S_HIGH = 150, 255
YELLOW_V_LOW, YELLOW_V_HIGH = 150, 255

# 箭頭輪廓面積門檻
MIN_AREA = 300
MAX_AREA = 20000

SCAN_INTERVAL = 0.01


class DetectMarkerTask(MapleTask):
    def __init__(self, hwnd=None):
        super(DetectMarkerTask, self).__init__()
        self.hwnd = hwnd if hwnd is not None else self.detect_hwnd()
        self.arrow_found_callback = None
        self.last_position = None
        self._last_marker_cmd_time = 0

    def set_arrow_found_callback(self, callback):
        """設定找到箭頭時的 callback(x, y)"""
        self.arrow_found_callback = callback

    def _get_window_rect(self):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        return left, top, right - left, bottom - top

    def _send_marker_command(self):
        """Focus 遊戲視窗後輸入 /marker 指令"""
        if not win32gui.IsWindow(self.hwnd):
            return
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(self.hwnd)
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.1)
        pyautogui.typewrite('/marker', interval=0.05)
        pyautogui.press('enter')
        print("[DetectMarkerTask] 已送出 /marker 指令")

    def find_arrow(self):
        """
        在遊戲畫面偵測黃色向下箭頭，回傳 (x, y) 絕對座標，未找到回傳 None
        """
        win_left, win_top, win_w, win_h = self._get_window_rect()

        region_left = int(win_left + win_w * SEARCH_LEFT_RATIO)
        region_top  = int(win_top  + win_h * SEARCH_TOP_RATIO)
        region_w    = int(win_w * (SEARCH_RIGHT_RATIO  - SEARCH_LEFT_RATIO))
        region_h    = int(win_h * (SEARCH_BOTTOM_RATIO - SEARCH_TOP_RATIO))

        screenshot = pyautogui.screenshot(region=(region_left, region_top, region_w, region_h))
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)

        lower = np.array([YELLOW_H_LOW, YELLOW_S_LOW, YELLOW_V_LOW])
        upper = np.array([YELLOW_H_HIGH, YELLOW_S_HIGH, YELLOW_V_HIGH])
        mask = cv2.inRange(img, lower, upper)

        # 形態學處理去除雜訊
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_AREA or area > MAX_AREA:
                continue
            # 確認 bounding box 高度大於寬度（箭頭呈縱向）或接近正方形
            x, y, w, h = cv2.boundingRect(cnt)
            if h < w * 0.5:
                continue
            if area > best_area:
                best_area = area
                best = cnt

        if best is None:
            return None

        M = cv2.moments(best)
        if M['m00'] == 0:
            return None

        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])

        # 轉回螢幕絕對座標（region_top 已含 top offset）
        abs_x = region_left + cx
        abs_y = region_top  + cy
        return abs_x, abs_y

    def task(self):
        print("DetectMarkerTask starting")
        while True:
            position = self.find_arrow()
            if position is not None:
                self.last_position = position
                # print(f"偵測到黃色箭頭：{position}")
                if self.arrow_found_callback is not None:
                    self.arrow_found_callback(position[0], position[1])
            else:
                self.last_position = None
                now = time.time()
                if win32gui.IsWindow(self.hwnd) and now - self._last_marker_cmd_time >= MARKER_COMMAND_COOLDOWN:
                    self._send_marker_command()
                    self._last_marker_cmd_time = now

            if self.wait_stop_event(SCAN_INTERVAL):
                break

        print("DetectMarkerTask end")
