import time

import cv2
import easyocr
import numpy as np
import pyautogui
import win32gui

# from logger import logger

reader = None

def recognize_text(hWnd, width_scale, height_scale, x_scale, y_scale):
    global reader

    start_time = time.time()

    left, top, right, bottom = win32gui.GetWindowRect(hWnd)
    width = right - left
    height = bottom - top
    #print(f'left {left} top {top} right {right} bottom {bottom}')

    catch_width = int(width * width_scale)
    catch_height = int(height * height_scale)

    catch_left = int(left + width * x_scale)
    catch_top = int(top + height * y_scale)
    #print(f'catch_left {catch_left} catch_top {catch_top} catch_width {catch_width} catch_height {catch_height}')

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