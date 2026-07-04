# 批量保存捕获条目 — 设计文档

- 日期: 2026-07-04
- 作者: wuxiao / Claude
- 状态: 已批准

## 背景与动机

使用场景：调整一个电压 → 观察光谱仪数据 → 捕获 → 重复，最终会累积**非常多**的捕获条目。
当前 `_on_save`（main.py:401）每次只能保存**当前选中的单个**条目，且每次弹出文件对话框要求手动输入文件名。N 个条目 = N 次弹框，非常繁琐。

目标：**多选 + 一键批量保存**，一次选好目录后，所有目标条目自动命名写入。

## 现状

- `self.captures: list[dict]`，每项为 `{"name", "type": "spectrum"|"screenshot", "data"}`
  - spectrum：`data = (x, y)`，x/y 为 numpy 数组
  - screenshot：`data = <bmp 文件路径>`
- `capture_list` 为单选 `QListWidget`（main.py:223）
- `_on_save`（main.py:401）：spectrum → 逐行 `xi,yi` 写 CSV（无表头）；screenshot → 原始字节拷贝到 `.bmp`

## 需求

1. `capture_list` 支持多选（Ctrl/Shift）。
2. 新增按钮「批量保存」，位于「保存」右侧。
3. 点击行为：**有选中 → 只存选中的；未选中任何条目 → 存全部**（一个按钮覆盖两种需求）。
4. 只弹**一次**目录选择框；之后所有条目按其 `name` 自动命名写入该目录。
5. spectrum → `.csv`，screenshot → `.bmp`，格式与现有单个保存**完全一致**。
6. 文件名非法字符（`/ \ : * ? " < > |` 及控制字符）替换为 `_`。
7. 同名冲突自动追加 `_1`、`_2`…，不覆盖已有文件（同一秒多次捕获、或重复存入同一目录）。
8. 列表为空时提示「没有可保存的数据」并返回。
9. 逐条 `try/except`，单条失败不中断其余；结束弹汇总框：成功 N 个 / 失败 M 个（含失败项与原因）。

## 架构决策

**本机 `PyQt5` 不可导入**（`import main` 会失败），因此可单测的纯逻辑必须放在**不依赖 Qt 的独立模块**，沿用项目已有的「可测原语放 `osa.py`」模式。

### 新模块 `capture_io.py`（纯函数，仅依赖 stdlib，可单测）

```python
def sanitize_filename(name: str) -> str: ...
    # 非法字符 / \ : * ? " < > | 及控制字符 → "_"；去首尾空白；空串回退为 "capture"

def resolve_unique_path(directory: str, base: str, ext: str, used: set[str]) -> str: ...
    # 返回 directory/base+ext；若已存在于 used 或磁盘，追加 _1/_2…；把结果登记进 used

def write_spectrum_csv(x, y, path: str) -> None: ...
    # 逐行 "xi,yi\n"（与现有 _on_save 一致，无表头）

def copy_screenshot(src: str, path: str) -> None: ...
    # 二进制拷贝 src → path
```

`used: set[str]` 由调用方（批量保存）维护，避免同一批内多条目重名互相覆盖；`resolve_unique_path` 同时检查磁盘上已存在的文件。

### `main.py` 改动

- 顶部 `from capture_io import sanitize_filename, resolve_unique_path, write_spectrum_csv, copy_screenshot`
- `capture_list.setSelectionMode(QAbstractItemView.ExtendedSelection)`
- 按钮行新增 `self.save_all_btn = QPushButton("批量保存")`，tooltip：「保存所选条目；未选中时保存全部」，接在「保存」之后
- 绑定 `self.save_all_btn.clicked.connect(self._on_save_all)`
- 新增槽 `_on_save_all()`：
  1. 无捕获 → 提示返回
  2. 取选中行 `selectedIndexes()`；为空则取全部索引
  3. `QFileDialog.getExistingDirectory` 选目录（取消则返回）
  4. 维护 `used=set()`，逐条：按 type 定 ext → `sanitize_filename(name)` → `resolve_unique_path` → 写文件；try/except 累计成功/失败
  5. `QMessageBox` 汇总
- 重构 `_on_save()`：写文件部分改为调用 `write_spectrum_csv` / `copy_screenshot`（行为不变，去重复）

## 错误处理

- 目录未选 → 直接返回，无副作用。
- 单条写失败 → 记入失败列表（含 name 与异常信息），继续处理其余。
- 全部完成后统一 `QMessageBox`：成功数、失败数，失败项逐条列出。

## 测试

`tests/test_capture_io.py`（pytest，风格对齐 `tests/test_osa.py`）：

- `sanitize_filename`：非法字符替换、正常名保留、空串回退、含中文名保留。
- `resolve_unique_path`：无冲突原样返回；`used` 已占用则追加 `_1`；磁盘已存在则追加；连续冲突递增 `_2`；返回后登记进 `used`。
- `write_spectrum_csv`：用 `tmp_path` 写入并读回，逐行 `xi,yi` 校验、行数正确、无表头。
- `copy_screenshot`：用 `tmp_path` 造源文件，拷贝后字节一致。

GUI 部分（`_on_save_all` 槽、多选、按钮）因本机无 PyQt5 无法自动测，靠纯逻辑抽离 + `py_compile` 静态校验保证。

## 影响范围

- 新增：`capture_io.py`、`tests/test_capture_io.py`
- 修改：`main.py`（导入、多选、按钮、`_on_save_all`、`_on_save` 重构）、`README.md`
- 不改动：`osa.py`（不涉及仪器通信）

## 非目标（YAGNI）

- 不做打包 zip、不做进度条、不做自定义命名模板、不做导出格式选择（CSV 表头/单位换算等保持现状）。
