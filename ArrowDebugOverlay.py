import tkinter as tk
import win32gui

from DetectMarkerTask import SEARCH_LEFT_RATIO, SEARCH_RIGHT_RATIO, SEARCH_TOP_RATIO, SEARCH_BOTTOM_RATIO


class ArrowDebugOverlay:
    """透明覆蓋層，實時顯示黃色箭頭偵測結果"""

    def __init__(self, detect_arrow_task):
        self.task = detect_arrow_task
        self.window = None
        self.canvas = None
        self.running = False

    def show(self):
        if self.window:
            return

        self.window = tk.Toplevel()
        self.window.title("Arrow Debug Overlay")
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.4)

        self.canvas = tk.Canvas(self.window, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.running = True
        self.update_overlay()
        print("[ArrowDebugOverlay] 覆蓋層已顯示")

    def hide(self):
        self.running = False
        if self.window:
            self.window.destroy()
            self.window = None
            self.canvas = None
        print("[ArrowDebugOverlay] 覆蓋層已隱藏")

    def toggle(self):
        if self.window:
            self.hide()
        else:
            self.show()

    def _get_window_rect(self):
        hwnd = self.task.hwnd
        if not hwnd:
            return None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            return left, top, right - left, bottom - top
        except Exception:
            return None

    def update_overlay(self):
        if not self.running or not self.window:
            return

        try:
            rect = self._get_window_rect()
            if rect:
                wx, wy, ww, wh = rect
                self.window.geometry(f"{ww}x{wh}+{wx}+{wy}")
                self.canvas.delete("all")

                # 標題提示
                self.canvas.create_text(
                    ww // 2, 22,
                    text="黃色箭頭偵測 Debug 模式",
                    fill='yellow', font=('Arial', 13, 'bold')
                )

                # 偵測範圍框（綠色虛線）
                rx0 = int(ww * SEARCH_LEFT_RATIO)
                ry0 = int(wh * SEARCH_TOP_RATIO)
                rx1 = int(ww * SEARCH_RIGHT_RATIO)
                ry1 = int(wh * SEARCH_BOTTOM_RATIO)
                self.canvas.create_rectangle(
                    rx0, ry0, rx1, ry1,
                    outline='lime', width=2, dash=(10, 5)
                )
                self.canvas.create_text(
                    rx0 + 8, ry0 + 5,
                    text="偵測範圍", fill='lime',
                    font=('Arial', 11, 'bold'), anchor='nw'
                )

                pos = self.task.last_position
                if pos is not None:
                    cx = pos[0] - wx
                    cy = pos[1] - wy

                    # 十字線
                    s = 20
                    self.canvas.create_line(cx - s, cy, cx + s, cy, fill='yellow', width=3)
                    self.canvas.create_line(cx, cy - s, cx, cy + s, fill='yellow', width=3)

                    # 圓圈
                    r = 18
                    self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                            outline='yellow', width=3)

                    # 座標標籤
                    self.canvas.create_text(
                        cx, cy - r - 8,
                        text=f"箭頭 ({pos[0]}, {pos[1]})",
                        fill='yellow', font=('Arial', 11, 'bold'), anchor='s'
                    )
                else:
                    self.canvas.create_text(
                        ww // 2, wh // 2,
                        text="未偵測到箭頭",
                        fill='gray', font=('Arial', 16, 'bold')
                    )

        except Exception as e:
            print(f"[ArrowDebugOverlay] 更新失敗: {e}")

        if self.running:
            self.window.after(3, self.update_overlay)
