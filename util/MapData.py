import json
import os
from dataclasses import dataclass, field

_MAPS_DIR = "maps"


@dataclass
class MapData:
    """
    代表一張已錄製的地圖。

    Attributes:
        name          : 地圖名稱（同時作為存檔檔名）
        points        : 按經過順序排列的唯一格點列表 [(x, y), ...]，座標 0.0～1.0
        climb_indices : 爬升點在 points 中的索引集合
        bounds        : 小地圖邊界（遊戲視窗像素座標）(x0, y0, x1, y1)
        record_decimals: 格點精度（小數位數）
        climb_x_tol   : 爬升偵測 x 軸容差
        climb_y_step  : 爬升偵測 y 軸最小步距
        climb_min_run : 爬升偵測最小連續步數
    """
    name: str
    points: list[tuple[float, float]] = field(default_factory=list)
    climb_indices: set[int] = field(default_factory=set)
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)   # (x0, y0, x1, y1) 視窗像素
    record_decimals: int = 2
    climb_x_tol: float = 0.04
    climb_y_step: float = 0.008
    climb_min_run: int = 4

    # ── 便捷查詢 ─────────────────────────────────────────────────

    @property
    def point_set(self) -> set[tuple[float, float]]:
        """所有格點的集合（O(1) 查詢用）。"""
        return set(self.points)

    @property
    def climb_point_set(self) -> set[tuple[float, float]]:
        """爬升點座標集合（O(1) 查詢用）。"""
        return {self.points[i] for i in self.climb_indices if i < len(self.points)}

    # ── 序列化 ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "bounds": list(self.bounds),
            "record_decimals": self.record_decimals,
            "climb_x_tol": self.climb_x_tol,
            "climb_y_step": self.climb_y_step,
            "climb_min_run": self.climb_min_run,
            "points": [list(p) for p in self.points],
            "climb_indices": sorted(self.climb_indices),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MapData":
        return cls(
            name=data.get("name", "unnamed"),
            points=[tuple(p) for p in data.get("points", [])],
            climb_indices=set(data.get("climb_indices", [])),
            bounds=tuple(data.get("bounds", (0, 0, 0, 0))),
            record_decimals=data.get("record_decimals", 2),
            climb_x_tol=data.get("climb_x_tol", 0.04),
            climb_y_step=data.get("climb_y_step", 0.008),
            climb_min_run=data.get("climb_min_run", 4),
        )

    # ── 存檔 / 讀檔 ──────────────────────────────────────────────

    def save(self) -> str:
        """將地圖存為 maps/<name>.json，回傳完整路徑。"""
        os.makedirs(_MAPS_DIR, exist_ok=True)
        path = os.path.join(_MAPS_DIR, f"{self.name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"[MapData] 已存檔：{path}"
              f"（{len(self.points)} 點，爬升點 {len(self.climb_indices)} 個）")
        return path

    @classmethod
    def load(cls, name: str) -> "MapData":
        """從 maps/<name>.json 讀取，回傳 MapData 實例。"""
        path = os.path.join(_MAPS_DIR, f"{name}.json")
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def load_latest(cls) -> "MapData | None":
        """讀取 maps/ 目錄中檔名字母序最新的 JSON，回傳 MapData 或 None。"""
        if not os.path.isdir(_MAPS_DIR):
            return None
        files = sorted(
            [f for f in os.listdir(_MAPS_DIR) if f.endswith(".json")],
            reverse=True
        )
        if not files:
            return None
        name = files[0][:-5]   # 去掉 .json
        return cls.load(name)

    @classmethod
    def list_names(cls) -> list[str]:
        """列出 maps/ 目錄中所有可用地圖名稱（不含副檔名）。"""
        if not os.path.isdir(_MAPS_DIR):
            return []
        return sorted(
            [f[:-5] for f in os.listdir(_MAPS_DIR) if f.endswith(".json")],
            reverse=True
        )

    def __repr__(self) -> str:
        bx0, by0, bx1, by1 = self.bounds
        return (f"MapData(name={self.name!r}, "
                f"points={len(self.points)}, "
                f"climb={len(self.climb_indices)}, "
                f"bounds=({bx0},{by0})→({bx1},{by1}))")
