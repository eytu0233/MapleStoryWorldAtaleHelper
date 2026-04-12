"""
capture_dataset.py
------------------
每 5 秒截取 MapleStory Worlds-Artale 遊戲視窗畫面，
存至 dataset 目錄，供 YOLO 模型訓練資料集使用。

執行方式（從專案根目錄）：
    python tool/capture_dataset.py
"""

import signal
import time
from ctypes import windll
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import win32gui
import win32ui

# ── 常數 ────────────────────────────────────────────────────────
_WINDOW_TITLE = "MapleStory Worlds-Artale"
_OUTPUT_DIR = Path("dataset")
_INTERVAL = 5.0  # 擷取間隔（秒）
_IMG_EXT = ".jpg"
_IMG_QUALITY = 95  # JPEG 品質


# ── 視窗偵測 ────────────────────────────────────────────────────

def _find_game_hwnd() -> int:
    """搜尋標題含 _WINDOW_TITLE 的視窗，回傳 HWND；找不到回傳 0。"""
    result = [0]

    def _enum_cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if _WINDOW_TITLE in title and win32gui.IsWindowVisible(hwnd):
            result[0] = hwnd
            return False

    win32gui.EnumWindows(_enum_cb, None)
    return result[0]


# ── 截圖 ────────────────────────────────────────────────────────

def capture_window(hwnd: int) -> np.ndarray | None:
    """
    使用 PrintWindow(PW_RENDERFULLCONTENT) 截取整個視窗畫面。

    Returns:
        RGB numpy array (H×W×3)；失敗時回傳 None。
    """
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        ww, wh = right - left, bottom - top
    except Exception:
        return None

    if ww <= 0 or wh <= 0:
        return None

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    if hwnd_dc == 0:
        return None

    save_dc = bmp = None
    img = None
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, ww, wh)
        save_dc.SelectObject(bmp)

        if windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2):
            raw = bmp.GetBitmapBits(True)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(wh, ww, 4)
            img = arr[:, :, 2::-1].copy()  # BGRA → RGB
    except Exception:
        img = None
    finally:
        if bmp is not None:
            handle = bmp.GetHandle()
            if handle:
                win32gui.DeleteObject(handle)
        if save_dc is not None:
            save_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img


# ── 主迴圈 ──────────────────────────────────────────────────────

def run():
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    running = True

    def _sigint_handler(sig, frame):
        nonlocal running
        print("\n[capture_dataset] 收到中斷訊號，正在停止…")
        running = False

    signal.signal(signal.SIGINT, _sigint_handler)

    print(f"[capture_dataset] 輸出目錄：{_OUTPUT_DIR.resolve()}")
    print(f"[capture_dataset] 擷取間隔：{_INTERVAL} 秒")
    print("[capture_dataset] 按 Ctrl+C 停止\n")

    hwnd = 0

    while running:
        if not hwnd or not win32gui.IsWindow(hwnd):
            hwnd = _find_game_hwnd()
            if not hwnd:
                print(f"[capture_dataset] 找不到視窗「{_WINDOW_TITLE}」，5 秒後重試…")
                time.sleep(5)
                continue
            print(f"[capture_dataset] 偵測到視窗 hwnd={hex(hwnd)}")

        img = capture_window(hwnd)
        if img is None:
            print("[capture_dataset] 截圖失敗，略過此次。")
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = _OUTPUT_DIR / f"{ts}{_IMG_EXT}"
            bgr = img[:, :, ::-1]  # RGB → BGR
            cv2.imwrite(str(filename), bgr, [cv2.IMWRITE_JPEG_QUALITY, _IMG_QUALITY])
            total += 1
            print(f"[{total:>5}] → {filename.name}")

        # 等待下次擷取（可被中斷）
        deadline = time.monotonic() + _INTERVAL
        while running and time.monotonic() < deadline:
            time.sleep(0.1)

    print(f"\n[capture_dataset] 結束。共擷取 {total} 張")


if __name__ == "__main__":
    run()
