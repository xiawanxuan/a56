"""模块语法与功能验证脚本"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("光伏IV曲线分析系统 - 模块语法验证")
print("=" * 60)

errors = []

print("\n[1/8] 检查核心模块语法 (core)...")
try:
    from core import iv_parser
    print("  OK  - core.iv_parser")
except Exception as e:
    errors.append(('core.iv_parser', str(e)))
    print(f"  FAIL - core.iv_parser: {e}")

try:
    from core import pv_calculator
    print("  OK  - core.pv_calculator")
except Exception as e:
    errors.append(('core.pv_calculator', str(e)))
    print(f"  FAIL - core.pv_calculator: {e}")

try:
    from core import data_storage
    print("  OK  - core.data_storage")
except Exception as e:
    errors.append(('core.data_storage', str(e)))
    print(f"  FAIL - core.data_storage: {e}")

print("\n[2/8] 检查导出模块语法 (exporters)...")
try:
    from exporters import batch_exporter
    print("  OK  - exporters.batch_exporter")
except Exception as e:
    errors.append(('exporters.batch_exporter', str(e)))
    print(f"  FAIL - exporters.batch_exporter: {e}")

print("\n[3/8] 检查UI模块语法 (ui)...")
try:
    from ui import iv_canvas
    print("  OK  - ui.iv_canvas")
except Exception as e:
    errors.append(('ui.iv_canvas', str(e)))
    print(f"  FAIL - ui.iv_canvas: {e}")

try:
    from ui import calibration_dialog
    print("  OK  - ui.calibration_dialog")
except Exception as e:
    errors.append(('ui.calibration_dialog', str(e)))
    print(f"  FAIL - ui.calibration_dialog: {e}")

try:
    from ui import unit_converter_dialog
    print("  OK  - ui.unit_converter_dialog")
except Exception as e:
    errors.append(('ui.unit_converter_dialog', str(e)))
    print(f"  FAIL - ui.unit_converter_dialog: {e}")

print("\n[4/8] 检查主窗口语法 (ui.main_window)...")
try:
    from ui import main_window
    print("  OK  - ui.main_window")
except Exception as e:
    errors.append(('ui.main_window', str(e)))
    print(f"  FAIL - ui.main_window: {e}")

print("\n[5/8] 功能测试 - IVParser 解析模拟数据...")
try:
    import numpy as np
    from core.iv_parser import IVParser, DeviceType, IVDataSet

    test_file = os.path.join('data', 'samples', '_test_iv_data.txt')
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    V = np.linspace(-0.1, 0.7, 101)
    I = 0.038 * (1 - np.exp(V / 0.026)) - 0.002 * V
    I = -I + 1e-7 * np.random.randn(len(V))

    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("# Keithley 4200 IV Sweep\n")
        f.write("# DeviceID: TEST-001\n")
        f.write("# BatchID: BatchTEST\n")
        f.write("Voltage (V)\tCurrent (A)\n")
        for vv, ii in zip(V, I):
            f.write(f"{vv:.5f}\t{ii:.9e}\n")

    parser = IVParser()
    ds = parser.parse_file(test_file)
    assert ds.is_valid, "数据无效"
    assert ds.point_count >= 100, "数据点不足"
    assert ds.device_type == DeviceType.KEITHLEY_4200, f"设备类型识别错误: {ds.device_type}"
    print(f"  OK  - 解析成功: {ds.point_count} 点, 设备: {ds.device_type.value}")
except Exception as e:
    errors.append(('IVParser功能', str(e)))
    print(f"  FAIL - IVParser: {e}")

print("\n[6/8] 功能测试 - PVCalculator 参数计算...")
try:
    from core.pv_calculator import PVCalculator

    calc = PVCalculator()
    params = calc.calculate(ds, cell_area=1.0, light_intensity=100.0, temperature=25.0)
    assert params.calc_success, f"计算失败: {params.message}"
    assert 0.4 < params.voc < 0.9, f"Voc 异常: {params.voc}"
    assert 0.02 < params.isc < 0.08, f"Isc 异常: {params.isc}"
    assert 0.4 < params.ff < 0.95, f"FF 异常: {params.ff}"
    assert 0 < params.efficiency < 0.5, f"Eff 异常: {params.efficiency}"
    print(f"  OK  - Voc={params.voc:.4f}V  Isc={params.isc*1000:.2f}mA  "
          f"FF={params.ff*100:.1f}%  Eff={params.efficiency*100:.2f}%  "
          f"Rs={params.rs:.2f}Ω·cm²  Rsh={params.rsh:.0f}Ω·cm²")
except Exception as e:
    errors.append(('PVCalculator功能', str(e)))
    print(f"  FAIL - PVCalculator: {e}")

print("\n[7/8] 功能测试 - DeviceStorage SQLite存储...")
try:
    from core.data_storage import DeviceStorage, DeviceRecord

    test_db = os.path.join('data', '_test_devices.db')
    if os.path.exists(test_db):
        os.remove(test_db)
    with DeviceStorage(test_db) as store:
        rec = DeviceRecord(
            device_id='TEST-STORAGE-001',
            batch_id='Batch2024001',
            absorber_layer='MAPbI3',
            cell_area_cm2=1.5,
            notes='测试记录'
        )
        rid = store.add_device(rec)
        assert rid > 0, "记录未保存"
        fetched = store.get_by_device_id('TEST-STORAGE-001')
        assert fetched is not None, "读取失败"
        assert fetched.cell_area_cm2 == 1.5, f"数据不匹配: {fetched.cell_area_cm2}"
        assert store.get_count() >= 1, "数据库计数错误"
    os.remove(test_db)
    print(f"  OK  - 存储记录ID={rid}, 读取验证成功")
except Exception as e:
    errors.append(('DeviceStorage功能', str(e)))
    print(f"  FAIL - DeviceStorage: {e}")

print("\n[8/8] 功能测试 - BatchExporter 导出...")
try:
    from exporters.batch_exporter import BatchExporter, ExportFormat

    results = [(ds, params)]
    exporter = BatchExporter()

    out_dir = os.path.join('data', 'test_exports')
    os.makedirs(out_dir, exist_ok=True)

    for fmt, ext in [(ExportFormat.JSON, '.json'), (ExportFormat.CSV, '/csv_test'),
                     (ExportFormat.TXT, '.txt'), (ExportFormat.HTML, '.html')]:
        path = os.path.join(out_dir, 'export_test' + ext)
        ok = exporter.export(results, path, fmt, include_raw_data=True)
        assert ok, f"{fmt.value} 导出失败"
    print(f"  OK  - 4种格式导出成功 (JSON/CSV/TXT/HTML)")

    import shutil
    shutil.rmtree(out_dir, ignore_errors=True)
except Exception as e:
    errors.append(('BatchExporter功能', str(e)))
    print(f"  FAIL - BatchExporter: {e}")

# 清理测试文件
for f in [os.path.join('data', 'samples', '_test_iv_data.txt')]:
    if os.path.exists(f):
        try:
            os.remove(f)
        except Exception:
            pass

print("\n" + "=" * 60)
if errors:
    print(f"❌ 检测到 {len(errors)} 个错误：")
    for name, msg in errors:
        print(f"  - {name}: {msg[:120]}")
    print("\n请根据错误信息修复后重新运行。")
    sys.exit(1)
else:
    print("✅ 全部模块语法与功能验证通过！")
    print("\n启动命令:  python main.py")
    print("\n界面布局:")
    print("  ▸ 左侧:   实验文件列表 + 器件参数配置")
    print("  ▸ 中央:   IV多曲线绘图画布")
    print("  ▸ 右侧:   光伏参数结果面板 + 曲线对比表")
    print("  ▸ 底部:   运行状态栏")
    print("\n模块清单:")
    print("  core/iv_parser.py       IV原始数据解析器 (3类设备)")
    print("  core/pv_calculator.py   参数计算内核 (Voc/Jsc/FF/Eff/Rs/Rsh)")
    print("  core/data_storage.py    SQLite器件参数本地存储")
    print("  ui/iv_canvas.py         多曲线绘图画布")
    print("  ui/calibration_dialog.py 设备校准参数配置")
    print("  ui/unit_converter_dialog.py 单位转换表")
    print("  ui/main_window.py       菜单栏布局管理 + 主界面")
    print("  exporters/batch_exporter.py 批量实验数据导出")
    sys.exit(0)
