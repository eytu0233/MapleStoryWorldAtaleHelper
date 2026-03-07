import pyautogui
import time
import json
import os


class ArtaleController:
    def __init__(self, config_path="board_config.json"):
        self.load_config(config_path)
        pyautogui.PAUSE = 0.01 # 降低內建延遲，由我們手動控制

    def load_config(self, config_path):
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            # 預設值包含按鍵與延遲
            self.config = {
                "keys": {
                    "teleport": "c", "heal": "z", "shining_ray": "x",
                    "holy_symbol": "1", "blessing": "2", "invincible": "3", "magic_guard": "4"
                },
                "delays": {
                    "shining_ray": 0.95, # 聖光僵直較長
                    "teleport": 0.15,
                    "buff": 1.2,
                    "default": 0.05
                }
            }

    def _press(self, key_name, duration=0.1):
        """通用按鍵方法，自動抓取對應的按鍵並施加僵直延遲"""
        key = self.config["keys"].get(key_name)
        delay = self.config["delays"].get(key_name, self.config["delays"]["default"])

        if key:
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)
            print(f"發動 {key_name}，進入僵直延遲: {delay}s")
            time.sleep(delay)  # 關鍵：消化僵直時間

    def _press_key(self, key, duration=0.1):
        """底層按鍵模擬，帶有些微按下時間提高成功率"""
        pyautogui.keyDown(key)
        time.sleep(duration)
        pyautogui.keyUp(key)

    # --- 動作 API ---

    def teleport(self, direction="left"):
        """瞬間移動：C + 方向鍵"""
        tele_key = self.config["keys"]["teleport"]
        dir_key = "left" if direction == "left" else "right"
        delay = self.config["delays"]["teleport"]

        print(f"執行瞬間移動: {direction}")

        pyautogui.keyDown(tele_key)
        self._press_key(dir_key, duration=0.1)
        pyautogui.keyUp(tele_key)
        time.sleep(delay)

    def heal(self):
        """補血 (Z) - 補血通常僵直極短，可連續按"""
        self._press("heal")

    def shining_ray(self, duration=0.1):
        """聖光 (X) - 發動後會卡住，須等延遲結束才能做下一件事"""
        self._press("shining_ray", duration)

    def cast_all_buffs(self):
        """放所有 Buff，每個 Buff 之間都有較長的動畫僵直"""
        buff_list = ["holy_symbol", "blessing", "invincible", "magic_guard", "dragon"]
        for b in buff_list:
            self._press(b)
            # 這裡 _press 會自動套用 'default' 延遲，
            # 但 Buff 通常需要更長，我們可以額外加：
            time.sleep(self.config["delays"]["buff"] - self.config["delays"]["default"])

# --- 測試範例 ---
if __name__ == "__main__":
    # 給予 3 秒切換到遊戲視窗的時間
    print("程式將在 2 秒後開始執行，請切換至遊戲視窗...")
    time.sleep(2)

    ctrl = ArtaleController()

    # 範例動作序列
    ctrl.cast_all_buffs()  # 一次性施放所有狀態技能
    ctrl.teleport("right")  # 向右瞬移
    ctrl.teleport("right")  # 向右瞬移
    ctrl.teleport("right")  # 向右瞬移
    ctrl.teleport("left")  # 向左瞬移
    ctrl.teleport("left")  # 向左瞬移
    ctrl.teleport("left")  # 向左瞬移
    # ctrl.heal()
    # ctrl.shining_ray()  # 此處會自動等待 0.95 秒僵直
    # ctrl.heal()  # 這一下就不會被「卡掉」了
