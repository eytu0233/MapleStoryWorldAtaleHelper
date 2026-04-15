import json
import tkinter as tk
import win32gui

from util.logger import MSLogger

_logger = MSLogger('DebugOverlay')

from controller.GameCharacter import (
    _HP_REGION, _MP_REGION, GameCharacter,
    _CHAR_SEARCH_X_MIN, _CHAR_SEARCH_X_MAX,
    _CHAR_SEARCH_Y_MIN, _CHAR_SEARCH_Y_MAX,
)
from controller.CurseMonitor import _SCAN_REGION as _CURSE_SCAN_REGION
from controller.MinimapTask import MinimapTask
from util.CursorTracker import CursorTracker

_CONFIG_FILE = "config/config.json"


def _load_show_cursor_pos() -> bool:
    try:
        with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("show_cursor_pos", True)
    except Exception:
        return True


class DebugOverlay:
    """透明覆蓋層，顯示任意 GameCharacter 的小地圖邊框、黃點位置及 HP/MP 辨識區域。"""

    def __init__(self, character: GameCharacter):
        self.character       = character
        self.window          = None
        self.canvas          = None
        self.running         = False
        self.on_hide_callback = None

    def show(self):
        if self.window:
            return
        self.window = tk.Toplevel()
        self.window.title("Debug Overlay")
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.4)
        self.canvas = tk.Canvas(self.window, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", lambda e: self.hide())
        self.running = True
        if _load_show_cursor_pos():
            CursorTracker().start()
        self.update_overlay()
        _logger.info(f"[DebugOverlay] 覆蓋層已顯示（{self.character.name}）")

    def hide(self):
        self.running = False
        if self.window:
            self.window.destroy()
            self.window = None
            self.canvas = None
        _logger.info("[DebugOverlay] 覆蓋層已隱藏")
        if self.on_hide_callback:
            self.on_hide_callback()

    def set_character(self, character: GameCharacter):
        self.character = character
        _logger.info(f"[DebugOverlay] 切換角色：{character.name}")

    def toggle(self):
        if self.window:
            self.hide()
        else:
            self.show()

    def _get_window_rect(self):
        gw = self.character.game_window
        if not gw.is_valid:
            return None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(gw.hwnd)
            return left, top, right - left, bottom - top
        except Exception:
            return None

    def _draw_region(self, ww, wh, region, color, label, value=None):
        """以比例座標 (x,y,w,h) 繪製虛線框與標籤，回傳像素座標 (x0,y0,x1,y1)。"""
        x_ratio, y_ratio, w_ratio, h_ratio = region
        x0 = int(ww * x_ratio)
        y0 = int(wh * y_ratio)
        x1 = int(ww * (x_ratio + w_ratio))
        y1 = int(wh * (y_ratio + h_ratio))
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2, dash=(6, 3))
        text = f"{label}: {value:.1f}%" if value is not None else label
        self.canvas.create_text(x0 + 3, y0 - 2, text=text, fill=color,
                                font=('Arial', 9, 'bold'), anchor='sw')
        return x0, y0, x1, y1

    def update_overlay(self):
        if not self.running or not self.window:
            return

        try:
            gw = self.character.game_window
            if gw.is_valid and win32gui.IsIconic(gw.hwnd):
                self.hide()
                return

            rect = self._get_window_rect()
            if rect:
                wx, wy, ww, wh = rect
                self.window.geometry(f"{ww}x{wh}+{wx}+{wy}")
                self.canvas.delete("all")

                # ── 標題 ─────────────────────────────────────────
                self.canvas.create_text(
                    ww // 2, 14,
                    text=f"Debug — {self.character.name}",
                    fill='yellow', font=('Arial', 11, 'bold')
                )

                # ── 小地圖白色邊框 ────────────────────────────────
                mt: MinimapTask = self.character.minimap_task
                bounds_region = mt.bounds_as_window_region()
                if bounds_region is not None:
                    bx0, by0, bx1, by1 = self._draw_region(
                        ww, wh, bounds_region, 'white', '小地圖邊框'
                    )
                    map_w = bx1 - bx0
                    map_h = by1 - by0

                    # ── 黃點位置（在邊框內）──────────────────────
                    pos = mt.pos
                    dot_cx = bx0 + int(pos[0] * map_w)
                    dot_cy = by0 + int(pos[1] * map_h)

                    r = 5
                    self.canvas.create_oval(
                        dot_cx - r, dot_cy - r,
                        dot_cx + r, dot_cy + r,
                        fill='yellow', outline='orange', width=2
                    )
                    self.canvas.create_text(
                        dot_cx, dot_cy - r - 3,
                        text=f"({pos[0]:.2f}, {pos[1]:.2f})",
                        fill='yellow', font=('Arial', 8, 'bold'), anchor='s'
                    )
                else:
                    self.canvas.create_text(
                        80, 40, text="小地圖邊框未偵測到",
                        fill='gray', font=('Arial', 10, 'bold'), anchor='nw'
                    )

                # ── 名字邊框偵測搜尋範圍 ─────────────────────────
                search_region = (
                    _CHAR_SEARCH_X_MIN,
                    _CHAR_SEARCH_Y_MIN,
                    _CHAR_SEARCH_X_MAX - _CHAR_SEARCH_X_MIN,
                    _CHAR_SEARCH_Y_MAX - _CHAR_SEARCH_Y_MIN,
                )
                self._draw_region(ww, wh, search_region, '#a0c0ff', '名字偵測範圍')

                # ── 角色螢幕位置（名字邊框）──────────────────────
                sx = self.character.screen_x
                sy = self.character.screen_y
                sw = self.character.screen_w
                sh = self.character.screen_h
                if sw > 0 and sh > 0:
                    self.canvas.create_rectangle(
                        sx, sy, sx + sw, sy + sh,
                        outline='#c7a8d6', width=2
                    )
                    self.canvas.create_text(
                        sx, sy - 2,
                        text=f"角色 ({sx}, {sy}) {sw}×{sh}",
                        fill='#c7a8d6', font=('Arial', 8, 'bold'), anchor='sw'
                    )
                    # ── 角色中心點 ────────────────────────────────
                    cx = self.character.screen_center_x
                    cy = self.character.screen_center_y
                    r = 4
                    self.canvas.create_oval(
                        cx - r, cy - r, cx + r, cy + r,
                        fill='#c7a8d6', outline='white', width=1
                    )
                    self.canvas.create_text(
                        cx + r + 2, cy,
                        text=f"center ({cx}, {cy})",
                        fill='#c7a8d6', font=('Arial', 8, 'bold'), anchor='w'
                    )

                # ── HP / MP 辨識範圍 ─────────────────────────────
                self._draw_region(ww, wh, _HP_REGION, '#ff4444', 'HP', self.character.hp)
                self._draw_region(ww, wh, _MP_REGION, '#4488ff', 'MP', self.character.mp)

                # ── 詛咒偵測掃描範圍 ─────────────────────────────
                self._draw_region(ww, wh, _CURSE_SCAN_REGION, '#cc44ff', '詛咒偵測範圍')

                # ── ModelController 怪物偵測框 ────────────────────
                if hasattr(self.character, '_monster_detections'):
                    for det in self.character._monster_detections:
                        x1, y1, x2, y2 = det['bbox']
                        cx = int((x1 + x2) / 2)
                        cy = int((y1 + y2) / 2)
                        self.canvas.create_rectangle(
                            x1, y1, x2, y2,
                            outline='#ff8800', width=2
                        )
                        self.canvas.create_text(
                            x1, y1 - 2,
                            text=f"{det['name']} ({cx}, {cy})",
                            fill='#ff8800', font=('Arial', 8, 'bold'), anchor='sw'
                        )

                # ── ModelController 角色位置標記 ──────────────────
                char_cx = getattr(self.character, '_char_screen_cx', 0)
                char_cy = getattr(self.character, '_char_screen_cy', 0)
                if char_cx > 0 and char_cy > 0:
                    r = 6
                    self.canvas.create_line(
                        char_cx - r, char_cy, char_cx + r, char_cy,
                        fill='#00ff88', width=2
                    )
                    self.canvas.create_line(
                        char_cx, char_cy - r, char_cx, char_cy + r,
                        fill='#00ff88', width=2
                    )
                    self.canvas.create_text(
                        char_cx + r + 2, char_cy,
                        text=f"x={char_cx} y={char_cy}",
                        fill='#00ff88', font=('Arial', 8, 'bold'), anchor='w'
                    )

                # ── 游標位置 ──────────────────────────────────────
                if _load_show_cursor_pos():
                    ct = CursorTracker()
                    if ct.is_running:
                        # 螢幕絕對座標轉換為視窗相對座標
                        cx = ct.x - wx
                        cy = ct.y - wy
                        r = 8
                        # 十字準心
                        self.canvas.create_line(
                            cx - r, cy, cx + r, cy,
                            fill='#ff0066', width=2
                        )
                        self.canvas.create_line(
                            cx, cy - r, cx, cy + r,
                            fill='#ff0066', width=2
                        )
                        # 座標文字（螢幕絕對值 + 視窗相對值）
                        self.canvas.create_text(
                            cx + r + 4, cy,
                            text=f"游標 ({cx}, {cy})",
                            fill='#ff0066', font=('Arial', 8, 'bold'), anchor='w'
                        )

        except Exception as e:
            _logger.error(f"[DebugOverlay] 更新失敗: {e}")

        if self.running:
            self.window.after(16, self.update_overlay)   # ~60 fps
