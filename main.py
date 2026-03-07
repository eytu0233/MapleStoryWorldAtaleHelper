import os
import sys
import time

import cv2
import numpy as np
import win32gui
from mss import mss
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer
import torch
from ultralytics import YOLO
from character_control import ArtaleController # 匯入先前定義的控制器


# --- 設定參數 ---
MODEL_PATH = "best.pt"
GAME_TITLE = "MapleStory Worlds"
TARGET_LABEL = "snow_woman"
ATTACK_RANGE = 300      # 聖光攻擊半徑 (像素)
TELEPORT_DIST = 150     # 單次瞬移預估距離 (像素)
BUFF_INTERVAL = 240     # Buff 刷新間隔 (秒)
ATTACK_DURATION = 5     # 每次鎖定後的攻擊持續時間 (秒)

class GameMonitor(QMainWindow):
    def __init__(self, target_title):
        super().__init__()
        self.target_title = target_title
        self.setWindowTitle("AI 偵測預覽視窗")
        self.label = QLabel(self)
        self.setCentralWidget(self.label)

        # 初始化 mss 截圖
        self.sct = mss()

        # 設定計時器，每 30ms 更新一次畫面 (約 33 FPS)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        # 初始化控制器
        self.ctrl = ArtaleController()
        self.last_buff_time = 0

        self.last_save_time = 0

        # CUDA
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"正在使用設備: {self.device}")

        self.model = YOLO(MODEL_PATH)
        self.model.to(self.device)


    def get_window_rect(self):
        """獲取遊戲視窗的座標"""
        hwnd = win32gui.FindWindow(None, self.target_title)
        if hwnd:
            # 獲取視窗矩形 (left, top, right, bottom)
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "top": rect[1],
                "left": rect[0],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1]
            }
        return None

    def capture_frame(self, frame):

        # 建立儲存圖片的資料夾
        if not os.path.exists("dataset2"):
            os.makedirs("dataset2")

        # 在你的 while True 迴圈中加入
        # 每隔 5 秒存一張圖，避免存下太多重複畫面
        if time.time() - self.last_save_time > 5:
            file_path = f"dataset2/msw_{int(time.time())}.png"
            cv2.imwrite(file_path, frame)
            self.last_save_time = time.time()

    def find_best_target(self, results, screen_center_x):
        """尋找最適合瞬移攻擊的目標"""
        best_target_x = None
        targets = []

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cx = (x1 + x2) / 2
                targets.append(cx)

        if not targets:
            return None

        # 簡單策略：鎖定離目前中心最近的一隻雪女
        best_target_x = min(targets, key=lambda x: abs(x - screen_center_x))
        return best_target_x

    def start_ai_monitor(self, frame):
        results = self.model.predict(frame, conf=0.6, device=self.device, verbose=False)

        for r in results:
            boxes = r.boxes
            for box in boxes:
                # 取得邊框座標
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                # 取得信心度
                conf = box.conf[0].item()

                # 畫出偵測框 (綠色)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # 標註名稱與信心度
                label = f"Snow Woman: {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # 計算中心點 (未來點擊用)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

        h, w = frame.shape[:2]
        center_x = w / 2

        target_x = self.find_best_target(results, center_x)
        if target_x:
            relative_dist = target_x - center_x
            print(f"目標距離: {relative_dist:.1f} 像素")

            # 3. 判斷是否需要瞬移進入 300 像素範圍
            if abs(relative_dist) > ATTACK_RANGE:
                num_teleports = int(abs(relative_dist - (ATTACK_RANGE * np.sign(relative_dist))) // TELEPORT_DIST) + 1
                direction = "right" if relative_dist > 0 else "left"

                print(f"距離過遠，執行瞬移 {num_teleports} 次 -> {direction}")
                for _ in range(min(num_teleports, 3)):  # 最多連續瞬移3次，避免失控
                    self.ctrl.teleport(direction)

            # 4. 進行 5 秒的聖光與治癒輪流攻擊
            print("進入攻擊範圍，開始 5 秒循環攻擊...")
            attack_start = time.time()
            while time.time() - attack_start < ATTACK_DURATION:
                self.ctrl.shining_ray()  # 內建僵直等待
                self.ctrl.heal()  # 內建延遲
        else:
            print("搜尋不到雪女，等待中...")

    def get_hp_percentage(self, frame):
        height, width = frame.shape[:2]

        # 1. 定義 HP 條的精確 ROI
        roi_x1, roi_x2 = int(width * 0.265), int(width * 0.38)
        roi_y1, roi_y2 = int(height * 0.96), int(height * 0.97)

        # 確保不越界
        hp_roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
        if hp_roi.size == 0: return 0, (roi_x1, roi_y1, roi_x2, roi_y2)

        # 2. 轉換為 HSV 並過濾紅色
        hsv = cv2.cvtColor(hp_roi, cv2.COLOR_BGR2HSV)

        # 紅色範圍 (包含低飽和與高飽和兩段)
        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 100, 100])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        # 3. 計算紅色像素佔比
        # 橫向計算每一行紅色像素的平均寬度
        pixel_counts = np.sum(red_mask > 0, axis=1)
        if len(pixel_counts) == 0 or np.max(pixel_counts) == 0:
            return 0, (roi_x1, roi_y1, roi_x2, roi_y2)

        current_width = np.mean(pixel_counts)
        total_width = roi_x2 - roi_x1
        percentage = (current_width / total_width) * 100

        return round(percentage, 2), (roi_x1, roi_y1, roi_x2, roi_y2)

    def update_frame(self):
        rect = self.get_window_rect()
        if not rect:
            self.setWindowTitle("找不到遊戲視窗...")
            return

        # 截取遊戲區域
        # 注意：如果遊戲最小化，截圖會變黑或錯誤
        sct_img = self.sct.grab(rect)

        # 轉換為 OpenCV 格式 (BGR)12
        frame = np.array(sct_img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        self.capture_frame(frame)

        # --- 在這裡加入之後的怪物偵測邏輯 ---
        # 例如：cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        # --------------------------------
        # 1. 檢查並施放 Buff (240秒一次)
        # current_time = time.time()
        # if current_time - self.last_buff_time > BUFF_INTERVAL:
        #     print("--- 執行定時補 Buff ---")
        #     self.ctrl.cast_all_buffs()
        #     self.last_buff_time = time.time()
        # self.start_ai_monitor(frame)
        # --- HP 偵測與繪製 ---
        # hp_val, roi_coords = self.get_hp_percentage(frame)
        # x1, y1, x2, y2 = roi_coords
        #
        # # 畫出 HP ROI 邊框 (黃色)
        # cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        #
        # # 在邊框上方顯示百分比文字
        # color = (0, 0, 255) if hp_val < 50 else (0, 255, 0)  # 低於 50% 變紅字
        # cv2.putText(frame, f"HP: {hp_val}%", (x1, y1 - 10),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        #
        # # # 將 OpenCV 影像轉為 PyQt 格式
        # height, width, channel = frame.shape
        # bytesPerLine = 3 * width
        # q_img = QImage(frame.data, width, height, bytesPerLine, QImage.Format_RGB888).rgbSwapped()
        #
        # # 顯示在視窗上 (縮放以適應視窗大小)
        # pixmap = QPixmap.fromImage(q_img)
        # self.label.setPixmap(pixmap)
        # self.resize(width // 2, height // 2)  # 預覽視窗縮小一半避免佔空間


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 請確保標題與你的遊戲視窗完全一致
    # 可以用你之前的 list_all_child_windows 腳本確認
    GAME_TITLE = "MapleStory Worlds-Artale (繁體中文版)"

    monitor = GameMonitor(GAME_TITLE)
    monitor.show()
    sys.exit(app.exec_())
