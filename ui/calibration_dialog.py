import json
from datetime import datetime
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QLineEdit, QDoubleSpinBox, QPushButton,
                               QTabWidget, QWidget, QComboBox, QTextEdit, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
                               QGroupBox, QDateEdit)
from PyQt6.QtCore import Qt, QDate, pyqtSignal

from core.data_storage import DeviceStorage


class CalibrationDialog(QDialog):
    """设备校准参数配置对话框"""

    calibration_updated = pyqtSignal(dict)

    def __init__(self, storage: DeviceStorage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("设备校准参数配置")
        self.setMinimumSize(760, 600)
        self._init_ui()
        self._load_history()
        self._load_latest()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_current_tab(), "当前校准")
        self.tabs.addTab(self._build_history_tab(), "历史记录")
        self.tabs.addTab(self._build_device_tab(), "设备参数表")
        main_layout.addWidget(self.tabs, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton("保存并应用")
        btn_save.setMinimumWidth(120)
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        btn_close = QPushButton("关闭")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        main_layout.addLayout(btn_row)

    def _build_current_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.addItems([
            'Keithley 4200-SMU',
            'Newport Oriel Sol3A',
            '国产通用IV测试仪-A型',
            '国产通用IV测试仪-B型',
            '太阳能模拟器标准光源',
        ])
        form.addRow("设备名称:", self.device_combo)

        self.intensity_spin = QDoubleSpinBox()
        self.intensity_spin.setRange(0.0001, 10.0)
        self.intensity_spin.setDecimals(6)
        self.intensity_spin.setSingleStep(0.001)
        self.intensity_spin.setValue(1.0)
        self.intensity_spin.setToolTip("光强校准系数，测量值 * 系数 = 真实值")
        form.addRow("光强校准系数:", self.intensity_spin)

        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.0001, 100.0)
        self.area_spin.setDecimals(6)
        self.area_spin.setSingleStep(0.001)
        self.area_spin.setValue(1.0)
        form.addRow("面积校准系数:", self.area_spin)

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0.0001, 10.0)
        self.current_spin.setDecimals(6)
        self.current_spin.setSingleStep(0.001)
        self.current_spin.setValue(1.0)
        form.addRow("电流校准系数:", self.current_spin)

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0.0001, 10.0)
        self.voltage_spin.setDecimals(6)
        self.voltage_spin.setSingleStep(0.001)
        self.voltage_spin.setValue(1.0)
        form.addRow("电压校准系数:", self.voltage_spin)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(-50, 200)
        self.temp_spin.setDecimals(2)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(25.0)
        self.temp_spin.setSuffix(" °C")
        form.addRow("标准测试温度:", self.temp_spin)

        self.irradiance_spin = QDoubleSpinBox()
        self.irradiance_spin.setRange(0.01, 5000)
        self.irradiance_spin.setDecimals(2)
        self.irradiance_spin.setSingleStep(1.0)
        self.irradiance_spin.setValue(100.0)
        self.irradiance_spin.setSuffix(" mW/cm²")
        form.addRow("标准辐照度:", self.irradiance_spin)

        self.std_area_spin = QDoubleSpinBox()
        self.std_area_spin.setRange(0.0001, 1000)
        self.std_area_spin.setDecimals(4)
        self.std_area_spin.setSingleStep(0.01)
        self.std_area_spin.setValue(1.0)
        self.std_area_spin.setSuffix(" cm²")
        form.addRow("默认器件面积:", self.std_area_spin)

        form.addRow(QLabel("<hr>"))

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        form.addRow("校准日期:", self.date_edit)

        self.operator_edit = QLineEdit()
        self.operator_edit.setPlaceholderText("校准人员姓名")
        form.addRow("校准人员:", self.operator_edit)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("校准备注、环境条件等...")
        self.notes_edit.setMaximumHeight(80)
        form.addRow("备注:", self.notes_edit)

        hint = QLabel(
            "<span style='color:#888;font-size:11px;'>校准系数用于将设备读数修正为真实值：真实值 = 读数 × 校准系数<br>"
            "例如：参考电池测得光强95 mW/cm²，标准为100，则系数设为 100/95 = 1.052632</span>"
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.history_table = QTableWidget(0, 9)
        self.history_table.setHorizontalHeaderLabels([
            'ID', '设备名称', '光强系数', '面积系数', '电流系数',
            '电压系数', '校准日期', '操作人员', '备注'
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.doubleClicked.connect(self._on_history_doubleclick)
        layout.addWidget(self.history_table, stretch=1)

        btn_row = QHBoxLayout()
        btn_import = QPushButton("导入JSON校准文件")
        btn_import.clicked.connect(self._on_import_json)
        btn_row.addWidget(btn_import)
        btn_export = QPushButton("导出全部记录")
        btn_export.clicked.connect(self._on_export_json)
        btn_row.addWidget(btn_export)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    def _build_device_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel("<h4>常用光伏材料/器件参数参考表</h4>")
        layout.addWidget(info)

        self.device_table = QTableWidget(0, 7)
        self.device_table.setHorizontalHeaderLabels([
            '器件类型', 'Voc范围(V)', 'Jsc范围(mA/cm²)', 'FF范围(%)',
            'Efficiency范围(%)', '温度系数(%/°C)', '带隙Eg(eV)'
        ])
        refs = [
            ['单晶硅 Si', '0.60 ~ 0.74', '35 ~ 45', '75 ~ 84', '20 ~ 26.8', '-0.38 ~ -0.45', '1.12'],
            ['多晶硅 mc-Si', '0.58 ~ 0.68', '32 ~ 40', '72 ~ 82', '16 ~ 24.4', '-0.40 ~ -0.47', '1.12'],
            ['CdTe 碲化镉', '0.80 ~ 0.95', '23 ~ 29', '70 ~ 79', '14 ~ 22.1', '-0.23 ~ -0.33', '1.45'],
            ['CIGS 铜铟镓硒', '0.60 ~ 0.75', '30 ~ 38', '68 ~ 80', '14 ~ 23.6', '-0.30 ~ -0.40', '1.10 ~ 1.70'],
            ['钙钛矿 MAPbI3', '1.00 ~ 1.18', '22 ~ 26', '70 ~ 86', '15 ~ 26.1', '-0.17 ~ -0.25', '1.55'],
            ['非晶硅 a-Si:H', '0.80 ~ 0.95', '13 ~ 18', '60 ~ 72', '6 ~ 15', '-0.20 ~ -0.30', '1.75'],
            ['砷化镓 GaAs', '0.98 ~ 1.12', '28 ~ 33', '80 ~ 88', '24 ~ 29.1', '-0.17 ~ -0.23', '1.42'],
            ['有机光伏 OPV', '0.70 ~ 1.00', '15 ~ 24', '65 ~ 80', '10 ~ 20', '-0.15 ~ -0.30', '1.2 ~ 2.0'],
            ['染料敏化 DSSC', '0.65 ~ 0.85', '12 ~ 20', '60 ~ 75', '7 ~ 14', '-0.20 ~ -0.30', '~1.8'],
        ]
        self.device_table.setRowCount(len(refs))
        for r, row in enumerate(refs):
            for c, val in enumerate(row):
                item = QTableWidgetItem(val)
                if c == 0:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.device_table.setItem(r, c, item)

        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.device_table, stretch=1)

        return w

    def _load_history(self):
        try:
            records = self.storage.list_calibrations(limit=500)
        except Exception:
            records = []
        self.history_table.setRowCount(len(records))
        for r, rec in enumerate(records):
            self.history_table.setItem(r, 0, QTableWidgetItem(str(rec.get('id', ''))))
            self.history_table.setItem(r, 1, QTableWidgetItem(str(rec.get('device_name', ''))))
            self.history_table.setItem(r, 2, QTableWidgetItem(f"{rec.get('intensity_cal', 1.0):.6f}"))
            self.history_table.setItem(r, 3, QTableWidgetItem(f"{rec.get('area_cal', 1.0):.6f}"))
            self.history_table.setItem(r, 4, QTableWidgetItem(f"{rec.get('current_cal', 1.0):.6f}"))
            self.history_table.setItem(r, 5, QTableWidgetItem(f"{rec.get('voltage_cal', 1.0):.6f}"))
            self.history_table.setItem(r, 6, QTableWidgetItem(str(rec.get('last_cal_date', ''))))
            self.history_table.setItem(r, 7, QTableWidgetItem(str(rec.get('operator', ''))))
            self.history_table.setItem(r, 8, QTableWidgetItem(str(rec.get('notes', ''))))

    def _load_latest(self):
        try:
            latest = self.storage.get_latest_calibration()
        except Exception:
            latest = None
        if latest:
            idx = self.device_combo.findText(str(latest.get('device_name', '')))
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
            else:
                self.device_combo.addItem(str(latest.get('device_name', '')))
                self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
            self.intensity_spin.setValue(float(latest.get('intensity_cal', 1.0)))
            self.area_spin.setValue(float(latest.get('area_cal', 1.0)))
            self.current_spin.setValue(float(latest.get('current_cal', 1.0)))
            self.voltage_spin.setValue(float(latest.get('voltage_cal', 1.0)))
            self.operator_edit.setText(str(latest.get('operator', '')))
            self.notes_edit.setPlainText(str(latest.get('notes', '')))

    def _collect_data(self) -> Dict[str, Any]:
        return {
            'device_name': self.device_combo.currentText().strip() or '未知设备',
            'intensity_cal': self.intensity_spin.value(),
            'area_cal': self.area_spin.value(),
            'current_cal': self.current_spin.value(),
            'voltage_cal': self.voltage_spin.value(),
            'temperature_c': self.temp_spin.value(),
            'std_irradiance': self.irradiance_spin.value(),
            'std_area': self.std_area_spin.value(),
            'last_cal_date': self.date_edit.date().toString('yyyy-MM-dd'),
            'operator': self.operator_edit.text().strip(),
            'notes': self.notes_edit.toPlainText().strip(),
            'params': {
                'temperature_c': self.temp_spin.value(),
                'std_irradiance': self.irradiance_spin.value(),
                'std_area': self.std_area_spin.value(),
            },
        }

    def _on_save(self):
        try:
            data = self._collect_data()
            self.storage.save_calibration(data)
            self.storage.set_setting('last_calibration', data)
            self.calibration_updated.emit(data)
            self._load_history()
            QMessageBox.information(self, "成功", f"校准参数已保存并应用。\n设备: {data['device_name']}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")

    def _on_history_doubleclick(self, index):
        row = index.row()
        if row < 0 or row >= self.history_table.rowCount():
            return
        try:
            records = self.storage.list_calibrations(limit=500)
        except Exception:
            records = []
        if row < len(records):
            rec = records[row]
            idx = self.device_combo.findText(str(rec.get('device_name', '')))
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
            else:
                self.device_combo.insertItem(0, str(rec.get('device_name', '')))
                self.device_combo.setCurrentIndex(0)
            self.intensity_spin.setValue(float(rec.get('intensity_cal', 1.0)))
            self.area_spin.setValue(float(rec.get('area_cal', 1.0)))
            self.current_spin.setValue(float(rec.get('current_cal', 1.0)))
            self.voltage_spin.setValue(float(rec.get('voltage_cal', 1.0)))
            self.operator_edit.setText(str(rec.get('operator', '')))
            self.notes_edit.setPlainText(str(rec.get('notes', '')))
            self.tabs.setCurrentIndex(0)

    def _on_import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入校准文件", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        self.storage.save_calibration(item)
            elif isinstance(data, dict):
                if 'calibrations' in data and isinstance(data['calibrations'], list):
                    for item in data['calibrations']:
                        self.storage.save_calibration(item)
                else:
                    self.storage.save_calibration(data)
            self._load_history()
            QMessageBox.information(self, "成功", "校准记录导入完成")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入失败: {str(e)}")

    def _on_export_json(self):
        default = f"calibration_history_{datetime.now().strftime('%Y%m%d')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "导出校准记录", default, "JSON Files (*.json)")
        if not path:
            return
        try:
            records = self.storage.list_calibrations(limit=10000)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'calibrations': records,
                }, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出 {len(records)} 条校准记录")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def get_current_calibration(self) -> Dict[str, Any]:
        return self._collect_data()
