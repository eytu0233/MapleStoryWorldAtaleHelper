import threading
import abc

from util.GameDetector import get_artale_hwnd


class MapleTask(abc.ABC):
    @staticmethod
    def detect_hwnd():
        hwnd = get_artale_hwnd()
        if hwnd == 0:
            print("[MapleTask] 找不到 Artale 視窗")
        return hwnd

    def __init__(self):
        self.is_running = False
        self.is_started = False
        self.wait_event = threading.Event()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

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
        print('MapleTask start')
        if self.is_running:
            return
        self.is_running = True
        self.wait_event.set()
        if self.is_started is False:
            self.is_started = True
            self.thread.start()
        self.start_event_notify()

    def stop(self):
        print('MapleTask stop')
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
