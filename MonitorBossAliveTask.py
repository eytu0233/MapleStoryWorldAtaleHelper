import re
import time

import util.Utility as Utility
from controller.MapleTask import MapleTask


class MonitorBossAliveTask(MapleTask):
    def __init__(self, hwnd=None, notify_func=None):
        super(MonitorBossAliveTask, self).__init__()
        self.hwnd = hwnd if hwnd is not None else self.detect_hwnd()
        self.notify_func = notify_func

    def task(self):
        print("monitor_boss_alive_thread starting")
        boss_hp = 0xFFFFFFFF
        boss_hp_percent = 100
        counter = 0
        found_once = False

        start_time = time.time()

        while not self.wait_stop_event(0.001):
            results = Utility.recognize_text(self.hwnd, 0.11, 0.03, 0.19, 0.03)

            if len(results) == 0:
                if time.time() - start_time < 60:
                    continue
                if found_once is False:
                    continue
                if boss_hp_percent <= 10:
                    print("找不到Boss血條，停止任務")
                    self.notify_func()
                    break
                counter += 1
                print(f"可能是誤判，增加counter {counter}")
                if counter > 4:
                    print("找不到Boss血條，停止任務")
                    self.notify_func()
                    break
            else:
                for bbox, text, conf in results:
                    print(f"找到關鍵字 ：{text} bbox {bbox}")
                    val = self.extract_percentage(text)
                    boss_hp_percent = val
                    print(f"boss_hp_percent ：{boss_hp_percent}")
                    val = self.extract_number(text)
                    boss_hp = val if val < boss_hp else boss_hp
                    print(f"boss_hp ：{boss_hp}")
                    found_once = True
                    counter = 0
        print("monitor_boss_alive_thread stop")

    @staticmethod
    def extract_percentage(text):
        match = re.search(r'\((\d+)', text)
        if match:
            val = float(match.group(1))
            return 100 if val > 100 else val
        return 100

    @staticmethod
    def extract_number(text):
        match = re.search(r'[\u4e00-\u9fff]+\s*([\d,]+)', text)
        if match:
            number_str = match.group(1).replace(',', '')  # 去掉千分位逗號
            try:
                val = int(number_str)
            except Exception as e:
                val = 0
            return val
        return 0xFFFFFFFF
