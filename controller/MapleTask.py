import threading
import abc

from util.GameDetector import get_artale_hwnd
from util.logger import MSLogger

_logger = MSLogger('MapleTask')


class _SingletonABCMeta(abc.ABCMeta):
    _instances: dict = {}
    _by_name: dict = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
            cls._by_name[cls.__name__] = instance
        return cls._instances[cls]


class MapleTask(abc.ABC, metaclass=_SingletonABCMeta):
    @staticmethod
    def detect_hwnd():
        hwnd = get_artale_hwnd()
        if hwnd == 0:
            _logger.warning("[MapleTask] 找不到 Artale 視窗")
        return hwnd

    def __init__(self):
        self.is_running = False
        self.is_started = False
        self.wait_event = threading.Event()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    @classmethod
    def get(cls, name: str) -> "MapleTask | None":
        """以類別名稱取得已建立的 Singleton 實體，找不到回傳 None。"""
        return _SingletonABCMeta._by_name.get(name)

    @classmethod
    def all(cls) -> dict[str, "MapleTask"]:
        """回傳所有已建立的 Singleton 實體 {類別名稱: 實體}。"""
        return dict(_SingletonABCMeta._by_name)

    @abc.abstractmethod
    def task(self):
        return NotImplemented

    def start_event_notify(self):
        pass

    def stop_event_notify(self):
        pass

    def run(self):
        while True:
            self.wait_event.wait()
            self.task()

    def start(self):
        _logger.info('MapleTask start')
        if self.is_running:
            return
        self.is_running = True
        self.stop_event.clear()   # 清除上一次 stop() 殘留的訊號，避免 task() 立即退出
        self.wait_event.set()
        if self.is_started is False:
            self.is_started = True
            self.thread.start()
        self.start_event_notify()

    def stop(self):
        _logger.info('MapleTask stop')
        if not self.is_running:
            return
        self.is_running = False
        self.stop_event.set()
        self.wait_event.clear()
        self.stop_event_notify()

    def wait_stop_event(self, timeout=None):
        ret = self.stop_event.wait(timeout)
        self.stop_event.clear()
        return ret

    def toggle(self):
        if self.is_running:
            self.stop()
        else:
            self.start()
