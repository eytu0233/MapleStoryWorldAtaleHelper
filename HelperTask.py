import random
import time
import pyautogui

from controller.MapleTask import MapleTask
from util.logger import MSLogger

_logger = MSLogger('HelperTask')


class HelperTask(MapleTask):
    def __init__(self):
        super(HelperTask, self).__init__()

    def task(self):
        _logger.info(f"Helper thread started")
        while not self.wait_stop_event(0.1):
            pyautogui.press('=')
        _logger.info(f"Helper thread stopped")