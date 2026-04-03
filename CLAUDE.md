# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 執行方式

```bash
python GUI_main.py
```

tkinter GUI 啟動後，透過熱鍵控制各任務（詳見下方熱鍵對應表）。無單元測試框架，功能驗證需直接在遊戲視窗中執行。

## 架構概覽

### 類別繼承鏈

```
MapleTask（抽象基底，threading）
└── GameCharacter（抽象，新增小地圖位置、HP/MP、按鍵控制）
    ├── NightLordTask       ← 標準地圖，事件佇列狀態機
    ├── BowmasterTask       ← 標準地圖，事件佇列狀態機
    ├── Lab102RoomTask      ← 二層地圖，爬升邏輯
    ├── OakBeetleTask       ← 多層地圖，JSON 設定驅動
    ├── GhostWomen / Priest / ScholarTask / MapTestTask
    └── SupportTask
MapleTask
    ├── MinimapTask         ← 黃點偵測，~60fps
    ├── HelperTask
    ├── KingKongTask / ZombieMushKingTask / FindBossTask / MonitorBossAliveTask
    └── Righter
```

### 核心元件

| 檔案 | 職責 |
|------|------|
| `MapleTask.py` | `start()` / `stop()` / `toggle()`；`wait_stop_event(timeout)` 是所有睡眠的唯一入口，回傳 True 表示收到停止訊號 |
| `GameWindow.py` | 追蹤 Artale 視窗 HWND，透過 `PrintWindow` DC 截圖，背景執行緒每 0.5 秒輪詢一次 |
| `MinimapTask.py` | 偵測小地圖黃點（HSV 範圍 H 26–38），輸出 `pos: tuple[float, float]`（0.0–1.0）；同時支援地圖錄製與位置事件 |
| `GameCharacter.py` | 所有 `*Task.py` 的基底；`_init_shared()` 確保 `GameWindow`、`MinimapTask`、HP/MP monitor 全域只建立一次 |
| `GameDetector.py` | 透過視窗標題 `"MapleStory Worlds-Artale"` 找 HWND |
| `MapData.py` | 錄製地圖的序列化／反序列化，存放於 `maps/*.json` |
| `GUI_main.py` | tkinter 主視窗 + pynput 熱鍵監聽；`print` 輸出重導向至 log 視窗 |
| `character_control.py` | `ArtaleController`：按鍵映射與技能延遲設定，讀取 `board_config.json` |

### 停止訊號慣例

`task()` 方法中每一個阻塞呼叫都必須：
```python
if self.wait_stop_event(duration):   # 或 _hold_key / move_up / move_down / jump
    break  # 或 return
```
`wait_stop_event` 同時兼作 sleep；**禁止使用** `time.sleep()`（會忽略停止訊號）。

### 等待多個條件：使用 Event，禁止 polling

需要同時等待「位置到達」與「被打斷」兩種條件時，建立共用 `done` event，由各來源 set，再以 `done.wait()` 單次阻塞：

```python
import threading
done = threading.Event()

# 條件一：位置事件
eid = self.minimap_task.register_pos_event(
    condition=lambda x, y: y >= 0.9,
    callback=done.set,
    once=True,
)
# 條件二：interrupt_event（daemon thread 監聽，不 polling）
threading.Thread(target=lambda: (self.interrupt_event.wait(), done.set()),
                 daemon=True).start()

done.wait()  # 純阻塞，無 polling
self.minimap_task.unregister_pos_event(eid)
```

**禁止**用 `while` + `event.wait(timeout)` 的 polling 迴圈來模擬多事件等待。

### 座標系

- `map_x` / `map_y` 回傳 `0.0–1.0`（比例，0 = 左/上，1 = 右/下）
- `GameCharacter` 子類別慣用 `self.map_x * 100` 換算為百分比做常數比對
- 小地圖邊界（像素）存於各地圖的 `*.json`，由 `MinimapTask.set_bounds()` 套用

### Command 設計準則（CommandGameCharacter 體系）

每個 `Command` 只能做**一件事**，`trigger_command` 內只能有**一個** `self.interrupt_event.wait`。

**禁止** `done.wait()`、daemon thread 模式、`while` loop、`time.sleep`。

**等待位置條件**的標準寫法：將 position callback 設為呼叫 `self.interrupt_command()`，再用 `interrupt_event.wait` 阻塞。結束後透過本地 flag 判斷是「條件達成」還是「外部打斷」：

```python
def trigger_command(self):
    self.interrupt_event.clear()
    reached = [False]

    def _on_condition():
        reached[0] = True
        self.interrupt_command()   # 讓 interrupt_event.wait 提前返回

    eid = self._char.minimap_task.register_pos_event(condition, _on_condition, once=True)

    pyautogui.keyDown('right')
    self.interrupt_event.wait(10)  # 唯一的 wait
    pyautogui.keyUp('right')

    self._char.minimap_task.unregister_pos_event(eid)

    if reached[0]:
        # 條件達成 → 推進到下一個 Command
        self._queue.put(NextCommand(self._char, self._queue))
    else:
        # 外部打斷，條件未達成 → 重新入隊重試
        self._queue.put(self)
```

**條件達成** → 將下一個 Command 加入 queue；**被打斷或條件未達成** → 將自身重新加回 queue。

## 新增地圖任務 Checklist

1. 建立 `<MapName>Task.py`，繼承 `GameCharacter`，指定 `Job.NIGHTLORD`（或其他職業）
2. 實作三個抽象方法：`move(direction)`、`normal_attack()`、`task()`
3. 若需地圖設定，建立同名 `<MapName>.json`（參考 `OakBeetle.json` 格式）
4. 在 `GUI_main.py` 匯入並綁定熱鍵

## 熱鍵對應

| 熱鍵 | 任務 |
|------|------|
| F2  | BowmasterTask |
| F3  | SupportTask (back_time=1s) |
| F4  | SupportTask (back_time=1.5s) |
| F5  | 地圖錄製 toggle |
| F6  | MapTestTask |
| F7  | Priest |
| F8  | GhostWomen（鬼女） |
| F9  | Lab102RoomTask（研究所102） |
| F10 | NightLordTask（龍蛋） |
| F11 | HelperTask |

## 設定檔

| 檔案 | 用途 |
|------|------|
| `board_config.json` | `ArtaleController` 按鍵映射與技能僵直延遲 |
| `config.json` | Boss 圖片路徑、全域小地圖邊界預設值 |
| `<MapName>.json` | 各地圖小地圖邊界（像素），多層地圖另含 `timing` 與 `layers` |
| `maps/*.json` | `MinimapTask` 自動錄製的地圖路徑點資料（`MapData` 格式） |