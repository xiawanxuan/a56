from typing import Dict, Callable

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QDoubleSpinBox, QComboBox, QPushButton, QTabWidget,
                               QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
                               QFrame, QGridLayout, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class UnitConverterDialog(QDialog):
    """单位转换表对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("光伏参数单位转换表")
        self.setMinimumSize(820, 600)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_converter_tab(), "🔄 实时转换")
        tabs.addTab(self._build_reference_tab(), "📖 参考转换表")
        tabs.addTab(self._build_constants_tab(), "⚛ 物理常数表")
        main_layout.addWidget(tabs, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        main_layout.addLayout(btn_row)

    def _build_converter_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        hint = QLabel("💡 在左侧输入数值，自动进行所有相关单位的转换")
        hint.setStyleSheet("color:#2c5282;font-weight:bold;padding:6px;background:#ebf8ff;border-radius:4px;")
        layout.addWidget(hint)

        self._unit_groups = {
            '辐照度/光强': {
                'base_unit': 'W/m²',
                'units': [
                    ('W/m²', lambda x: x, lambda x: x),
                    ('mW/cm²', lambda x: x / 10.0, lambda x: x * 10.0),
                    ('kW/m²', lambda x: x / 1000.0, lambda x: x * 1000.0),
                    ('Suns (1 Sun=1000W/m²)', lambda x: x / 1000.0, lambda x: x * 1000.0),
                    ('W/cm²', lambda x: x / 10000.0, lambda x: x * 10000.0),
                ],
                'default': 1000.0,
            },
            '电流': {
                'base_unit': 'A',
                'units': [
                    ('A', lambda x: x, lambda x: x),
                    ('mA', lambda x: x * 1000.0, lambda x: x / 1000.0),
                    ('μA', lambda x: x * 1e6, lambda x: x / 1e6),
                    ('nA', lambda x: x * 1e9, lambda x: x / 1e9),
                ],
                'default': 0.01,
            },
            '电流密度': {
                'base_unit': 'A/cm²',
                'units': [
                    ('A/cm²', lambda x: x, lambda x: x),
                    ('mA/cm²', lambda x: x * 1000.0, lambda x: x / 1000.0),
                    ('A/m²', lambda x: x * 10000.0, lambda x: x / 10000.0),
                    ('mA/mm²', lambda x: x * 10.0, lambda x: x / 10.0),
                ],
                'default': 0.03,
            },
            '功率': {
                'base_unit': 'W',
                'units': [
                    ('W', lambda x: x, lambda x: x),
                    ('mW', lambda x: x * 1000.0, lambda x: x / 1000.0),
                    ('μW', lambda x: x * 1e6, lambda x: x / 1e6),
                    ('kW', lambda x: x / 1000.0, lambda x: x * 1000.0),
                ],
                'default': 0.02,
            },
            '面积': {
                'base_unit': 'cm²',
                'units': [
                    ('cm²', lambda x: x, lambda x: x),
                    ('mm²', lambda x: x * 100.0, lambda x: x / 100.0),
                    ('m²', lambda x: x / 10000.0, lambda x: x * 10000.0),
                    ('inch²', lambda x: x / 6.4516, lambda x: x * 6.4516),
                ],
                'default': 1.0,
            },
            '长度/厚度': {
                'base_unit': 'nm',
                'units': [
                    ('nm', lambda x: x, lambda x: x),
                    ('μm', lambda x: x / 1000.0, lambda x: x * 1000.0),
                    ('mm', lambda x: x / 1e6, lambda x: x * 1e6),
                    ('cm', lambda x: x / 1e7, lambda x: x * 1e7),
                    ('Å (埃)', lambda x: x * 10.0, lambda x: x / 10.0),
                ],
                'default': 300.0,
            },
            '电阻': {
                'base_unit': 'Ω',
                'units': [
                    ('Ω', lambda x: x, lambda x: x),
                    ('kΩ', lambda x: x / 1000.0, lambda x: x * 1000.0),
                    ('MΩ', lambda x: x / 1e6, lambda x: x * 1e6),
                    ('Ω·cm² (面积归一)', lambda x: x, lambda x: x),
                ],
                'default': 5.0,
            },
            '温度': {
                'base_unit': 'K',
                'units': [
                    ('K', lambda x: x, lambda x: x),
                    ('°C', lambda x: x - 273.15, lambda x: x + 273.15),
                    ('°F', lambda x: (x - 273.15) * 9 / 5 + 32, lambda x: (x - 32) * 5 / 9 + 273.15),
                ],
                'default': 298.15,
            },
        }

        self._input_spins: Dict[str, Dict[str, QDoubleSpinBox]] = {}

        for group_name, group_data in self._unit_groups.items():
            group_box = self._create_group_box(group_name, group_data)
            layout.addWidget(group_box)

        layout.addStretch()
        return w

    def _create_group_box(self, name: str, data: dict) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
            QFrame { background: #fafcff; border: 1px solid #e2e8f0; border-radius: 6px; margin: 4px 0; }
            QLabel#grouplabel { font-weight: bold; color: #2c5282; font-size: 13px; }
        """)
        glayout = QVBoxLayout(frame)
        glayout.setContentsMargins(10, 8, 10, 8)

        title = QLabel(f"▣ {name}")
        title.setObjectName("grouplabel")
        glayout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        self._input_spins[name] = {}

        for idx, (unit_name, from_base, to_base) in enumerate(data['units']):
            label = QLabel(f"{unit_name}:")
            label.setMinimumWidth(170)
            grid.addWidget(label, idx, 0)

            decimals = 6
            spin = QDoubleSpinBox()
            spin.setRange(-1e15, 1e15)
            spin.setDecimals(decimals)
            if name == '温度' and '°C' in unit_name:
                spin.setValue(from_base(data['default']))
            else:
                val = from_base(data['default'])
                if abs(val) > 1e-6 and abs(val) < 1e10:
                    spin.setValue(val)
                else:
                    spin.setValue(val)
            spin.valueChanged.connect(
                lambda v, g=name, u=unit_name, tb=to_base: self._on_value_changed(g, u, tb, v)
            )
            grid.addWidget(spin, idx, 1)
            self._input_spins[name][unit_name] = spin

        glayout.addLayout(grid)
        return frame

    def _on_value_changed(self, group: str, unit: str, to_base: Callable, value: float):
        if getattr(self, '_updating_units', False):
            return
        self._updating_units = True
        try:
            base_val = to_base(value)
            gdata = self._unit_groups[group]
            for u2, (from_b, to_b) in [(u, fb, tb) for (u, fb, tb) in gdata['units'] if u != unit]:
                try:
                    new_val = from_b(base_val)
                    if new_val != self._input_spins[group][u2].value():
                        self._input_spins[group][u2].setValue(new_val)
                except Exception:
                    pass
        finally:
            self._updating_units = False

    def _build_reference_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel("<h4>光伏测试常用单位换算速查表</h4>")
        layout.addWidget(info)

        sections = [
            ("辐照度 / 光强 (Irradiance)", [
                ['1000 W/m²', '=', '100 mW/cm²', '=', '1 kW/m²', '=', '1 Sun (AM1.5G)'],
                ['1 W/m²', '=', '0.1 mW/cm²', '=', '0.0001 W/cm²', '=', '0.001 Suns'],
                ['1 mW/cm²', '=', '10 W/m²', '=', '10000 mW/m²', '=', '0.01 Suns'],
            ]),
            ("电流 / 电流密度", [
                ['1 A', '=', '1000 mA', '=', '10⁶ μA', '=', '10⁹ nA'],
                ['1 mA/cm²', '=', '10 A/m²', '=', '10⁻³ A/cm²', '=', '0.01 mA/mm²'],
                ['1 A/cm²', '=', '10⁴ A/m²', '=', '10³ mA/cm²', '=', '10 mA/mm²'],
            ]),
            ("能量 / 功率 / 效率", [
                ['1 W', '=', '1000 mW', '=', '1 J/s', '=', '1 V·A'],
                ['1 eV', '=', '1.602×10⁻¹⁹ J', '— 光子能量', 'Eg(eV)=1.24/λ(μm)'],
                ['效率 η(%)', '=', Pmax/(Pin) × 100%', 'Pin = 光强 × 面积', '—'],
            ]),
            ("长度 / 面积", [
                ['1 nm', '=', '10 Å', '=', '0.001 μm', '=', '10⁻⁷ cm'],
                ['1 μm', '=', '1000 nm', '=', '10⁻⁴ cm', '=', '10⁻³ mm'],
                ['1 cm²', '=', '100 mm²', '=', '10⁻⁴ m²', '=', '0.155 inch²'],
            ]),
            ("电阻 / 电阻率", [
                ['1 Ω', '=', '1 V/A', '—', '—'],
                ['1 Ω·cm²', '串联电阻Rs', '归一化到面积', '便于对比不同器件'],
                ['Rsh (kΩ·cm²)', '并联电阻', '越大漏电流越小', '—'],
            ]),
            ("温度", [
                ['25 °C', '=', '298.15 K', '=', '77 °F', '(标准测试温度 STC)'],
                ['0 K', '=', '-273.15 °C', '=', '-459.67 °F', '(绝对零度)'],
                ['ΔT °C', '=', 'ΔT K', '≠ ΔT °F', '(变化量)'],
            ]),
        ]

        for sec_name, rows in sections:
            sec_label = QLabel(f"<b style='color:#2c5282;'>{sec_name}</b>")
            layout.addWidget(sec_label)

            table = QTableWidget(len(rows), 7)
            table.horizontalHeader().setVisible(False)
            table.verticalHeader().setVisible(False)
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    item = QTableWidgetItem(str(val))
                    if val in ('=', '—'):
                        item.setForeground(QColor('#666'))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    else:
                        f = item.font()
                        f.setPointSize(10)
                        item.setFont(f)
                    table.setItem(r, c, item)
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)
            table.setMaximumHeight(len(rows) * 28 + 20)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            layout.addWidget(table)

        layout.addStretch()
        return w

    def _build_constants_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel("<h4>光伏材料计算常用物理常数 & 公式</h4>")
        layout.addWidget(info)

        consts = [
            ['元电荷 q', '1.602176634 × 10⁻¹⁹', 'C', '基本电荷单位'],
            ['玻尔兹曼常数 k', '1.380649 × 10⁻²³', 'J/K', '统计物理常数'],
            ['kT/q (300K)', '~0.02585', 'V', '热电压 VT，二极管理想因子'],
            ['普朗克常数 h', '6.62607015 × 10⁻³⁴', 'J·s', '量子力学基本常数'],
            ['真空光速 c', '2.99792458 × 10⁸', 'm/s', '电磁波传播速度'],
            ['hc', '1239.8', 'eV·nm', '光子能量: Eg(eV)=1240/λ(nm)'],
            ['电子伏特 eV', '1.602176634 × 10⁻¹⁹', 'J', '能量换算单位'],
            ['AM1.5G 光强', '100.045', 'mW/cm²', '标准太阳光谱辐照度'],
            ['斯特藩常数 σ', '5.6703744 × 10⁻⁸', 'W/(m²·K⁴)', '黑体辐射'],
        ]

        table = QTableWidget(len(consts), 4)
        table.setHorizontalHeaderLabels(['物理量', '数值', '单位', '说明'])
        for r, row in enumerate(consts):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if c in (0, 1):
                    f = item.font()
                    f.setBold(c == 1)
                    item.setFont(f)
                table.setItem(r, c, item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)

        form_label = QLabel("<h4 style='margin-top:16px;'>核心公式</h4>")
        layout.addWidget(form_label)

        formulas = [
            ("填充因子 FF", "FF = (Vmpp × Impp) / (Voc × Isc)"),
            ("转换效率 η", "η = Pmpp / Pin = (Vmpp × Impp) / (光强 × 面积)"),
            ("短路电流密度 Jsc", "Jsc = Isc / Area"),
            ("二极管理想因子 n", "J = J0(exp(qV/nkT) - 1) - Jsc"),
            ("热电压 VT", "VT = kT/q ≈ 0.02585 V @ 300K"),
            ("Rs (串联电阻)", "Rs ≈ -dV/dI (在 Voc 附近) × Area"),
            ("Rsh (并联电阻)", "Rsh ≈ -dV/dI (在 Isc 附近) × Area"),
            ("SQ极限效率", "η_SQ 单结 ≈ 33.16% (AM1.5G)"),
        ]

        for title, expr in formulas:
            line = QLabel(f"  <b style='color:#2c5282;'>{title}:</b> &nbsp;&nbsp;<code>{expr}</code>")
            line.setStyleSheet("padding:6px;background:#f7fafc;border-bottom:1px solid #edf2f7;")
            line.setWordWrap(True)
            layout.addWidget(line)

        layout.addStretch()
        return w
