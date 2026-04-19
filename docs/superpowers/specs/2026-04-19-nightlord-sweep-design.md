# NightLord 往返掃蕩移動邏輯設計

**日期：** 2026-04-19  
**檔案：** `job/NightLord_map_separate.py`

## 背景

原邏輯：移動到中間觀察點（`_CENTER_X`）→ 統計左右怪數 → 原地攻擊，依無怪計時器或強制計時器才移往邊界。

新需求：角色一開始隨機往左或右邊界移動，到達後折返，邊走邊搜尋前方怪物，有怪就停下攻擊，攻完繼續同方向前進，到達邊界再折返。

---

## 移除項目

| 項目 | 說明 |
|------|------|
| `MoveToCenterCommand` | 不再有中間觀察點 |
| `MoveToSideCommand` | 改由 `SweepCommand` 處理 |
| `_CENTER_X` | 不再使用 |
| `_NO_MONSTER_TIMEOUT` | 改以前方無怪作為攻擊停止條件 |
| `_FORCE_MOVE_INTERVAL` | 往返掃蕩自然避免卡死，不需強制計時 |
| `_preferred_dir` | 不再需要偏好方向 |
| `_no_monster_timer` / `_force_move_timer` | 計時器一併移除 |
| `_reset_no_monster_timer` / `_reset_force_move_timer` | 移除 |
| `_on_no_monster_timeout` / `_on_force_move_timeout` | 移除 |
| `_interrupt_attack_and_move` | 移除 |

---

## 新增：SweepCommand

### 職責
往指定邊界（`_LEFT_X` 或 `_RIGHT_X`）移動，遇到前方怪物時中斷並交給 `AttackCommand`。

### 防重複入隊
使用 `_queued: 'SweepCommand | None' = None` 實例追蹤，`_try_enqueue` 檢查後入隊。

### trigger_command 流程

```
interrupt_event.clear()
target_x = _LEFT_X or _RIGHT_X（依 direction）

reached = [False]
monster_found = [False]

# 儲存自身供 _on_monster_detected 中斷使用
self._char._sweep_command = self
self._char._sweep_monster_found = monster_found

register_pos_event(abs(x - target_x) <= _X_TOL → reached[0]=True, interrupt)
keyDown(direction)
interrupt_event.wait(15)
keyUp(direction)
unregister_pos_event
self._char._sweep_command = None

if stop_event → return
if reached     → SweepCommand._try_enqueue(queue, char, opposite_direction)
if monster     → AttackCommand._try_enqueue(priority_queue, char, direction, attack_key)
else (timeout) → SweepCommand._try_enqueue(queue, char, direction)   # 重試
```

### 邊界到達後換方向
- `direction == 'right'` → 到達 `_RIGHT_X` → 下一個方向 `'left'`
- `direction == 'left'`  → 到達 `_LEFT_X`  → 下一個方向 `'right'`

---

## 修改：AttackCommand

### 結束條件（新增）
原本每次攻擊後自我重入隊直到外部中斷。改為：每次攻擊後用 `_count_forward_monsters()` 計算前方（`self._direction`）同一Y範圍內的怪物數量：

- 怪物數 > 0 → 自我重入隊繼續攻擊
- 怪物數 = 0 → `SweepCommand._try_enqueue(command_queue, char, self._direction)` 恢復掃蕩

### `_count_forward_monsters()` 輔助方法
```python
def _count_forward_monsters(self) -> int:
    cx, cy = self._char.screen_x, self._char.screen_y
    if cx == 0:
        return 0
    count = 0
    for d in self._char._monster_detections:
        x1, y1, x2, y2 = d['bbox']
        mcx, mcy = (x1+x2)/2, (y1+y2)/2
        if abs(mcy - cy) > _ATTACK_RANGE_Y:
            continue
        if self._direction == 'right' and cx < mcx <= cx + _ATTACK_RANGE_PX:
            count += 1
        elif self._direction == 'left' and cx - _ATTACK_RANGE_PX <= mcx < cx:
            count += 1
    return count
```

`_decide_attack_key()` 改用此方法（不再統計雙側）。

---

## 修改：NightLord._on_monster_detected

偵測到怪物後，檢查是否有 `_sweep_command` 正在執行，且前方有怪 → 中斷掃蕩：

```python
sweep_cmd = getattr(self, '_sweep_command', None)
if sweep_cmd is not None and not self.stop_event.is_set():
    forward_count = <計算 sweep_cmd._direction 方向的怪物數>
    if forward_count > 0:
        self._sweep_monster_found[0] = True
        sweep_cmd.interrupt_command()
```

移除舊的無怪計時器邏輯。

---

## 修改：NightLord.__init__

- 移除：`_preferred_dir`、`_no_monster_timer`、`_force_move_timer`
- 新增：`_sweep_command: SweepCommand | None = None`、`_sweep_monster_found: list[bool] = [False]`

---

## 修改：NightLord.task_prepare

```python
import random
direction = random.choice(['left', 'right'])
SweepCommand._try_enqueue(self.command_queue, self, direction)
```

移除 MoveToCenterCommand、計時器重置。

---

## 修改：NightLord.stop

移除計時器 cancel 邏輯，新增：
```python
SweepCommand._queued = None
self._sweep_command = None
```

---

## 狀態機示意

```
task_prepare
    ↓ random direction
SweepCommand(dir) ──────────────────────────────────────┐
    │ 邊走邊偵測                                          │ 到達邊界
    │ 前方有怪                                            ↓
    ↓                                         SweepCommand(opposite)
AttackCommand(dir)
    │ 每次攻擊後
    ├─ 前方有怪 → 自我重入隊
    └─ 前方無怪 → SweepCommand(dir)  ← 繼續同方向
```

---

## 不變項目

- `Buff1` / `Buff2` / `Buff3`：不變
- `ModelController` 啟動方式：不變
- `_ATTACK_RANGE_PX` / `_ATTACK_RANGE_Y` / `_MULTI_ATTACK_THRESHOLD`：不變
- `_LEFT_X` / `_RIGHT_X` / `_X_TOL`：不變
- 日誌規範（`MSLogger`）：不變
