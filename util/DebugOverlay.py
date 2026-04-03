import tkinter as tk
import win32gui

from controller.GameCharacter import (
    _HP_REGION, _MP_REGION, GameCharacter,
    _CHAR_SEARCH_X_MIN, _CHAR_SEARCH_X_MAX,
    _CHAR_SEARCH_Y_MIN, _CHAR_SEARCH_Y_MAX,
)
from controller.MinimapTask import MinimapTask
from controller.MonsterDetector import MonsterDetector

_MONSTER_DETECT_INTERVAL = 6   # 每 N 幀執行一次 template matching（~10fps@60fps）
_MONSTER_DOT_R           = 8   # 怪物中心點圓半徑（px）


class DebugOverlay:
    """透明覆蓋層，顯示任意 GameCharacter 的小地圖邊框、黃點位置及 HP/MP 辨識區域。"""

    def __init__(self, character: GameCharacter,
                 monster_detector: MonsterDetector | None = None):
        self.character        = character
        self.monster_detector = monster_detector
        self.window  = None
        self.canvas  = None
        self.running = False
        self.on_hide_callback  = None
        self._detect_tick      = 0
        self._last_monsters:   list[tuple[int, int]] = []
        self._last_search_rect: tuple[int, int, int, int] | None = None

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
        self.update_overlay()
        print(f"[DebugOverlay] 覆蓋層已顯示（{self.character.name}）")

    def hide(self):
        self.running = False
        if self.window:
            self.window.destroy()
            self.window = None
            self.canvas = None
        print("[DebugOverlay] 覆蓋層已隱藏")
        if self.on_hide_callback:
            self.on_hide_callback()

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
                    pos = mt.pos  # 快照，避免兩次屬性存取不一致
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

                # ── HP / MP 辨識範圍 ─────────────────────────────
                self._draw_region(ww, wh, _HP_REGION, '#ff4444', 'HP', self.character.hp)
                self._draw_region(ww, wh, _MP_REGION, '#4488ff', 'MP', self.character.mp)

                # ── 怪物偵測範圍與結果 ────────────────────────────
                if self.monster_detector is not None:
                    self._update_monster_detection(ww, wh)
                    self._draw_monster_overlay()

        except Exception as e:
            print(f"[DebugOverlay] 更新失敗: {e}")

        if self.running:
            self.window.after(16, self.update_overlay)   # ~60 fps

    def _update_monster_detection(self, ww: int, wh: int):
        """每 _MONSTER_DETECT_INTERVAL 幀執行一次 template matching，更新快取結果。"""
        self._detect_tick += 1
        if self._detect_tick < _MONSTER_DETECT_INTERVAL:
            return
        self._detect_tick = 0

        gw = self.character.game_window
        if not gw.is_valid:
            return
        frame = gw.capture(0.0, 0.0, 1.0, 1.0)
        if frame is None:
            return

        cx = self.character.screen_center_x
        cy = self.character.screen_center_y
        if cx == 0 and cy == 0:
            return

        fh, fw = frame.shape[:2]
        self._last_search_rect = self.monster_detector.search_rect(cx, cy, fw, fh)
        self._last_monsters    = self.monster_detector.find(frame, cx, cy)

    def _draw_monster_overlay(self):
        """將快取的搜尋範圍與怪物位置畫到 canvas 上。"""
        if self._last_search_rect is not None:
            x0, y0, x1, y1 = self._last_search_rect
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline='#00ff88', width=2, dash=(8, 4)
            )
            self.canvas.create_text(
                x0 + 3, y0 - 2,
                text='怪物搜尋範圍',
                fill='#00ff88', font=('Arial', 9, 'bold'), anchor='sw'
            )

        r = _MONSTER_DOT_R
        for i, (mx, my) in enumerate(self._last_monsters):
            self.canvas.create_oval(
                mx - r, my - r, mx + r, my + r,
                fill='#ff4400', outline='#ffcc00', width=2
            )
            self.canvas.create_text(
                mx, my - r - 3,
                text=str(i + 1),
                fill='#ffcc00', font=('Arial', 8, 'bold'), anchor='s'
            )
