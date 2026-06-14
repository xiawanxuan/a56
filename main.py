#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
光伏材料实验室 IV 曲线分析系统
Photovoltaic IV Curve Analyzer v1.0

入口文件
"""

import os
import sys


def bootstrap():
    """启动前检查与初始化"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)

    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    return base_dir


def check_dependencies():
    """检查依赖库是否安装"""
    required = [
        ('PyQt6', 'PyQt6.QtWidgets', 'Qt界面框架'),
        ('numpy', 'numpy', '数值计算'),
        ('scipy', 'scipy.optimize', '拟合与优化'),
        ('matplotlib', 'matplotlib', '绘图'),
        ('pandas', 'pandas', '数据处理'),
        ('openpyxl', 'openpyxl', 'Excel导出'),
    ]
    missing = []
    for pkg_name, import_path, desc in required:
        try:
            __import__(import_path)
        except ImportError:
            missing.append((pkg_name, desc))
    return missing


def main():
    """主入口函数"""
    base_dir = bootstrap()
    missing = check_dependencies()
    if missing:
        print("缺少以下依赖库，请先安装:")
        print("-" * 50)
        for pkg, desc in missing:
            print(f"  * {pkg:<16s}  {desc}")
        print("-" * 50)
        print("\n执行安装命令:")
        req = os.path.join(base_dir, 'requirements.txt')
        print(f"  pip install -r {req}")
        print(f"\n或单独安装: pip install {' '.join(x[0] for x in missing)}")
        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            app = QApplication.instance() or QApplication(sys.argv)
            msg = "缺少依赖库:\n\n" + "\n".join(f"* {p} - {d}" for p, d in missing)
            msg += f"\n\n请执行: pip install -r {req}"
            QMessageBox.critical(None, "依赖缺失", msg)
        except Exception:
            pass
        return 1

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFont
        from ui.main_window import MainWindow
    except ImportError as e:
        print(f"导入模块失败: {e}")
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("光伏IV曲线分析系统")
    app.setOrganizationName("光伏材料实验室")
    app.setApplicationVersion("1.0.0")

    try:
        font = QFont("Microsoft YaHei", 9)
        app.setFont(font)
    except Exception:
        pass

    try:
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as e:
        print(f"启动异常: {e}")
        import traceback
        traceback.print_exc()
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "启动失败", f"程序启动异常:\n\n{str(e)}")
        except Exception:
            pass
        return 3


if __name__ == '__main__':
    sys.exit(main())
