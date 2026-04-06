import random

from controller.GameCharacter import GameCharacter
from util.logger import MSLogger

_logger = MSLogger('MapTestTask')
from util.MapData import MapData
from controller.MinimapTask import _RECORD_DECIMALS

_MOVE_STEP = 0.4   # 每步移動持續時間（秒）


class MapTestTask(GameCharacter):
    """
    地圖探索測試角色。
    - 載入最近一次錄製的地圖（MapData）
    - 持續在地圖上左右移動
    - 抵達爬升點時有 50% 機率執行 move_up()
    - 移動到地圖外（無記錄位置）時立即反向
    - 一開始及爬升完後都往右移動
    """

    def __init__(self):
        super().__init__(name='MapTest')
        self._direction = 'right'
        self._map_data: MapData | None = None
        self._map_points_set:   set[tuple[float, float]] = set()
        self._climb_points_set: set[tuple[float, float]] = set()
        self._load_latest_map()

    # ── 地圖載入 ─────────────────────────────────────────────────

    def _load_latest_map(self):
        """載入 maps/ 目錄中最新的 MapData。"""
        md = MapData.load_latest()
        if md is None:
            _logger.info("[MapTestTask] 無可用地圖，將以無地圖資料執行")
            return
        self.load_map_data(md)

    def load_map(self, name: str):
        """手動載入指定名稱的地圖。"""
        self.load_map_data(MapData.load(name))

    def load_map_data(self, md: MapData):
        """套用 MapData（同時更新 MinimapTask 邊界）。"""
        self._map_data         = md
        self._map_points_set   = md.point_set
        self._climb_points_set = md.climb_point_set
        if md.bounds != (0, 0, 0, 0):
            self.minimap_task.set_bounds(*md.bounds)
        _logger.info(f"[MapTestTask] 已載入：{md}")

    # ── GameCharacter 抽象方法 ────────────────────────────────────

    def move(self, direction: str) -> bool:
        return self._hold_key(direction, 1.5)

    def normal_attack(self) -> bool:
        return False

    # ── 輔助 ─────────────────────────────────────────────────────

    def _pos_key(self) -> tuple[float, float]:
        """取得目前位置對應的格點鍵（與 MinimapTask 相同精度）。"""
        x, y = self.minimap_task.pos
        return round(x, _RECORD_DECIMALS), round(y, _RECORD_DECIMALS)

    def _reverse(self):
        self._direction = 'left' if self._direction == 'right' else 'right'

    # ── Task 主迴圈 ──────────────────────────────────────────────

    def task(self):
        _logger.info("MapTestTask starting")

        while True:
            key = self._pos_key()

            if key in self._climb_points_set and random.random() < 0.5:
                # 爬升點：50% 機率往上移動，完成後重置為往右
                _logger.info(f"[MapTestTask] 爬升點 {key}，往上移動")
                if self.move_up():
                    break
                self._direction = 'right'

            elif self._map_points_set and key not in self._map_points_set:
                # 移動到地圖外（無記錄位置）：反向
                _logger.info(f"[MapTestTask] 位置 {key} 不在地圖內，反向 → {self._direction}")
                self._reverse()

            # 往當前方向移動一步
            if self._hold_key(self._direction, _MOVE_STEP):
                break

        _logger.info("MapTestTask end")
