# OSA 扫描控制（开始 / 暂停 / 立即停止）设计

**日期**: 2026-05-29
**设备**: Yokogawa AQ6370C（兼容 AQ6370B 同系列）
**方式**: 在现有代码上最小改动（延续 Approach A 风格）

## 1. 背景与目标

连续扫描场景下，用户经常需要在看到一个理想光谱值的瞬间立刻让设备停下，以便捕获 / 截图。
现有程序只能"应用设置"启动扫描，没有任何停止手段。本次新增三个扫描控制按钮：

- **开始扫描**：按当前扫描模式启动 / 恢复扫描。
- **暂停**：等当前这一次扫描走完后再停（曲线完整，贴合"抓住好值"的需求）。
- **立即停止**：立刻中止扫描，不等当前扫描完成（与"暂停"语义和外观明确区分）。

三个按钮统一放在**捕获与截图标签页**的操作按钮行（即绘图界面下）。

## 2. SCPI 命令（已对照横河官方手册与 InstrumentKit 实现核实）

| 用途 | 命令 | 说明 |
|---|---|---|
| 启动 / 恢复扫描 | `:INIT` | 按当前 `smode`（单次/连续/自动）触发扫描 |
| 中止扫描 | `:ABORt` | 立即停止当前扫描，回到 IDLE，不改其他设置 |
| 查询扫描完成事件 | `:STATus:OPERation:EVENt?` | 返回整数；**bit 0 = Sweep finished**。读取会清除锁存位 |

参考：
- InstrumentKit Yokogawa 6370：`start_sweep` 用 `*CLS;:init`，`abort` 用 `:ABORT`，sweep 完成检测用 `:status:operation:event`（bit 0 = Sweep finished）。
- Yokogawa AQ6370C Remote Control 手册（IMAQ6370C-01EN）。

## 3. 实现方式

"暂停"需要等待当前扫描完成，这是一个异步等待（取决于扫描范围/分辨率/灵敏度，可能数秒到数十秒）。
采用 **QTimer 非阻塞轮询**（已与用户确认 = 方案 A）：点击后启动定时器周期性查询扫描完成事件，
界面保持响应（可继续观察实时曲线），避免阻塞主线程。

## 4. `osa.py` 改动

新增模块级常量与四个小方法，复用现有 `send` / `query`：

```python
SWEEP_FINISHED_BIT = 0b1   # operation 状态寄存器 bit0 = Sweep finished

def abort(self):
    """立即中止扫描。"""
    self.send(':ABORt\n')

def start_sweep(self):
    """按当前扫描模式启动 / 恢复扫描。"""
    self.send(':init\n')

def poll_sweep_finished(self) -> bool:
    """读取并清除『扫描完成』事件；返回自上次读取以来是否完成过一次扫描。"""
    resp = self.query(':STATus:OPERation:EVENt?\n', print_cmd=False)
    return bool(self._parse_int(resp) & SWEEP_FINISHED_BIT)

@staticmethod
def _parse_int(resp) -> int:
    """把 b'1\\r\\n' 这类响应安全转成 int；None / 解析失败返回 0。"""
    if resp is None:
        return 0
    try:
        return int(resp.decode().strip())
    except (ValueError, AttributeError):
        return 0
```

## 5. `main.py` 改动

### 5.1 模块级常量

```python
PAUSE_POLL_INTERVAL_MS = 150     # 轮询间隔
PAUSE_WAIT_TIMEOUT_MS = 60000    # 等待当前扫描完成的安全超时（兜底）
```

### 5.2 UI（捕获与截图标签页按钮行）

按钮行从 `[迹线][捕获][保存][截图]` 调整为：

```
[开始扫描] [暂停] [立即停止] | 迹线:[TRA] [捕获] [保存] [截图]
```

三个扫描控制按钮用 QSS 着色，形成红绿灯语义并带 hover 态，使"立即停止"与"暂停"明确区分：

- **开始扫描** —— 绿色（`#2e7d32`，hover `#388e3c`，disabled `#a5d6a7`）
- **暂停** —— 琥珀色（`#f0a000`，hover `#ffb300`，disabled `#ffe0a3`）
- **立即停止** —— 红色（`#c62828`，hover `#d32f2f`）

捕获/保存/截图保持默认样式，使三个着色按钮作为"扫描控制组"在视觉上成组。

### 5.3 状态字段（`__init__`）

```python
self._pause_timer: QTimer | None = None
self._pause_ticks: int = 0
```

### 5.4 槽函数

**开始扫描** `_on_start_sweep`：
1. 未连接 → 提示返回。
2. `client.start_sweep()`，状态栏显示"扫描中…"。

**暂停** `_on_pause`（完成当前扫描后停止）：
1. 未连接 → 提示返回。
2. 禁用「暂停」按钮防重入；状态栏"暂停中…（等待当前扫描完成）"。
3. `client.poll_sweep_finished()` 读一次，清掉旧的锁存事件。
4. `self._pause_ticks = 0`，创建并启动 `QTimer(PAUSE_POLL_INTERVAL_MS)` → `_poll_pause`。

**轮询** `_poll_pause`（定时器回调）：
- 若 `self.client` 已断开 → `_finish_pause("已断开，暂停取消")`。
- `self._pause_ticks += 1`。
- 若 `client.poll_sweep_finished()` 为真 → `client.abort()` → `_finish_pause("已暂停")`。
- 否则若 `_pause_ticks * PAUSE_POLL_INTERVAL_MS >= PAUSE_WAIT_TIMEOUT_MS` → `client.abort()` → `_finish_pause("已暂停（超时）")`。

**立即停止** `_on_stop`：
1. 未连接 → 提示返回。
2. `client.abort()`。
3. `_finish_pause("已停止")` —— 若此时正有"暂停"等待中，会一并取消定时器并复位（这也是空闲/不耐烦时的逃生通道）；若无定时器则只复位按钮与状态。

**复位辅助** `_finish_pause(message)`：
```python
def _finish_pause(self, message: str) -> None:
    if self._pause_timer is not None:
        self._pause_timer.stop()
        self._pause_timer = None
    self.pause_btn.setEnabled(True)
    self.status_label.setText(message)
```

### 5.5 信号绑定与导入

- `from PyQt5.QtCore import QTimer`（追加导入）。
- `start_btn.clicked → _on_start_sweep`，`pause_btn.clicked → _on_pause`，`stop_btn.clicked → _on_stop`。

## 6. 边界与取舍

- **空闲时点"暂停"**（设备没在扫）：扫描完成事件永不到来 → 60s 超时兜底后 `:ABORt`（空操作）。
  用户也可随时点「立即停止」立刻退出等待。实际仅会在连续扫描时点"暂停"，空闲点击属罕见误操作。
- **未连接**：沿用现有风格（按钮始终可点，未连接时弹提示），不做连接态联动禁用。
- **单次模式下点"开始扫描"**：`:init` 自然只扫一次后停止，行为正确。
- **等待中断开连接**：`_poll_pause` 每次检查 `self.client`，断开则安全收尾。
- **重入**：进入"暂停"等待即禁用「暂停」按钮，避免重复启动定时器。

## 7. 测试

项目当前无测试基建，按比例补充：

- **单元测试（pytest，可脱离硬件）**：`osa._parse_int` 的各类输入（`b'1\r\n'`、`b'0'`、`None`、非法字节）；
  以及 `SWEEP_FINISHED_BIT` 掩码判定逻辑（用伪造响应注入验证 `poll_sweep_finished` 的 bit0 判断）。
- **真机手动验证**：连接 → 连续扫描 → 暂停（确认停在完整曲线）→ 开始扫描（恢复连续）→ 连续扫描中点立即停止（确认即时中止）。
- 同步更新 `README.md`：功能详解新增"扫描控制"一节，`osa` 类方法表补充 `abort` / `start_sweep` / `poll_sweep_finished`。

## 8. 影响范围

- `osa.py`：+1 常量、+4 方法（纯新增，不改现有方法）。
- `main.py`：+2 常量、+1 导入、+3 按钮及样式、+2 状态字段、+4 槽函数/辅助方法。
- `README.md`：文档补充。
- `tests/test_osa.py`：新增单元测试。
