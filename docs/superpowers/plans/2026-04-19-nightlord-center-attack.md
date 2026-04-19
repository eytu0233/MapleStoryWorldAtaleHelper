# NightLord Center-First Attack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 攻擊只在到達中間點後觸發，方向鎖定至下次回到中間點，3 秒無怪或 1 分鐘後強制移往邊界。

**Architecture:** 攻擊觸發點從 `_on_monster_detected` 移至 `MoveToCenterCommand`；`AttackCommand` 自我循環直到被打斷；兩個計時器（3 秒無怪、1 分鐘強制）呼叫共用 `_interrupt_attack_and_move` 中斷攻擊並移往邊界。

**Tech Stack:** Python threading.Timer, pyautogui, queue.Queue

---

## 檔案異動

- Modify: `job/NightLord_map_separate.py`（唯一異動檔案）

---

### Task 1：更新常數、移除 `_on_monster_detected` 的攻擊邏輯

**Files:**
- Modify: `job/NightLord_map_separate.py:15-26`（常數區）
- Modify: `job/NightLord_map_separate.py:328-371`（`_on_monster_detected`）

- [ ] **Step 1: 更新常數**

將檔案頂部常數區改為：

```python
_BUFF_INTERVAL          = 270   # 秒
_LEFT_X                 = 0.46  # 左邊界
_CENTER_X               = 0.63  # 中間觀察點
_RIGHT_X                = 0.80  # 右邊界
_X_TOL                  = 0.02
_MAP_CONFIG             = os.path.join(os.path.dirname(__file__), '..', 'maps', 'map_dragon_nest.json')
_MONSTER_MODEL          = os.path.join(os.path.dirname(__file__), '..', 'model', 'egg_dragon.pt')
_MONSTER_DETECT_NAMES   = {'eggDragon', 'eggDragon01'}
_ATTACK_RANGE_PX        = 600   # 方向前方怪物偵測距離（視窗像素）
_ATTACK_RANGE_Y         = 200   # 垂直方向誤差容許值（像素，±）
_MULTI_ATTACK_THRESHOLD = 2     # 怪物數量 >= 此值時改用多體攻擊（z 鍵）
_NO_MONSTER_TIMEOUT     = 3.0   # 秒：優先方向無怪後移往對應邊界
_FORCE_MOVE_INTERVAL    = 60    # 秒：強制移往邊界（不論有無怪）
```

- [ ] **Step 2: 簡化 `_on_monster_detected`**

將整個 `_on_monster_detected` 方法改為只更新偵測結果並重置計時器：

```python
def _on_monster_detected(self, detections: list[dict]):
    filtered = [d for d in detections if d['name'] in _MONSTER_DETECT_NAMES]
    self._monster_detections = filtered

    if not filtered or self._preferred_dir is None:
        return

    cx = self.screen_x
    cy = self.screen_y
    if cx == 0:
        return

    # 只統計鎖定方向的怪物數量，有怪才重置計時器
    preferred_count = 0
    for d in filtered:
        x1, y1, x2, y2 = d['bbox']
        mcx = (x1 + x2) / 2
        mcy = (y1 + y2) / 2
        if abs(mcy - cy) > _ATTACK_RANGE_Y:
            continue
        if self._preferred_dir == 'left' and cx - _ATTACK_RANGE_PX <= mcx < cx:
            preferred_count += 1
        elif self._preferred_dir == 'right' and cx < mcx <= cx + _ATTACK_RANGE_PX:
            preferred_count += 1

    if preferred_count > 0:
        self._reset_no_monster_timer(self._preferred_dir)
```

- [ ] **Step 3: 確認沒有任何 `AttackCommand._try_enqueue` 殘留在 `_on_monster_detected`**

確認整個 `_on_monster_detected` 方法內不含 `AttackCommand._try_enqueue` 呼叫。

---

### Task 2：簡化 `AttackCommand`（移除方向切換邏輯）

**Files:**
- Modify: `job/NightLord_map_separate.py:60-158`（`AttackCommand` 類別）

- [ ] **Step 1: 以新版 `AttackCommand` 取代舊版**

用以下完整類別取代原本的 `AttackCommand`：

```python
class AttackCommand(Command):
    """
    攻擊指令。方向由中間點決定後鎖定，不在此處更改。
    每次 0.4 秒攻擊後自我重入隊，直到被外部打斷為止。
    """

    _queued:     'AttackCommand | None' = None
    _is_running: bool                   = False

    @classmethod
    def _try_enqueue(cls, priority_queue: queue.Queue,
                     char: 'NightLord', direction: str, attack_key: str):
        if cls._queued is not None or cls._is_running:
            return False
        obj = cls(priority_queue, char, direction, attack_key)
        cls._queued = obj
        priority_queue.put(obj)
        return True

    def __init__(self, priority_queue: queue.Queue, char: 'NightLord',
                 direction: str, attack_key: str):
        super().__init__(CommandType.CONDITION)
        self._queue      = priority_queue
        self._char       = char
        self._direction  = direction
        self._attack_key = attack_key
        self._cancelled  = False

    def release(self):
        self._cancelled = True

    def _decide_attack_key(self) -> str:
        """根據攻擊範圍內總怪物數量決定使用單體（c）或多體（z）技能。"""
        cx = self._char.screen_x
        cy = self._char.screen_y
        if cx == 0:
            return self._attack_key
        total = 0
        for d in self._char._monster_detections:
            x1, y1, x2, y2 = d['bbox']
            mcx = (x1 + x2) / 2
            mcy = (y1 + y2) / 2
            if abs(mcy - cy) <= _ATTACK_RANGE_Y:
                if cx - _ATTACK_RANGE_PX <= mcx <= cx + _ATTACK_RANGE_PX:
                    total += 1
        return 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'

    def trigger_command(self):
        AttackCommand._queued     = None
        AttackCommand._is_running = True
        try:
            if self._cancelled:
                return
            self.interrupt_event.clear()

            # 轉向（鎖定方向，不更改）
            self._char.minimap_task.char_facing = self._direction
            pyautogui.keyDown(self._direction)
            pyautogui.keyUp(self._direction)

            _logger.info(f'[PRIORITY][AttackCommand] 攻擊 dir={self._direction} key={self._attack_key}')
            pyautogui.keyDown(self._attack_key)
            self.interrupt_event.wait(0.4)
            pyautogui.keyUp(self._attack_key)

            if self.interrupt_event.is_set() or self._cancelled:
                _logger.info('[PRIORITY][AttackCommand] 被中斷，停止攻擊')
                return

            # 更新攻擊鍵（方向不變），繼續攻擊
            self._attack_key = self._decide_attack_key()
            AttackCommand._queued = self
            self._queue.put(self)
        finally:
            AttackCommand._is_running = False
```

---

### Task 3：新增計時器輔助方法與共用中斷邏輯

**Files:**
- Modify: `job/NightLord_map_separate.py`（`NightLord` 類別）

- [ ] **Step 1: 在 `__init__` 加入 `_force_move_timer`**

將 `NightLord.__init__` 改為：

```python
def __init__(self):
    super().__init__(name='NightLord')
    self._monster_monitor:    ModelController | None     = None
    self._monster_detections: list[dict]                 = []
    self._preferred_dir:      str | None                 = None
    self._no_monster_timer:   threading.Timer | None     = None
    self._force_move_timer:   threading.Timer | None     = None
```

- [ ] **Step 2: 新增 `_reset_force_move_timer` 方法**

在 `_reset_no_monster_timer` 方法下方新增：

```python
def _reset_force_move_timer(self):
    """每次到達中間點後呼叫，重設 1 分鐘強制移動倒數。"""
    if self._force_move_timer is not None:
        self._force_move_timer.cancel()
    if self.stop_event.is_set():
        return
    t = threading.Timer(_FORCE_MOVE_INTERVAL, self._on_force_move_timeout)
    t.daemon = True
    t.start()
    self._force_move_timer = t
```

- [ ] **Step 3: 新增 `_interrupt_attack_and_move` 共用方法**

在 `_reset_force_move_timer` 下方新增：

```python
def _interrupt_attack_and_move(self, direction: str):
    """中斷當前攻擊並排入移往邊界的指令。"""
    if AttackCommand._queued is not None:
        AttackCommand._queued._cancelled = True
        AttackCommand._queued = None
    if (self.current_command is not None
            and isinstance(self.current_command, AttackCommand)):
        self.current_command.interrupt_command()
    MoveToSideCommand._try_enqueue(self.command_queue, self, direction)
```

- [ ] **Step 4: 新增 `_on_force_move_timeout` 方法**

在 `_interrupt_attack_and_move` 下方新增：

```python
def _on_force_move_timeout(self):
    """1 分鐘到期後強制移往當前優先方向的邊界。"""
    self._force_move_timer = None
    if self.stop_event.is_set():
        return
    direction = self._preferred_dir or 'right'
    _logger.info(f'[NightLord] 1 分鐘強制移動，方向={direction}')
    self._interrupt_attack_and_move(direction)
```

- [ ] **Step 5: 更新 `_on_no_monster_timeout` 使用共用方法**

將原本的 `_on_no_monster_timeout` 改為：

```python
def _on_no_monster_timeout(self, direction: str):
    """_NO_MONSTER_TIMEOUT 秒後仍未見 direction 方向的怪：移往對應邊界。"""
    self._no_monster_timer = None
    if self.stop_event.is_set():
        return
    if self._preferred_dir != direction:
        return  # 優先方向已改變，忽略
    _logger.info(f'[NightLord] {direction} 方向 {_NO_MONSTER_TIMEOUT}s 無怪，移往邊界')
    self._interrupt_attack_and_move(direction)
```

---

### Task 4：更新 `MoveToCenterCommand`，到達後觸發攻擊

**Files:**
- Modify: `job/NightLord_map_separate.py:163-225`（`MoveToCenterCommand`）

- [ ] **Step 1: 在 `trigger_command` 的 `reached[0]` 成立區塊加入方向決策與攻擊觸發**

將 `trigger_command` 的 `reached[0]` 判斷區段（原本只有 log）改為：

```python
if not reached[0]:
    _logger.warning('[MoveToCenterCommand] 被打斷或超時，重試')
    MoveToCenterCommand._try_enqueue(self._queue, self._char)
    return

_logger.info(f'[MoveToCenterCommand] 到達中間 x={self._char.map_x:.2f}，決定攻擊方向')

# 計算左右怪物數量
cx = self._char.screen_x
cy = self._char.screen_y
counts = {'left': 0, 'right': 0}
total = 0
if cx != 0:
    for d in self._char._monster_detections:
        x1, y1, x2, y2 = d['bbox']
        mcx = (x1 + x2) / 2
        mcy = (y1 + y2) / 2
        if abs(mcy - cy) > _ATTACK_RANGE_Y:
            continue
        if cx - _ATTACK_RANGE_PX <= mcx < cx:
            counts['left'] += 1
            total += 1
        elif cx < mcx <= cx + _ATTACK_RANGE_PX:
            counts['right'] += 1
            total += 1

# 決定並鎖定攻擊方向
if counts['left'] > counts['right']:
    direction = 'left'
elif counts['right'] > counts['left']:
    direction = 'right'
else:
    direction = self._char._preferred_dir or 'right'

self._char._preferred_dir = direction
attack_key = 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'

_logger.info(
    f'[MoveToCenterCommand] 攻擊方向={direction} key={attack_key} '
    f'L={counts["left"]} R={counts["right"]}'
)

# 重置計時器
self._char._reset_no_monster_timer(direction)
self._char._reset_force_move_timer()

# 觸發攻擊（只在中間點觸發）
AttackCommand._try_enqueue(
    self._char.priority_command_queue, self._char, direction, attack_key
)
```

完整 `trigger_command` 方法（供參照，確保 finally 結構正確）：

```python
def trigger_command(self):
    MoveToCenterCommand._queued = None
    try:
        self.interrupt_event.clear()
        cur_x = self._char.map_x
        if abs(cur_x - _CENTER_X) <= _X_TOL:
            _logger.info('[MoveToCenterCommand] 已在中間位置')
            # 同樣觸發攻擊（已在中間點）
            cx = self._char.screen_x
            cy = self._char.screen_y
            counts = {'left': 0, 'right': 0}
            total = 0
            if cx != 0:
                for d in self._char._monster_detections:
                    x1, y1, x2, y2 = d['bbox']
                    mcx = (x1 + x2) / 2
                    mcy = (y1 + y2) / 2
                    if abs(mcy - cy) > _ATTACK_RANGE_Y:
                        continue
                    if cx - _ATTACK_RANGE_PX <= mcx < cx:
                        counts['left'] += 1
                        total += 1
                    elif cx < mcx <= cx + _ATTACK_RANGE_PX:
                        counts['right'] += 1
                        total += 1
            if counts['left'] > counts['right']:
                direction = 'left'
            elif counts['right'] > counts['left']:
                direction = 'right'
            else:
                direction = self._char._preferred_dir or 'right'
            self._char._preferred_dir = direction
            attack_key = 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'
            self._char._reset_no_monster_timer(direction)
            self._char._reset_force_move_timer()
            AttackCommand._try_enqueue(
                self._char.priority_command_queue, self._char, direction, attack_key
            )
            return

        direction = 'right' if cur_x < _CENTER_X else 'left'
        _logger.info(f'[MoveToCenterCommand] →{direction} cur={cur_x:.2f}')
        self._char.minimap_task.char_facing = direction

        reached = [False]

        def _on_reached():
            reached[0] = True
            self.interrupt_command()

        eid = self._char.minimap_task.register_pos_event(
            condition=lambda x, y: abs(x - _CENTER_X) <= _X_TOL,
            callback=_on_reached,
            once=True,
        )
        pyautogui.keyDown(direction)
        self.interrupt_event.wait(15)
        pyautogui.keyUp(direction)
        self._char.minimap_task.unregister_pos_event(eid)

        if self._char.stop_event.is_set():
            return

        if not reached[0]:
            _logger.warning('[MoveToCenterCommand] 被打斷或超時，重試')
            MoveToCenterCommand._try_enqueue(self._queue, self._char)
            return

        _logger.info(f'[MoveToCenterCommand] 到達中間 x={self._char.map_x:.2f}，決定攻擊方向')

        cx = self._char.screen_x
        cy = self._char.screen_y
        counts = {'left': 0, 'right': 0}
        total = 0
        if cx != 0:
            for d in self._char._monster_detections:
                x1, y1, x2, y2 = d['bbox']
                mcx = (x1 + x2) / 2
                mcy = (y1 + y2) / 2
                if abs(mcy - cy) > _ATTACK_RANGE_Y:
                    continue
                if cx - _ATTACK_RANGE_PX <= mcx < cx:
                    counts['left'] += 1
                    total += 1
                elif cx < mcx <= cx + _ATTACK_RANGE_PX:
                    counts['right'] += 1
                    total += 1

        if counts['left'] > counts['right']:
            direction = 'left'
        elif counts['right'] > counts['left']:
            direction = 'right'
        else:
            direction = self._char._preferred_dir or 'right'

        self._char._preferred_dir = direction
        attack_key = 'z' if total >= _MULTI_ATTACK_THRESHOLD else 'c'

        _logger.info(
            f'[MoveToCenterCommand] 攻擊方向={direction} key={attack_key} '
            f'L={counts["left"]} R={counts["right"]}'
        )

        self._char._reset_no_monster_timer(direction)
        self._char._reset_force_move_timer()
        AttackCommand._try_enqueue(
            self._char.priority_command_queue, self._char, direction, attack_key
        )
    finally:
        MoveToCenterCommand._queued = None
```

---

### Task 5：更新 `stop` 與 `task_prepare` 處理新計時器

**Files:**
- Modify: `job/NightLord_map_separate.py:395-449`（`stop`, `task_prepare`）

- [ ] **Step 1: 更新 `stop` 方法，加入 `_force_move_timer` 清除**

```python
def stop(self):
    if hasattr(self, '_buff_timer'):
        self._buff_timer.cancel()
    if self._no_monster_timer is not None:
        self._no_monster_timer.cancel()
        self._no_monster_timer = None
    if self._force_move_timer is not None:
        self._force_move_timer.cancel()
        self._force_move_timer = None
    if self._monster_monitor is not None:
        self._monster_monitor.stop()
        self._monster_monitor = None
    self._monster_detections = []
    self._preferred_dir       = None
    AttackCommand._queued     = None
    AttackCommand._is_running = False
    MoveToCenterCommand._queued = None
    MoveToSideCommand._queued   = None
    super().stop()
    for q in (self.emerg_command_queue, self.priority_command_queue, self.command_queue):
        while not q.empty():
            try:
                q.get_nowait()
            except Exception:
                break
    _logger.info('[NightLord] 已停止')
```

- [ ] **Step 2: 更新 `task_prepare` 方法，加入 `_force_move_timer` 重置**

```python
def task_prepare(self):
    if hasattr(self, '_buff_timer'):
        self._buff_timer.cancel()
    if self._no_monster_timer is not None:
        self._no_monster_timer.cancel()
        self._no_monster_timer = None
    if self._force_move_timer is not None:
        self._force_move_timer.cancel()
        self._force_move_timer = None

    self._load_minimap_bounds()

    AttackCommand._queued       = None
    AttackCommand._is_running   = False
    MoveToCenterCommand._queued = None
    MoveToSideCommand._queued   = None
    self._preferred_dir         = None
    self.minimap_task.char_facing      = 'right'
    self.minimap_task.char_y_direction = 'down'

    if self._monster_monitor is not None:
        self._monster_monitor.stop()
        self._monster_monitor = None
    self._monster_detections = []
    self._monster_monitor = ModelController(
        self.game_window, _MONSTER_MODEL, self._on_monster_detected
    )
    self._monster_monitor.start()

    self._enqueue_buffs()
    MoveToCenterCommand._try_enqueue(self.command_queue, self)
```

- [ ] **Step 3: Commit**

```bash
git add job/NightLord_map_separate.py
git commit -m "feat: 攻擊只在中間點觸發，方向鎖定，3秒無怪或1分鐘強制移往邊界"
```

---

## Self-Review 結果

- **Spec coverage：** 全部需求覆蓋：(1) 中間點才觸發攻擊 ✓ (2) 3 秒攻擊後持續直到被打斷 ✓ (3) 方向鎖定到下次中間點 ✓ (4) 3 秒無怪移往邊界 ✓ (5) 1 分鐘強制移往邊界 ✓
- **Placeholder scan：** 無 TBD / TODO
- **Type consistency：** `AttackCommand._try_enqueue` 簽名在 Task 2 定義，Task 4 呼叫一致
