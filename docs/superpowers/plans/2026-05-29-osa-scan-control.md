# 扫描控制（开始 / 暂停 / 立即停止）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在绘图（捕获与截图）界面新增"开始扫描 / 暂停 / 立即停止"三个按钮，让用户在连续扫描时能优雅地停在完整曲线或即时中止。

**Architecture:** `osa.py` 纯新增 4 个薄方法封装 SCPI（`:init` / `:ABORt` / `:STATus:OPERation:EVENt?`）；`main.py` 用 QTimer 非阻塞轮询"扫描完成"事件实现"暂停"，"立即停止"直接 `:ABORt` 并可打断等待。

**Tech Stack:** Python 3.10+、PyQt5、socket/SCPI、pytest。

**对应 Spec:** [docs/superpowers/specs/2026-05-29-osa-scan-control-design.md](../specs/2026-05-29-osa-scan-control-design.md)

> ⚠️ **提交约定（用户指定）：所有改动都不要自动 `git commit`。全部任务完成并经用户真机确认后，由用户自行提交。** 下方任务不含提交步骤。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `osa.py` | 设备 SCPI 薄封装 | 修改：+1 常量、+4 方法 |
| `main.py` | PyQt5 界面与交互 | 修改：+2 常量、+1 导入、+2 状态字段、+3 按钮、+5 槽/辅助方法、+3 信号绑定 |
| `tests/test_osa.py` | osa 纯逻辑单元测试 | 新建 |
| `README.md` | 用户文档 | 修改：新增"扫描控制"说明与方法表行 |

---

## Task 1: `osa.py` 扫描控制原语 + 单元测试（TDD）

**Files:**
- Modify: `osa.py`（顶部常量区 + 类内 `hide` 与 `close` 之间）
- Create: `tests/test_osa.py`

- [ ] **Step 1: 确认 pytest 可用**

Run: `python -c "import pytest" 2>/dev/null && echo OK || pip install pytest`
Expected: 输出 `OK`，或安装完成。

- [ ] **Step 2: 写失败测试 `tests/test_osa.py`**

```python
import pytest

from osa import osa, SWEEP_FINISHED_BIT


class TestParseInt:
    def test_crlf(self):
        assert osa._parse_int(b"1\r\n") == 1

    def test_zero(self):
        assert osa._parse_int(b"0") == 0

    def test_none(self):
        assert osa._parse_int(None) == 0

    def test_garbage(self):
        assert osa._parse_int(b"abc") == 0

    def test_with_spaces(self):
        assert osa._parse_int(b"  3 \r\n") == 3


class TestPollSweepFinished:
    def _make(self, response):
        obj = osa.__new__(osa)  # 跳过 __init__，不连真机
        obj.query = lambda *a, **k: response
        return obj

    def test_finished_bit_set(self):
        assert self._make(b"1\r\n").poll_sweep_finished() is True

    def test_finished_bit_set_with_other_bits(self):
        # 值=3（二进制 11），bit0 置位
        assert self._make(b"3\r\n").poll_sweep_finished() is True

    def test_finished_bit_clear(self):
        assert self._make(b"0\r\n").poll_sweep_finished() is False

    def test_other_bit_only(self):
        # 值=2（二进制 10），bit0 未置位
        assert self._make(b"2\r\n").poll_sweep_finished() is False

    def test_none_response(self):
        assert self._make(None).poll_sweep_finished() is False


class TestScanCommands:
    def _make(self):
        obj = osa.__new__(osa)
        sent = []
        obj.send = lambda msg: sent.append(msg)
        return obj, sent

    def test_abort_sends_abort(self):
        obj, sent = self._make()
        obj.abort()
        assert sent == [":ABORt\n"]

    def test_start_sweep_sends_init(self):
        obj, sent = self._make()
        obj.start_sweep()
        assert sent == [":init\n"]


def test_sweep_finished_bit_value():
    assert SWEEP_FINISHED_BIT == 0b1
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `python -m pytest tests/test_osa.py -v`
Expected: FAIL —— `ImportError: cannot import name 'SWEEP_FINISHED_BIT'`（以及方法不存在）。

- [ ] **Step 4: 在 `osa.py` 顶部 import 之后新增常量**

在 `import numpy as np`（第 12 行）之后插入：

```python

# operation 状态寄存器 bit0 = Sweep finished（扫描完成）
SWEEP_FINISHED_BIT = 0b1
```

- [ ] **Step 5: 在 `osa.py` 类内 `hide()` 方法之后、`close()` 之前新增 4 个方法**

```python
    def abort(self):
        '''立即中止扫描'''
        self.send(':ABORt\n')

    def start_sweep(self):
        '''按当前扫描模式启动/恢复扫描'''
        self.send(':init\n')

    def poll_sweep_finished(self):
        '''读取并清除"扫描完成"事件；返回自上次读取以来是否完成过一次扫描'''
        resp = self.query(':STATus:OPERation:EVENt?\n', print_cmd=False)
        return bool(self._parse_int(resp) & SWEEP_FINISHED_BIT)

    @staticmethod
    def _parse_int(resp):
        '''把 b'1\\r\\n' 这类响应安全转成 int；None / 解析失败返回 0'''
        if resp is None:
            return 0
        try:
            return int(resp.decode().strip())
        except (ValueError, AttributeError):
            return 0
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `python -m pytest tests/test_osa.py -v`
Expected: PASS（13 passed）。

---

## Task 2: `main.py` 常量、导入与状态字段

**Files:**
- Modify: `main.py:18`（导入）、`main.py:42-54`（常量区）、`main.py:79`（`__init__` 状态字段）

- [ ] **Step 1: 追加 QTimer 导入**

将第 18 行：

```python
from PyQt5.QtCore import Qt
```

改为：

```python
from PyQt5.QtCore import Qt, QTimer
```

- [ ] **Step 2: 新增模块级常量**

在 `SENSITIVITY_MAP = { ... }` 字典闭合之后（第 54 行后）插入：

```python

PAUSE_POLL_INTERVAL_MS = 150     # "暂停"等待时的轮询间隔
PAUSE_WAIT_TIMEOUT_MS = 60000    # 等待当前扫描完成的安全超时（兜底）
```

- [ ] **Step 3: 在 `__init__` 中新增暂停状态字段**

在 `self._ch_font_available: bool = False`（第 79 行）之后插入：

```python
        self._pause_timer: QTimer | None = None
        self._pause_ticks: int = 0
```

- [ ] **Step 4: 确认程序仍可导入（语法检查）**

Run: `python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"`
Expected: 输出 `OK`。

---

## Task 3: `main.py` 扫描控制槽函数

**Files:**
- Modify: `main.py`（在 `_on_screenshot` 方法之后、`# ---- 设置 ----` 注释之前，第 428~430 行附近新增一节）

- [ ] **Step 1: 新增"扫描控制"槽函数块**

在 `_on_screenshot` 方法结束之后插入：

```python
    # ---- 扫描控制 ----

    def _on_start_sweep(self) -> None:
        if not self.client:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return
        try:
            self.client.start_sweep()
            self.status_label.setText("扫描中…")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))

    def _on_pause(self) -> None:
        """完成当前扫描后停止：轮询扫描完成事件，扫完即 ABORt。"""
        if not self.client:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return
        if self._pause_timer is not None:
            return  # 已在等待中，避免重入
        self.pause_btn.setEnabled(False)
        self.status_label.setText("暂停中…（等待当前扫描完成）")
        try:
            self.client.poll_sweep_finished()  # 读一次，清除旧的锁存事件
        except Exception as e:
            self.pause_btn.setEnabled(True)
            self.status_label.setText("暂停失败")
            QMessageBox.critical(self, "暂停失败", str(e))
            return
        self._pause_ticks = 0
        self._pause_timer = QTimer(self)
        self._pause_timer.timeout.connect(self._poll_pause)
        self._pause_timer.start(PAUSE_POLL_INTERVAL_MS)

    def _poll_pause(self) -> None:
        if not self.client:
            self._finish_pause("已断开，暂停取消")
            return
        self._pause_ticks += 1
        try:
            if self.client.poll_sweep_finished():
                self.client.abort()
                self._finish_pause("已暂停")
                return
            if self._pause_ticks * PAUSE_POLL_INTERVAL_MS >= PAUSE_WAIT_TIMEOUT_MS:
                self.client.abort()
                self._finish_pause("已暂停（超时）")
        except Exception as e:
            self._finish_pause("暂停出错")
            QMessageBox.critical(self, "暂停出错", str(e))

    def _on_stop(self) -> None:
        """立即停止：直接 ABORt，并打断可能正在进行的"暂停"等待。"""
        if not self.client:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return
        try:
            self.client.abort()
            self._finish_pause("已停止")
        except Exception as e:
            QMessageBox.critical(self, "停止失败", str(e))

    def _finish_pause(self, message: str) -> None:
        """收尾：停止并清除定时器、恢复暂停按钮、更新状态栏。"""
        if self._pause_timer is not None:
            self._pause_timer.stop()
            self._pause_timer = None
        self.pause_btn.setEnabled(True)
        self.status_label.setText(message)
```

- [ ] **Step 2: 语法检查**

Run: `python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"`
Expected: 输出 `OK`。

---

## Task 4: `main.py` 三个按钮、样式与信号绑定

**Files:**
- Modify: `main.py:171-184`（按钮行）、`main.py:230-240`（信号绑定）

- [ ] **Step 1: 在按钮行创建三个扫描控制按钮并着色**

将现有按钮行（第 171~184 行）：

```python
        # 操作按钮行
        btn_row = QHBoxLayout()
        self.trace_edit = QLineEdit("TRA")
        self.trace_edit.setMaximumWidth(70)
        self.capture_btn = QPushButton("捕获")
        self.save_btn = QPushButton("保存")
        self.screenshot_btn = QPushButton("截图")
        btn_row.addWidget(QLabel("迹线:"))
        btn_row.addWidget(self.trace_edit)
        btn_row.addWidget(self.capture_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.screenshot_btn)
        btn_row.addStretch()
        cp_layout.addLayout(btn_row)
```

替换为：

```python
        # 操作按钮行
        btn_row = QHBoxLayout()

        # 扫描控制按钮（绿=开始 / 琥珀=暂停 / 红=立即停止）
        self.start_btn = QPushButton("开始扫描")
        self.pause_btn = QPushButton("暂停")
        self.stop_btn = QPushButton("立即停止")
        self.start_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;"
            "padding:4px 12px;border:none;border-radius:4px;}"
            "QPushButton:hover{background:#388e3c;}"
            "QPushButton:disabled{background:#a5d6a7;}"
        )
        self.pause_btn.setStyleSheet(
            "QPushButton{background:#f0a000;color:white;font-weight:bold;"
            "padding:4px 12px;border:none;border-radius:4px;}"
            "QPushButton:hover{background:#ffb300;}"
            "QPushButton:disabled{background:#ffe0a3;}"
        )
        self.stop_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;"
            "padding:4px 12px;border:none;border-radius:4px;}"
            "QPushButton:hover{background:#d32f2f;}"
        )
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.pause_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addSpacing(16)

        self.trace_edit = QLineEdit("TRA")
        self.trace_edit.setMaximumWidth(70)
        self.capture_btn = QPushButton("捕获")
        self.save_btn = QPushButton("保存")
        self.screenshot_btn = QPushButton("截图")
        btn_row.addWidget(QLabel("迹线:"))
        btn_row.addWidget(self.trace_edit)
        btn_row.addWidget(self.capture_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.screenshot_btn)
        btn_row.addStretch()
        cp_layout.addLayout(btn_row)
```

- [ ] **Step 2: 绑定三个按钮的点击信号**

在信号绑定区，`self.screenshot_btn.clicked.connect(self._on_screenshot)`（第 240 行）之后插入：

```python
        self.start_btn.clicked.connect(self._on_start_sweep)
        self.pause_btn.clicked.connect(self._on_pause)
        self.stop_btn.clicked.connect(self._on_stop)
```

- [ ] **Step 3: 启动程序确认无报错、按钮显示正常**

Run: `python main.py`
Expected: 窗口正常弹出；"捕获与截图"页按钮行从左到右出现 `[开始扫描(绿)] [暂停(琥珀)] [立即停止(红)] | 迹线:[TRA] [捕获] [保存] [截图]`。手动关闭窗口。

---

## Task 5: `README.md` 文档更新

**Files:**
- Modify: `README.md`（"功能详解"新增小节；"程序化调用"方法表补充行）

- [ ] **Step 1: 在"功能详解"中"设备截图"小节之后新增"扫描控制"小节**

插入以下内容（标题层级与相邻小节保持一致）：

```markdown
### 扫描控制

"捕获与截图"页按钮行最左侧提供三个扫描控制按钮，用于在连续扫描时精确控制停/启：

| 按钮 | 颜色 | 作用 | SCPI |
|------|------|------|------|
| **开始扫描** | 绿 | 按当前扫描模式启动 / 恢复扫描 | `:INIT` |
| **暂停** | 琥珀 | 等当前这一次扫描走完后再停（曲线完整） | 轮询 `:STATus:OPERation:EVENt?` 后 `:ABORt` |
| **立即停止** | 红 | 立刻中止扫描，不等当前扫描完成 | `:ABORt` |

> **使用建议：** 连续扫描时看到理想光谱，点 **暂停** 可停在完整曲线再捕获/截图；
> 若不想等待当前扫描，点 **立即停止**（也可在"暂停"等待过程中点它直接打断）。
> "暂停"在设备空闲时最多等待 60 秒后兜底停止。
```

- [ ] **Step 2: 在"程序化调用"的方法表中补充三行**

在方法表里 `| init(mode, trace) | ... |` 一行之后插入：

```markdown
| `start_sweep()` | 按当前扫描模式启动/恢复扫描（`:INIT`） |
| `abort()` | 立即中止扫描（`:ABORt`） |
| `poll_sweep_finished()` | 读取并清除"扫描完成"事件，返回是否完成过一次扫描 |
```

- [ ] **Step 3: 确认 Markdown 渲染无明显错位**

Run: `grep -n "扫描控制" README.md`
Expected: 能定位到新增小节标题。

---

## Task 6: 真机手动验证清单

**Files:** 无（人工验证）

- [ ] **Step 1: 完整回归脚本**

连接真机后依次验证：

1. 未连接时点 开始扫描/暂停/立即停止 → 均弹"请先连接设备"。
2. 连接 → 应用设置（连续模式）→ 设备开始连续扫描。
3. 点 **暂停** → 状态栏显示"暂停中…" → 当前扫描走完后变"已暂停"，曲线完整、不再刷新。
4. 点 **开始扫描** → 恢复连续扫描，曲线重新刷新。
5. 连续扫描中点 **立即停止** → 立刻停止（状态栏"已停止"）。
6. 点 **暂停** 进入等待，等待期间点 **立即停止** → 立即打断并停止。
7. 暂停按钮在等待期间为禁用态（灰），收尾后恢复可点。

- [ ] **Step 2: 全部单元测试回归**

Run: `python -m pytest tests/test_osa.py -v`
Expected: PASS。

---

## 完成后

所有任务完成、Task 6 真机验证通过后，**交由用户自行 `git commit`**（用户已明确要求不自动提交）。
建议提交信息：`feat: 新增扫描开始/暂停/立即停止控制`。
