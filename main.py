"""
光谱仪 (Yokogawa AQ6370B) 控制UI
date: 2025-10-10
author: wuxiao
"""

import os
import sys
import time
from typing import Any

from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from osa import osa

ALLOWED_RESOLUTIONS = [2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02]
ALLOWED_WAVELENGTH_MIN = 600
ALLOWED_WAVELENGTH_MAX = 1700

SENSITIVITY_MAP = {
    0: "NAUT",
    1: "NHLD",
    2: "NORM",
    3: "MID",
    4: "HIGH1",
    5: "HIGH2",
    6: "HIGH3",
}


class EmittingStream:
    """重定向 stdout/stderr 到 QTextEdit"""

    def __init__(self, text_edit: QTextEdit) -> None:
        self.text_edit = text_edit

    def write(self, text: str) -> None:
        if text.strip():
            self.text_edit.append(text)

    def flush(self) -> None:
        pass


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("光谱仪控制UI")
        self.client: osa | None = None
        self.captures: list[dict] = []
        self.current_capture_idx: int | None = None
        self._screenshot_dir: str = ""
        self._ch_font_available: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        self._ch_font_available = self._setup_matplotlib_font()

        root = QVBoxLayout()
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # --- 连接栏（始终可见） ---
        conn_layout = QHBoxLayout()
        self.ip_edit = QLineEdit("192.168.100.176")
        self.port_edit = QLineEdit("10001")
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.status_label = QLabel("未连接")
        self.rst_checkbox = QCheckBox("连接时重置")
        conn_layout.addWidget(QLabel("IP:"))
        conn_layout.addWidget(self.ip_edit)
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_edit)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addWidget(self.disconnect_btn)
        conn_layout.addWidget(self.status_label)
        conn_layout.addStretch()
        conn_layout.addWidget(self.rst_checkbox)
        root.addLayout(conn_layout)

        # --- 标签页 ---
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # ---- 第一页：设置 ----
        settings_page = QWidget()
        sp_layout = QVBoxLayout(settings_page)
        sp_layout.setContentsMargins(12, 12, 12, 12)
        sp_layout.setSpacing(8)

        settings_group = QGroupBox("参数设置")
        form = QFormLayout()
        form.setSpacing(8)

        self.scan_mode_combo = QComboBox()
        self.scan_mode_combo.addItems(["单次", "连续", "自动"])
        form.addRow("扫描模式:", self.scan_mode_combo)

        self.start_edit = QLineEdit("1540")
        form.addRow("起始波长 (nm):", self.start_edit)
        self.start_error_label = QLabel("")
        self.start_error_label.setStyleSheet("color: red;")
        form.addRow("", self.start_error_label)

        self.stop_edit = QLineEdit("1560")
        form.addRow("终止波长 (nm):", self.stop_edit)
        self.stop_error_label = QLabel("")
        self.stop_error_label.setStyleSheet("color: red;")
        form.addRow("", self.stop_error_label)

        self.resolution_edit = QLineEdit("0.02")
        form.addRow("分辨率 (nm):", self.resolution_edit)
        self.resolution_error_label = QLabel("")
        self.resolution_error_label.setStyleSheet("color: red;")
        form.addRow("", self.resolution_error_label)

        self.pdiv_edit = QLineEdit("10")
        form.addRow("纵轴每格刻度 (dB):", self.pdiv_edit)

        self.ylevel_edit = QLineEdit("-20")
        form.addRow("参考高度线 (dBm):", self.ylevel_edit)

        self.sensitivity_combo = QComboBox()
        self.sensitivity_combo.addItems([
            "NORM/AUTO", "NORM/HOLD", "NORM", "MID",
            "HIGH1", "HIGH2", "HIGH3",
        ])
        form.addRow("灵敏度:", self.sensitivity_combo)

        self.apply_btn = QPushButton("应用设置")
        form.addRow(self.apply_btn)

        settings_group.setLayout(form)
        sp_layout.addWidget(settings_group)
        sp_layout.addStretch(1)
        tabs.addTab(settings_page, "设置")

        # ---- 第二页：捕获与截图 ----
        capture_page = QWidget()
        cp_layout = QVBoxLayout(capture_page)
        cp_layout.setContentsMargins(8, 8, 8, 8)
        cp_layout.setSpacing(4)

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

        # 主内容区（填满剩余空间）
        content_row = QHBoxLayout()

        # 左列：历史列表
        left_col = QVBoxLayout()
        self.capture_list = QListWidget()
        self.clear_btn = QPushButton("清空")
        left_col.addWidget(self.capture_list, 1)
        left_col.addWidget(self.clear_btn, 0)
        content_row.addLayout(left_col, 1)

        # 右列：图表/截图（用 QStackedWidget，切换时不改变尺寸）
        self.right_stack = QStackedWidget()

        canvas_widget = QWidget()
        canvas_layout = QVBoxLayout(canvas_widget)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        canvas_layout.addWidget(self.canvas, 1)
        canvas_layout.addWidget(self.toolbar, 0)
        self.right_stack.addWidget(canvas_widget)   # index 0

        self.screenshot_label = QLabel("截图预览区域")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        self.right_stack.addWidget(self.screenshot_label)  # index 1

        content_row.addWidget(self.right_stack, 5)
        cp_layout.addLayout(content_row, 1)

        # 日志（固定高度，不参与拉伸）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(60)
        self.log_text.setMaximumHeight(100)
        cp_layout.addWidget(self.log_text, 0)

        tabs.addTab(capture_page, "捕获与截图")

        self.setLayout(root)

        # --- 信号绑定 ---
        self.connect_btn.clicked.connect(self._on_connect)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.capture_btn.clicked.connect(self._on_capture)
        self.save_btn.clicked.connect(self._on_save)
        self.capture_list.itemClicked.connect(self._on_capture_selected)
        self.apply_btn.clicked.connect(self._on_apply_settings)
        self.resolution_edit.textChanged.connect(self._validate_resolution)
        self.start_edit.textChanged.connect(self._validate_wavelength_range)
        self.stop_edit.textChanged.connect(self._validate_wavelength_range)
        self.clear_btn.clicked.connect(self._on_clear_captures)
        self.screenshot_btn.clicked.connect(self._on_screenshot)

        sys.stdout = EmittingStream(self.log_text)
        sys.stderr = EmittingStream(self.log_text)

    # ---- Matplotlib 字体 ----

    @staticmethod
    def _setup_matplotlib_font() -> bool:
        """配置支持中文的字体，返回是否找到中文字体。"""
        try:
            candidates = [
                "Microsoft YaHei",
                "SimHei",
                "SimSun",
                "Noto Sans CJK SC",
                "Source Han Sans CN",
            ]
            installed = {f.name for f in font_manager.fontManager.ttflist}
            chosen = None
            for name in candidates:
                if name in installed:
                    chosen = name
                    break
            if chosen:
                current = rcParams.get("font.sans-serif", [])
                rcParams["font.sans-serif"] = [chosen] + list(current)
                rcParams["font.family"] = "sans-serif"
                rcParams["axes.unicode_minus"] = False
                return True
            rcParams["axes.unicode_minus"] = False
            return False
        except Exception:
            try:
                rcParams["axes.unicode_minus"] = False
            except Exception:
                pass
            return False

    # ---- 连接 / 断开 ----

    def _on_connect(self) -> None:
        ip = self.ip_edit.text()
        port = int(self.port_edit.text())
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        try:
            self.status_label.setText("正在连接...")
            QApplication.processEvents()
            rst = self.rst_checkbox.isChecked()
            try:
                self.client = osa(ip, port, rst=rst)
            except Exception:
                print("第一次连接失败，正在重试...")
                time.sleep(1)
                self.client = osa(ip, port, rst=rst)
            device_id = self.client.idn
            self.status_label.setText(f"已连接: {device_id}")
        except Exception as e:
            self.status_label.setText("连接失败")
            QMessageBox.critical(self, "连接失败", str(e))
            self.client = None

    def _on_disconnect(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.status_label.setText("已断开")
        self.client = None

    # ---- 捕获 / 显示 / 保存 ----

    def _on_capture(self) -> None:
        if not self.client:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return
        try:
            trace = self.trace_edit.text().strip() or "TRA"
            x, y = self.client.get_spectrum(display=False, trace=trace)
            name = time.strftime("捕获_%Y%m%d_%H%M%S") + f"_{trace}"
            self.captures.append({"name": name, "type": "spectrum", "data": (x, y)})
            self.capture_list.addItem(name)
            self.current_capture_idx = len(self.captures) - 1
            self._show_capture(x, y)
        except Exception as e:
            QMessageBox.critical(self, "采集失败", str(e))

    def _show_capture(self, x: Any, y: Any) -> None:
        self.right_stack.setCurrentIndex(0)
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.plot(x * 1e9, y)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Power (dBm)")
        ax.set_title("光谱图" if self._ch_font_available else "Spectrum")
        self.canvas.draw()

    def _on_capture_selected(self, item: QListWidget) -> None:
        idx = self.capture_list.row(item)
        self.current_capture_idx = idx
        entry = self.captures[idx]
        if entry["type"] == "screenshot":
            self._show_screenshot(entry["data"])
        else:
            x, y = entry["data"]
            self._show_capture(x, y)

    def _show_screenshot(self, filepath: str) -> None:
        self.right_stack.setCurrentIndex(1)
        pixmap = QPixmap(filepath)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.screenshot_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.screenshot_label.setPixmap(scaled)

    def _on_save(self) -> None:
        if self.current_capture_idx is None:
            QMessageBox.warning(self, "错误", "没有可保存的数据")
            return
        entry = self.captures[self.current_capture_idx]
        if entry["type"] == "screenshot":
            src = entry["data"]
            path, _ = QFileDialog.getSaveFileName(
                self, "保存截图", "", "BMP Files (*.bmp);;All Files (*)"
            )
            if path:
                try:
                    with open(src, "rb") as fin, open(path, "wb") as fout:
                        fout.write(fin.read())
                    QMessageBox.information(self, "保存成功", f"截图已保存到 {path}")
                except Exception as e:
                    QMessageBox.critical(self, "保存失败", str(e))
        else:
            x, y = entry["data"]
            path, _ = QFileDialog.getSaveFileName(self, "保存数据", "", "CSV Files (*.csv)")
            if path:
                try:
                    with open(path, "w") as f:
                        for xi, yi in zip(x, y):
                            f.write(f"{xi},{yi}\n")
                    QMessageBox.information(self, "保存成功", f"数据已保存到 {path}")
                except Exception as e:
                    QMessageBox.critical(self, "保存失败", str(e))

    def _on_clear_captures(self) -> None:
        self.captures.clear()
        self.capture_list.clear()
        self.current_capture_idx = None
        self.figure.clear()
        self.canvas.draw()
        self.screenshot_label.clear()
        self.right_stack.setCurrentIndex(0)

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
            data = self.client.read_device_file("screenshot")
            ts = time.strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self._screenshot_dir, f"screenshot_{ts}.bmp")
            with open(filepath, "wb") as f:
                f.write(data)
            name = time.strftime("截图_%Y%m%d_%H%M%S")
            self.captures.append({"name": name, "type": "screenshot", "data": filepath})
            self.capture_list.addItem(name)
            self.current_capture_idx = len(self.captures) - 1
            self._show_screenshot(filepath)
            self.status_label.setText(f"截图已保存: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "截图失败", str(e))
            self.status_label.setText("截图失败")

    # ---- 设置 ----

    def _on_apply_settings(self) -> None:
        if not self.client:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return
        try:
            mode = self.scan_mode_combo.currentIndex() + 1  # 1:单次, 2:连续, 3:自动
            start = float(self.start_edit.text())
            stop = float(self.stop_edit.text())
            wl_center = (start + stop) / 2
            wl_span = stop - start
            resolution = float(self.resolution_edit.text())

            if resolution not in ALLOWED_RESOLUTIONS:
                QMessageBox.warning(
                    self,
                    "无效分辨率",
                    "分辨率必须是以下之一：2, 1, 0.5, 0.2, 0.1, 0.05, 0.02",
                )
                return
            if (
                start < ALLOWED_WAVELENGTH_MIN
                or stop > ALLOWED_WAVELENGTH_MAX
                or start >= stop
            ):
                QMessageBox.warning(
                    self,
                    "无效波长范围",
                    f"起始波长必须 >= {ALLOWED_WAVELENGTH_MIN} nm，"
                    f"终止波长必须 <= {ALLOWED_WAVELENGTH_MAX} nm，且起始 < 终止。",
                )
                return

            pdiv = float(self.pdiv_edit.text())
            ylevel = float(self.ylevel_edit.text())

            self.client.init(mode=mode)
            self.client.wl_center = wl_center
            self.client.wl_span = wl_span
            self.client.resolution = resolution
            self.client.pdiv = pdiv
            self.client.ylevel = ylevel
            sensitivity_key = self.sensitivity_combo.currentIndex()
            self.client.sensitivity = SENSITIVITY_MAP[sensitivity_key]
            QMessageBox.information(self, "成功", "设置已应用")
        except Exception as e:
            QMessageBox.critical(self, "设置失败", str(e))

    # ---- 输入验证 ----

    def _validate_resolution(self) -> None:
        try:
            res = float(self.resolution_edit.text())
            if res not in ALLOWED_RESOLUTIONS:
                self.resolution_error_label.setText(
                    "无效分辨率，请选择：2, 1, 0.5, 0.2, 0.1, 0.05, 0.02"
                )
                self.resolution_edit.setStyleSheet("border: 1px solid red;")
            else:
                self.resolution_error_label.setText("")
                self.resolution_edit.setStyleSheet("")
        except ValueError:
            self.resolution_error_label.setText("请输入有效的数字")
            self.resolution_edit.setStyleSheet("border: 1px solid red;")

    def _validate_wavelength_range(self) -> None:
        try:
            start = float(self.start_edit.text())
            stop = float(self.stop_edit.text())
            if (
                start < ALLOWED_WAVELENGTH_MIN
                or stop > ALLOWED_WAVELENGTH_MAX
                or start >= stop
            ):
                error_msg = (
                    f"波长范围无效。起始波长必须 >= {ALLOWED_WAVELENGTH_MIN} nm，"
                    f"终止波长必须 <= {ALLOWED_WAVELENGTH_MAX} nm，且起始 < 终止。"
                )
                self.start_error_label.setText(error_msg)
                self.stop_error_label.setText(error_msg)
                self.start_edit.setStyleSheet("border: 1px solid red;")
                self.stop_edit.setStyleSheet("border: 1px solid red;")
            else:
                self.start_error_label.setText("")
                self.stop_error_label.setText("")
                self.start_edit.setStyleSheet("")
                self.stop_edit.setStyleSheet("")
        except ValueError:
            error_msg = "请输入有效的数字"
            self.start_error_label.setText(error_msg)
            self.stop_error_label.setText(error_msg)
            self.start_edit.setStyleSheet("border: 1px solid red;")
            self.stop_edit.setStyleSheet("border: 1px solid red;")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.setMinimumSize(860, 560)
    win.resize(1000, 680)
    win.show()
    sys.exit(app.exec_())
