import time

import cv2
import easyocr
import numpy as np
import pyautogui
import win32gui

# from logger import logger

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
    from GameWindow import GameWindow
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
    #print(f"recognize_text辨識花費秒數 {record} 秒")

    return results

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