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

## 常用指令

```bash
# 查看目前環境的套件
uv pip list

# 新增套件
uv add <package-name>

# 更新所有套件
uv sync --upgrade
```
