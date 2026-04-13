"""
ModelController — 使用 YOLO 模型偵測遊戲畫面中的怪物，並透過 callback 回報結果。

使用方式：
    from ultralytics import YOLO
    controller = ModelController(game_window, 'models/monster.pt', on_detected)
    controller.start()
    ...
    controller.stop()

    def on_detected(results: list[dict]):
        # results 每個元素：{'bbox': (x1, y1, x2, y2), 'conf': float, 'cls': int, 'name': str}
        ...

架構說明：
    從 gw.get_latest_frame() 讀取 GameWindow 的全幀緩衝後裁切，
    PrintWindow 由 GameWindow 統一以 120fps 呼叫，所有 subscriber 共用同一張幀。
"""

import threading
from typing import Callable

import numpy as np
from ultralytics import YOLO

from util.logger import MSLogger
from .GameWindow import GameWindow

_logger = MSLogger('ModelController')

# ── 掃描區域（比例座標：x, y, w, h）── 全螢幕遊戲區域
_SCAN_REGION = (0.0, 0.0, 1.0, 1.0)

# ── 推理間隔（秒）── 實際速率受 YOLO 推理時間限制
_INFER_INTERVAL = 1 / 120  # ~120fps 上限

# ── 偵測信心閾值
_CONF_THRESHOLD = 0.5


class ModelController:
    """
    使用 YOLO 模型持續偵測遊戲畫面中的怪物。

    Args:
        game_window:    GameWindow 實例
        model_path:     YOLO .pt 模型路徑
        callback:       偵測到怪物時呼叫，傳入 list[dict]；
                        每個 dict 含 bbox / conf / cls / name
        conf:           信心閾值，低於此值的偵測結果將被過濾
        scan_region:    截圖區域 (x_ratio, y_ratio, w_ratio, h_ratio)，預設全視窗
        infer_interval: 兩次推理之間的等待秒數
    """

    def __init__(
        self,
        game_window: GameWindow,
        model_path: str,
        callback: Callable[[list[dict]], None],
        conf: float = _CONF_THRESHOLD,
        scan_region: tuple[float, float, float, float] = _SCAN_REGION,
        infer_interval: float = _INFER_INTERVAL,
    ):
        self._gw = game_window
        self._model_path = model_path
        self._callback = callback
        self._conf = conf
        self._scan_region = scan_region
        self._infer_interval = infer_interval
        self._model: YOLO | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── 公開介面 ─────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            _logger.warning("[ModelController] 已在執行中，忽略重複 start()")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ModelController")
        self._thread.start()
        _logger.info("[ModelController] 已啟動")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        _logger.info("[ModelController] 已停止")

    # ── 推理 ─────────────────────────────────────────────────────

    def _load_model(self):
        _logger.info(f"[ModelController] 載入模型：{self._model_path}")
        self._model = YOLO(self._model_path)
        _logger.info("[ModelController] 模型載入完成")

    def _infer(self, frame: np.ndarray) -> list[dict]:
        """對 frame 執行推理，回傳過濾後的偵測結果列表。"""
        results = self._model(frame, conf=self._conf, verbose=False)
        detections: list[dict] = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            names = r.names
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    'bbox': (x1, y1, x2, y2),
                    'conf': float(box.conf[0]),
                    'cls':  int(box.cls[0]),
                    'name': names[int(box.cls[0])],
                })
        return detections

    # ── 主迴圈 ───────────────────────────────────────────────────

    def _run(self):
        self._load_model()
        _logger.info(f"[ModelController] 執行中（conf={self._conf}, interval={self._infer_interval}s）")

        while not self._stop_event.wait(self._infer_interval):
            gw = self._gw
            if gw is None or not gw.is_valid:
                continue

            full_frame = gw.get_latest_frame()
            if full_frame is None:
                continue

            fh, fw = full_frame.shape[:2]
            rx = int(fw * self._scan_region[0])
            ry = int(fh * self._scan_region[1])
            rw = int(fw * self._scan_region[2])
            rh = int(fh * self._scan_region[3])
            frame = full_frame[ry:ry + rh, rx:rx + rw]
            if frame.size == 0:
                continue

            try:
                detections = self._infer(frame)
                if detections:
                    self._callback(detections)
            except Exception as e:
                _logger.error(f"[ModelController] 推理異常: {e}")

        _logger.info("[ModelController] 迴圈結束")
