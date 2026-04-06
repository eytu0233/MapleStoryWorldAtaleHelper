import time

import cv2
import easyocr
import numpy as np
import pyautogui
import win32gui

from util.logger import MSLogger

_logger = MSLogger('Utility')

reader = None

def recognize_text(hWnd_or_window, width_scale, height_scale, x_scale, y_scale):
    """
    辨識遊戲視窗內指定比例區域的文字。

    第一個參數可傳入：
        - GameWindow 實例（推薦）：使用即時更新的視窗幾何，截圖更準確。
        - int (hwnd)：向後相容舊用法，每次呼叫都重新查詢視窗大小。
    """
    global reader

    start_time = time.time()

    # 支援 GameWindow 或舊版 hwnd
    from controller.GameWindow import GameWindow
    if isinstance(hWnd_or_window, GameWindow):
        img_np = hWnd_or_window.capture(x_scale, y_scale, width_scale, height_scale)
        if img_np is None:
            return []
    else:
        hWnd = hWnd_or_window
        left, top, right, bottom = win32gui.GetWindowRect(hWnd)
        width = right - left
        height = bottom - top

        catch_width = int(width * width_scale)
        catch_height = int(height * height_scale)
        catch_left = int(left + width * x_scale)
        catch_top = int(top + height * y_scale)

        screenshot = pyautogui.screenshot(region=(catch_left, catch_top, catch_width, catch_height))
        img_np = np.array(screenshot)

    if reader is None:
        reader = easyocr.Reader(['ch_tra'], gpu=True)
    results = reader.readtext(img_np)

    record = time.time() - start_time
    #_logger.info(f"recognize_text辨識花費秒數 {record} 秒")

    return results

def _px_matches(px, rgb: tuple[int, int, int], tol: int) -> bool:
    return (abs(int(px[0]) - rgb[0]) <= tol and
            abs(int(px[1]) - rgb[1]) <= tol and
            abs(int(px[2]) - rgb[2]) <= tol)


def detect_minimap_bounds(game_window) -> tuple[int, int, int, int] | None:
    """
    自動偵測小地圖在遊戲視窗中的像素邊界 (x0, y0, x1, y1)。

    小地圖固定位於視窗左上角，函式只截取前 40%×60% 的區域。

    邊界辨識方式（垂直白線搜尋法）：
      - 從 x=0 開始，逐欄掃描白色像素連續段是否超過 100 pixels。
      - 若某欄 x 有符合條件的長白線，且 x+1 欄沒有，則 x 為左邊界。
      - 繼續往右搜尋，找到連續段長度相近（±20%）的白線欄，視為右邊界。
      - y 範圍由左邊界白線的起迄決定。

    Returns:
        (x0, y0, x1, y1) 視窗像素座標，找不到時回傳 None。
    """
    from controller.GameWindow import GameWindow
    if not game_window.is_valid:
        return None
    frame = game_window.capture(0.0, 0.0, 0.4, 0.6)
    if frame is None:
        return None

    h, w = frame.shape[:2]
    tol = 30
    MIN_LINE_LEN = 100

    def get_white_vline_len(x: int) -> int:
        """回傳欄 x 中最長白色連續段的長度。"""
        col = frame[:, x]
        white = (col[:, 0] >= 255 - tol) & (col[:, 1] >= 255 - tol) & (col[:, 2] >= 255 - tol)
        max_len = cur_len = 0
        for v in white:
            if v:
                cur_len += 1
                if cur_len > max_len:
                    max_len = cur_len
            else:
                cur_len = 0
        return max_len

    def get_white_vline_range(x: int) -> tuple[int, int] | None:
        """回傳欄 x 中最長白色連續段的 (y_start, y_end)，找不到時回傳 None。"""
        col = frame[:, x]
        white = (col[:, 0] >= 255 - tol) & (col[:, 1] >= 255 - tol) & (col[:, 2] >= 255 - tol)
        best_start = best_end = best_len = 0
        cur_start = cur_len = 0
        in_run = False
        for y, v in enumerate(white):
            if v:
                if not in_run:
                    cur_start = y
                    cur_len = 0
                    in_run = True
                cur_len += 1
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = cur_start
                    best_end = y
            else:
                in_run = False
        if best_len < MIN_LINE_LEN:
            return None
        return best_start, best_end

    # 步驟 1：掃描全部欄位，收集所有白線
    _logger.info(f"[detect_minimap_bounds] 掃描範圍 w={w} h={h}")
    white_lines = []  # list of (x, y_start, y_end, length)
    for x in range(w):
        r = get_white_vline_range(x)
        if r is not None:
            seg_len = r[1] - r[0] + 1
            white_lines.append((x, r[0], r[1], seg_len))
            _logger.info(f"  [白線] x={x}  y={r[0]}~{r[1]}  len={seg_len}")

    _logger.info(f"[detect_minimap_bounds] 共找到 {len(white_lines)} 條白線")

    if len(white_lines) < 2:
        _logger.info("[detect_minimap_bounds] 白線數量不足，無法偵測邊界")
        return None

    # 步驟 2：找 x 差距大於 10、長度相近（±20%），且 x 差最小的兩條
    best_pair = None
    best_diff = None
    for i in range(len(white_lines)):
        for j in range(i + 1, len(white_lines)):
            xa, ya0, ya1, la = white_lines[i]
            xb, yb0, yb1, lb = white_lines[j]
            x_diff = abs(xb - xa)
            if x_diff <= 10:
                continue
            ref = max(la, lb)
            if abs(la - lb) > ref * 0.2:
                continue
            _logger.info(f"  [候選對] x={xa} len={la}  x={xb} len={lb}  x_diff={x_diff}")
            if best_diff is None or x_diff < best_diff:
                best_diff = x_diff
                best_pair = (white_lines[i], white_lines[j])

    if best_pair is None:
        _logger.info("[detect_minimap_bounds] 找不到符合條件的白線對")
        return None

    left_line, right_line = sorted(best_pair, key=lambda t: t[0])
    x0 = left_line[0]
    x1 = right_line[0]
    rough_y0 = left_line[1]
    rough_y1 = left_line[2]

    _logger.info(f"[detect_minimap_bounds] 垂直搜尋結果：x0={x0} x1={x1} rough_y={rough_y0}~{rough_y1}")

    # 步驟 3：在 x0~x1 範圍內，掃描每列橫向白線，精確定出上下邊界
    def get_white_hline_range(y: int, xa: int, xb: int) -> tuple[int, int] | None:
        """回傳列 y 在 xa~xb 中最長白色連續段的 (x_start, x_end)，找不到時回傳 None。"""
        row = frame[y, xa:xb + 1]
        white = (row[:, 0] >= 255 - tol) & (row[:, 1] >= 255 - tol) & (row[:, 2] >= 255 - tol)
        best_start = best_end = best_len = 0
        cur_start = cur_len = 0
        in_run = False
        for xi, v in enumerate(white):
            if v:
                if not in_run:
                    cur_start = xi
                    cur_len = 0
                    in_run = True
                cur_len += 1
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = cur_start
                    best_end = xi
            else:
                in_run = False
        if best_len < MIN_LINE_LEN:
            return None
        return xa + best_start, xa + best_end

    _logger.info(f"[detect_minimap_bounds] 橫線掃描範圍 y={rough_y0}~{rough_y1} x={x0}~{x1}")
    h_lines = []  # list of (y, x_start, x_end, length)
    for y in range(rough_y0, rough_y1 + 1):
        r = get_white_hline_range(y, x0, x1)
        if r is not None:
            seg_len = r[1] - r[0] + 1
            h_lines.append((y, r[0], r[1], seg_len))
            _logger.info(f"  [橫白線] y={y}  x={r[0]}~{r[1]}  len={seg_len}")

    _logger.info(f"[detect_minimap_bounds] 共找到 {len(h_lines)} 條橫白線")

    if len(h_lines) < 2:
        _logger.info("[detect_minimap_bounds] 橫白線不足，改用垂直搜尋的粗略 y 邊界")
        y0, y1 = rough_y0, rough_y1
    else:
        # 找 y 差距大於 10、長度相近（±20%），且 y 差最小的兩條
        best_hpair = None
        best_hdiff = None
        for i in range(len(h_lines)):
            for j in range(i + 1, len(h_lines)):
                ya, xa0, xa1, la = h_lines[i]
                yb, xb0, xb1, lb = h_lines[j]
                y_diff = abs(yb - ya)
                if y_diff <= 10:
                    continue
                ref = max(la, lb)
                if abs(la - lb) > ref * 0.2:
                    continue
                _logger.info(f"  [橫候選對] y={ya} len={la}  y={yb} len={lb}  y_diff={y_diff}")
                if best_hdiff is None or y_diff < best_hdiff:
                    best_hdiff = y_diff
                    best_hpair = (h_lines[i], h_lines[j])

        if best_hpair is None:
            _logger.info("[detect_minimap_bounds] 找不到符合條件的橫白線對，改用粗略 y 邊界")
            y0, y1 = rough_y0, rough_y1
        else:
            top_line, bot_line = sorted(best_hpair, key=lambda t: t[0])
            y0 = top_line[0]
            y1 = bot_line[0]

    _logger.info(f"[detect_minimap_bounds] 最終結果：x0={x0} y0={y0} x1={x1} y1={y1}")

    if x0 >= x1 or y0 >= y1:
        _logger.info("[detect_minimap_bounds] 邊界無效（x0>=x1 或 y0>=y1）")
        return None

    return x0, y0, x1, y1


def key_down(key):
    '''
    Press key down
    '''
    try:
        pyautogui.keyDown(key)
    except pyautogui.FailSafeException:
        logger.warning("[key_down] pyautogui failsafe triggered during key_down.")
        recover_mouse()

def key_up(key):
    '''
    Release key
    '''
    try:
        pyautogui.keyUp(key)
    except pyautogui.FailSafeException:
        logger.warning("[key_up] pyautogui failsafe triggered during key_up.")
        recover_mouse()

def recover_mouse():
    '''
    Move mouse back to center to avoid pyautogui failsafe
    '''
    pyautogui.FAILSAFE = False # Temp disasble failsafe to avoid nested exception

    screen_w, screen_h = pyautogui.size()
    pyautogui.moveTo(screen_w // 2, screen_h // 2)
    time.sleep(0.2) # Give it a moment to "cool down"

    pyautogui.FAILSAFE = True # Recover failsafe

def press_key(key, duration=0.05):
    '''
    Simulates a key press for a specified duration
    '''
    if key:
        key_down(key)
        time.sleep(duration)
        key_up(key)