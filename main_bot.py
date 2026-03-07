import cv2
import time
import numpy as np
import torch
import win32con
from ultralytics import YOLO
from mss import mss
import win32gui
from character_control import ArtaleController  # 匯入先前定義的控制器

# --- 設定參數 ---
MODEL_PATH = "best.pt"
GAME_TITLE = "MapleStory Worlds-Artale (繁體中文版)"
TARGET_LABEL = "snow_woman"
ATTACK_RANGE = 300  # 聖光攻擊半徑 (像素)
TELEPORT_DIST = 150  # 單次瞬移預估距離 (像素)
BUFF_INTERVAL = 240  # Buff 刷新間隔 (秒)
ATTACK_DURATION = 5  # 每次鎖定後的攻擊持續時間 (秒)


class ArtaleBot:
    def __init__(self):
        # 初始化 AI 大腦
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model = YOLO(MODEL_PATH).to(self.device)

        # 初始化控制器
        self.ctrl = ArtaleController()
        self.last_buff_time = 0
        self.sct = mss()

    def get_game_screen(self, hwnd):
        if not hwnd: return None, None
        rect = win32gui.GetWindowRect(hwnd)
        monitor = {"top": rect[1], "left": rect[0], "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
        img = np.array(self.sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), monitor

    def get_hp_percentage(self, frame):
        height, width = frame.shape[:2]

        # --- 1. 定義 HP 條的精確 ROI (根據 1920x1080 比例調整) ---
        # 這裡的數值需要根據你的遊戲視窗解析度稍微微調
        roi_x1, roi_x2 = int(width * 0.178), int(width * 0.332)
        roi_y1, roi_y2 = int(height * 0.945), int(height * 0.965)

        hp_roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]

        # --- 2. 轉換為 HSV 顏色空間 ---
        hsv = cv2.cvtColor(hp_roi, cv2.COLOR_BGR2HSV)

        # --- 3. 定義紅色的範圍 (HP 條的顏色) ---
        # 紅色在 HSV 中跨越了 0 附近的區域
        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 100, 100])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        # --- 4. 計算比例 ---
        # 取得遮罩中白色像素 (即紅色部分) 的總和
        # 由於 HP 是橫向填滿，我們只需計算每一行中「最右邊」的白色像素位置
        pixel_counts = np.sum(red_mask > 0, axis=1)  # 計算每一行的紅色像素數量
        if len(pixel_counts) == 0: return 0

        # 取平均寬度並除以總寬度
        current_width = np.mean(pixel_counts)
        total_width = roi_x2 - roi_x1

        percentage = (current_width / total_width) * 100

        # Debug: 畫出邊框方便校正
        # cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (255, 255, 0), 2)

        return round(percentage, 2)

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

    def find_positions(self, results, frame_width):
        """
        同時尋找玩家與目標的精確座標
        """
        player_x = None
        monster_targets = []

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                name = self.model.names[cls]
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cx = (x1 + x2) / 2

                if name == "Player":  # 假設你訓練了玩家類別
                    player_x = cx
                elif name == "GhostWomen":
                    monster_targets.append(cx)

        # 如果 YOLO 沒抓到玩家，則退而求其次使用畫面中心 (保險機制)
        if player_x is None:
            player_x = frame_width / 2

        return player_x, monster_targets

    def run(self):
        hWnd = win32gui.FindWindow(None, GAME_TITLE)

        if hWnd == 0:
            print("找不到視窗，請確認視窗名稱正確")
            return
        else:
            print(f"找到視窗 Handle: {hWnd}")

            if win32gui.IsIconic(hWnd):
                win32gui.ShowWindow(hWnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hWnd)

        while True:
            frame, monitor = self.get_game_screen(hWnd)
            if frame is None: continue

            h, w = frame.shape[:2]
            center_x = w / 2

            # 1. 檢查並施放 Buff (240秒一次)
            current_time = time.time()
            if current_time - self.last_buff_time > BUFF_INTERVAL:
                print("--- 執行定時補 Buff ---")
                self.ctrl.cast_all_buffs()
                self.last_buff_time = time.time()

            # 2. AI 偵測
            results = self.model.predict(frame, conf=0.6, verbose=False, device=self.device)
            # target_x = self.find_best_target(results, center_x)
            #
            # if target_x:
            #     relative_dist = target_x - center_x
            #     print(f"目標距離: {relative_dist:.1f} 像素")
            #
            #     # 3. 判斷是否需要瞬移進入 300 像素範圍
            #     if abs(relative_dist) > ATTACK_RANGE:
            #         num_teleports = int(
            #             abs(relative_dist - (ATTACK_RANGE * np.sign(relative_dist))) // TELEPORT_DIST) + 1
            #         direction = "right" if relative_dist > 0 else "left"
            #
            #         print(f"距離過遠，執行瞬移 {num_teleports} 次 -> {direction}")
            #         for _ in range(min(num_teleports, 3)):  # 最多連續瞬移3次，避免失控
            #             self.ctrl.teleport(direction)

                # 4. 進行 5 秒的聖光與治癒輪流攻擊
                # print("進入攻擊範圍，開始 5 秒循環攻擊...")
                # attack_start = time.time()
                # while time.time() - attack_start < ATTACK_DURATION:
                #     self.ctrl.shining_ray()  # 內建僵直等待
                #     self.ctrl.heal()  # 內建延遲

            #     print("進入攻擊範圍，開始攻擊...")
            #     self.ctrl.shining_ray(3)  # 內建僵直等待
            #     self.ctrl.heal()  # 內建延遲
            #     self.ctrl.shining_ray(3)  # 內建僵直等待
            #     self.ctrl.heal()  # 內建延遲
            # else:
            #     print("搜尋不到雪女，等待中...")
            #     self.ctrl.shining_ray(5)
            #     self.ctrl.heal()

            # 顯示偵測畫面 (選配)
            # cv2.imshow("Bot View", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'): break

            # 1. 獲取當前角色的真實 X 座標
            current_player_x, monsters = self.find_positions(results, frame.shape[1])
            if monsters:
                # 2. 找到離「角色」最近的怪，而非離「畫面中心」最近的怪
                target_x = min(monsters, key=lambda x: abs(x - current_player_x))

                # 3. 計算真實相對距離
                real_relative_dist = target_x - current_player_x

                print(f"角色位置: {current_player_x:.0f}, 目標距離: {real_relative_dist:.0f}")

                # 4. 根據真實距離執行瞬移或攻擊
                if abs(real_relative_dist) > ATTACK_RANGE:
                    direction = "right" if real_relative_dist > 0 else "left"
                    self.ctrl.teleport(direction)
                    self.ctrl.heal()
                else:
                    print("進入攻擊範圍，開始攻擊...")
                    self.ctrl.shining_ray(3)
                    self.ctrl.heal()


if __name__ == "__main__":
    bot = ArtaleBot()
    bot.run()
