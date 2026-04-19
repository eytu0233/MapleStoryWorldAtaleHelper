# MapleStory World Atale ZhTW Channel Change

## 環境安裝

### 1. 安裝 uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安裝完成後重新開啟終端機。

### 2. 安裝套件

```bash
uv sync --extra yolo
```

> uv 會自動建立虛擬環境（`.venv`）並安裝所有相依套件，包含 PyTorch CUDA 124。

### 3. 執行

```bash
uv run python main.py
```

---

## 套件說明

| 群組 | 套件 | 說明 |
|------|------|------|
| 基本 | pyautogui, pynput | 滑鼠鍵盤控制 |
| 基本 | opencv-python, pillow, numpy | 影像處理 |
| 基本 | easyocr | OCR 文字辨識 |
| 基本 | pywin32 | Windows API |
| 基本 | scapy, websockets | 網路封包 |
| yolo | ultralytics | YOLO 模型 |
| yolo | torch, torchvision, torchaudio | PyTorch CUDA 124 |
| yolo | mss | 螢幕擷取 |

---

## Discord Bot 設定

### 1. 建立 Discord Bot 並取得 Token

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)。
2. 點擊 **New Application**，輸入名稱後建立。
3. 在左側選單選擇 **Bot**。
4. 點擊 **Reset Token**（或 **Copy**）取得你的 Token，請妥善保管。
5. 在 **Privileged Gateway Intents** 區塊，開啟 **Message Content Intent**（機器人讀取訊息內容所必需）。

### 2. 邀請機器人進入伺服器

1. 在左側選擇 **OAuth2** → **URL Generator**。
2. **Scopes** 勾選 `bot`。
3. **Bot Permissions** 勾選 `Read Messages/View Channels` 與 `Send Messages`。
4. 複製產生的網址到瀏覽器，將機器人邀請進你的伺服器。

### 3. 設定 config.json

將 Token 與頻道 ID 填入 `config.json`：

```json
{
  "discord": {
    "token": "你的 Bot Token",
    "channel_id": 123456789012345678,
    "allowed_user_ids": []
  }
}
```

> `channel_id`：在 Discord 文字頻道上按右鍵 → **複製頻道 ID**（需先在「使用者設定 → 進階」啟用「開發者模式」）。
> `allowed_user_ids`：空陣列表示允許所有人使用指令；填入使用者 ID 則只允許指定人員。

### 4. 可用指令

| 指令 | 說明 |
|------|------|
| `!ping` | 確認機器人在線，回傳延遲 |
| `!status` | 查詢各任務執行狀態 |
| `!start <任務名稱>` | 啟動指定任務 |
| `!stop <任務名稱>` | 停止指定任務 |
| `!help` | 顯示指令列表 |

---

## 設定檔說明

### support.json

補師機器人（SupportBot / F4）的行為設定。

```json
{
  "support": {
    "interval": 270,
    "buff_skills": ["1", "2", "5"]
  }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `interval` | int | 在自由市場等待的秒數，時間到後離開並重新施放 buff |
| `buff_skills` | string[] | 依序施放的技能按鍵列表，每個技能按下持續 0.6 秒 |

---

### free_market.json

自由市場地圖的小地圖邊界與操作位置設定。

```json
{
  "minimap_bounds": { "x": 18, "y": 193, "w": 348, "h": 233 },
  "free_market_button_pos": { "x": 0.76, "y": 0.965 },
  "free_market_exit": { "minimap_x": 0.15, "minimap_y": 0.84 }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `minimap_bounds` | object | 自由市場地圖的小地圖邊界（遊戲視窗像素座標）。進入自由市場後套用，離開後還原 |
| `minimap_bounds.x` / `.y` | int | 小地圖左上角像素座標 |
| `minimap_bounds.w` / `.h` | int | 小地圖寬高（像素） |
| `free_market_button_pos` | object | 遊戲畫面上「自由市場」按鈕的視窗相對座標（0.0～1.0） |
| `free_market_exit` | object | 進入自由市場後，角色要移動到的出口等待位置（小地圖比例座標） |
| `free_market_exit.minimap_x` | float | 出口等待點的小地圖 x 比例（0.0＝左，1.0＝右） |
| `free_market_exit.minimap_y` | float | 同時作為「確認已進入自由市場」的 y 基準值，實際 y 與此值差距在 ±0.05 內視為成功 |

---

### maps/\<MapName\>.json（多層地圖設定）

多層地圖任務（如龍蛋 `map_dragon_nest.json`）除了基本的小地圖邊界外，還需設定角色銀幕座標換算參數，供怪物偵測方向判斷使用。

#### 完整範例

```json
{
  "minimap_bounds": {
    "x": 0.00699,
    "y": 0.1364,
    "w": 0.13903,
    "h": 0.17031
  },
  "layers": [
    { "id": 1, "map_y": 0.36, "map_x_min": 0.43, "map_x_max": 0.86 },
    { "id": 2, "map_y": 0.59, "map_x_min": 0.55, "map_x_max": 0.86 },
    { "id": 3, "map_y": 0.82, "map_x_min": 0.15, "map_x_max": 0.86 }
  ],
  "char_screen_x": {
    "facing_left":  { "base_x": 1247, "left_transition": 0.45, "right_transition": 0.54 },
    "facing_right": { "base_x": 1360, "left_transition": 0.46, "right_transition": 0.58 }
  },
  "char_screen_y": {
    "default_direction": "down",
    "up":   950,
    "down": 1050
  }
}
```

#### `minimap_bounds`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `x` / `y` | float | 小地圖左上角在遊戲視窗的比例座標（0.0～1.0） |
| `w` / `h` | float | 小地圖的寬高比例 |

#### `layers`（各層座標範圍）

每個物件代表地圖中的一個平台層，`MinimapTask` 會根據角色目前的 `map_y` 找最近的層，決定該層的 x 邊界供銀幕座標換算使用。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | int | 層編號（僅供識別，由上往下遞增） |
| `map_y` | float | 該層在小地圖上的 y 比例座標（0.0＝最上層） |
| `map_x_min` | float | 該層的小地圖 x 左邊界 |
| `map_x_max` | float | 該層的小地圖 x 右邊界 |

#### `char_screen_x`（角色銀幕 X 換算）

角色在銀幕上的 X 座標並非線性對應小地圖 X，而是分三段換算。`facing_left` 與 `facing_right` 分別對應角色朝左與朝右時的參數。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `base_x` | int | 中段固定區間的角色銀幕 X（像素），即鏡頭跟隨時角色的銀幕基準位置 |
| `left_transition` | float | 左轉換點（小地圖 x 比例）。角色在此點左側時銀幕 X 線性縮小 |
| `right_transition` | float | 右轉換點（小地圖 x 比例）。角色在此點右側時銀幕 X 線性增大 |

**三段換算規則：**

```
小地圖 x 落在以下區間時，角色銀幕 X＝
  [map_x_min,   left_transition)   →  base_x × (map_x - map_x_min) / (left_transition - map_x_min)
  [left_transition, right_transition]  →  base_x（固定，鏡頭跟隨中）
  (right_transition, map_x_max]   →  base_x + (銀幕寬度 - base_x) × (map_x - right_transition) / (map_x_max - right_transition)
```

直觀說明：角色靠近地圖左邊界時，鏡頭貼著左牆不動，角色在銀幕上偏左；靠近右邊界時對稱；中間大部分區域鏡頭跟著角色移動，角色固定在銀幕中央附近。

#### `char_screen_y`（角色銀幕 Y）

角色在銀幕上的 Y 座標只有兩種狀態，取決於垂直移動方向（往高樓層移動時角色在銀幕偏上，往低樓層時偏下）。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `default_direction` | string | 任務啟動時的預設方向，`"up"` 或 `"down"` |
| `up` | int | 往高樓層移動時角色銀幕 Y（像素），需在遊戲中實測後填入 |
| `down` | int | 往低樓層移動時角色銀幕 Y（像素），需在遊戲中實測後填入 |

> **校正方式**：在遊戲中開啟 DebugOverlay，觀察角色名字邊框的 Y 座標，分別在換層向上、向下移動時記錄數值填入。

#### 如何在任務中更新方向

任務程式碼中需主動更新 `MinimapTask` 的方向狀態：

```python
# 角色轉向時（左右攻擊、移動）
self.minimap_task.char_facing = 'left'   # 或 'right'

# 角色換層時
self.minimap_task.char_y_direction = 'up'    # 往高層移動
self.minimap_task.char_y_direction = 'down'  # 往低層移動
```

更新後，`GameCharacter.screen_x` / `screen_y` 會自動依公式重算，供怪物偵測範圍判斷使用。

---

## 常用指令

```bash
# 查看目前環境的套件
uv pip list

# 新增套件
uv add <package-name>

# 更新所有套件
uv sync --upgrade
```
