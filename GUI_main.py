import sys
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
import json
import os
from pynput.keyboard import Listener

from ArrowDebugOverlay import ArrowDebugOverlay
from BowmasterTask import BowmasterTask
from FindBossTask import FindBossTask
from GameDetector import get_artale_hwnd
from HelperTask import HelperTask
from KingKongTask import KingKongTask
from Priest import Priest
from Righter import Righter
from ScholarTask import ScholarTask
from SupportTask import SupportTask
from ZombieMushKingTask import ZombieMushKingTask

CONFIG_FILE = "config.json"

HOTKEY_MAP = [
    ("F2",  "弓手 (BowmasterTask)"),
    ("F3",  "支援 back_time=1s"),
    ("F4",  "支援 back_time=1.5s"),
    ("F5",  "找 BOSS"),
    ("F6",  "Scholar"),
    ("F7",  "Priest"),
    ("F8",  "KingKong"),
    ("F9",  "大菇菇"),
    ("F10", "Righter"),
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
    def __init__(self, root, arrow_overlay):
        self.root = root
        self.root.title("MapleStory Worlds-Artale 輔助工具")
        self.root.geometry("500x640")
        self.root.resizable(True, True)
        self.root.minsize(400, 500)

        self.arrow_overlay = arrow_overlay

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
            text="▶ 顯示箭頭偵測",
            command=self._toggle_arrow_overlay,
            font=("Arial", 10),
            bg="#95a5a6", fg="white",
            relief=tk.FLAT, padx=12, pady=4
        )
        self.overlay_btn.pack(side=tk.LEFT)

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

    def _toggle_arrow_overlay(self):
        self.arrow_overlay.toggle()
        if self.arrow_overlay.running:
            self.overlay_btn.config(text="⏸ 隱藏箭頭偵測", bg="#e67e22")
        else:
            self.overlay_btn.config(text="▶ 顯示箭頭偵測", bg="#95a5a6")

    def _update_status(self):
        hwnd = get_artale_hwnd()
        if hwnd:
            self.process_label.config(text="✓ 檢測到", fg="green")
            self.hwnd_label.config(text=hex(hwnd))
        else:
            self.process_label.config(text="✗ 未檢測到", fg="red")
            self.hwnd_label.config(text="--")
        self.root.after(2000, self._update_status)


# ── 鍵盤事件 ─────────────────────────────────────────────────
def on_press(key):
    if not hasattr(key, 'name'):
        return
    if key.name == 'f2':
        print("F2 - BowmasterTask")
        bowmaster_task.toggle()
    if key.name == 'f3':
        print("F3 - SupportTask (back_time=1)")
        support_task.set_back_time(1)
        support_task.toggle()
    if key.name == 'f4':
        print("F4 - SupportTask (back_time=1.5)")
        support_task.set_back_time(1.5)
        support_task.toggle()
    if key.name == 'f5':
        print("F5 - FindBossTask")
        find_boss_task.toggle()
    if key.name == 'f6':
        print("F6 - ScholarTask")
        scholar_task.toggle()
    if key.name == 'f7':
        print("F7 - PriestTask")
        priest_task.toggle()
    if key.name == 'f8':
        print("F8 - KingKongTask")
        king_kong_task.toggle()
    if key.name == 'f9':
        print("F9 - ZombieMushKingTask")
        zombie_mushking_task.toggle()
    if key.name == 'f10':
        print("F10 - Righter")
        righter_task.toggle()
    if key.name == 'f11':
        print("F11 - HelperTask")
        helper_task.toggle()


# ── 初始化 Tasks ─────────────────────────────────────────────
bowmaster_task      = BowmasterTask()
find_boss_task      = FindBossTask()
priest_task         = Priest()
king_kong_task      = KingKongTask(find_boss_task)
scholar_task        = ScholarTask(find_boss_task)
righter_task        = Righter()
support_task        = SupportTask()
zombie_mushking_task = ZombieMushKingTask()
helper_task         = HelperTask()

find_boss_task.register_boss_found_event('大菇菇', zombie_mushking_task)

config = load_config()

# ── 啟動 ─────────────────────────────────────────────────────
root = tk.Tk()
arrow_debug_overlay = ArrowDebugOverlay(bowmaster_task.detect_arrow_task)
app = MainWindow(root, arrow_debug_overlay)

listener = Listener(on_press=on_press)
listener.start()

root.mainloop()
