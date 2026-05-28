# OSA Feature Additions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional initialization, sensitivity control, and screenshot capture with file transfer to the OSA remote control program.

**Architecture:** Minimal changes to the two existing files (`osa.py` device layer, `main.py` PyQt5 GUI). New SCPI methods added to `osa.py`; new UI controls added to `main.py`. No new files created.

**Tech Stack:** Python 3, PyQt5, socket (SCPI over TCP/IP)

**Note:** This project has no test suite and controls physical hardware, so testing is manual (connect to device, verify behavior). No unit test steps.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `osa.py` | Modify | Add sensitivity property, screenshot save, file read methods; change default `rst` |
| `main.py` | Modify | Add reset checkbox, sensitivity dropdown, screenshot button + preview |

---

### Task 1: Change default initialization to not reset device

**Files:**
- Modify: `osa.py:20`

- [ ] **Step 1: Change `rst` default to `False`**

In `osa.py` line 20, change the default parameter:

```python
def __init__(self, ip, port, rst=False):
```

- [ ] **Step 2: Move FORMAT:DATA outside the rst conditional**

The `:FORMAT:DATA REAL,64\n` on line 38 should always be sent (even when not resetting), because the login sequence may reset the format. Verify the current code already does this (it does — line 38 is outside the `if rst:` block).

- [ ] **Step 3: Commit**

```bash
git add osa.py
git commit -m "feat: default to no device reset on connect"
```

---

### Task 2: Add reset checkbox to UI

**Files:**
- Modify: `main.py:72-85` (connection layout area)

- [ ] **Step 1: Add QCheckBox import and create checkbox**

Add `QCheckBox` to the imports from `PyQt5.QtWidgets` (line 17-32). Then in `_init_ui`, after creating `self.status_label` (line 77), add:

```python
self.rst_checkbox = QCheckBox("连接时重置")
conn_layout.addWidget(self.rst_checkbox)
```

This should be added right after `conn_layout.addWidget(self.status_label)` (line 84).

- [ ] **Step 2: Modify `_on_connect` to use checkbox state**

In `_on_connect` (line 209), change the two places where `osa(ip, port)` is called to pass the checkbox state:

```python
rst = self.rst_checkbox.isChecked()
try:
    self.client = osa(ip, port, rst=rst)
except Exception:
    print("第一次连接失败，正在重试...")
    time.sleep(1)
    self.client = osa(ip, port, rst=rst)
```

- [ ] **Step 3: Test manually**

Run the program. With checkbox unchecked, connect to device — device should NOT reset. With checkbox checked, connect — device should reset as before.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add optional device reset checkbox in connection UI"
```

---

### Task 3: Add sensitivity property to osa.py

**Files:**
- Modify: `osa.py:172-184` (property definitions area)

- [ ] **Step 1: Add sensitivity property**

After the existing property definitions (line 184), add:

```python
    sensitivity = osa_property(
        ':SENSe:SENSe?\n', ':SENSe:SENSe {value}\n'
    )
```

This follows the exact same `osa_property` pattern as the other properties. The getter sends `:SENSe:SENSe?` and returns the device response. The setter sends `:SENSe:SENSe <value>` where `<value>` is a string like `HIGH1`, `MID`, `NORM`, etc.

- [ ] **Step 2: Test manually**

Connect to device, then in Python try `client.sensitivity = 'HIGH1'` and `print(client.sensitivity)` to verify the round-trip.

- [ ] **Step 3: Commit**

```bash
git add osa.py
git commit -m "feat: add sensitivity property to osa device class"
```

---

### Task 4: Add sensitivity dropdown to UI

**Files:**
- Modify: `main.py:88-118` (settings layout area)
- Modify: `main.py:299-342` (`_on_apply_settings` method)

- [ ] **Step 1: Add sensitivity combo box to settings layout**

After the `ylevel_edit` row (line 114), add:

```python
self.sensitivity_combo = QComboBox()
self.sensitivity_combo.addItems([
    "NORM/AUTO", "NORM/HOLD", "NORM", "MID",
    "HIGH1", "HIGH2", "HIGH3",
])
settings_layout.addRow("灵敏度:", self.sensitivity_combo)
```

- [ ] **Step 2: Define sensitivity value mapping**

Add a class-level constant after the `ALLOWED_WAVELENGTH_MAX` line (line 38):

```python
SENSITIVITY_MAP = {
    0: "NAUT",
    1: "NHLD",
    2: "NORM",
    3: "MID",
    4: "HIGH1",
    5: "HIGH2",
    6: "HIGH3",
}
```

The keys are combo box indices, the values are SCPI command strings.

- [ ] **Step 3: Add sensitivity to `_on_apply_settings`**

In `_on_apply_settings`, after setting `ylevel` (line 339), add:

```python
sensitivity_key = self.sensitivity_combo.currentIndex()
self.client.sensitivity = SENSITIVITY_MAP[sensitivity_key]
```

- [ ] **Step 4: Test manually**

Connect, select different sensitivity levels, click "应用设置", verify the device sensitivity changes.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add sensitivity dropdown to settings UI"
```

---

### Task 5: Add screenshot save and file read methods to osa.py

**Files:**
- Modify: `osa.py` (add methods after `read_device_file`)

- [ ] **Step 1: Add `save_screenshot` method**

Add after the `get_spectrum` method (after line 138):

```python
def save_screenshot(self, filename="screenshot.bmp"):
    self.send(':MMEMory:CDRive INTernal\n')
    self.send(f':MMEMory:STORe:GRAPhics COLor,BMP,"{filename}",INTernal\n')
```

This tells the OSA to save its current display as a color BMP file to internal storage.

- [ ] **Step 2: Add `read_device_file` method**

Add right after `save_screenshot`:

```python
def read_device_file(self, filename):
    self.sock.sendall(f':MMEMory:DATA? "{filename}"\n'.encode())
    data = self.recv_all()
    if data[0:1] != b'#':
        raise ValueError("Not a SCPI binblock!")
    n_len = int(data[1:2])
    n_bytes = int(data[2:2 + n_len])
    return data[2 + n_len:2 + n_len + n_bytes]
```

This reads a file from the device's memory via SCPI binary block transfer. It uses the same `#<n><count><bytes>` header parsing as `parse_scpi_binblock` but returns raw bytes instead of a numpy array.

- [ ] **Step 3: Add wait after save for device to finish writing**

Update `save_screenshot` to add a small delay after the save command, since the device needs time to write the BMP:

```python
def save_screenshot(self, filename="screenshot.bmp"):
    self.send(':MMEMory:CDRive INTernal\n')
    self.send(f':MMEMory:STORe:GRAPhics COLor,BMP,"{filename}",INTernal\n')
    time.sleep(2)
```

Add `import time` at the top of `osa.py` if not already present.

- [ ] **Step 4: Test manually**

Connect, call `client.save_screenshot()`, then `data = client.read_device_file("screenshot.bmp")`, write `data` to a local file, verify it's a valid BMP.

- [ ] **Step 5: Commit**

```bash
git add osa.py
git commit -m "feat: add screenshot save and device file read to osa class"
```

---

### Task 6: Add screenshot UI — button, save directory, and preview

**Files:**
- Modify: `main.py:121-130` (capture controls area)
- Modify: `main.py:55-63` (`__init__` state variables)
- Modify: `main.py:132-148` (main content area)

- [ ] **Step 1: Add state variables in `__init__`**

Add after `self.current_capture_idx` (line 61):

```python
self._screenshot_dir: str = ""
```

- [ ] **Step 2: Add imports**

Add `QPixmap` to the PyQt5 imports. Also add `os` import at the top:

```python
import os
```

Change the PyQt5 import line to include `QPixmap`:

```python
from PyQt5.QtGui import QPixmap
```

- [ ] **Step 3: Add screenshot button in capture controls**

In the capture layout section (line 121-130), after `self.save_btn = QPushButton("保存")`, add:

```python
self.screenshot_btn = QPushButton("截图")
capture_layout.addWidget(self.screenshot_btn)
```

- [ ] **Step 4: Add preview area in main content**

In the right_layout section (line 142-147), after the toolbar widget, add a QLabel for image preview:

```python
self.screenshot_label = QLabel("截图预览区域")
self.screenshot_label.setAlignment(Qt.AlignCenter)
self.screenshot_label.setMaximumHeight(200)
self.screenshot_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
self.screenshot_label.hide()
right_layout.addWidget(self.screenshot_label)
```

Add `Qt` to the PyQt5 imports:

```python
from PyQt5.QtCore import Qt
```

- [ ] **Step 5: Implement `_on_screenshot` method**

Add this method after `_on_clear_captures`:

```python
def _on_screenshot(self) -> None:
    if not self.client:
        QMessageBox.warning(self, "错误", "请先连接设备")
        return
    if not self._screenshot_dir:
        d = QFileDialog.getExistingDirectory(self, "选择截图保存目录")
        if not d:
            return
        self._screenshot_dir = d
    try:
        self.status_label.setText("正在截图...")
        QApplication.processEvents()
        self.client.save_screenshot()
        data = self.client.read_device_file("screenshot.bmp")
        ts = time.strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self._screenshot_dir, f"screenshot_{ts}.bmp")
        with open(filepath, "wb") as f:
            f.write(data)
        pixmap = QPixmap(filepath)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.screenshot_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.screenshot_label.setPixmap(scaled)
            self.screenshot_label.show()
        self.status_label.setText(f"截图已保存: {filepath}")
    except Exception as e:
        QMessageBox.critical(self, "截图失败", str(e))
        self.status_label.setText("截图失败")
```

- [ ] **Step 6: Connect signal**

Add in the signal binding section (after line 167):

```python
self.screenshot_btn.clicked.connect(self._on_screenshot)
```

- [ ] **Step 7: Test manually**

Connect to device, click "截图", select save directory, verify BMP file is saved and preview appears in GUI. Click again to verify it uses the same directory without prompting.

- [ ] **Step 8: Commit**

```bash
git add main.py
git commit -m "feat: add screenshot capture with file transfer and GUI preview"
```

---

## Self-Review

**Spec coverage:**
- [x] Section 1 (Init change): Tasks 1-2
- [x] Section 2 (Sensitivity): Tasks 3-4
- [x] Section 3 (Screenshot): Tasks 5-6

**Placeholder scan:** No TBD/TODO/placeholders found.

**Type consistency:** `sensitivity` property uses string values set via `osa_property` pattern — `SENSITIVITY_MAP` values are strings matching SCPI commands. `save_screenshot` / `read_device_file` method names are consistent between osa.py and main.py. `_screenshot_dir` state variable used consistently.
