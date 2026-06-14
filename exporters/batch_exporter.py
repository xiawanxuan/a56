import os
import json
import csv
from enum import Enum
from typing import List, Optional, Dict, Tuple
import numpy as np
import pandas as pd

from core.iv_parser import IVDataSet
from core.pv_calculator import PVParams


class ExportFormat(Enum):
    CSV = "CSV 表格"
    EXCEL = "Excel 工作簿"
    JSON = "JSON 结构"
    TXT = "纯文本 TXT"
    HTML = "HTML 报告"


class BatchExporter:
    """批量实验数据导出模块"""

    def __init__(self):
        self._default_encoding = 'utf-8-sig'

    def export(self, results: List[Tuple[IVDataSet, PVParams]],
               output_path: str,
               fmt: ExportFormat = ExportFormat.EXCEL,
               include_raw_data: bool = True,
               include_curves_figure=None,
               figure_dpi: int = 300) -> bool:
        """导出批量实验结果"""
        if not results:
            raise ValueError("没有可导出的数据")

        try:
            handlers = {
                ExportFormat.CSV: self._export_csv,
                ExportFormat.EXCEL: self._export_excel,
                ExportFormat.JSON: self._export_json,
                ExportFormat.TXT: self._export_txt,
                ExportFormat.HTML: self._export_html,
            }
            handler = handlers.get(fmt)
            if not handler:
                raise ValueError(f"不支持的导出格式: {fmt}")

            return handler(results, output_path, include_raw_data, include_curves_figure, figure_dpi)
        except Exception as e:
            print(f"导出失败: {str(e)}")
            return False

    def _export_csv(self, results, output_path, include_raw_data, figure, dpi):
        base_dir = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        os.makedirs(base_dir, exist_ok=True)

        summary_path = os.path.join(base_dir, f"{base_name}_summary.csv")
        self._write_summary_csv(results, summary_path)

        if include_raw_data:
            raw_dir = os.path.join(base_dir, f"{base_name}_raw_data")
            os.makedirs(raw_dir, exist_ok=True)
            for idx, (dataset, params) in enumerate(results):
                raw_file = os.path.join(raw_dir, f"{idx + 1:03d}_{dataset.device_id or 'sample'}.csv")
                self._write_raw_csv(dataset, params, raw_file)

        if figure is not None:
            fig_path = os.path.join(base_dir, f"{base_name}_curves.png")
            try:
                figure.save_figure(fig_path, dpi)
            except Exception:
                pass

        return True

    def _export_excel(self, results, output_path, include_raw_data, figure, dpi):
        base_dir = os.path.dirname(output_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)

        if not output_path.lower().endswith(('.xlsx', '.xlsm')):
            output_path += '.xlsx'

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            self._write_summary_excel(results, writer)

            if include_raw_data:
                for idx, (dataset, params) in enumerate(results):
                    sheet_name = self._safe_sheet_name(f"Curve{idx + 1}_{dataset.device_id or 'Smp'}")
                    self._write_raw_excel(dataset, params, writer, sheet_name)

            meta_df = self._build_metadata_df(results)
            if len(meta_df) > 0:
                meta_df.to_excel(writer, sheet_name='元数据', index=False)

        if figure is not None:
            fig_path = os.path.splitext(output_path)[0] + '_curves.png'
            try:
                figure.save_figure(fig_path, dpi)
            except Exception:
                pass

        return True

    def _export_json(self, results, output_path, include_raw_data, figure, dpi):
        base_dir = os.path.dirname(output_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)

        json_data = {
            'export_info': {
                'format': 'PV_IV_Analysis',
                'version': '1.0',
                'sample_count': len(results),
            },
            'samples': []
        }

        for dataset, params in results:
            sample = {
                'device_id': dataset.device_id,
                'batch_id': dataset.batch_id,
                'file_name': dataset.file_name,
                'device_type': dataset.device_type.value if hasattr(dataset.device_type, 'value') else str(dataset.device_type),
                'test_date': dataset.test_date,
                'cell_area_cm2': dataset.cell_area,
                'light_intensity_mwcm2': dataset.light_intensity,
                'parameters': params.to_dict(),
            }
            if include_raw_data:
                sample['raw_data'] = {
                    'voltage_V': np.array(dataset.voltages, dtype=float).tolist(),
                    'current_A': np.array(dataset.currents, dtype=float).tolist(),
                }
            json_data['samples'].append(sample)

        with open(output_path, 'w', encoding=self._default_encoding) as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        if figure is not None:
            fig_path = os.path.splitext(output_path)[0] + '_curves.png'
            try:
                figure.save_figure(fig_path, dpi)
            except Exception:
                pass

        return True

    def _export_txt(self, results, output_path, include_raw_data, figure, dpi):
        base_dir = os.path.dirname(output_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)

        with open(output_path, 'w', encoding=self._default_encoding) as f:
            f.write("=" * 72 + "\n")
            f.write("光伏器件IV特性批量分析报告\n")
            f.write(f"样品数量: {len(results)}\n")
            f.write("=" * 72 + "\n\n")

            f.write("--- 参数汇总表 ---\n")
            f.write(self._build_summary_txt(results))
            f.write("\n\n")

            for idx, (dataset, params) in enumerate(results):
                f.write("-" * 72 + "\n")
                f.write(f"[{idx + 1}] 器件编号: {dataset.device_id or dataset.file_name}\n")
                f.write(f"    批次编号: {dataset.batch_id or '-'}\n")
                f.write(f"    测试日期: {dataset.test_date or '-'}\n")
                f.write(f"    设备类型: {dataset.device_type.value if hasattr(dataset.device_type, 'value') else str(dataset.device_type)}\n")
                f.write(f"    面积: {dataset.cell_area:.4f} cm²    光强: {dataset.light_intensity:.2f} mW/cm²\n")
                f.write(f"\n    特性参数:\n")
                for k, v in params.to_dict().items():
                    f.write(f"      {k}: {v}\n")

                if include_raw_data:
                    f.write(f"\n    IV 原始数据 ({len(dataset.voltages)} 点):\n")
                    f.write(f"      {'V (V)':>12s}  {'I (A)':>14s}\n")
                    f.write(f"      {'-' * 12}  {'-' * 14}\n")
                    step = max(1, len(dataset.voltages) // 200)
                    for i in range(0, len(dataset.voltages), step):
                        f.write(f"      {dataset.voltages[i]:12.5f}  {dataset.currents[i]:14.8f}\n")
                    f.write("\n")

        if figure is not None:
            fig_path = os.path.splitext(output_path)[0] + '_curves.png'
            try:
                figure.save_figure(fig_path, dpi)
            except Exception:
                pass

        return True

    def _export_html(self, results, output_path, include_raw_data, figure, dpi):
        base_dir = os.path.dirname(output_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)

        if figure is not None:
            fig_name = os.path.splitext(os.path.basename(output_path))[0] + '_curves.png'
            fig_path = os.path.join(base_dir, fig_name)
            try:
                figure.save_figure(fig_path, dpi)
            except Exception:
                fig_name = None
        else:
            fig_name = None

        html = self._build_html_report(results, fig_name)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return True

    def _write_summary_csv(self, results, path):
        rows = []
        for idx, (dataset, params) in enumerate(results):
            row = {
                '序号': idx + 1,
                '器件编号': dataset.device_id,
                '批次': dataset.batch_id,
                '文件': dataset.file_name,
                '测试日期': dataset.test_date,
            }
            row.update(params.to_dict())
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(path, index=False, encoding=self._default_encoding)

    def _write_raw_csv(self, dataset, params, path):
        df = pd.DataFrame({
            'Voltage (V)': np.array(dataset.voltages, dtype=float),
            'Current (A)': np.array(dataset.currents, dtype=float),
            'Current Density (mA/cm²)': (np.array(dataset.currents, dtype=float) / max(params.cell_area, 1e-10)) * 1000,
            'Power (mW)': np.abs(np.array(dataset.voltages, dtype=float) * np.array(dataset.currents, dtype=float)) * 1000,
        })
        df.to_csv(path, index=False, encoding=self._default_encoding)

    def _write_summary_excel(self, results, writer):
        rows = []
        for idx, (dataset, params) in enumerate(results):
            row = {
                '序号': idx + 1,
                '器件编号': dataset.device_id,
                '批次': dataset.batch_id,
                '文件': dataset.file_name,
                '测试日期': dataset.test_date,
            }
            row.update(params.to_dict())
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='参数汇总', index=False)

    def _write_raw_excel(self, dataset, params, writer, sheet_name):
        df = pd.DataFrame({
            'Voltage (V)': np.array(dataset.voltages, dtype=float),
            'Current (A)': np.array(dataset.currents, dtype=float),
            'Current Density (mA/cm²)': (np.array(dataset.currents, dtype=float) / max(params.cell_area, 1e-10)) * 1000,
            'Power (mW)': np.abs(np.array(dataset.voltages, dtype=float) * np.array(dataset.currents, dtype=float)) * 1000,
        })
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    def _build_metadata_df(self, results) -> pd.DataFrame:
        rows = []
        for idx, (dataset, _) in enumerate(results):
            for k, v in dataset.metadata.items():
                rows.append({'序号': idx + 1, 'Key': k, 'Value': str(v)})
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _build_summary_txt(self, results) -> str:
        lines = []
        keys = list(results[0][1].to_dict().keys()) if results else []
        header = f"{'No':>4s} {'ID':<18s}"
        for k in keys[:6]:
            short = k.split('(')[0].strip()[:8]
            header += f" {short:>9s}"
        lines.append(header)
        lines.append('-' * len(header))

        for idx, (dataset, params) in enumerate(results):
            pdict = params.to_dict()
            vals = list(pdict.values())
            line = f"{idx + 1:>4d} {(dataset.device_id or 'N/A')[:17]:<18s}"
            for v in vals[:6]:
                if isinstance(v, float):
                    line += f" {v:>9.3f}"
                else:
                    line += f" {str(v)[:9]:>9s}"
            lines.append(line)

        return '\n'.join(lines)

    def _build_html_report(self, results, fig_name) -> str:
        param_keys = list(results[0][1].to_dict().keys()) if results else []
        table_rows = []
        for idx, (dataset, params) in enumerate(results):
            cells = f"<td>{idx + 1}</td><td>{dataset.device_id or 'N/A'}</td>"
            cells += f"<td>{dataset.batch_id or '-'}</td>"
            pdict = params.to_dict()
            for k in param_keys:
                v = pdict.get(k, '')
                cells += f"<td>{v}</td>"
            table_rows.append(f"<tr>{cells}</tr>")

        ths = "<th>序号</th><th>器件编号</th><th>批次</th>" + ''.join(f"<th>{k}</th>" for k in param_keys)

        details_html = ""
        for idx, (dataset, params) in enumerate(results):
            details_html += f"""
            <details style="margin:10px 0;padding:10px;border:1px solid #ddd;border-radius:6px;">
                <summary style="cursor:pointer;font-weight:bold;">
                    [{idx + 1}] {dataset.device_id or dataset.file_name}
                    <span style="color:#666;font-weight:normal;">- 效率: {params.efficiency * 100:.3f}% | FF: {params.ff * 100:.2f}%</span>
                </summary>
                <div style="margin-top:10px;">
                    <p><strong>测试信息:</strong> 批次: {dataset.batch_id or '-'} | 日期: {dataset.test_date or '-'} | 面积: {dataset.cell_area:.4f} cm² | 光强: {dataset.light_intensity:.2f} mW/cm²</p>
                    <table border="1" cellpadding="6" style="border-collapse:collapse;margin-top:8px;">
                        <tr>{''.join(f'<th>{k}</th>' for k in params.to_dict().keys())}</tr>
                        <tr>{''.join(f'<td>{v}</td>' for v in params.to_dict().values())}</tr>
                    </table>
                </div>
            </details>
            """

        fig_img = f'<img src="{fig_name}" style="max-width:100%;border:1px solid #ccc;margin:16px 0;" alt="IV curves">' if fig_name else ''

        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>光伏IV曲线分析报告</title>
<style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:24px;color:#222;max-width:1400px;}}
h1{{color:#1a365d;border-bottom:3px solid #2c5282;padding-bottom:10px;}}
h2{{color:#2c5282;margin-top:28px;}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px;}}
th{{background:#2c5282;color:#fff;padding:8px 6px;}}
td{{border:1px solid #cbd5e0;padding:6px;text-align:center;}}
tr:nth-child(even) td{{background:#f7fafc;}}
.info-box{{background:#ebf8ff;border:1px solid #bee3f8;padding:12px;border-radius:6px;margin:12px 0;}}
</style></head><body>
<h1>光伏器件IV特性分析报告</h1>
<div class="info-box">
    <p><strong>样品总数:</strong> {len(results)} 件</p>
    <p><strong>分析时间:</strong> 本报告由 PV IV Analyzer 自动生成</p>
</div>
<h2>IV 曲线对比图</h2>
{fig_img}
<h2>参数汇总表</h2>
<table><thead><tr>{ths}</tr></thead><tbody>{''.join(table_rows)}</tbody></table>
<h2>各器件详细参数</h2>
{details_html}
</body></html>"""

    def _safe_sheet_name(self, name: str, limit: int = 31) -> str:
        invalid = '[]:*?/\\'
        for c in invalid:
            name = name.replace(c, '_')
        return name[:limit]
