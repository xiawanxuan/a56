"""批量文件夹处理对话框 - 递归遍历测试文件 → 批量计算参数 → 批量生成对比图表+Excel报告

完全复用底层工具：
  - core.iv_parser.IVParser    (解析3类设备)
  - core.pv_calculator.PVCalculator  (参数计算)
  - ui.iv_canvas.IVCanvas    (多曲线叠加绘图)
  - exporters.batch_exporter.BatchExporter  (Excel/CSV等导出)
"""

import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from enum import Enum

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QCheckBox, QDoubleSpinBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QComboBox, QGroupBox, QPlainTextEdit, QSplitter, QWidget,
    QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDate
from PyQt6.QtGui import QColor, QFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.iv_parser import IVParser, IVDataSet, DeviceType
from core.pv_calculator import PVCalculator, PVParams
from exporters.batch_exporter import BatchExporter, ExportFormat


SUPPORTED_EXT = {'.txt', '.csv', '.dat', '.iv'}


class BatchStatus(Enum):
    PENDING = "待处理"
    RUNNING = "处理中"
    OK = "成功"
    WARN = "告警"
    FAIL = "失败"


@dataclass
class BatchRow:
    """单个文件的批处理结果行"""
    file_path: str
    file_name: str = ""
    device_type: DeviceType = DeviceType.UNKNOWN
    device_id: str = ""
    batch_id: str = ""
    status: BatchStatus = BatchStatus.PENDING
    params: Optional[PVParams] = None
    dataset: Optional[IVDataSet] = None
    message: str = ""
    duration_ms: int = 0


class BatchWorker(QObject):
    """后台批处理工作线程 - 避免UI卡顿"""

    progress = pyqtSignal(int, int, str)     # (已完成, 总数, 当前文件名)
    row_updated = pyqtSignal(int)           # 行号
    finished = pyqtSignal(int, int, float)  # (成功数, 失败数, 耗时秒)
    log = pyqtSignal(str)

    def __init__(self, rows: List[BatchRow], parser: IVParser, calculator: PVCalculator,
                 area: float, intensity: float, temperature: float):
        super().__init__()
        self._rows = rows
        self._parser = parser
        self._calculator = calculator
        self._area = area
        self._intensity = intensity
        self._temperature = temperature
        self._stop = False

    def stop(self):
        self._stop = True

    @property
    def rows(self) -> List[BatchRow]:
        return self._rows

    def run(self):
        t0 = time.time()
        ok = fail = 0
        total = len(self._rows)
        for idx, row in enumerate(self._rows):
            if self._stop:
                self.log.emit("⏹ 用户中止批处理")
                break
            self.progress.emit(idx, total, row.file_name)
            row.status = BatchStatus.RUNNING
            self.row_updated.emit(idx)
            t_start = time.perf_counter()
            try:
                ds = self._parser.parse_file(row.file_path)
                row.dataset = ds
                row.file_name = ds.file_name
                row.device_type = ds.device_type
                row.device_id = ds.device_id
                row.batch_id = ds.batch_id
                if not ds.is_valid:
                    row.status = BatchStatus.WARN
                    row.message = "数据不足或格式无法识别"
                    fail += 1
                else:
                    use_area = self._area if self._area > 0 else ds.cell_area
                    use_int = self._intensity if self._intensity > 0 else ds.light_intensity
                    params = self._calculator.calculate(ds, use_area, use_int, self._temperature)
                    row.params = params
                    if params.calc_success:
                        row.status = BatchStatus.OK
                        row.message = (f"Voc={params.voc:.3f}V  "
                                       f"FF={params.ff*100:.1f}%  "
                                       f"Eff={params.efficiency*100:.2f}%")
                        ok += 1
                    else:
                        row.status = BatchStatus.WARN
                        row.message = params.message or "参数计算失败"
                        fail += 1
            except Exception as e:
                row.status = BatchStatus.FAIL
                row.message = f"{type(e).__name__}: {str(e)}"
                fail += 1
                self.log.emit(f"❌ {row.file_name}: {row.message}")
            finally:
                row.duration_ms = int((time.perf_counter() - t_start) * 1000)
                self.row_updated.emit(idx)

        self.progress.emit(total, total, "完成")
        self.finished.emit(ok, fail, time.time() - t0)


class BatchFolderDialog(QDialog):
    """批量文件夹处理主对话框"""

    def __init__(self, storage=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 批量文件夹处理 - IV曲线参数计算与报告导出")
        self.setMinimumSize(1180, 760)

        from core.data_storage import DeviceStorage
        self._storage = storage or DeviceStorage()
        self._parser = IVParser()
        self._calculator = PVCalculator()
        self._exporter = BatchExporter()

        self._rows: List[BatchRow] = []
        self._worker: Optional[BatchWorker] = None
        self._thread: Optional[QThread] = None
        self._last_output_dir: Optional[str] = None

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 顶部：输入配置
        top_group = QGroupBox("① 输入 & 参数")
        top_layout = QFormLayout(top_group)
        top_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        row_dir = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择包含 IV 测试文件的文件夹（将递归扫描子目录）")
        row_dir.addWidget(self._dir_edit, stretch=1)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse_dir)
        row_dir.addWidget(btn_browse)
        btn_scan = QPushButton("🔍 扫描文件")
        btn_scan.clicked.connect(self._on_scan)
        row_dir.addWidget(btn_scan)
        top_layout.addRow("根目录:", row_dir)

        opt_row = QHBoxLayout()
        self._recursive_check = QCheckBox("递归扫描子目录")
        self._recursive_check.setChecked(True)
        opt_row.addWidget(self._recursive_check)
        self._include_hidden_check = QCheckBox("包含隐藏文件")
        self._include_hidden_check.setChecked(False)
        opt_row.addWidget(self._include_hidden_check)
        self._match_edit = QLineEdit()
        self._match_edit.setPlaceholderText("文件名匹配 (留空=全部, 如 *Sample*,*.txt)")
        self._match_edit.setMaximumWidth(260)
        opt_row.addWidget(QLabel("过滤:"))
        opt_row.addWidget(self._match_edit, stretch=1)
        top_layout.addRow("扫描选项:", opt_row)

        param_row = QHBoxLayout()
        self._area_spin = QDoubleSpinBox()
        self._area_spin.setRange(0, 10000)
        self._area_spin.setDecimals(4)
        self._area_spin.setSingleStep(0.01)
        self._area_spin.setValue(1.0)
        self._area_spin.setSuffix(" cm²")
        self._area_spin.setPrefix("面积: ")
        self._area_spin.setMinimumWidth(140)
        self._area_spin.setToolTip("设置为 0 时将使用文件中内嵌的面积值")
        param_row.addWidget(self._area_spin)

        self._int_spin = QDoubleSpinBox()
        self._int_spin.setRange(0, 10000); self._int_spin.setDecimals(2)
        self._int_spin.setSingleStep(1); self._int_spin.setValue(100.0)
        self._int_spin.setSuffix(" mW/cm²")
        self._int_spin.setPrefix("光强: ")
        self._int_spin.setMinimumWidth(160)
        param_row.addWidget(self._int_spin)

        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(-100, 500); self._temp_spin.setDecimals(1)
        self._temp_spin.setSingleStep(0.1); self._temp_spin.setValue(25.0)
        self._temp_spin.setSuffix(" °C")
        self._temp_spin.setPrefix("温度: ")
        self._temp_spin.setMinimumWidth(130)
        param_row.addWidget(self._temp_spin)

        param_row.addSpacing(20)
        param_row.addWidget(QLabel("导出格式:"))
        self._fmt_combo = QComboBox()
        for fmt in (ExportFormat.EXCEL, ExportFormat.CSV, ExportFormat.JSON, ExportFormat.HTML):
            self._fmt_combo.addItem(fmt.value, fmt)
        self._fmt_combo.setCurrentIndex(0)
        param_row.addWidget(self._fmt_combo)

        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 1200); self._dpi_spin.setValue(300)
        self._dpi_spin.setSuffix(" dpi")
        self._dpi_spin.setPrefix("图: ")
        param_row.addWidget(self._dpi_spin)

        param_row.addStretch(1)
        top_layout.addRow("计算参数:", param_row)
        root.addWidget(top_group)

        # 中部：进度 + 表格 + 预览图
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 表格+控制
        table_group = QGroupBox("② 文件列表 & 处理结果")
        tgl = QVBoxLayout(table_group)
        tgl.setContentsMargins(8, 16, 8, 8)

        ctrl_row = QHBoxLayout()
        self._stat_label = QLabel("0 个文件  |  就绪")
        ctrl_row.addWidget(self._stat_label)
        ctrl_row.addStretch(1)

        self._btn_run = QPushButton("▶ 开始批量计算")
        self._btn_run.setMinimumWidth(150)
        self._btn_run.clicked.connect(self._on_start)
        ctrl_row.addWidget(self._btn_run)

        self._btn_stop = QPushButton("⏹ 停止")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setMinimumWidth(100)
        self._btn_stop.clicked.connect(self._on_stop)
        ctrl_row.addWidget(self._btn_stop)

        self._btn_export = QPushButton("📤 导出报告 + 对比图")
        self._btn_export.setEnabled(False)
        self._btn_export.setMinimumWidth(200)
        self._btn_export.clicked.connect(self._on_export)
        ctrl_row.addWidget(self._btn_export)

        tgl.addLayout(ctrl_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("待处理")
        tgl.addWidget(self._progress)

        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            ['状态', '文件名', '器件编号', '批次', '设备类型', 'Voc(V)', 'FF(%)', 'Eff(%)', '耗时(ms)', '说明'])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        tgl.addWidget(self._table, stretch=1)

        splitter.addWidget(table_group)

        # 图表预览
        plot_group = QGroupBox("③ 多曲线对比预览图 (处理完成后自动生成)")
        pgl = QVBoxLayout(plot_group)
        pgl.setContentsMargins(8, 16, 8, 8)

        self._fig = Figure(figsize=(10, 4.8), tight_layout=True)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setMinimumHeight(320)
        pgl.addWidget(self._canvas, stretch=1)

        hint = QLabel("💡 处理完成后将叠加显示所有成功曲线，与 Excel 报告中的图表一致")
        hint.setStyleSheet("color:#666;padding:4px;")
        pgl.addWidget(hint)
        splitter.addWidget(plot_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([420, 320])
        root.addWidget(splitter, stretch=1)

        # 日志
        log_group = QGroupBox("运行日志")
        lgl = QVBoxLayout(log_group)
        lgl.setContentsMargins(8, 16, 8, 8)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 12px;")
        lgl.addWidget(self._log)
        log_group.setMaximumHeight(140)
        root.addWidget(log_group)

        # 底部按钮
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self._on_close)
        bottom_row.addWidget(btn_close)
        root.addLayout(bottom_row)

    # ---------- 扫描 ----------

    def _on_browse_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 IV 测试数据根目录")
        if folder:
            self._dir_edit.setText(folder)
            self._on_scan()

    def _on_scan(self):
        folder = self._dir_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "提示", "请先选择有效的文件夹"); return

        t0 = time.time()
        recursive = self._recursive_check.isChecked()
        include_hidden = self._include_hidden_check.isChecked()
        patterns = self._parse_patterns(self._match_edit.text().strip())

        files = self._collect_files(folder, recursive, include_hidden, patterns)

        self._rows = [BatchRow(file_path=fp, file_name=os.path.basename(fp)) for fp in sorted(files)]
        self._refresh_table(full=True)
        self._progress.setRange(0, max(1, len(self._rows)))
        self._progress.setValue(0)
        self._progress.setFormat(f"已扫描 {len(self._rows)} 个文件")
        self._stat_label.setText(f"共 {len(self._rows)} 个文件  |  待处理")
        self._btn_export.setEnabled(False)
        self._append_log(f"🔍 扫描目录: {folder}  (递归={recursive})")
        self._append_log(f"   匹配到 {len(self._rows)} 个IV文件 ({time.time()-t0:.2f}s)")

        self._ax.clear()
        self._ax.set_title("等待处理...")
        self._canvas.draw_idle()

    def _parse_patterns(self, raw: str) -> List[str]:
        if not raw: return []
        parts = [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]
        return parts

    def _matches_patterns(self, filename: str, patterns: List[str]) -> bool:
        if not patterns: return True
        import fnmatch
        return any(fnmatch.fnmatch(filename.lower(), p.lower()) for p in patterns)

    def _collect_files(self, root: str, recursive: bool, include_hidden: bool, patterns: List[str]) -> List[str]:
        results = []
        if recursive:
            walker = os.walk(root)
        else:
            walker = [(root, [], [f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))])]
        for dirpath, _dirs, filenames in walker:
            if not include_hidden:
                filenames = [f for f in filenames if not f.startswith('.')]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in SUPPORTED_EXT and self._matches_patterns(fn, patterns):
                    results.append(os.path.join(dirpath, fn))
        return results

    # ---------- 表格 ----------

    def _refresh_table(self, full: bool = False, row_idx: Optional[int] = None):
        if full:
            self._table.setRowCount(len(self._rows))
            for i in range(len(self._rows)):
                self._paint_row(i)
        elif row_idx is not None and 0 <= row_idx < len(self._rows):
            self._paint_row(row_idx)

    def _paint_row(self, idx: int):
        row = self._rows[idx]
        status_text = row.status.value
        status_item = QTableWidgetItem(status_text)
        color_map = {
            BatchStatus.PENDING: QColor('#6a737d'),
            BatchStatus.RUNNING: QColor('#005cc5'),
            BatchStatus.OK: QColor('#22863a'),
            BatchStatus.WARN: QColor('#e36209'),
            BatchStatus.FAIL: QColor('#d73a49'),
        }
        status_item.setForeground(color_map.get(row.status, QColor('#333')))
        f = status_item.font(); f.setBold(True); status_item.setFont(f)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(idx, 0, status_item)

        def _cell(val, align_center=True, color=None):
            it = QTableWidgetItem("" if val is None else str(val))
            if align_center: it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if color is not None:
                if isinstance(color, str):
                    it.setForeground(QColor(color))
                else:
                    it.setForeground(color)
            return it

        p = row.params
        self._table.setItem(idx, 1, _cell(row.file_name, False))
        self._table.setItem(idx, 2, _cell(row.device_id or '-', False))
        self._table.setItem(idx, 3, _cell(row.batch_id or '-', False))
        dt_val = row.device_type.value if hasattr(row.device_type, 'value') else str(row.device_type)
        self._table.setItem(idx, 4, _cell(dt_val.split(' ')[0] if ' ' in dt_val else dt_val))

        if p and p.calc_success:
            self._table.setItem(idx, 5, _cell(f"{p.voc:.4f}", True))
            self._table.setItem(idx, 6, _cell(f"{p.ff*100:.2f}", True))
            eff_item = _cell(f"{p.efficiency*100:.3f}")
            ef = eff_item.font(); ef.setBold(True); eff_item.setFont(ef)
            eff_item.setForeground(QColor('#22863a'))
            self._table.setItem(idx, 7, eff_item)
        else:
            for c in (5, 6, 7):
                self._table.setItem(idx, c, _cell('-', True, '#aaa'))

        self._table.setItem(idx, 8, _cell(str(row.duration_ms) if row.duration_ms > 0 else '-'))
        self._table.setItem(idx, 9, _cell(row.message or '', False))

    # ---------- 批处理 ----------

    def _on_start(self):
        if not self._rows:
            QMessageBox.information(self, "提示", "请先扫描文件夹"); return
        if self._thread is not None and self._thread.isRunning():
            return
        self._prepare_run()

        area = self._area_spin.value() if self._area_spin.value() > 0 else 0.0
        intensity = self._int_spin.value() if self._int_spin.value() > 0 else 0.0
        temperature = self._temp_spin.value()

        self._worker = BatchWorker(self._rows, self._parser, self._calculator, area, intensity, temperature)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self._on_progress)
        self._worker.row_updated.connect(lambda i: self._refresh_table(row_idx=i))
        self._worker.finished.connect(self._on_finished)
        self._worker.log.connect(self._append_log)
        self._thread.started.connect(self._worker.run)

        self._append_log(f"▶ 开始批处理 {len(self._rows)} 个文件  (面积={area}, 光强={intensity}, T={temperature}°C)")
        self._thread.start()

    def _prepare_run(self):
        for r in self._rows:
            r.status = BatchStatus.PENDING
            r.params = None
            r.dataset = None
            r.message = ""
            r.duration_ms = 0
        self._refresh_table(full=True)
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_export.setEnabled(False)
        self._progress.setValue(0)
        self._progress.setFormat("处理中... %p%")

        self._ax.clear()
        self._ax.set_title(f"处理中... (0/{len(self._rows)})")
        self._canvas.draw_idle()

    def _on_progress(self, done: int, total: int, current: str):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
            self._stat_label.setText(f"进度 {done}/{total}  |  当前: {current}")

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._append_log("⏹ 已请求停止，等待当前文件完成...")

    def _on_finished(self, ok: int, fail: int, elapsed: float):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._worker = None
        self._thread = None

        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_export.setEnabled(ok > 0)

        self._stat_label.setText(f"完成: ✅ {ok} 成功 / ⚠ {fail} 问题  |  耗时 {elapsed:.2f}s")
        self._append_log(f"✅ 批处理结束: {ok} 成功, {fail} 问题/失败  ({elapsed:.2f}s)")

        if ok > 0:
            self._build_comparison_chart()

    # ---------- 对比图 ----------

    def _build_comparison_chart(self):
        """生成多曲线叠加对比图 (与Excel导出中的图表一致)"""
        self._ax.clear()

        from ui.iv_canvas import DEFAULT_COLORS

        ok_rows = [r for r in self._rows if r.status == BatchStatus.OK and r.params and r.dataset]
        ok_rows.sort(key=lambda r: (r.batch_id, r.device_id or r.file_name))

        for i, row in enumerate(ok_rows):
            ds = row.dataset
            p = row.params
            color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]

            vs = np.array(ds.voltages, dtype=np.float64)
            cs = np.array(ds.currents, dtype=np.float64)
            ys = cs * 1000  # mA

            label = (row.device_id or row.file_name)
            if row.batch_id:
                label = f"{row.batch_id}/{label}"
            if p and p.calc_success:
                label += f"  (η={p.efficiency*100:.2f}%)"

            self._ax.plot(vs, ys, color=color, linewidth=1.7, label=label, alpha=0.92, zorder=3)

            if p and p.calc_success and p.vmpp > 0 and p.impp > 0:
                self._ax.scatter([p.vmpp], [p.impp * 1000], s=90, marker='*',
                                 color=color, edgecolors='black', linewidths=0.6, zorder=5)

        self._ax.axhline(y=0, color='#888', linewidth=0.7, linestyle='-', alpha=0.6, zorder=1)
        self._ax.axvline(x=0, color='#888', linewidth=0.7, linestyle='-', alpha=0.6, zorder=1)
        self._ax.grid(True, alpha=0.25, linestyle='--')
        self._ax.set_xlabel('Voltage V (V)', fontsize=11)
        self._ax.set_ylabel('Current I (mA)', fontsize=11)
        self._ax.set_title(f'I-V 多器件对比  ({len(ok_rows)} 条成功曲线)', fontsize=12, fontweight='bold')
        if len(ok_rows) <= 12:
            self._ax.legend(loc='best', fontsize=8.5, framealpha=0.92)
        elif len(ok_rows) <= 30:
            self._ax.legend(loc='best', fontsize=7, framealpha=0.9, ncol=2)
        else:
            self._ax.legend(loc='best', fontsize=6, framealpha=0.85, ncol=3)

        self._fig.tight_layout()
        self._canvas.draw_idle()

    # ---------- 导出 ----------

    def _on_export(self):
        ok_rows = [r for r in self._rows if r.status == BatchStatus.OK and r.params and r.dataset]
        if not ok_rows:
            QMessageBox.information(self, "提示", "没有成功处理的文件可导出"); return

        fmt = self._fmt_combo.currentData()
        default_name = f"batch_iv_report_{QDate.currentDate().toString('yyyyMMdd')}"
        folder = QFileDialog.getExistingDirectory(self, "选择报告输出目录")
        if not folder:
            return
        os.makedirs(folder, exist_ok=True)

        self._append_log(f"📤 导出 {len(ok_rows)} 条记录 → {fmt.value}")

        # 1) 导出数据表格
        base_name = os.path.join(folder, default_name)
        results = [(r.dataset, r.params) for r in ok_rows]

        class _FigProxy:
            """包装 figure 以便 BatchExporter.export 保存图表"""
            def __init__(self, fig, dpi):
                self._fig = fig
                self._dpi = dpi
            def save_figure(self, path, dpi=None):
                self._fig.savefig(path, dpi=dpi or self._dpi, bbox_inches='tight', facecolor='white')

        try:
            dpi = self._dpi_spin.value()
            ok = self._exporter.export(results, base_name, fmt,
                                       include_raw_data=True,
                                       include_curves_figure=_FigProxy(self._fig, dpi),
                                       figure_dpi=dpi)
            if not ok:
                raise RuntimeError("导出返回 False")

            # 2) 额外单独输出一份对比图 PNG
            extra_png = os.path.join(folder, f"{default_name}_comparison.png")
            self._fig.savefig(extra_png, dpi=dpi, bbox_inches='tight', facecolor='white')

            # 3) 输出统计汇总
            self._write_summary_csv(ok_rows, os.path.join(folder, f"{default_name}_statistics.csv"))

            self._last_output_dir = folder
            self._append_log(f"✅ 导出成功 → {folder}")
            QMessageBox.information(self, "导出完成",
                                    f"成功导出 {len(ok_rows)} 条记录到目录：\n{folder}\n\n"
                                    f"已生成：\n"
                                    f"  • 数据表 ({fmt.value})\n"
                                    f"  • IV 对比图 ({dpi}dpi PNG)\n"
                                    f"  • 统计汇总 CSV")
        except Exception as e:
            self._append_log(f"❌ 导出失败: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "导出失败", str(e))

    def _write_summary_csv(self, rows: List[BatchRow], path: str):
        params_list = [r.params for r in rows if r.params]
        if not params_list:
            return
        keys = list(params_list[0].to_dict().keys())
        summary = {'参数': keys}
        arrays = {k: np.array([p.to_dict().get(k, np.nan) for p in params_list if isinstance(p.to_dict().get(k, 0), (int, float))])
                  for k in keys}
        summary['Count'] = [int(np.sum(~np.isnan(arrays[k]))) if k in arrays else '' for k in keys]
        summary['Mean'] = [float(np.nanmean(arrays[k])) if k in arrays and len(arrays[k]) > 0 else '' for k in keys]
        summary['Std'] = [float(np.nanstd(arrays[k])) if k in arrays and len(arrays[k]) > 0 else '' for k in keys]
        summary['Min'] = [float(np.nanmin(arrays[k])) if k in arrays and len(arrays[k]) > 0 else '' for k in keys]
        summary['Max'] = [float(np.nanmax(arrays[k])) if k in arrays and len(arrays[k]) > 0 else '' for k in keys]
        summary['Median'] = [float(np.nanmedian(arrays[k])) if k in arrays and len(arrays[k]) > 0 else '' for k in keys]
        df = pd.DataFrame(summary)
        df.to_csv(path, index=False, encoding='utf-8-sig')

    # ---------- 日志 ----------

    def _append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {msg}")

    # ---------- 关闭 ----------

    def _on_close(self):
        if self._thread is not None and self._thread.isRunning():
            if QMessageBox.question(self, "确认",
                "批处理仍在进行，确定关闭？\n(当前文件处理完后将停止)") != QMessageBox.StandardButton.Yes:
                return
            if self._worker: self._worker.stop()
            self._thread.quit()
            self._thread.wait(3000)
        self.accept()

    def closeEvent(self, event):
        try:
            if self._thread is not None and self._thread.isRunning():
                if self._worker: self._worker.stop()
                self._thread.quit()
                self._thread.wait(3000)
        except Exception:
            pass
        super().closeEvent(event)
