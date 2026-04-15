import threading

from pynput import mouse

from util.logger import MSLogger

_logger = MSLogger('CursorTracker')


class CursorTracker:
    """追蹤滑鼠游標的螢幕絕對座標。

    使用 pynput mouse.Listener 監聽，不輪詢，不佔 CPU。
    同一 process 只需一個實體（Singleton）。
    """

    _instance: 'CursorTracker | None' = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._x = 0
                cls._instance._y = 0
                cls._instance._listener: mouse.Listener | None = None
                cls._instance._running = False
        return cls._instance

    # ── 座標屬性 ────────────────────────────────────────────────
    @property
    def x(self) -> int:
        return self._x

    @property
    def y(self) -> int:
        return self._y

    # ── 啟動 / 停止 ─────────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._listener = mouse.Listener(on_move=self._on_move)
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        _logger.info('[CursorTracker] 已啟動')

    def stop(self):
        if not self._running:
            return
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._running = False
        _logger.info('[CursorTracker] 已停止')

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 內部回調 ────────────────────────────────────────────────
    def _on_move(self, x: int, y: int):
        self._x = x
        self._y = y