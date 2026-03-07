import re
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import win32gui
import win32con
import pyautogui
import easyocr
import time
import cv2
import numpy as np
import threading
import json
import os
from pynput.keyboard import Key, Listener

from BowmasterTask import BowmasterTask
from FindBossTask import FindBossTask
from HelperTask import HelperTask
from KingKongTask import KingKongTask
from Priest import Priest
from Righter import Righter
from ScholarTask import ScholarTask
from SupportTask import SupportTask
from ZombieMushKingTask import ZombieMushKingTask

stop_flag = False  # 全域停止旗標
monitor_flag = False
holy_thread = None
mushkill_thread = None
monitor_thread = None
stop_event = None

priest_task = None
find_boss_task = None
scholar_task = None
support_task = None
zombie_mushking_task = None
helper_task = None

template_base_width = 2576
template_base_height = 1416

save_x = -1
save_y = -1

WIDTH_SCALE = 0.2
HEIGHT_SCALE = 0.07
X_OFFSET_SCALE = 0.4
Y_OFFSET_SCALE = 0.25


def get_actual_width_height(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    return width, height


def find_and_click(img_file_name, hWnd, delay=0, click=1, loop=False, threshold=0.8, use_last=False):
    global template_base_width
    global template_base_height
    global save_x
    global save_y

    actual_width, actual_height = get_actual_width_height(hWnd)

    counter = 0

    if use_last is False:
        save_x = -1
        save_y = -1
    else:
        if save_x >= 0 or save_y >= 0:
            pyautogui.click(save_x, save_y, clicks=click)
            print(f"點擊位置: {save_x}, {save_y}")
            return True

    while True:
        template = cv2.imread(img_file_name, cv2.IMREAD_GRAYSCALE)
        w, h = template.shape[::-1]
        screenshot = pyautogui.screenshot()
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

        scale_x = actual_width / template_base_width
        scale_y = actual_height / template_base_height

        # 6. 縮放 template
        new_w = int(template.shape[1] * scale_x)
        new_h = int(template.shape[0] * scale_y)
        resized_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

        result = cv2.matchTemplate(screenshot, resized_template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= threshold)

        if stop_flag:
            return False
        for pt in zip(*loc[::-1]):
            x, y = pt[0] + w // 2, pt[1] + h // 2
            if delay > 0:
                time.sleep(delay)
            if click > 0:
                pyautogui.click(x, y, clicks=click)
                save_x = x
                save_y = y
                print(f"點擊位置: {x}, {y}")
                return True
        if loop:
            counter += 1
            if threshold == 0.1:
                return False
            if counter >= 10:
                counter = 0
                threshold -= 0.1
            time.sleep(0.5)
            continue
        return False


def reentry_world(hWnd):
    while not stop_flag:
        print('找menu')
        found = find_and_click("img/system_menu.png", hWnd)
        if not found:
            continue
        print('找重新進入世界')
        found = find_and_click("img/reentry_world.png", hWnd)
        print('找是')
        found = find_and_click("img/yes.png", hWnd)
        if found:
            break


def change_channel(hWnd):
    while not stop_flag:
        print('找目錄')
        find_and_click("img/directory.png", hWnd, loop=True)
        print('找頻道')
        found = find_and_click("img/channel.png", hWnd, loop=True)
        if not found:
            continue
        print('找隨機')
        found = find_and_click("img/random.png", hWnd, loop=True)
        if not found:
            continue
        print('找確定')
        found = find_and_click("img/confirm.png", hWnd, loop=True)
        if found:
            break

    while not stop_flag:
        print('找登入')
        found = find_and_click("img/login.png", hWnd, click=2)
        if found:
            pyautogui.move(-100, -100)
            pyautogui.click()
        print('找腳色')
        found = find_and_click("img/select.png", hWnd)
        if found:
            break
        print('找重新連線')
        find_and_click("img/reconnect.png", hWnd)


def recognize_text(hWnd, width_scale, height_scale, x_scale, y_scale):
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
    reader = easyocr.Reader(['ch_tra'], gpu=True)
    results = reader.readtext(img_np)

    return results


def find_boss(hWnd, delay=2):
    time.sleep(delay)
    results = recognize_text(hWnd, WIDTH_SCALE, HEIGHT_SCALE, X_OFFSET_SCALE, Y_OFFSET_SCALE)
    print('辨識完成')

    for bbox, text, conf in results:
        print(f"找到關鍵字 ：{text}")
        return True

    print('未發現')
    return False


def function_find_boss(hWnd):
    change_channel(hWnd)
    while not stop_flag:
        found = find_boss(hWnd)
        if found:
            pyautogui.keyDown('home')
            time.sleep(0.5)
            pyautogui.keyUp('home')
            break
        if stop_flag:
            break
        change_channel(hWnd)


def if_in_free_market(hWnd):
    results = recognize_text(hWnd, 0.11, 0.21, 0, 0)

    keyword = ['自由市場']
    for bbox, text, conf in results:
        if text in keyword:
            print(f"找到關鍵字 ：{text}")
            return True

    print('未發現')
    return False

def function_support(hWnd):
    while not stop_flag:
        found = find_and_click("img/market.png", hWnd, loop=True, use_last=True)
        if not found:
            continue
        time.sleep(1)
        pyautogui.keyDown('left')
        time.sleep(5)
        pyautogui.keyUp('left')

        # 施放技能間隔時間
        time.sleep(270)

        pyautogui.keyDown('right')
        time.sleep(1)
        pyautogui.keyUp('right')
        pyautogui.press('up')

        time.sleep(5)
        pyautogui.keyDown('1')
        time.sleep(0.5)
        pyautogui.keyUp('1')
        pyautogui.keyDown('2')
        time.sleep(0.5)
        pyautogui.keyUp('2')
        pyautogui.keyDown('5')
        time.sleep(0.5)
        pyautogui.keyUp('5')


function_map = {
    '找BOSS': function_find_boss,
    '死補助': function_support,
}

def get_artale_handle():
    return win32gui.FindWindow(None, "MapleStory Worlds-Artale (繁體中文版)")


def run_script():
    global stop_flag
    global actual_width
    global actual_height
    stop_flag = False

    hWnd = get_artale_handle()

    if hWnd == 0:
        print("找不到視窗，請確認視窗名稱正確")
        update_buttons(start_enabled=True, stop_enabled=False)
        return
    else:
        print(f"找到視窗 Handle: {hWnd}")

        if win32gui.IsIconic(hWnd):
            win32gui.ShowWindow(hWnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hWnd)

    pyautogui.PAUSE = 0.3

    print(functions_selected.get())
    selected = functions_selected.get()
    if selected in function_map:
        function_map[selected](hWnd)  # 呼叫對應的函式
    else:
        print("沒有對應的函式")

    update_buttons(start_enabled=True, stop_enabled=False)
    print("任務停止")


# -------------------- GUI 相關 --------------------

def start_thread():
    update_buttons(start_enabled=False, stop_enabled=True)
    # threading.Thread(target=run_script, daemon=True).start()
    find_boss_task.start()


def stop_script():
    global stop_flag
    # stop_flag = True
    find_boss_task.stop()

def update_buttons(start_enabled, stop_enabled):
    start_button.config(state=tk.NORMAL if start_enabled else tk.DISABLED)
    stop_button.config(state=tk.NORMAL if stop_enabled else tk.DISABLED)

def toggle_script(event=None):
    if start_button['state'] == tk.NORMAL:
        start_thread()
    elif stop_button['state'] == tk.NORMAL:
        stop_script()

def on_press(key):
    global priest_task

    if not hasattr(key, 'name'):
        return
    if key.name == 'f2':
        print("F2 event")
        bowmaster_task.toggle()
    if key.name == 'f3':
        print("F3 event")
        support_task.set_back_time(1)
        support_task.toggle()
    if key.name == 'f4':
        print("F4 event")
        support_task.set_back_time(1.5)
        support_task.toggle()
    if key.name == 'f5':
        print("F5 event")
        find_boss_task.toggle()
    if key.name == 'f6':
        print("F6 event")
        scholar_task.toggle()
    if key.name == 'f7':
        print("F7 event")
        priest_task.toggle()
    if key.name == 'f8':
        king_kong_task.toggle()
    if key.name == 'f9':
        zombie_mushking_task.toggle()
    if key.name == 'f10':
        righter_task.toggle()
    if key.name == 'f11':
        helper_task.toggle()

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"boss": {}}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# -------------------- 建立 GUI --------------------
CONFIG_FILE = "config.json"


hwnd = get_artale_handle()
bowmaster_task = BowmasterTask()
find_boss_task = FindBossTask(hwnd)
priest_task = Priest(hwnd)
king_kong_task = KingKongTask(hwnd, find_boss_task)
scholar_task = ScholarTask(hwnd, find_boss_task)
righter_task = Righter(hwnd)
support_task = SupportTask(hwnd)
zombie_mushking_task = ZombieMushKingTask(hwnd)
helper_task = HelperTask()

find_boss_task.register_boss_found_event('大菇菇', zombie_mushking_task)

config = load_config()

root = tk.Tk()
root.title("MapleStory 自動找 BOSS 工具")
root.geometry("300x200")

tk.Label(root, text="選擇功能：").pack(pady=5)

frame = tk.Frame(root)
frame.pack(pady=5)

functions_selected = tk.StringVar()
functions = ['找BOSS', '死補助']
function_menu = ttk.Combobox(frame, textvariable=functions_selected, values=functions, state="readonly")
function_menu.set(functions[0])

function_menu.pack(side=tk.LEFT)

start_button = tk.Button(root, text="開始", command=start_thread, height=2, width=10)
start_button.pack(pady=5)

stop_button = tk.Button(root, text="停止", command=stop_script, height=2, width=10, state=tk.DISABLED)
stop_button.pack(pady=5)

listener = Listener(on_press=on_press)
listener.start()

root.bind("<F5>", toggle_script)  # 新增這行來綁定 F5 鍵
root.mainloop()
