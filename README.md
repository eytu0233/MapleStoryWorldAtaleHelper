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

## 常用指令

```bash
# 查看目前環境的套件
uv pip list

# 新增套件
uv add <package-name>

# 更新所有套件
uv sync --upgrade
```
