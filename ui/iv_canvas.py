import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.widgets import RectangleSelector
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import matplotlib

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QCheckBox, QGroupBox, QSpinBox, QDoubleSpinBox, QPushButton)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

matplotlib.use('QtAgg')

from core.iv_parser import IVDataSet
from core.pv_calculator import PVParams


@dataclass
class CurveStyle:
    color: str
    linewidth: float = 1.8
    linestyle: str = '-'
    marker: str = ''
    markersize: int = 4
    label: str = ''
    visible: bool = True
    show_mpp: bool = True


DEFAULT_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
]


class IVCanvas(QWidget):
    """多曲线IV绘图画布组件"""

    x_range_changed = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curves: Dict[str, Tuple[IVDataSet, PVParams, CurveStyle]] = {}
        self._selected_curve_id: Optional[str] = None
        self._current_color_index = 0
        self._x_auto = True
        self._y_auto = True
        self._current_mode = 'IV'

        self._figure = Figure(figsize=(8, 6), tight_layout=True)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvas(self._figure)
        self._toolbar = NavigationToolbar(self._canvas, self)

        self._init_ui()
        self._setup_mouse_interaction()
        self._apply_style()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(8, 4, 8, 0)

        mode_group = QGroupBox("绘图模式")
        mode_layout = QHBoxLayout(mode_group)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(['I-V 曲线', 'J-V 曲线', 'P-V 曲线', 'Jsc归一化'])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self._mode_combo)
        toolbar_layout.addWidget(mode_group)

        axis_group = QGroupBox("坐标控制")
        axis_layout = QHBoxLayout(axis_group)

        self._auto_check = QCheckBox("自动坐标")
        self._auto_check.setChecked(True)
        self._auto_check.toggled.connect(self._on_auto_axis_toggled)
        axis_layout.addWidget(self._auto_check)

        axis_layout.addWidget(QLabel("Xmin:"))
        self._xmin_spin = QDoubleSpinBox()
        self._xmin_spin.setRange(-100, 1000)
        self._xmin_spin.setDecimals(3)
        self._xmin_spin.setValue(-0.5)
        self._xmin_spin.setSingleStep(0.1)
        self._xmin_spin.setMaximumWidth(80)
        self._xmin_spin.valueChanged.connect(self._on_axis_range_changed)
        axis_layout.addWidget(self._xmin_spin)

        axis_layout.addWidget(QLabel("Xmax:"))
        self._xmax_spin = QDoubleSpinBox()
        self._xmax_spin.setRange(-100, 1000)
        self._xmax_spin.setDecimals(3)
        self._xmax_spin.setValue(1.2)
        self._xmax_spin.setSingleStep(0.1)
        self._xmax_spin.setMaximumWidth(80)
        self._xmax_spin.valueChanged.connect(self._on_axis_range_changed)
        axis_layout.addWidget(self._xmax_spin)

        axis_layout.addWidget(QLabel("Ymin:"))
        self._ymin_spin = QDoubleSpinBox()
        self._ymin_spin.setRange(-10000, 10000)
        self._ymin_spin.setDecimals(3)
        self._ymin_spin.setValue(0)
        self._ymin_spin.setSingleStep(0.5)
        self._ymin_spin.setMaximumWidth(80)
        self._ymin_spin.valueChanged.connect(self._on_axis_range_changed)
        axis_layout.addWidget(self._ymin_spin)

        axis_layout.addWidget(QLabel("Ymax:"))
        self._ymax_spin = QDoubleSpinBox()
        self._ymax_spin.setRange(-10000, 10000)
        self._ymax_spin.setDecimals(3)
        self._ymax_spin.setValue(30)
        self._ymax_spin.setSingleStep(0.5)
        self._ymax_spin.setMaximumWidth(80)
        self._ymax_spin.valueChanged.connect(self._on_axis_range_changed)
        axis_layout.addWidget(self._ymax_spin)

        toolbar_layout.addWidget(axis_group)

        show_group = QGroupBox("显示项")
        show_layout = QHBoxLayout(show_group)
        self._grid_check = QCheckBox("网格")
        self._grid_check.setChecked(True)
        self._grid_check.toggled.connect(self._on_grid_toggled)
        show_layout.addWidget(self._grid_check)

        self._mpp_check = QCheckBox("标注MPP")
        self._mpp_check.setChecked(True)
        self._mpp_check.toggled.connect(self._on_mpp_toggled)
        show_layout.addWidget(self._mpp_check)

        self._zero_check = QCheckBox("坐标轴零点")
        self._zero_check.setChecked(True)
        self._zero_check.toggled.connect(self.redraw)
        show_layout.addWidget(self._zero_check)

        toolbar_layout.addWidget(show_group)

        toolbar_layout.addStretch()

        btn_reset = QPushButton("重置视图")
        btn_reset.clicked.connect(self.reset_view)
        toolbar_layout.addWidget(btn_reset)

        btn_clear = QPushButton("清除全部")
        btn_clear.clicked.connect(self.clear_all)
        toolbar_layout.addWidget(btn_clear)

        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self._toolbar)
        main_layout.addWidget(self._canvas, stretch=1)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #666; padding: 2px 8px;")
        main_layout.addWidget(self._status_label)

    def _apply_style(self):
        self._axes.set_facecolor('#fafafa')
        for spine in self._axes.spines.values():
            spine.set_color('#888')
        self._axes.tick_params(colors='#333', labelsize=10)
        self._axes.xaxis.label.set_color('#333')
        self._axes.yaxis.label.set_color('#333')

    def _setup_mouse_interaction(self):
        self._canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self._selector = RectangleSelector(
            self._axes, self._on_select,
            useblit=True,
            button=[1],
            minspanx=5, minspany=5,
            spancoords='pixels',
            interactive=True
        )

    def add_curve(self, dataset: IVDataSet, params: PVParams,
                  style: Optional[CurveStyle] = None) -> str:
        """添加一条IV曲线"""
        curve_id = dataset.file_name
        if curve_id in self._curves:
            self.remove_curve(curve_id)

        if style is None:
            color = DEFAULT_COLORS[self._current_color_index % len(DEFAULT_COLORS)]
            self._current_color_index += 1
            style = CurveStyle(
                color=color,
                label=dataset.device_id or dataset.file_name
            )
        self._curves[curve_id] = (dataset, params, style)
        self.redraw()
        self._update_status(f"已加载曲线: {style.label}")
        return curve_id

    def remove_curve(self, curve_id: str):
        if curve_id in self._curves:
            del self._curves[curve_id]
            self.redraw()

    def update_curve_style(self, curve_id: str, style: CurveStyle):
        if curve_id in self._curves:
            ds, params, _ = self._curves[curve_id]
            self._curves[curve_id] = (ds, params, style)
            self.redraw()

    def set_curve_visibility(self, curve_id: str, visible: bool):
        if curve_id in self._curves:
            ds, params, style = self._curves[curve_id]
            style.visible = visible
            self._curves[curve_id] = (ds, params, style)
            self.redraw()

    def clear_all(self):
        self._curves.clear()
        self._current_color_index = 0
        self.redraw()
        self._update_status("已清除全部曲线")

    def reset_view(self):
        self._auto_check.setChecked(True)
        self._x_auto = True
        self._y_auto = True
        self.redraw()

    def set_axis_range(self, xmin=None, xmax=None, ymin=None, ymax=None):
        if xmin is not None:
            self._xmin_spin.setValue(xmin)
        if xmax is not None:
            self._xmax_spin.setValue(xmax)
        if ymin is not None:
            self._ymin_spin.setValue(ymin)
        if ymax is not None:
            self._ymax_spin.setValue(ymax)

    def redraw(self):
        self._axes.clear()
        self._apply_style()

        self._draw_reference_lines()
        drawn_count = 0

        for curve_id, (dataset, params, style) in self._curves.items():
            if not style.visible or len(dataset.voltages) == 0:
                continue
            self._plot_single_curve(dataset, params, style)
            drawn_count += 1

        self._update_axes_labels()

        if self._grid_check.isChecked():
            self._axes.grid(True, alpha=0.3, linestyle='--')

        if drawn_count > 0:
            self._axes.legend(loc='best', fontsize=9, framealpha=0.9)

        self._apply_axis_limits()
        self._canvas.draw_idle()

    def _get_mode_coords(self, voltages, currents, area, params=None, norm_factor=None):
        """统一的模式坐标转换函数。对曲线和MPP点使用完全相同的映射逻辑，
        返回 (x_coords, y_coords, used_norm_factor)。当 norm_factor=None 时
        自动计算并返回，用于后续对同一曲线的 MPP 标注进行一致的归一化。"""
        if self._current_mode == 'IV':
            x = voltages
            y = currents * 1000
            return x, y, None
        elif self._current_mode == 'JV':
            x = voltages
            y = (currents / area) * 1000
            return x, y, None
        elif self._current_mode == 'PV':
            x = voltages
            y = np.abs(voltages * currents) * 1000
            return x, y, None
        else:
            x = voltages
            if norm_factor is None:
                if len(currents) > 0 and area > 0:
                    norm_factor = float(np.max(np.abs(currents / area)) * 1000)
                else:
                    norm_factor = 1.0
            if norm_factor > 0:
                y = ((currents / area) * 1000) / norm_factor
            else:
                y = currents
            return x, y, norm_factor

    def _plot_single_curve(self, dataset: IVDataSet, params: PVParams, style: CurveStyle):
        voltages = np.array(dataset.voltages, dtype=np.float64)
        currents = np.array(dataset.currents, dtype=np.float64)
        area = params.cell_area if params.cell_area > 0 else 1.0

        x_vals, y_vals, used_norm = self._get_mode_coords(voltages, currents, area)

        self._axes.plot(
            x_vals, y_vals,
            color=style.color,
            linewidth=style.linewidth,
            linestyle=style.linestyle,
            marker=style.marker if style.marker else None,
            markersize=style.markersize,
            label=style.label,
            alpha=0.95,
            zorder=3
        )

        if self._mpp_check.isChecked() and style.show_mpp and params.vmpp > 0 and params.impp > 0:
            if self._current_mode == 'IV':
                mpp_x = params.vmpp
                mpp_y = params.impp * 1000
            elif self._current_mode == 'JV':
                mpp_x = params.vmpp
                mpp_y = params.jmpp * 1000
            elif self._current_mode == 'PV':
                mpp_x = params.vmpp
                mpp_y = params.pmpp * 1000
            else:
                mpp_x = params.vmpp
                if used_norm is not None and used_norm > 0:
                    mpp_y = (params.jmpp * 1000) / used_norm
                else:
                    jsc_norm = params.jsc * 1000 if params.jsc > 0 else 1.0
                    mpp_y = (params.jmpp * 1000) / jsc_norm

            if np.isfinite(mpp_x) and np.isfinite(mpp_y):
                self._axes.scatter(
                    [mpp_x], [mpp_y],
                    color=style.color, s=80, marker='*',
                    edgecolors='black', linewidths=0.8, zorder=5
                )
                self._axes.annotate(
                    f' MPP\n({mpp_x:.3f}V, {mpp_y:.2f})',
                    xy=(float(mpp_x), float(mpp_y)),
                    xycoords='data',
                    fontsize=7.5,
                    textcoords='offset points',
                    xytext=(8, 5),
                    bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=style.color, alpha=0.85),
                    zorder=6
                )

    def _draw_reference_lines(self):
        if self._zero_check.isChecked():
            self._axes.axhline(
                y=0, color='#666', linewidth=0.8,
                linestyle='-', alpha=0.6, zorder=1
            )
            self._axes.axvline(
                x=0, color='#666', linewidth=0.8,
                linestyle='-', alpha=0.6, zorder=1
            )

    def _update_axes_labels(self):
        mode_labels = {
            'IV': ('Voltage V (V)', 'Current I (mA)'),
            'JV': ('Voltage V (V)', 'Current Density J (mA/cm²)'),
            'PV': ('Voltage V (V)', 'Power P (mW)'),
            '归一化': ('Voltage V (V)', 'Normalized Jsc'),
        }
        mapping = {
            0: 'IV', 1: 'JV', 2: 'PV', 3: '归一化'
        }
        mode_key = mapping.get(self._mode_combo.currentIndex(), 'IV')
        x_label, y_label = mode_labels.get(mode_key, mode_labels['IV'])
        self._axes.set_xlabel(x_label, fontsize=11, fontweight='medium')
        self._axes.set_ylabel(y_label, fontsize=11, fontweight='medium')

    def _apply_axis_limits(self):
        all_ylim = [float('inf'), -float('inf')]
        all_xlim = [float('inf'), -float('inf')]

        for _, (dataset, params, style) in self._curves.items():
            if not style.visible or len(dataset.voltages) == 0:
                continue
            vs = np.array(dataset.voltages, dtype=np.float64)
            cs = np.array(dataset.currents, dtype=np.float64)
            area = params.cell_area if params.cell_area > 0 else 1.0

            _, ys, _ = self._get_mode_coords(vs, cs, area)

            all_xlim[0] = min(all_xlim[0], float(np.min(vs)))
            all_xlim[1] = max(all_xlim[1], float(np.max(vs)))
            all_ylim[0] = min(all_ylim[0], float(np.min(ys)))
            all_ylim[1] = max(all_ylim[1], float(np.max(ys)))

        if self._x_auto:
            if all_xlim[0] < all_xlim[1]:
                margin = (all_xlim[1] - all_xlim[0]) * 0.05
                self._axes.set_xlim(all_xlim[0] - margin, all_xlim[1] + margin)
        else:
            self._axes.set_xlim(self._xmin_spin.value(), self._xmax_spin.value())

        if self._y_auto:
            if all_ylim[0] < all_ylim[1]:
                margin = (all_ylim[1] - all_ylim[0]) * 0.08
                self._axes.set_ylim(all_ylim[0] - margin, all_ylim[1] + margin)
        else:
            self._axes.set_ylim(self._ymin_spin.value(), self._ymax_spin.value())

        xmin, xmax = self._axes.get_xlim()
        ymin, ymax = self._axes.get_ylim()
        self.x_range_changed.emit(xmin, xmax, ymin, ymax)

    def _on_mode_changed(self, idx):
        mapping = {0: 'IV', 1: 'JV', 2: 'PV', 3: '归一化'}
        self._current_mode = mapping.get(idx, 'IV')
        self.redraw()

    def _on_auto_axis_toggled(self, checked):
        self._x_auto = checked
        self._y_auto = checked
        for w in [self._xmin_spin, self._xmax_spin, self._ymin_spin, self._ymax_spin]:
            w.setEnabled(not checked)
        self.redraw()

    def _on_axis_range_changed(self, _val=None):
        if not self._auto_check.isChecked():
            self._x_auto = False
            self._y_auto = False
            self.redraw()

    def _on_grid_toggled(self, checked):
        self.redraw()

    def _on_mpp_toggled(self, checked):
        self.redraw()

    def _on_mouse_move(self, event):
        if event.inaxes and event.xdata is not None and event.ydata is not None:
            mapping = {
                0: 'V={:.4f}V  I={:.4f}mA',
                1: 'V={:.4f}V  J={:.4f}mA/cm²',
                2: 'V={:.4f}V  P={:.4f}mW',
                3: 'V={:.4f}V  Jnorm={:.4f}',
            }
            idx = self._mode_combo.currentIndex()
            fmt = mapping.get(idx, mapping[0])
            self._status_label.setText(fmt.format(event.xdata, event.ydata))
        else:
            curve_count = sum(1 for _, (_, _, s) in self._curves.items() if s.visible)
            self._status_label.setText(f"就绪 - 显示 {curve_count} 条曲线")

    def _on_select(self, eclick, erelease):
        pass

    def _update_status(self, message: str):
        self._status_label.setText(message)

    def get_curve_ids(self) -> List[str]:
        return list(self._curves.keys())

    def get_curve_info(self, curve_id: str):
        return self._curves.get(curve_id)

    def curve_count(self) -> int:
        return len(self._curves)

    def save_figure(self, file_path: str, dpi: int = 300):
        self._figure.savefig(file_path, dpi=dpi, bbox_inches='tight', facecolor='white')
