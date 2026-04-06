'''
Global Logger
'''
# Standard Import
import logging
import datetime
import os

# ── 全域共用 FileHandler（所有模組寫入同一個 log 檔）──────────────
os.makedirs("log", exist_ok=True)
_now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_LOG_PATH = f"log/msbot_{_now_str}.log"
_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s',
                               datefmt='%Y-%m-%d %H:%M:%S')

_shared_file_handler = logging.FileHandler(_LOG_PATH, mode='w', encoding="utf-8")
_shared_file_handler.setFormatter(_formatter)


class MSLogger:
    '''
    MapleStory AutoBot Logger
    '''
    def __init__(self, name="MSBot"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)

        # 所有模組共用同一個 FileHandler
        if not any(isinstance(h, logging.FileHandler) for h in self._logger.handlers):
            self._logger.addHandler(_shared_file_handler)

        # 每個 logger 仍輸出到 console
        if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                   for h in self._logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(_formatter)
            self._logger.addHandler(console_handler)

    def set_level(self, level):
        '''
        Set logger level, e.g. DEBUG, INFO, WARNING
        '''
        self._logger.setLevel(level)

    def info(self, msg):
        self._logger.info(msg)

    def warning(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)

    def debug(self, msg):
        self._logger.debug(msg)

    def addHandler(self, handle):
        self._logger.addHandler(handle)

# Initialize shared logger instance for global import
logger = MSLogger()
