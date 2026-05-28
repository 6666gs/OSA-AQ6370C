# OSA Remote Control - Feature Additions Design

**Date**: 2026-04-25
**Device**: Yokogawa AQ6370B
**Approach**: Minimal changes to existing codebase (Approach A)

## 1. Connection Initialization Change

### Current Behavior
`osa.__init__` defaults `rst=True`, sending `*RST` (device reset) and `*CLS` (clear status) on every connection. This wipes user-configured display settings.

### Changes

**osa.py**:
- Change `rst` parameter default from `True` to `False`
- When `rst=False`: skip `*RST` and `*CLS`, only perform login and `*IDN?` query

**main.py UI**:
- Add a checkbox "连接时重置设备" next to the Connect button, unchecked by default
- Pass `rst=True` only when checkbox is checked

## 2. Sensitivity Control

### SCPI Command
`:SENSe:SENSe <value>` / `:SENSe:SENSe?`

### Supported Values (AQ6370B)

| Display Text | SCPI Value | Numeric |
|---|---|---|
| NORM/HOLD | NHLD | 0 |
| NORM/AUTO | NAUT | 1 |
| MID | MID | 2 |
| HIGH1 | HIGH1 | 3 |
| HIGH2 | HIGH2 | 4 |
| HIGH3 | HIGH3 | 5 |
| NORM | NORM | 6 |

### Changes

**osa.py**:
- Add `sensitivity` property using the existing `osa_property` pattern
- Getter: sends `:SENSe:SENSe?`, maps response to display string
- Setter: sends `:SENSe:SENSe <value>` with the SCPI string value

**main.py UI**:
- Add a "灵敏度" QComboBox in the settings area, alongside resolution, Y-axis scale, and reference level
- Items display Chinese labels mapped to SCPI values
- Value is sent with "应用设置" button click

## 3. Screenshot Capture and Transfer

### Workflow
1. User clicks "截图" button
2. Program sends `:MMEMory:CDRive INTernal` to select internal storage
3. Program sends `:MMEMory:STORe:GRAPhics COLor,BMP,"screenshot.bmp",INTernal` to capture current display
4. Program sends `:MMEMory:DATA? "screenshot.bmp"` to read file binary data via SCPI
5. Binary data is saved to user-configured directory with timestamped filename (e.g., `screenshot_20260425_103300.bmp`)
6. Image preview displayed in GUI via QLabel

### Changes

**osa.py**:
- Add `save_screenshot(filename="screenshot.bmp")` method: sends the graphics save SCPI command
- Add `read_device_file(filename)` method: sends `:MMEMory:DATA?` and parses the binary block response, returns raw bytes

**main.py UI**:
- Add "截图" button in capture controls area
- On first screenshot click, show QFileDialog to select default save directory; persist choice for session
- Add QLabel preview area in the main content section to display latest screenshot
- Auto-save with timestamp: `screenshot_YYYYMMDD_HHMMSS.bmp`
