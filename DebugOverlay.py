import tkinter as tk
import win32gui

from GameCharacter import _HP_REGION, _MP_REGION, GameCharacter
from MinimapTask import MinimapTask


class DebugOverlay:
    """透明覆蓋層，顯示任意 GameCharacter 的小地圖邊框、黃點位置及 HP/MP 辨識區域。"""

    def __init__(self, character: GameCharacter):
        self.character = character
        self.window = None
        self.canvas = None
        self.running = False

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

                # ── HP / MP 辨識範圍 ─────────────────────────────
                self._draw_region(ww, wh, _HP_REGION, '#ff4444', 'HP', self.character.hp)
                self._draw_region(ww, wh, _MP_REGION, '#4488ff', 'MP', self.character.mp)

        except Exception as e:
            print(f"[DebugOverlay] 更新失敗: {e}")

        if self.running:
            self.window.after(16, self.update_overlay)   # ~60 fps
