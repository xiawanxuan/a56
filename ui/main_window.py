import os
import sys
import time
from typing import Optional, List, Dict
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QToolBar,
    QStatusBar, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QDialog, QInputDialog, QDateEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtGui import QAction, QKeySequence, QColor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.iv_parser import IVParser, IVDataSet, DeviceType
from core.pv_calculator import PVCalculator, PVParams
from core.data_storage import DeviceStorage, DeviceRecord
from ui.iv_canvas import IVCanvas
from ui.calibration_dialog import CalibrationDialog
from ui.unit_converter_dialog import UnitConverterDialog
from exporters.batch_exporter import BatchExporter, ExportFormat


@dataclass
class LoadedSample:
    dataset: IVDataSet
    params: PVParams
    curve_id: str
    visible: bool = True


class MainWindow(QMainWindow):
    """主窗口 - 菜单栏布局管理 + 主界面集成"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("光伏材料实验室 - IV曲线分析系统 v1.0")
        self.setMinimumSize(1360, 860)

        self._parser = IVParser()
        self._calculator = PVCalculator()
        self._storage = DeviceStorage()
        self._exporter = BatchExporter()
        self._samples: Dict[str, LoadedSample] = {}
        self._sample_order: List[str] = []
        self._calibration_cache: Optional[Dict] = None

        self._build_ui()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_statusbar()
        self._apply_theme()
        self._load_calibration_cache()
        self._load_last_devices()
        self._set_status("系统就绪")

    # ---------- UI ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(2, 0, 2, 0)
        root.setSpacing(2)
        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.addWidget(self._build_left_panel())
        main_split.addWidget(self._build_center_panel())
        main_split.addWidget(self._build_right_panel())
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 4)
        main_split.setStretchFactor(2, 2)
        main_split.setSizes([260, 780, 380])
        root.addWidget(main_split, stretch=1)

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(220)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        file_group = QGroupBox("实验文件列表")
        fg_layout = QVBoxLayout(file_group)
        fg_layout.setContentsMargins(6, 12, 6, 6)
        fg_layout.setSpacing(4)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索器件编号/文件名...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        fg_layout.addWidget(self._search_edit)
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.setAlternatingRowColors(True)
        self._file_list.itemDoubleClicked.connect(self._on_file_doubleclick)
        self._file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
        self._file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(self._on_file_list_contextmenu)
        fg_layout.addWidget(self._file_list, stretch=1)
        btn_row1 = QHBoxLayout()
        btn_add = QPushButton("添加文件")
        btn_add.clicked.connect(self._on_add_files)
        btn_row1.addWidget(btn_add)
        btn_folder = QPushButton("文件夹")
        btn_folder.clicked.connect(self._on_add_folder)
        btn_row1.addWidget(btn_folder)
        fg_layout.addLayout(btn_row1)
        btn_row2 = QHBoxLayout()
        btn_remove = QPushButton("删除")
        btn_remove.clicked.connect(self._on_remove_selected)
        btn_row2.addWidget(btn_remove)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._on_clear_all)
        btn_row2.addWidget(btn_clear)
        fg_layout.addLayout(btn_row2)
        self._file_count_label = QLabel("共 0 条曲线，0 条显示中")
        self._file_count_label.setStyleSheet("color:#555;font-size:11px;")
        fg_layout.addWidget(self._file_count_label)
        layout.addWidget(file_group, stretch=1)

        device_group = QGroupBox("器件参数配置 (对已选器件生效)")
        dg_layout = QFormLayout(device_group)
        dg_layout.setContentsMargins(6, 12, 6, 6)
        dg_layout.setSpacing(4)
        dg_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._area_spin = QDoubleSpinBox()
        self._area_spin.setRange(0.0001, 1000)
        self._area_spin.setDecimals(4)
        self._area_spin.setSingleStep(0.01)
        self._area_spin.setValue(1.0)
        self._area_spin.setSuffix(" cm2")
        dg_layout.addRow("光电池面积:", self._area_spin)
        self._intensity_spin = QDoubleSpinBox()
        self._intensity_spin.setRange(0.01, 5000)
        self._intensity_spin.setDecimals(2)
        self._intensity_spin.setSingleStep(1)
        self._intensity_spin.setValue(100)
        self._intensity_spin.setSuffix(" mW/cm2")
        dg_layout.addRow("辐照强度:", self._intensity_spin)
        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(-50, 300)
        self._temp_spin.setDecimals(1)
        self._temp_spin.setSingleStep(0.1)
        self._temp_spin.setValue(25)
        self._temp_spin.setSuffix(" C")
        dg_layout.addRow("测试温度:", self._temp_spin)
        btn_apply_params = QPushButton("应用参数到已选")
        btn_apply_params.clicked.connect(self._on_apply_params_to_selection)
        dg_layout.addRow(btn_apply_params)
        btn_save_to_db = QPushButton("保存器件信息到本地")
        btn_save_to_db.clicked.connect(self._on_save_device_to_db)
        dg_layout.addRow(btn_save_to_db)
        layout.addWidget(device_group)
        return w

    def _build_center_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        self._canvas = IVCanvas()
        layout.addWidget(self._canvas, stretch=1)
        return w

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(300)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        param_group = QGroupBox("光伏参数结果")
        pg_layout = QVBoxLayout(param_group)
        pg_layout.setContentsMargins(6, 12, 6, 6)
        self._selected_info = QLabel("请在左侧选择曲线查看详细参数")
        self._selected_info.setWordWrap(True)
        pg_layout.addWidget(self._selected_info)
        self._param_table = QTableWidget(0, 2)
        self._param_table.setHorizontalHeaderLabels(['参数', '数值'])
        self._param_table.horizontalHeader().setStretchLastSection(True)
        self._param_table.verticalHeader().setVisible(False)
        self._param_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._param_table.setAlternatingRowColors(True)
        self._param_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        pg_layout.addWidget(self._param_table, stretch=1)
        layout.addWidget(param_group, stretch=1)

        compare_group = QGroupBox("已加载曲线对比")
        cg_layout = QVBoxLayout(compare_group)
        cg_layout.setContentsMargins(6, 12, 6, 6)
        self._compare_table = QTableWidget(0, 5)
        self._compare_table.setHorizontalHeaderLabels(['显示', 'ID', 'Voc', 'FF', 'Eff'])
        self._compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._compare_table.horizontalHeader().setStretchLastSection(True)
        self._compare_table.verticalHeader().setVisible(False)
        self._compare_table.setAlternatingRowColors(True)
        self._compare_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._compare_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._compare_table.cellChanged.connect(self._on_compare_table_changed)
        cg_layout.addWidget(self._compare_table, stretch=1)
        layout.addWidget(compare_group, stretch=1)

        btn_row = QHBoxLayout()
        btn_recalc = QPushButton("重新计算")
        btn_recalc.clicked.connect(self._on_recalculate_all)
        btn_row.addWidget(btn_recalc)
        btn_export = QPushButton("导出数据")
        btn_export.clicked.connect(self._on_export_batch)
        btn_row.addWidget(btn_export)
        btn_savefig = QPushButton("保存图像")
        btn_savefig.clicked.connect(self._on_save_figure)
        btn_row.addWidget(btn_savefig)
        layout.addLayout(btn_row)
        return w

    # ---------- 菜单栏/工具栏/状态栏 ----------

    def _build_menu_bar(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")
        act_open = QAction("打开IV数据文件...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._on_add_files)
        file_menu.addAction(act_open)
        act_folder = QAction("从文件夹导入...", self)
        act_folder.setShortcut("Ctrl+Shift+O")
        act_folder.triggered.connect(self._on_add_folder)
        file_menu.addAction(act_folder)
        file_menu.addSeparator()
        act_savefig = QAction("保存IV曲线图...", self)
        act_savefig.setShortcut("Ctrl+S")
        act_savefig.triggered.connect(self._on_save_figure)
        file_menu.addAction(act_savefig)
        act_export = QAction("批量导出分析数据...", self)
        act_export.setShortcut("Ctrl+E")
        act_export.triggered.connect(self._on_export_batch)
        file_menu.addAction(act_export)
        file_menu.addSeparator()
        act_db_import = QAction("导入器件数据库(JSON)...", self)
        act_db_import.triggered.connect(self._on_db_import)
        file_menu.addAction(act_db_import)
        act_db_export = QAction("导出器件数据库(JSON)...", self)
        act_db_export.triggered.connect(self._on_db_export)
        file_menu.addAction(act_db_export)
        file_menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        edit_menu = mb.addMenu("编辑(&E)")
        act_clear = QAction("清空全部曲线", self)
        act_clear.triggered.connect(self._on_clear_all)
        edit_menu.addAction(act_clear)
        act_recalc = QAction("重新计算所有参数", self)
        act_recalc.setShortcut("F5")
        act_recalc.triggered.connect(self._on_recalculate_all)
        edit_menu.addAction(act_recalc)
        edit_menu.addSeparator()
        act_remove_sel = QAction("移除已选曲线", self)
        act_remove_sel.setShortcut(QKeySequence.StandardKey.Delete)
        act_remove_sel.triggered.connect(self._on_remove_selected)
        edit_menu.addAction(act_remove_sel)

        view_menu = mb.addMenu("视图(&V)")
        act_fit_view = QAction("自适应坐标视图", self)
        act_fit_view.triggered.connect(lambda: self._canvas.reset_view())
        view_menu.addAction(act_fit_view)
        act_grid = QAction("显示/隐藏网格", self)
        act_grid.triggered.connect(lambda: self._canvas._grid_check.setChecked(not self._canvas._grid_check.isChecked()))
        view_menu.addAction(act_grid)
        act_mpp = QAction("显示/隐藏MPP标注", self)
        act_mpp.triggered.connect(lambda: self._canvas._mpp_check.setChecked(not self._canvas._mpp_check.isChecked()))
        view_menu.addAction(act_mpp)

        data_menu = mb.addMenu("数据(&D)")
        act_dev_list = QAction("器件参数管理", self)
        act_dev_list.triggered.connect(self._on_manage_devices)
        data_menu.addAction(act_dev_list)
        data_menu.addSeparator()
        act_gen_sample = QAction("生成模拟IV曲线(演示)", self)
        act_gen_sample.triggered.connect(self._on_generate_sample)
        data_menu.addAction(act_gen_sample)

        cal_menu = mb.addMenu("校准(&C)")
        act_cal = QAction("设备校准参数配置...", self)
        act_cal.setShortcut("Ctrl+Shift+C")
        act_cal.triggered.connect(self._on_open_calibration)
        cal_menu.addAction(act_cal)
        cal_menu.addSeparator()
        act_unit = QAction("单位转换工具...", self)
        act_unit.setShortcut("Ctrl+U")
        act_unit.triggered.connect(self._on_open_unit_converter)
        cal_menu.addAction(act_unit)

        help_menu = mb.addMenu("帮助(&H)")
        act_about = QAction("关于系统", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)
        act_help = QAction("使用说明", self)
        act_help.triggered.connect(self._on_show_help)
        help_menu.addAction(act_help)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)
        acts = [
            ("打开", self._on_add_files, "Ctrl+O"),
            ("文件夹", self._on_add_folder, None),
            (None, None, None),
            ("重算", self._on_recalculate_all, "F5"),
            ("导出", self._on_export_batch, "Ctrl+E"),
            ("存图", self._on_save_figure, "Ctrl+S"),
            (None, None, None),
            ("校准", self._on_open_calibration, "Ctrl+Shift+C"),
            ("单位", self._on_open_unit_converter, "Ctrl+U"),
            (None, None, None),
            ("器件库", self._on_manage_devices, None),
            ("演示曲线", self._on_generate_sample, None),
        ]
        for text, func, shortcut in acts:
            if text is None:
                tb.addSeparator(); continue
            a = QAction(text, self)
            if shortcut: a.setShortcut(shortcut)
            a.triggered.connect(func)
            tb.addAction(a)

    def _build_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_main = QLabel("就绪")
        self._statusbar.addWidget(self._status_main, stretch=1)
        self._status_cal = QLabel("校准系数: 未加载")
        self._status_cal.setStyleSheet("color:#666;padding:0 8px;")
        self._statusbar.addPermanentWidget(self._status_cal)
        self._status_db = QLabel(f"数据库: {self._storage.get_count()} 条器件记录")
        self._status_db.setStyleSheet("color:#666;padding:0 8px;border-left:1px solid #ddd;")
        self._statusbar.addPermanentWidget(self._status_db)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(180)
        self._progress.setVisible(False)
        self._statusbar.addPermanentWidget(self._progress)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f6f8fa; }
            QGroupBox { background: #ffffff; border: 1px solid #e1e4e8; border-radius: 6px;
                margin-top: 14px; padding: 8px; font-weight: 600; color: #24292f; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; font-size: 12px; }
            QPushButton { background: #ffffff; border: 1px solid #d0d7de; border-radius: 4px;
                padding: 5px 10px; color: #24292f; }
            QPushButton:hover { background: #f3f4f6; border-color: #0969da; }
            QPushButton:pressed { background: #ddedff; }
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QTextEdit {
                background: #ffffff; border: 1px solid #d0d7de; border-radius: 4px;
                padding: 3px 6px; selection-background-color: #0969da; }
            QListWidget, QTableWidget { background: #ffffff; border: 1px solid #d0d7de;
                border-radius: 4px; alternate-background-color: #f6f8fa; }
            QListWidget::item:selected, QTableWidget::item:selected { background: #ddedff; color: #0969da; }
            QMenuBar { background: #24292f; color: #ffffff; padding: 2px 4px; }
            QMenuBar::item { padding: 5px 12px; }
            QMenuBar::item:selected { background: #373e47; border-radius: 4px; }
            QMenu { background: #ffffff; border: 1px solid #d0d7de; padding: 4px; }
            QMenu::item { padding: 6px 24px; border-radius: 3px; }
            QMenu::item:selected { background: #0969da; color: white; }
            QToolBar { background: #ffffff; border: none; border-bottom: 1px solid #e1e4e8; padding: 4px 6px; }
            QToolBar::separator { width: 1px; background: #e1e4e8; margin: 4px; }
            QStatusBar { background: #ffffff; border-top: 1px solid #e1e4e8; }
            QHeaderView::section { background: #f6f8fa; padding: 6px; border: none;
                border-right: 1px solid #e1e4e8; border-bottom: 1px solid #e1e4e8; font-weight: 600; }
        """)

    # ---------- 事件 ----------

    def _set_status(self, message: str):
        self._status_main.setText(message)

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择IV数据文件", "",
            "IV数据文件 (*.txt *.csv *.dat *.iv);;文本文件 (*.txt);;CSV文件 (*.csv);;所有文件 (*.*)")
        if paths: self._load_files(paths)

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含IV数据的文件夹")
        if not folder: return
        paths = []
        for root, _, files in os.walk(folder):
            for f in files:
                if os.path.splitext(f)[1].lower() in ('.txt', '.csv', '.dat', '.iv'):
                    paths.append(os.path.join(root, f))
        if not paths:
            QMessageBox.information(self, "提示", "未找到支持的IV数据文件"); return
        if QMessageBox.question(self, "确认导入",
            f"发现 {len(paths)} 个文件，是否全部导入？") != QMessageBox.StandardButton.Yes: return
        self._load_files(paths)

    def _load_files(self, paths: List[str]):
        t0 = time.time()
        self._progress.setVisible(True)
        self._progress.setRange(0, len(paths))
        loaded = 0; errors = []
        for idx, path in enumerate(paths):
            self._progress.setValue(idx)
            try:
                ds = self._parser.parse_file(path)
                if not ds.is_valid:
                    errors.append(f"{os.path.basename(path)}: 数据无效"); continue
                area, intensity = ds.cell_area, ds.light_intensity
                existing = self._storage.get_by_device_id(ds.device_id)
                if existing:
                    area = existing.cell_area_cm2
                    intensity = existing.light_intensity_mwcm2
                    ds.batch_id = existing.batch_id
                params = self._calculator.calculate(ds, area, intensity, self._temp_spin.value())
                key = path.lower()
                self._samples[key] = LoadedSample(dataset=ds, params=params,
                    curve_id=ds.file_name or f"curve_{idx}")
                if key not in self._sample_order: self._sample_order.append(key)
                loaded += 1
                self._canvas.add_curve(ds, params)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")
        self._progress.setValue(len(paths))
        self._progress.setVisible(False)
        self._refresh_file_list(); self._refresh_compare_table()
        msg = f"成功加载 {loaded}/{len(paths)} 个文件 ({time.time()-t0:.2f}s)"
        if errors:
            msg += f"; {len(errors)} 个失败"
            QMessageBox.warning(self, "部分加载失败", msg + "\n\n" + "\n".join(errors[:8]))
        self._set_status(msg)

    def _refresh_file_list(self, filter_text: str = ""):
        self._file_list.clear()
        visible_count = 0
        for key in self._sample_order:
            sample = self._samples.get(key)
            if not sample: continue
            ds, ps = sample.dataset, sample.params
            info = f"{ds.device_id or ds.file_name}  |  {ps.efficiency*100:.2f}%  |  FF {ps.ff*100:.1f}%"
            if filter_text and filter_text.lower() not in info.lower(): continue
            item = QListWidgetItem(info)
            item.setData(Qt.ItemDataRole.UserRole, key)
            if sample.visible:
                visible_count += 1
                f = item.font(); f.setBold(ps.calc_success); item.setFont(f)
                if not ps.calc_success: item.setForeground(QColor('#c0392b'))
            else: item.setForeground(QColor('#999'))
            self._file_list.addItem(item)
        self._file_count_label.setText(f"共 {len(self._sample_order)} 条曲线，{visible_count} 条显示中")

    def _on_search_changed(self, text: str): self._refresh_file_list(text)

    def _on_file_doubleclick(self, item: QListWidgetItem):
        key = item.data(Qt.ItemDataRole.UserRole)
        sample = self._samples.get(key)
        if not sample: return
        sample.visible = not sample.visible
        self._canvas.set_curve_visibility(sample.curve_id, sample.visible)
        self._refresh_file_list(self._search_edit.text()); self._refresh_compare_table()

    def _on_file_selection_changed(self):
        items = self._file_list.selectedItems()
        if not items: return
        sample = self._samples.get(items[-1].data(Qt.ItemDataRole.UserRole))
        if sample: self._show_single_params(sample)

    def _on_file_list_contextmenu(self, pos):
        item = self._file_list.itemAt(pos)
        if not item: return
        key = item.data(Qt.ItemDataRole.UserRole)
        sample = self._samples.get(key)
        if not sample: return
        menu = QMenu(self)
        a_toggle = menu.addAction("切换显示/隐藏")
        a_rename = menu.addAction("修改器件编号...")
        a_recalc = menu.addAction("重新计算参数")
        a_copy = menu.addAction("复制参数到剪贴板")
        a_remove = menu.addAction("移除")
        action = menu.exec(self._file_list.mapToGlobal(pos))
        if action == a_toggle:
            sample.visible = not sample.visible
            self._canvas.set_curve_visibility(sample.curve_id, sample.visible)
        elif action == a_rename:
            new_id, ok = QInputDialog.getText(self, "修改", "新编号:", text=sample.dataset.device_id)
            if ok and new_id: sample.dataset.device_id = new_id.strip(); self._canvas.redraw()
        elif action == a_recalc:
            sample.params = self._calculator.calculate(sample.dataset,
                self._area_spin.value(), self._intensity_spin.value(), self._temp_spin.value())
            self._canvas.add_curve(sample.dataset, sample.params)
        elif action == a_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText("\n".join(f"{k}: {v}" for k,v in sample.params.to_dict().items()))
        elif action == a_remove: self._remove_sample(key)
        self._refresh_file_list(self._search_edit.text()); self._refresh_compare_table()

    def _on_remove_selected(self):
        for item in self._file_list.selectedItems():
            self._remove_sample(item.data(Qt.ItemDataRole.UserRole))
        self._refresh_file_list(self._search_edit.text()); self._refresh_compare_table()
        self._param_table.setRowCount(0); self._selected_info.setText("请在左侧选择曲线查看详细参数")

    def _on_clear_all(self):
        if not self._samples: return
        if QMessageBox.question(self, "确认", "清空所有曲线？") != QMessageBox.StandardButton.Yes: return
        self._samples.clear(); self._sample_order.clear(); self._canvas.clear_all()
        self._refresh_file_list(); self._refresh_compare_table()
        self._param_table.setRowCount(0); self._set_status("已清空")

    def _remove_sample(self, key: str):
        sample = self._samples.pop(key, None)
        if sample:
            self._canvas.remove_curve(sample.curve_id)
            if key in self._sample_order: self._sample_order.remove(key)

    def _show_single_params(self, sample: LoadedSample):
        ds, p = sample.dataset, sample.params
        dt_type = ds.device_type.value if hasattr(ds.device_type, 'value') else str(ds.device_type)
        self._selected_info.setText(
            f"<b style='color:#0969da;'>{ds.device_id or ds.file_name}</b><br>"
            f"<span style='color:#666;font-size:11px;'>文件: {ds.file_name} | 设备: {dt_type} | "
            f"点数: {ds.point_count} | 批次: {ds.batch_id or '-'}</span>")
        data = p.to_dict()
        self._param_table.setRowCount(len(data))
        for r, (k, v) in enumerate(data.items()):
            ki = QTableWidgetItem(str(k)); vi = QTableWidgetItem(str(v))
            if p.calc_success and any(t in k.lower() for t in ('efficiency', 'voc', 'ff', 'jsc')):
                f = vi.font(); f.setBold(True); vi.setFont(f); vi.setForeground(QColor('#0969da'))
            self._param_table.setItem(r, 0, ki); self._param_table.setItem(r, 1, vi)
        self._param_table.resizeColumnsToContents()

    def _refresh_compare_table(self):
        self._compare_table.blockSignals(True)
        self._compare_table.setRowCount(len(self._sample_order))
        for r, key in enumerate(self._sample_order):
            sample = self._samples.get(key)
            if not sample: continue
            ds, p = sample.dataset, sample.params
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb.setCheckState(Qt.CheckState.Checked if sample.visible else Qt.CheckState.Unchecked)
            cb.setData(Qt.ItemDataRole.UserRole, key)
            cb.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._compare_table.setItem(r, 0, cb)
            self._compare_table.setItem(r, 1, QTableWidgetItem(ds.device_id or ds.file_name))
            self._compare_table.setItem(r, 2, QTableWidgetItem(f"{p.voc:.4f}"))
            self._compare_table.setItem(r, 3, QTableWidgetItem(f"{p.ff*100:.2f}%"))
            ei = QTableWidgetItem(f"{p.efficiency*100:.3f}%")
            if p.calc_success and p.efficiency > 0:
                f = ei.font(); f.setBold(True); ei.setFont(f); ei.setForeground(QColor('#1a7f37'))
            self._compare_table.setItem(r, 4, ei)
        self._compare_table.blockSignals(False)

    def _on_compare_table_changed(self, row: int, col: int):
        if col != 0: return
        item = self._compare_table.item(row, 0)
        if not item: return
        sample = self._samples.get(item.data(Qt.ItemDataRole.UserRole))
        if not sample: return
        sample.visible = (item.checkState() == Qt.CheckState.Checked)
        self._canvas.set_curve_visibility(sample.curve_id, sample.visible)
        self._refresh_file_list(self._search_edit.text())

    def _on_apply_params_to_selection(self):
        items = self._file_list.selectedItems()
        if not items:
            QMessageBox.information(self, "提示", "请先选择曲线"); return
        area, intensity, temp = self._area_spin.value(), self._intensity_spin.value(), self._temp_spin.value()
        count = 0
        for item in items:
            sample = self._samples.get(item.data(Qt.ItemDataRole.UserRole))
            if not sample: continue
            sample.dataset.cell_area = area; sample.dataset.light_intensity = intensity
            sample.params = self._calculator.calculate(sample.dataset, area, intensity, temp)
            self._canvas.add_curve(sample.dataset, sample.params); count += 1
        self._refresh_file_list(self._search_edit.text()); self._refresh_compare_table()
        self._set_status(f"已对 {count} 条曲线应用新参数")

    def _on_save_device_to_db(self):
        items = self._file_list.selectedItems()
        if not items: QMessageBox.information(self, "提示", "请先选择曲线"); return
        saved = 0; skipped = []
        for item in items:
            sample = self._samples.get(item.data(Qt.ItemDataRole.UserRole))
            if not sample: continue
            ds, p = sample.dataset, sample.params
            rec = DeviceRecord(device_id=ds.device_id or ds.file_name, batch_id=ds.batch_id,
                cell_area_cm2=self._area_spin.value(),
                light_intensity_mwcm2=self._intensity_spin.value(),
                temperature_c=self._temp_spin.value(),
                notes=f"Voc={p.voc:.4f}V FF={p.ff*100:.1f}% Eff={p.efficiency*100:.2f}%")
            try:
                if self._storage.get_by_device_id(rec.device_id):
                    if QMessageBox.question(self, "已存在",
                        f"[{rec.device_id}]已存在，是否更新？") == QMessageBox.StandardButton.Yes:
                        self._storage.update_device(rec); saved += 1
                    else: skipped.append(rec.device_id)
                else: self._storage.add_device(rec); saved += 1
            except Exception as e: skipped.append(f"{rec.device_id}: {e}")
        self._status_db.setText(f"数据库: {self._storage.get_count()} 条器件记录")
        msg = f"保存 {saved} 条"
        if skipped: msg += f"; 跳过 {len(skipped)} 条\n\n" + "\n".join(skipped[:8])
        QMessageBox.information(self, "完成", msg)

    def _on_recalculate_all(self):
        area, intensity, temp = self._area_spin.value(), self._intensity_spin.value(), self._temp_spin.value()
        for sample in self._samples.values():
            sample.params = self._calculator.calculate(sample.dataset, area, intensity, temp)
            self._canvas.add_curve(sample.dataset, sample.params)
        self._refresh_file_list(self._search_edit.text()); self._refresh_compare_table()
        self._set_status(f"已重算 {len(self._samples)} 条曲线")

    def _on_export_batch(self):
        if not self._samples: QMessageBox.information(self, "提示", "无数据可导出"); return
        dialog = ExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        fmt = dialog.get_format()
        default = f"pv_iv_analysis_{QDate.currentDate().toString('yyyyMMdd')}"
        if fmt == ExportFormat.CSV:
            path = QFileDialog.getExistingDirectory(self, "选择CSV导出目录")
            if not path: return
            path = os.path.join(path, default)
        else:
            filters = {ExportFormat.EXCEL: "Excel (*.xlsx)", ExportFormat.JSON: "JSON (*.json)",
                        ExportFormat.TXT: "TXT (*.txt)", ExportFormat.HTML: "HTML (*.html)"}
            cap = {"Excel (*.xlsx)": "选择Excel文件", "JSON (*.json)": "选择JSON文件",
                   "TXT (*.txt)": "选择TXT文件", "HTML (*.html)": "选择HTML文件"}
            fstr = filters.get(fmt, "所有文件 (*.*)")
            path, _ = QFileDialog.getSaveFileName(self, cap.get(fstr, "导出"), default, fstr)
        if not path: return
        results = [(s.dataset, s.params) for s in self._samples.values()]
        self._progress.setVisible(True); self._progress.setRange(0, 0)
        try:
            ok = self._exporter.export(results, path, fmt,
                include_raw_data=dialog.include_raw(),
                include_curves_figure=self._canvas, figure_dpi=dialog.dpi_value())
            self._progress.setVisible(False)
            if ok: QMessageBox.information(self, "成功", f"已导出至:\n{path}"); self._set_status(f"导出: {path}")
            else: QMessageBox.critical(self, "失败", "导出出错")
        except Exception as e:
            self._progress.setVisible(False); QMessageBox.critical(self, "错误", str(e))

    def _on_save_figure(self):
        default = f"iv_curves_{QDate.currentDate().toString('yyyyMMdd')}.png"
        path, _ = QFileDialog.getSaveFileName(self, "保存图像", default,
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;JPEG (*.jpg)")
        if not path: return
        self._canvas.save_figure(path, 300)
        self._set_status(f"图像已保存: {path}")
        QMessageBox.information(self, "成功", f"图像已保存至:\n{path}")

    def _on_open_calibration(self):
        dlg = CalibrationDialog(self._storage, self)
        dlg.calibration_updated.connect(self._on_calibration_updated)
        dlg.exec()

    def _on_open_unit_converter(self): UnitConverterDialog(self).exec()

    def _on_calibration_updated(self, data: dict):
        self._calibration_cache = data
        params = data.get('params', {})
        self._area_spin.setValue(float(params.get('std_area', data.get('area_cal', 1.0))))
        self._intensity_spin.setValue(float(params.get('std_irradiance', 100.0)))
        self._temp_spin.setValue(float(params.get('temperature_c', 25.0)))
        name, cal = data.get('device_name', '未知'), data.get('intensity_cal', 1.0)
        self._status_cal.setText(f"校准: {name} 光强系数={cal:.4f}")
        self._set_status(f"已应用校准: {name}")

    def _load_calibration_cache(self):
        try:
            latest = self._storage.get_latest_calibration()
            if latest:
                self._calibration_cache = latest
                params = latest.get('params') if isinstance(latest.get('params'), dict) else {}
                self._area_spin.setValue(float(params.get('std_area', 1.0)))
                self._intensity_spin.setValue(float(params.get('std_irradiance', 100.0)))
                self._temp_spin.setValue(float(params.get('temperature_c', 25.0)))
                name, cal = latest.get('device_name', '未知'), latest.get('intensity_cal', 1.0)
                self._status_cal.setText(f"校准: {name} 光强系数={cal:.4f}")
        except Exception: pass

    def _on_manage_devices(self):
        DeviceManagerDialog(self._storage, self).exec()
        self._status_db.setText(f"数据库: {self._storage.get_count()} 条器件记录")

    def _on_db_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入", "", "JSON (*.json)")
        if not path: return
        try:
            n = self._storage.import_from_json(path)
            self._status_db.setText(f"数据库: {self._storage.get_count()} 条")
            QMessageBox.information(self, "完成", f"导入 {n} 条记录")
        except Exception as e: QMessageBox.critical(self, "失败", str(e))

    def _on_db_export(self):
        default = f"device_db_{QDate.currentDate().toString('yyyyMMdd')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "导出", default, "JSON (*.json)")
        if not path: return
        try:
            self._storage.export_to_json(path)
            QMessageBox.information(self, "完成", f"已导出至:\n{path}")
        except Exception as e: QMessageBox.critical(self, "失败", str(e))

    def _load_last_devices(self):
        try:
            last = self._storage.get_setting('last_open_files')
            if isinstance(last, list):
                valid = [p for p in last if os.path.exists(p)]
                if valid and QMessageBox.question(self, "恢复",
                    f"上次打开的 {len(valid)} 个文件可访问，是否重新加载？") == QMessageBox.StandardButton.Yes:
                    self._load_files(valid)
        except Exception: pass

    def _on_generate_sample(self):
        count, ok = QInputDialog.getInt(self, "演示曲线", "生成多少条？", 4, 1, 20)
        if not ok: return
        paths = self._create_sample_data(count)
        self._load_files(paths)

    def _create_sample_data(self, count: int) -> List[str]:
        import numpy as np
        from scipy.optimize import brentq
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'samples')
        os.makedirs(out_dir, exist_ok=True)
        paths = []
        materials = ['Si', 'CIGS', 'CdTe', 'Perovskite', 'Cz-Si']
        for i in range(count):
            name = f"Sample_{i+1:03d}_{materials[i%5]}_Batch{2024000+i}.txt"
            path = os.path.abspath(os.path.join(out_dir, name))
            V = np.linspace(-0.2, 0.75, 201)
            voc_base = [0.62, 0.68, 0.85, 1.10, 0.65][i%5]
            jsc_base = [38, 34, 26, 23, 40][i%5]
            voc = voc_base * (0.92 + 0.12*np.random.rand())
            jsc = jsc_base * 1e-3 * (0.90 + 0.18*np.random.rand())
            n = 1.2 + 0.8*np.random.rand(); kTq = 0.02585
            I0 = jsc * np.exp(-voc/(n*kTq))
            Rs = (2 + 6*np.random.rand()) * 1e-3
            Rsh = 1000 + 9000*np.random.rand()
            I = np.zeros_like(V)
            for idx, v in enumerate(V):
                def residual(c):
                    return c - jsc + I0*(np.exp((v+c*Rs)/(n*kTq))-1) + (v+c*Rs)/Rsh
                try: I[idx] = brentq(residual, -0.1, 0.02)
                except Exception: I[idx] = -jsc + I0*(np.exp(v/(n*kTq))-1) + v/Rsh
            I = -I + 1e-6*np.random.randn(len(V))
            with open(path, 'w', encoding='utf-8') as f:
                f.write("# Keithley 4200 IV Sweep - Simulated\n")
                f.write(f"# DeviceID: Sample_{i+1:03d}_{materials[i%5]}\n")
                f.write(f"# BatchID: Batch{2024000+i}\n")
                f.write(f"# TestDate: {QDate.currentDate().toString('yyyy-MM-dd')}\n")
                f.write("# CellArea: 1.0000 cm2\n")
                f.write("# Intensity: 100.0 mW/cm2 (AM1.5G)\n#\nVoltage (V)\tCurrent (A)\n")
                for vv, ii in zip(V, I): f.write(f"{vv:.5f}\t{ii:.9e}\n")
            paths.append(path)
        return paths

    def _on_about(self):
        QMessageBox.about(self, "关于",
            "<h2 style='text-align:center;'>光伏IV曲线分析系统 v1.0</h2><hr>"
            "<p>光伏材料实验室专用数据分析软件</p>"
            "<p>支持 Keithley 4200 / Newport Oriel / 国产通用 三大类设备<br>"
            "自动拟合 MPP，计算 Voc/Jsc/FF/Eff/Rs/Rsh<br>"
            "多曲线对比绘图，四种模式切换<br>"
            "SQLite本地器件库，启动自动加载<br>"
            "批量导出 CSV/Excel/JSON/TXT/HTML 报告<br>"
            "内置校准管理与单位换算工具</p>"
            "<p style='color:#888;text-align:center;'>PyQt6 + NumPy + SciPy + Matplotlib</p>")

    def _on_show_help(self):
        QMessageBox.information(self, "使用说明",
            "<h3>快速上手</h3>"
            "<p>1. 点「打开」或「文件夹」加载IV文件<br>"
            "2. 中央画布可平移/缩放，切换I-V/J-V/P-V模式<br>"
            "3. 左侧调整面积/光强/温度后点「应用参数到已选」<br>"
            "4. 选中曲线后右侧显示详细参数<br>"
            "5. 点「保存器件信息到本地」入库，后续自动匹配<br>"
            "6. 「导出数据」可输出Excel/CSV/JSON/HTML报告<br>"
            "7. 「校准→设备校准参数配置」保存校准系数<br>"
            "8. 内置单位换算工具</p>")

    def closeEvent(self, event):
        try:
            files = [s.dataset.file_path for s in self._samples.values()]
            if files: self._storage.set_setting('last_open_files', files)
        except Exception: pass
        try: self._storage.close()
        except Exception: pass
        super().closeEvent(event)


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出分析数据"); self.setMinimumWidth(420)
        layout = QVBoxLayout(self); form = QFormLayout()
        self._fmt_combo = QComboBox()
        for f in ExportFormat: self._fmt_combo.addItem(f.value, f)
        self._fmt_combo.setCurrentIndex(1)
        form.addRow("导出格式:", self._fmt_combo)
        self._raw_check = QPushButton()  # avoid lint
        self._raw_check = QCheckBox("包含 IV 原始数据点")
        self._raw_check.setChecked(True)
        form.addRow("数据内容:", self._raw_check)
        self._dpi_spin = QSpinBox(); self._dpi_spin.setRange(72, 1200); self._dpi_spin.setValue(300); self._dpi_spin.setSuffix(" dpi")
        form.addRow("曲线图分辨率:", self._dpi_spin)
        layout.addLayout(form)
        row = QHBoxLayout(); row.addStretch()
        btn_c = QPushButton("取消"); btn_c.clicked.connect(self.reject); row.addWidget(btn_c)
        btn_o = QPushButton("下一步 ->"); btn_o.setDefault(True); btn_o.clicked.connect(self.accept); row.addWidget(btn_o)
        layout.addLayout(row)
    def get_format(self): return self._fmt_combo.currentData()
    def include_raw(self): return self._raw_check.isChecked()
    def dpi_value(self): return self._dpi_spin.value()


class DeviceManagerDialog(QDialog):
    def __init__(self, storage: DeviceStorage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("器件参数数据库管理"); self.setMinimumSize(1100, 720)
        self._build_ui(); self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("搜索:"))
        self._search_edit = QLineEdit(); self._search_edit.setPlaceholderText("器件编号/批次/材料/备注")
        self._search_edit.textChanged.connect(lambda _: self._refresh_table())
        row.addWidget(self._search_edit, stretch=1)
        row.addWidget(QLabel("筛选批次:"))
        self._batch_combo = QComboBox(); self._batch_combo.addItem("全部批次", "")
        for b in self.storage.list_batches(): self._batch_combo.addItem(b, b)
        self._batch_combo.currentIndexChanged.connect(lambda _: self._refresh_table())
        row.addWidget(self._batch_combo)
        ba = QPushButton("新增"); ba.clicked.connect(self._on_add); row.addWidget(ba)
        be = QPushButton("编辑"); be.clicked.connect(self._on_edit); row.addWidget(be)
        bd = QPushButton("删除"); bd.clicked.connect(self._on_delete); row.addWidget(bd)
        layout.addLayout(row)
        self._table = QTableWidget(0, 15)
        self._table.setHorizontalHeaderLabels(
            ['ID','器件编号','批次','衬底','吸收层','缓冲层','窗口层','背电极',
             '制备方法','日期','厚度(nm)','面积(cm2)','光强(mW/cm2)','温度(C)','备注'])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self._table, stretch=1)
        self._count_lbl = QLabel(""); self._count_lbl.setStyleSheet("color:#666;padding:4px;")
        layout.addWidget(self._count_lbl)
        r2 = QHBoxLayout(); r2.addStretch()
        bc = QPushButton("关闭"); bc.clicked.connect(self.accept); r2.addWidget(bc)
        layout.addLayout(r2)

    def _refresh_table(self):
        kw, batch = self._search_edit.text().strip(), self._batch_combo.currentData() or ""
        if kw:
            recs = self.storage.search(kw)
            if batch: recs = [r for r in recs if r.batch_id == batch]
        elif batch: recs = self.storage.list_by_batch(batch)
        else: recs = self.storage.list_all()
        self._table.setRowCount(len(recs))
        for r, rec in enumerate(recs):
            d = rec.to_dict()
            vals = [d['id'],d['device_id'],d['batch_id'],d['substrate'],d['absorber_layer'],
                d['buffer_layer'],d['window_layer'],d['back_contact'],d['deposition_method'],
                d['deposition_date'],d['thickness_nm'],f"{d['cell_area_cm2']:.4f}",
                f"{d['light_intensity_mwcm2']:.2f}",d['temperature_c'],d['notes']]
            for c, v in enumerate(vals): self._table.setItem(r, c, QTableWidgetItem(str(v) if v is not None else ""))
        self._table.resizeColumnsToContents()
        self._count_lbl.setText(f"共 {len(recs)} 条 (总计 {self.storage.get_count()} 条)")

    def _selected(self) -> Optional[DeviceRecord]:
        rows = self._table.selectionModel().selectedRows()
        if not rows: return None
        id_item = self._table.item(rows[0].row(), 0)
        if not id_item: return None
        try: return self.storage.get_by_id(int(id_item.text()))
        except Exception: return None

    def _on_add(self): DeviceEditDialog(self.storage, None, self).exec(); self._refresh_batches(); self._refresh_table()
    def _on_edit(self):
        r = self._selected()
        if not r: QMessageBox.information(self, "提示", "请选择记录"); return
        DeviceEditDialog(self.storage, r, self).exec(); self._refresh_batches(); self._refresh_table()
    def _on_delete(self):
        r = self._selected()
        if not r: QMessageBox.information(self, "提示", "请选择记录"); return
        if QMessageBox.question(self, "确认", f"删除 [{r.device_id}]？") != QMessageBox.StandardButton.Yes: return
        if r.id is not None: self.storage.delete_device(r.id)
        self._refresh_batches(); self._refresh_table()
    def _refresh_batches(self):
        cur = self._batch_combo.currentData() or ""
        self._batch_combo.clear(); self._batch_combo.addItem("全部批次", "")
        for b in self.storage.list_batches(): self._batch_combo.addItem(b, b)
        idx = self._batch_combo.findData(cur)
        if idx >= 0: self._batch_combo.setCurrentIndex(idx)


class DeviceEditDialog(QDialog):
    def __init__(self, storage, record, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.record = record or DeviceRecord(device_id="")
        self.setWindowTitle("编辑器件" if record else "新增器件")
        self.setMinimumWidth(680)
        self._build_ui(); self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self); form = QFormLayout(); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._dev = QLineEdit(); self._dev.setPlaceholderText("必填"); form.addRow("器件编号:", self._dev)
        self._bat = QLineEdit(); self._bat.setPlaceholderText("批次"); form.addRow("批次编号:", self._bat)
        def ec(items): c = QComboBox(); c.setEditable(True); c.addItems(items); return c
        self._sub = ec(['SLG','FTO','ITO','PET','PEN','硅片','不锈钢','钼片','其它'])
        form.addRow("衬底:", self._sub)
        self._abs = ec(['MAPbI3 钙钛矿','FAPbI3','CsPbI3','多晶 CdTe','CIGS','CZTSSe','Sb2Se3','a-Si:H','微晶硅','P3HT:PCBM','PM6:Y6','硅','GaAs','CdTe'])
        form.addRow("吸收层:", self._abs)
        self._buf = ec(['CdS','ZnS','ZnO','Zn(O,S)','In2S3','TiO2','SnO2','PEAI','LiF','无','GaN'])
        form.addRow("缓冲层:", self._buf)
        self._win = ec(['i-ZnO','AZO','ITO','FTO','BZO','GZO','无'])
        form.addRow("窗口层:", self._win)
        self._bc = ec(['Mo','Au','Ag','Al','Cu','C','Ni','ITO','Au/Ni/Ag'])
        form.addRow("背电极:", self._bc)
        self._met = ec(['旋涂','刮涂','真空蒸发','磁控溅射','CVD','喷涂','电化学沉积','丝网印刷','ALD','PLD','其它'])
        form.addRow("制备方法:", self._met)
        self._d = QDateEdit(); self._d.setCalendarPopup(True); self._d.setDisplayFormat("yyyy-MM-dd"); self._d.setDate(QDate.currentDate())
        form.addRow("制备日期:", self._d)
        self._th = QDoubleSpinBox(); self._th.setRange(0, 1e6); self._th.setSuffix(" nm")
        form.addRow("厚度:", self._th)
        self._a = QDoubleSpinBox(); self._a.setRange(1e-4, 1000); self._a.setDecimals(4); self._a.setSingleStep(0.01); self._a.setValue(1.0); self._a.setSuffix(" cm2")
        form.addRow("面积:", self._a)
        self._i = QDoubleSpinBox(); self._i.setRange(0.01, 5000); self._i.setDecimals(2); self._i.setValue(100.0); self._i.setSuffix(" mW/cm2")
        form.addRow("光强:", self._i)
        self._t = QDoubleSpinBox(); self._t.setRange(-50, 300); self._t.setDecimals(1); self._t.setValue(25.0); self._t.setSuffix(" C")
        form.addRow("温度:", self._t)
        self._tags = QLineEdit(); self._tags.setPlaceholderText("逗号分隔")
        form.addRow("标签:", self._tags)
        self._notes = QTextEdit(); self._notes.setMaximumHeight(80)
        form.addRow("备注:", self._notes)
        layout.addLayout(form)
        r = QHBoxLayout(); r.addStretch()
        bc = QPushButton("取消"); bc.clicked.connect(self.reject); r.addWidget(bc)
        bs = QPushButton("保存"); bs.setDefault(True); bs.clicked.connect(self._on_save); r.addWidget(bs)
        layout.addLayout(r)

    def _load(self):
        r = self.record
        self._dev.setText(r.device_id); self._bat.setText(r.batch_id)
        def sc(cb, v):
            idx = cb.findText(v); cb.setCurrentIndex(idx) if idx >= 0 else cb.setEditText(v)
        for cb, v in [(self._sub,r.substrate),(self._abs,r.absorber_layer),(self._buf,r.buffer_layer),
                      (self._win,r.window_layer),(self._bc,r.back_contact),(self._met,r.deposition_method)]:
            sc(cb, v)
        if r.deposition_date:
            try:
                y,m,d = [int(x) for x in r.deposition_date.replace('/','-').split('-')[:3]]
                self._d.setDate(QDate(y,m,d))
            except Exception: pass
        self._th.setValue(float(r.thickness_nm or 0))
        self._a.setValue(float(r.cell_area_cm2 or 1.0))
        self._i.setValue(float(r.light_intensity_mwcm2 or 100.0))
        self._t.setValue(float(r.temperature_c or 25.0))
        self._tags.setText(r.tags); self._notes.setPlainText(r.notes)

    def _on_save(self):
        if not self._dev.text().strip():
            QMessageBox.warning(self, "提示", "请填写器件编号"); return
        self.record.device_id = self._dev.text().strip()
        self.record.batch_id = self._bat.text().strip()
        for attr, w in [('substrate',self._sub),('absorber_layer',self._abs),('buffer_layer',self._buf),
                        ('window_layer',self._win),('back_contact',self._bc),('deposition_method',self._met)]:
            setattr(self.record, attr, w.currentText().strip())
        self.record.deposition_date = self._d.date().toString("yyyy-MM-dd")
        self.record.thickness_nm = self._th.value()
        self.record.cell_area_cm2 = self._a.value()
        self.record.light_intensity_mwcm2 = self._i.value()
        self.record.temperature_c = self._t.value()
        self.record.tags = self._tags.text().strip()
        self.record.notes = self._notes.toPlainText().strip()
        try:
            if self.record.id is not None: self.storage.update_device(self.record)
            else: self.storage.add_device(self.record)
            self.accept()
        except Exception as e: QMessageBox.critical(self, "失败", str(e))
