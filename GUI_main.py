import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from datetime import datetime
import json
import os
from pynput.keyboard import Listener

from util.DebugOverlay import DebugOverlay
from BowmasterTask import BowmasterTask
from controller.GameCharacter import GameCharacter
import win32gui

from util.GameDetector import get_artale_hwnd
from HelperTask import HelperTask
from util.MapData import MapData
from MapTestTask import MapTestTask
from NightLordTask import NightLordTask
from GhostWomen import GhostWomen
from lab102roomTask import Lab102RoomTask
from job.Archbishop import Archbishop

CONFIG_FILE = "config.json"

HOTKEY_MAP = [
    ("F2",  "弓手 (BowmasterTask)"),
    ("F5",  "地圖錄製 (toggle)"),
    ("F6",  "地圖測試 (MapTestTask)"),
    ("F7",  "主教 (Archbishop)"),
    ("F8",  "標賊鬼女"),
    ("F9",  "研究所102號房"),
    ("F10", "標賊龍蛋"),
    ("F11", "Helper"),
]


# ── 將 print 輸出重導向至 log 視窗 ─────────────────────────────
class _PrintRedirector:
    def __init__(self, callback):
        self._cb = callback
        self._orig = sys.stdout

    def write(self, msg):
        if msg.strip():
            self._cb(msg.strip())
        self._orig.write(msg)

    def flush(self):
        self._orig.flush()


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"boss": {}}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ── 主視窗 ────────────────────────────────────────────────────
class MainWindow:
    def __init__(self, root, debug_overlay):
        self.root = root
        self.root.title("MapleStory Worlds-Artale 輔助工具")
        self.root.geometry("500x640")
        self.root.resizable(True, True)
        self.root.minsize(400, 500)

        self.debug_overlay = debug_overlay
        self.debug_overlay.on_hide_callback = self._on_overlay_hidden

        self._setup_ui()
        sys.stdout = _PrintRedirector(self.log)

        self._update_status()

    def _setup_ui(self):
        # 標題列
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=55)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        tk.Label(
            title_frame,
            text="MapleStory Worlds-Artale 輔助工具",
            font=("Arial", 16, "bold"),
            bg="#2c3e50", fg="white"
        ).pack(pady=14)

        # 主內容
        content = tk.Frame(self.root, bg="#ecf0f1", padx=15, pady=12)
        content.pack(fill=tk.BOTH, expand=True)

        self._setup_game_status(content)
        self._setup_map_panel(content)
        self._setup_hotkey_panel(content)
        self._setup_log_area(content)

    def _setup_game_status(self, parent):
        frame = tk.LabelFrame(
            parent, text="遊戲狀態",
            font=("Arial", 11, "bold"), bg="#ecf0f1", padx=12, pady=8
        )
        frame.pack(fill=tk.X, pady=(0, 10))

        def row(label):
            f = tk.Frame(frame, bg="#ecf0f1")
            f.pack(fill=tk.X, pady=2)
            tk.Label(f, text=label, font=("Arial", 10), bg="#ecf0f1",
                     width=10, anchor="w").pack(side=tk.LEFT)
            val = tk.Label(f, text="--", font=("Arial", 10), bg="#ecf0f1", anchor="w")
            val.pack(side=tk.LEFT)
            return val

        self.process_label = row("進程:")
        self.hwnd_label    = row("窗口句柄:")

        # Debug 按鈕列
        btn_frame = tk.Frame(frame, bg="#ecf0f1")
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        self.overlay_btn = tk.Button(
            btn_frame,
            text="▶ 顯示 Debug 覆蓋層",
            command=self._toggle_debug_overlay,
            font=("Arial", 10),
            bg="#95a5a6", fg="white",
            relief=tk.FLAT, padx=12, pady=4
        )
        self.overlay_btn.pack(side=tk.LEFT)

    def _setup_map_panel(self, parent):
        frame = tk.LabelFrame(
            parent, text="地圖管理",
            font=("Arial", 11, "bold"), bg="#ecf0f1", padx=12, pady=8
        )
        frame.pack(fill=tk.X, pady=(0, 10))

        # ── 載入列 ──────────────────────────────────────────────
        load_row = tk.Frame(frame, bg="#ecf0f1")
        load_row.pack(fill=tk.X, pady=2)
        tk.Label(load_row, text="地圖:", font=("Arial", 10),
                 bg="#ecf0f1", width=5, anchor="w").pack(side=tk.LEFT)
        self.map_combo = ttk.Combobox(load_row, width=22, state="readonly")
        self.map_combo.pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(load_row, text="整理", font=("Arial", 9),
                  command=self._refresh_map_list,
                  bg="#bdc3c7", relief=tk.FLAT, padx=6
                  ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(load_row, text="載入", font=("Arial", 9),
                  command=self._load_map,
                  bg="#2980b9", fg="white", relief=tk.FLAT, padx=8
                  ).pack(side=tk.LEFT)

        # ── 儲存列 ──────────────────────────────────────────────
        save_row = tk.Frame(frame, bg="#ecf0f1")
        save_row.pack(fill=tk.X, pady=2)
        tk.Label(save_row, text="名稱:", font=("Arial", 10),
                 bg="#ecf0f1", width=5, anchor="w").pack(side=tk.LEFT)
        self.map_name_var = tk.StringVar()
        tk.Entry(save_row, textvariable=self.map_name_var,
                 width=24, font=("Arial", 10)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(save_row, text="儲存", font=("Arial", 9),
                  command=self._save_map,
                  bg="#27ae60", fg="white", relief=tk.FLAT, padx=8
                  ).pack(side=tk.LEFT)

        self._refresh_map_list()

        # ── 小地圖邊界 ───────────────────────────────────────────
        sep = tk.Frame(frame, bg="#bdc3c7", height=1)
        sep.pack(fill=tk.X, pady=(6, 4))

        bounds_title = tk.Frame(frame, bg="#ecf0f1")
        bounds_title.pack(fill=tk.X)
        tk.Label(bounds_title, text="小地圖邊界（視窗像素）",
                 font=("Arial", 9, "bold"), bg="#ecf0f1", fg="#555").pack(side=tk.LEFT)
        self.winsize_label = tk.Label(bounds_title, text="視窗: --",
                                      font=("Arial", 9), bg="#ecf0f1", fg="#888")
        self.winsize_label.pack(side=tk.RIGHT)

        pos_row = tk.Frame(frame, bg="#ecf0f1")
        pos_row.pack(fill=tk.X, pady=2)
        mm = config.get("minimap_bounds", {})
        for label, default, key, attr in [("X:", 66, "x", "_mm_x"), ("Y:", 185, "y", "_mm_y")]:
            tk.Label(pos_row, text=label, font=("Arial", 10),
                     bg="#ecf0f1").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(mm.get(key, default)))
            setattr(self, attr, var)
            tk.Entry(pos_row, textvariable=var, width=5,
                     font=("Arial", 10)).pack(side=tk.LEFT, padx=(0, 8))

        size_row = tk.Frame(frame, bg="#ecf0f1")
        size_row.pack(fill=tk.X, pady=2)
        for label, default, key, attr in [("寬:", 253, "w", "_mm_w"), ("高:", 238, "h", "_mm_h")]:
            tk.Label(size_row, text=label, font=("Arial", 10),
                     bg="#ecf0f1").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(mm.get(key, default)))
            setattr(self, attr, var)
            tk.Entry(size_row, textvariable=var, width=5,
                     font=("Arial", 10)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(size_row, text="生效", font=("Arial", 9),
                  command=self._apply_minimap_bounds,
                  bg="#8e44ad", fg="white", relief=tk.FLAT, padx=10
                  ).pack(side=tk.LEFT)

        btn_row = tk.Frame(frame, bg="#ecf0f1")
        btn_row.pack(fill=tk.X, pady=2)
        tk.Button(btn_row, text="載入", font=("Arial", 9),
                  command=self._load_minimap_bounds,
                  bg="#16a085", fg="white", relief=tk.FLAT, padx=10
                  ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text="儲存", font=("Arial", 9),
                  command=self._save_minimap_bounds_to_file,
                  bg="#2980b9", fg="white", relief=tk.FLAT, padx=10
                  ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text="自動偵測", font=("Arial", 9),
                  command=self._detect_minimap_bounds,
                  bg="#e67e22", fg="white", relief=tk.FLAT, padx=10
                  ).pack(side=tk.LEFT)

    def _detect_minimap_bounds(self):
        from util.Utility import detect_minimap_bounds
        gw = GameCharacter.shared_game_window()
        if gw is None or not gw.is_valid:
            print("[GUI] 遊戲視窗未偵測到，無法自動偵測邊界")
            return
        result = detect_minimap_bounds(gw)
        if result is None:
            print("[GUI] 小地圖邊界自動偵測失敗，請手動設定")
            return
        x0, y0, x1, y1 = result
        self._mm_x.set(str(x0))
        self._mm_y.set(str(y0))
        self._mm_w.set(str(x1 - x0))
        self._mm_h.set(str(y1 - y0))
        print(f"[GUI] 自動偵測結果：x={x0} y={y0} w={x1-x0} h={y1-y0}")
        self._apply_minimap_bounds()

    def _apply_minimap_bounds(self):
        try:
            x = int(self._mm_x.get())
            y = int(self._mm_y.get())
            w = int(self._mm_w.get())
            h = int(self._mm_h.get())
        except ValueError:
            print("[GUI] 邊界數值格式錯誤")
            return
        mt = GameCharacter.shared_minimap()
        if mt is not None:
            mt.set_bounds(x, y, x + w, y + h)
        config["minimap_bounds"] = {"x": x, "y": y, "w": w, "h": h}
        save_config(config)
        print(f"[GUI] 小地圖邊界已套用：x={x} y={y} w={w} h={h}")

    def _load_minimap_bounds(self):
        path = filedialog.askopenfilename(
            title="載入小地圖邊界",
            filetypes=[("JSON 檔案", "*.json"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mm = data.get("minimap_bounds", data)
            x = int(mm["x"]); y = int(mm["y"])
            w = int(mm["w"]); h = int(mm["h"])
        except Exception as e:
            print(f"[GUI] 讀取邊界 JSON 失敗：{e}")
            return
        self._mm_x.set(str(x))
        self._mm_y.set(str(y))
        self._mm_w.set(str(w))
        self._mm_h.set(str(h))
        self._apply_minimap_bounds()
        print(f"[GUI] 已從檔案載入邊界：x={x} y={y} w={w} h={h}")

    def _save_minimap_bounds_to_file(self):
        try:
            x = int(self._mm_x.get())
            y = int(self._mm_y.get())
            w = int(self._mm_w.get())
            h = int(self._mm_h.get())
        except ValueError:
            print("[GUI] 邊界數值格式錯誤")
            return
        path = filedialog.asksaveasfilename(
            title="儲存小地圖邊界",
            defaultextension=".json",
            filetypes=[("JSON 檔案", "*.json"), ("所有檔案", "*.*")],
            initialfile="minimap_bounds.json",
        )
        if not path:
            return
        data = {"minimap_bounds": {"x": x, "y": y, "w": w, "h": h}}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[GUI] 小地圖邊界已儲存至：{path}")

    def _refresh_map_list(self):
        names = MapData.list_names()
        self.map_combo["values"] = names
        if names:
            self.map_combo.set(names[0])   # 最新在首位（list_names 已降序）

    def _load_map(self):
        name = self.map_combo.get()
        if not name:
            return
        try:
            map_test_task.load_map(name)
            self.map_name_var.set(name)
        except Exception as e:
            print(f"[GUI] 載入地圖失敗：{e}")

    def _save_map(self):
        name = self.map_name_var.get().strip()
        if not name:
            print("[GUI] 請輸入地圖名稱")
            return
        mt = GameCharacter.shared_minimap()
        if mt is None:
            return
        md = mt.save_recording_as(name)
        if md is not None:
            self._refresh_map_list()
            self.map_combo.set(name)

    def _setup_hotkey_panel(self, parent):
        frame = tk.LabelFrame(
            parent, text="快捷鍵對應",
            font=("Arial", 11, "bold"), bg="#ecf0f1", padx=12, pady=8
        )
        frame.pack(fill=tk.X, pady=(0, 10))

        cols = 2
        for i, (key, desc) in enumerate(HOTKEY_MAP):
            r, c = divmod(i, cols)
            cell = tk.Frame(frame, bg="#ecf0f1")
            cell.grid(row=r, column=c, sticky="w", padx=10, pady=1)
            tk.Label(cell, text=key, font=("Arial", 10, "bold"),
                     bg="#3498db", fg="white", width=5, relief=tk.FLAT,
                     padx=4).pack(side=tk.LEFT)
            tk.Label(cell, text=f"  {desc}", font=("Arial", 10),
                     bg="#ecf0f1").pack(side=tk.LEFT)

    def _setup_log_area(self, parent):
        frame = tk.LabelFrame(
            parent, text="日誌輸出",
            font=("Arial", 11, "bold"), bg="#ecf0f1", padx=12, pady=8
        )
        frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            frame, height=10,
            font=("Consolas", 9),
            bg="#2c3e50", fg="#ecf0f1",
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log("程式已啟動，使用 F2~F11 切換各功能")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: (
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n"),
            self.log_text.see(tk.END)
        ))

    def _on_overlay_hidden(self):
        self.overlay_btn.config(text="▶ 顯示 Debug 覆蓋層", bg="#95a5a6")

    def _toggle_debug_overlay(self):
        self.debug_overlay.toggle()
        if self.debug_overlay.running:
            self.overlay_btn.config(text="⏸ 隱藏 Debug 覆蓋層", bg="#e67e22")
            gw = GameCharacter.shared_game_window()
            if gw is not None and gw.is_valid:
                try:
                    win32gui.SetForegroundWindow(gw.hwnd)
                except Exception:
                    pass
        else:
            self.overlay_btn.config(text="▶ 顯示 Debug 覆蓋層", bg="#95a5a6")

    def _update_status(self):
        gw = GameCharacter.shared_game_window()
        if gw is not None and gw.is_valid:
            self.process_label.config(text="✓ 檢測到", fg="green")
            self.hwnd_label.config(text=hex(gw.hwnd))
            self.winsize_label.config(text=f"視窗: {gw.width}×{gw.height}")
        else:
            self.process_label.config(text="✗ 未檢測到", fg="red")
            self.hwnd_label.config(text="--")
            self.winsize_label.config(text="視窗: --")
        self.root.after(2000, self._update_status)


# ── 鍵盤事件 ─────────────────────────────────────────────────
def on_press(key):
    if not hasattr(key, 'name'):
        return
    if key.name == 'f2':
        print("F2 - BowmasterTask")
        bowmaster_task.toggle()
    if key.name == 'f5':
        mt = GameCharacter.shared_minimap()
        if mt is not None:
            if mt.recording:
                print("F5 - 地圖錄製 停止")
                mt.stop_recording()
            else:
                print("F5 - 地圖錄製 開始")
                mt.start_recording()
    if key.name == 'f6':
        print("F6 - MapTestTask")
        map_test_task.toggle()
    if key.name == 'f7':
        print("F7 - Archbishop")
        archbishop_task.toggle()
    if key.name == 'f8':
        print("F8 - 標賊鬼女")
        ghost_women_task.toggle()
    if key.name == 'f9':
        print("F9 - 研究所102號房")
        lab102room_task.toggle()
    if key.name == 'f10':
        print("F10 - 標賊龍蛋")
        night_lord_task.toggle()
    if key.name == 'f11':
        print("F11 - HelperTask")
        helper_task.toggle()


# ── 初始化 Tasks ─────────────────────────────────────────────
bowmaster_task   = BowmasterTask()
archbishop_task  = Archbishop()
night_lord_task  = NightLordTask()
ghost_women_task = GhostWomen()
map_test_task    = MapTestTask()   # 初始化時自動載入最新地圖
lab102room_task  = Lab102RoomTask()
helper_task      = HelperTask()

config = load_config()

# 啟動時套用已儲存的小地圖邊界
_mm = config.get("minimap_bounds", {})
if _mm:
    _mt = GameCharacter.shared_minimap()
    if _mt is not None:
        _mt.set_bounds(_mm.get("x", 66), _mm.get("y", 185),
                       _mm.get("x", 66) + _mm.get("w", 253),
                       _mm.get("y", 185) + _mm.get("h", 238))

# ── 啟動 ─────────────────────────────────────────────────────
root = tk.Tk()
debug_overlay = DebugOverlay(bowmaster_task)
app = MainWindow(root, debug_overlay)

listener = Listener(on_press=on_press)
listener.start()

root.mainloop()
