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

stop_flag = False  # 全域停止旗標
monitor_flag = False
holy_thread = None
mushkill_thread = None
monitor_thread = None
stop_event = None

template_base_width = 2576
template_base_height = 1416

WIDTH_SCALE = 0.2
HEIGHT_SCALE = 0.07
X_OFFSET_SCALE = 0.4
Y_OFFSET_SCALE = 0.25

def get_actual_width_height(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    return width, height


def find_and_click(img_file_name, hWnd, delay=0, click=1, loop=False, threshold=0.8):
    global template_base_width
    global template_base_height

    actual_width, actual_height = get_actual_width_height(hWnd)

    counter = 0

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
        found = find_and_click("img/market.png", hWnd, loop=True)
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
    threading.Thread(target=run_script, daemon=True).start()


def stop_script():
    global stop_flag
    stop_flag = True


def update_buttons(start_enabled, stop_enabled):
    start_button.config(state=tk.NORMAL if start_enabled else tk.DISABLED)
    stop_button.config(state=tk.NORMAL if stop_enabled else tk.DISABLED)


def toggle_script(event=None):
    if start_button['state'] == tk.NORMAL:
        start_thread()
    elif stop_button['state'] == tk.NORMAL:
        stop_script()


def toggle_monitor_thread():
    global stop_flag
    global monitor_thread

    if holy_thread is not None:
        stop_flag = True
        monitor_thread.join()
    monitor_thread = threading.Thread(target=monitor_boss_alive_thread, daemon=True)

    if monitor_thread.is_alive() is False:
        print("monitor_thread start")
        monitor_thread.start()
    else:
        print("monitor_thread stop")
        stop_flag = True
        monitor_thread.join()
        monitor_thread = None


def holy_light_thread():
    global stop_event
    global stop_flag
    global monitor_flag

    print("holy_thread starting")

    is_right = False
    while not stop_flag:
        print("keyDown x")
        pyautogui.keyDown('x')
        if stop_event.wait(timeout=20):
            stop_event.clear()
            if monitor_flag:
                pyautogui.keyUp('x')
                print("monitor_flag")
                time.sleep(0.5)
                pyautogui.keyDown('down')
                time.sleep(0.1)
                pyautogui.keyDown('alt')
                time.sleep(0.1)
                pyautogui.keyUp('down')
                pyautogui.keyUp('alt')
                time.sleep(3)
                stop_flag = True
                start_thread()
            break
        print("keyUp x")
        pyautogui.keyUp('x')
        if stop_event.wait(timeout=1):
            stop_event.clear()
            if monitor_flag:
                print("monitor_flag")
                time.sleep(0.5)
                pyautogui.keyDown('down')
                time.sleep(0.1)
                pyautogui.keyDown('alt')
                time.sleep(0.1)
                pyautogui.keyUp('down')
                pyautogui.keyUp('alt')
                time.sleep(3)
                stop_flag = True
                start_thread()
            break
        if is_right is True:
            print("right")
            pyautogui.keyDown('right')
            time.sleep(0.05)
            pyautogui.keyUp('right')
            is_right = not is_right
        else:
            print("left")
            pyautogui.keyDown('left')
            time.sleep(0.05)
            pyautogui.keyUp('left')
            is_right = not is_right
    print("holy_thread end")


def toggle_holy_light_thread():
    global stop_flag
    global holy_thread
    global stop_event

    if stop_event is None:
        stop_event = threading.Event()

    if holy_thread is not None:
        stop_flag = True
        stop_event.set()
        holy_thread.join()

    print("holy_thread create")
    holy_thread = threading.Thread(target=holy_light_thread, daemon=True)

    if holy_thread.is_alive() is False:
        stop_flag = False
        print("holy_thread start")
        holy_thread.start()
        toggle_monitor_thread()
    else:
        print("holy_thread stop")
        stop_flag = True
        stop_event.set()
        holy_thread.join()
        holy_thread = None


def mushking_kill_thread():
    global stop_event
    global stop_flag
    global monitor_flag

    print("mushking_kill_thread starting")

    for i in range(1, 4):
        pyautogui.keyDown('down')
        pyautogui.keyDown('alt')
        time.sleep(0.1)
        pyautogui.keyUp('down')
        pyautogui.keyUp('alt')
        time.sleep(0.5)

    while not stop_flag:
        pyautogui.keyDown('x')
        if stop_event.wait(timeout=1):
            stop_event.clear()
            if monitor_flag:
                print("Boss not found event")
                pyautogui.keyUp('x')
                pyautogui.keyDown('right')
                time.sleep(5.5)
                pyautogui.keyUp('right')
                time.sleep(0.1)
                pyautogui.keyDown('left')
                time.sleep(5.5)
                pyautogui.keyUp('left')
                stop_flag = True
                start_thread()
            break
        pyautogui.keyUp('x')
        pyautogui.keyDown('alt')
        time.sleep(0.1)
        pyautogui.keyUp('alt')

    print("mushking_kill_thread end")


def extract_percentage(text):
    match = re.search(r'\((\d+)', text)
    if match:
        val = float(match.group(1))
        return 100 if val > 100 else val
    return 100


def extract_number(text):
    match = re.search(r'[\u4e00-\u9fff]+\s*([\d,]+)', text)
    if match:
        number_str = match.group(1).replace(',', '')  # 去掉千分位逗號
        return int(number_str)
    return 0xFFFFFFFF


def monitor_boss_alive_thread():
    global stop_event
    global stop_flag
    global monitor_flag

    print("monitor_boss_alive_thread starting")

    hWnd = get_artale_handle()
    boss_hp = 0xFFFFFFFF
    boss_hp_percent = 100
    counter = 0
    found_once = False

    start_time = time.time()

    while not stop_flag:
        results = recognize_text(hWnd, 0.11, 0.03, 0.19, 0.03)

        if len(results) == 0:
            if time.time() - start_time < 120:
                continue
            if found_once is False:
                continue
            if boss_hp_percent < 8 and boss_hp < 10000:
                print("找不到Boss血條，停止任務")
                monitor_flag = True
                stop_event.set()
                break
            else:
                counter += 1
                print(f"可能是誤判，增加counter {counter}")
                if counter > 4:
                    print("找不到Boss血條，停止任務")
                    monitor_flag = True
                    stop_event.set()
                    break
        else:
            for bbox, text, conf in results:
                print(f"找到關鍵字 ：{text} bbox {bbox}")
                val = extract_percentage(text)
                boss_hp_percent = val if val < boss_hp_percent else boss_hp_percent
                print(f"boss_hp_percent ：{boss_hp_percent}")
                val = extract_number(text)
                boss_hp = val if val < boss_hp else boss_hp
                print(f"boss_hp ：{boss_hp}")
                found_once = True
    print("monitor_boss_alive_thread stop")

def toggle_mushking_kill_thread():
    global stop_flag
    global mushkill_thread
    global stop_event

    if stop_event is None:
        stop_event = threading.Event()

    if mushkill_thread is not None:
        stop_flag = True
        stop_event.set()
        mushkill_thread.join()
    print("mushking_kill_thread create")
    mushkill_thread = threading.Thread(target=mushking_kill_thread, daemon=True)

    if mushkill_thread.is_alive() is False:
        stop_flag = False
        print("mushking_kill_thread start")
        mushkill_thread.start()
        toggle_monitor_thread()
    else:
        print("mushking_kill_thread stop")
        stop_flag = True
        stop_event.set()
        mushkill_thread.join()
        mushkill_thread = None


def on_press(key):
    if not hasattr(key, 'name'):
        return
    if key.name == 'f5':
        print("F5 event")
        toggle_script()
    if key.name == 'f6':
        print("F6 event")
        toggle_holy_light_thread()
    if key.name == 'f7':
        print("F7 event")
        toggle_mushking_kill_thread()


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
