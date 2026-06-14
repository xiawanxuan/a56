import os
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np


class DeviceType(Enum):
    """光伏测试设备类型枚举"""
    KEITHLEY_4200 = "Keithley 4200 半导体参数分析仪"
    NEWPORT_ORIEL = "Newport Oriel 太阳光模拟器"
    CHINA_GENERIC = "国产通用IV测试仪"
    UNKNOWN = "未知格式"


@dataclass
class IVDataSet:
    """IV数据集容器"""
    file_path: str
    file_name: str
    device_type: DeviceType
    voltages: np.ndarray = field(default_factory=lambda: np.array([]))
    currents: np.ndarray = field(default_factory=lambda: np.array([]))
    light_intensity: float = 100.0
    cell_area: float = 1.0
    device_id: str = ""
    batch_id: str = ""
    test_date: str = ""
    metadata: Dict = field(default_factory=dict)
    is_valid: bool = False

    @property
    def point_count(self) -> int:
        return len(self.voltages)

    def __len__(self) -> int:
        return self.point_count


class IVParser:
    """IV曲线原始数据解析器 - 支持3类光伏测试设备"""

    def __init__(self):
        self._delimiter_patterns = [r',', r'\t', r';', r'\s+']
        self._voltage_keywords = [
            'voltage', 'volt', 'v', '电压', 'v_dc', 'v_smu', 'v_meter'
        ]
        self._current_keywords = [
            'current', 'curr', 'i', '电流', 'i_dc', 'i_smu', 'i_meter'
        ]

    def parse_file(self, file_path: str) -> IVDataSet:
        """解析单个IV数据文件，自动识别设备类型"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_name = os.path.basename(file_path)
        raw_lines = self._read_raw_lines(file_path)

        if not raw_lines:
            raise ValueError(f"文件为空: {file_name}")

        device_type = self._detect_device_type(raw_lines, file_name)

        parsers = {
            DeviceType.KEITHLEY_4200: self._parse_keithley_4200,
            DeviceType.NEWPORT_ORIEL: self._parse_newport_oriel,
            DeviceType.CHINA_GENERIC: self._parse_china_generic,
            DeviceType.UNKNOWN: self._parse_generic_fallback
        }

        parser_func = parsers.get(device_type, self._parse_generic_fallback)
        voltages, currents, metadata = parser_func(raw_lines, file_name)

        is_valid = self._validate_data(voltages, currents)

        return IVDataSet(
            file_path=file_path,
            file_name=file_name,
            device_type=device_type,
            voltages=np.array(voltages, dtype=np.float64),
            currents=np.array(currents, dtype=np.float64),
            light_intensity=metadata.get('light_intensity', 100.0),
            cell_area=metadata.get('cell_area', 1.0),
            device_id=metadata.get('device_id', self._extract_device_id(file_name)),
            batch_id=metadata.get('batch_id', self._extract_batch_id(file_name)),
            test_date=metadata.get('test_date', ''),
            metadata=metadata,
            is_valid=is_valid
        )

    def parse_files(self, file_paths: List[str]) -> List[IVDataSet]:
        """批量解析多个文件"""
        datasets = []
        for fp in file_paths:
            try:
                ds = self.parse_file(fp)
                datasets.append(ds)
            except Exception as e:
                print(f"解析文件 {fp} 失败: {str(e)}")
        return datasets

    def _read_raw_lines(self, file_path: str) -> List[str]:
        """读取原始文件行，处理多种编码"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'ascii']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.readlines()
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f"无法识别文件编码: {file_path}")

    def _detect_device_type(self, lines: List[str], file_name: str) -> DeviceType:
        """根据文件内容特征自动识别设备类型"""
        header = ''.join(lines[:30]).lower()
        fn_lower = file_name.lower()

        keithley_markers = ['keithley', '4200', 'smu', 'vds', 'ids', 'sweep', 'k4200']
        newport_markers = ['newport', 'oriel', 'ivstation', 'solar', 'xenon', 'sun simulator', 'i_sc', 'v_oc']
        china_markers = ['光伏', '太阳电池', 'iv测试', '测试日期', '样品编号', '辐照强度', 'am1.5']

        if any(m in header for m in keithley_markers) or fn_lower.startswith('k4200'):
            return DeviceType.KEITHLEY_4200

        if any(m in header for m in newport_markers) or fn_lower.startswith('oriel'):
            return DeviceType.NEWPORT_ORIEL

        if any(m in header for m in china_markers):
            return DeviceType.CHINA_GENERIC

        if self._looks_like_china_generic(lines):
            return DeviceType.CHINA_GENERIC

        return DeviceType.UNKNOWN

    def _looks_like_china_generic(self, lines: List[str]) -> bool:
        """判断是否为国产测试仪格式（中文标签+简单两列数据）"""
        chinese_count = sum(1 for line in lines[:20] if re.search(r'[\u4e00-\u9fff]', line))
        return chinese_count >= 2

    def _parse_keithley_4200(self, lines: List[str], file_name: str) -> Tuple[List[float], List[float], Dict]:
        """解析 Keithley 4200 格式"""
        voltages, currents = [], []
        metadata = {}
        col_voltage = -1
        col_current = -1
        data_started = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('#') or line.startswith('!'):
                self._extract_keithley_metadata(line, metadata)
                continue

            lower = line.lower()
            if any(kw in lower for kw in self._voltage_keywords) and any(
                    kw in lower for kw in self._current_keywords):
                col_voltage, col_current = self._find_columns(line)
                data_started = True
                continue

            if not data_started:
                if re.match(r'^[\d.+\-eE]', line):
                    data_started = True
                    parts = self._split_line(line)
                    if len(parts) >= 2:
                        col_voltage, col_current = 0, 1
                        self._try_append_point(parts, col_voltage, col_current, voltages, currents)
                continue

            parts = self._split_line(line)
            if len(parts) >= max(col_voltage, col_current) + 1 and col_voltage >= 0:
                self._try_append_point(parts, col_voltage, col_current, voltages, currents)

        return voltages, currents, metadata

    def _parse_newport_oriel(self, lines: List[str], file_name: str) -> Tuple[List[float], List[float], Dict]:
        """解析 Newport Oriel 太阳光模拟器格式"""
        voltages, currents = [], []
        metadata = {}
        col_voltage = -1
        col_current = -1
        data_started = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            lower = line.lower()

            if 'area' in lower and ('cm' in lower or 'mm' in lower):
                self._extract_area(line, metadata)
                continue
            if 'intensity' in lower or 'mismatch' in lower or 'irradiance' in lower:
                self._extract_intensity(line, metadata)
                continue
            if 'date' in lower or 'time' in lower:
                self._extract_datetime(line, metadata)
                continue

            if any(kw in lower for kw in ['v_oc', 'i_sc', 'j_sc', 'p_max', 'ff']):
                self._extract_summary_params(line, metadata)
                continue

            if any(kw in lower for kw in self._voltage_keywords) and any(
                    kw in lower for kw in self._current_keywords):
                col_voltage, col_current = self._find_columns(line)
                data_started = True
                continue

            if not data_started:
                continue

            parts = self._split_line(line)
            if len(parts) >= max(col_voltage, col_current) + 1 and col_voltage >= 0:
                self._try_append_point(parts, col_voltage, col_current, voltages, currents)

        return voltages, currents, metadata

    def _parse_china_generic(self, lines: List[str], file_name: str) -> Tuple[List[float], List[float], Dict]:
        """解析国产通用IV测试仪格式"""
        voltages, currents = [], []
        metadata = {}
        col_voltage = -1
        col_current = -1
        data_started = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if '面积' in line or 'Active Area' in line:
                self._extract_area_cn(line, metadata)
                continue
            if '辐照' in line or '光强' in line or 'Irradiance' in line:
                self._extract_intensity_cn(line, metadata)
                continue
            if '测试日期' in line or '日期' in line or 'Date' in line:
                self._extract_datetime_cn(line, metadata)
                continue
            if '样品编号' in line or '器件编号' in line or 'Sample' in line:
                self._extract_device_id_cn(line, metadata)
                continue
            if '批次' in line or 'Batch' in line:
                self._extract_batch_id_cn(line, metadata)
                continue

            if '电压' in line or 'V' in line:
                if '电流' in line or 'I' in line or 'J' in line:
                    col_voltage, col_current = self._find_columns_cn(line)
                    data_started = True
                    continue

            if not data_started:
                if re.match(r'^[\d.+\-eE]', line):
                    parts = self._split_line(line)
                    if len(parts) >= 2:
                        col_voltage, col_current = 0, 1
                        data_started = True
                        self._try_append_point(parts, col_voltage, col_current, voltages, currents)
                continue

            parts = self._split_line(line)
            if len(parts) >= max(col_voltage, col_current) + 1 and col_voltage >= 0:
                self._try_append_point(parts, col_voltage, col_current, voltages, currents)

        return voltages, currents, metadata

    def _parse_generic_fallback(self, lines: List[str], file_name: str) -> Tuple[List[float], List[float], Dict]:
        """通用回退解析：尝试找到数值列"""
        voltages, currents = [], []
        metadata = {}

        numeric_blocks = self._find_numeric_blocks(lines)
        if numeric_blocks:
            best_block = max(numeric_blocks, key=lambda b: len(b))
            for row in best_block:
                if len(row) >= 2:
                    try:
                        v = float(row[0])
                        c = float(row[1])
                        if not (np.isnan(v) or np.isnan(c) or np.isinf(v) or np.isinf(c)):
                            voltages.append(v)
                            currents.append(c)
                    except (ValueError, IndexError):
                        continue

        return voltages, currents, metadata

    def _find_numeric_blocks(self, lines: List[str]) -> List[List[List[str]]]:
        """找出所有连续数值数据块"""
        blocks = []
        current_block = []

        for line in lines:
            parts = self._split_line(line.strip())
            numeric_count = sum(1 for p in parts if re.match(r'^[+\-]?\d+\.?\d*[eE]?[+\-]?\d*$', p))
            if len(parts) >= 2 and numeric_count >= len(parts) * 0.5:
                current_block.append(parts)
            else:
                if current_block:
                    blocks.append(current_block)
                    current_block = []

        if current_block:
            blocks.append(current_block)

        return blocks

    def _split_line(self, line: str) -> List[str]:
        """智能分割数据行"""
        for pat in [r'\t', r',', r';']:
            if re.search(pat, line):
                return [p.strip() for p in re.split(pat, line) if p.strip()]
        return [p.strip() for p in re.split(r'\s+', line) if p.strip()]

    def _find_columns(self, header_line: str) -> Tuple[int, int]:
        """根据表头行找到电压和电流列索引"""
        parts = self._split_line(header_line)
        col_v, col_i = -1, -1
        for idx, p in enumerate(parts):
            pl = p.lower()
            if any(kw in pl for kw in self._voltage_keywords) and col_v < 0:
                col_v = idx
            if any(kw in pl for kw in self._current_keywords) and col_i < 0:
                col_i = idx
        return col_v, col_i

    def _find_columns_cn(self, header_line: str) -> Tuple[int, int]:
        """中文表头列定位"""
        parts = self._split_line(header_line)
        col_v, col_i = -1, -1
        for idx, p in enumerate(parts):
            if '电压' in p or p.upper().startswith('V') and col_v < 0:
                col_v = idx
            if ('电流' in p or p.upper().startswith('I') or p.upper().startswith('J')) and col_i < 0:
                col_i = idx
        if col_v < 0:
            col_v = 0
        if col_i < 0:
            col_i = min(1, len(parts) - 1)
        return col_v, col_i

    def _try_append_point(self, parts: List[str], col_v: int, col_i: int,
                          voltages: List[float], currents: List[float]):
        """尝试追加数据点"""
        try:
            v = float(parts[col_v])
            c = float(parts[col_i])
            if not (np.isnan(v) or np.isnan(c) or np.isinf(v) or np.isinf(c)):
                voltages.append(v)
                currents.append(c)
        except (ValueError, IndexError):
            pass

    def _validate_data(self, voltages: List[float], currents: List[float]) -> bool:
        """验证数据有效性"""
        if len(voltages) < 5 or len(currents) < 5:
            return False
        if len(voltages) != len(currents):
            return False
        return True

    def _extract_keithley_metadata(self, line: str, metadata: Dict):
        pass

    def _extract_area(self, line: str, metadata: Dict):
        m = re.search(r'(\d+\.?\d*)\s*(cm2|cm\^2|mm2|mm\^2)', line, re.I)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if 'mm' in unit:
                val /= 100.0
            metadata['cell_area'] = val

    def _extract_area_cn(self, line: str, metadata: Dict):
        m = re.search(r'(\d+\.?\d*)\s*(平方厘米|平方毫米|cm2|mm2)', line, re.I)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if 'mm' in unit:
                val /= 100.0
            metadata['cell_area'] = val
        else:
            m = re.search(r'[:：]\s*(\d+\.?\d*)', line)
            if m:
                metadata['cell_area'] = float(m.group(1))

    def _extract_intensity(self, line: str, metadata: Dict):
        m = re.search(r'(\d+\.?\d*)\s*(mw/cm2|mw|w/m2|sun|suns)', line, re.I)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if 'w/m2' in unit:
                val /= 10.0
            elif 'sun' in unit:
                val *= 100.0
            metadata['light_intensity'] = val

    def _extract_intensity_cn(self, line: str, metadata: Dict):
        m = re.search(r'(\d+\.?\d*)\s*(mw/cm2|毫瓦|w/m2)', line, re.I)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if 'w/m2' in unit:
                val /= 10.0
            metadata['light_intensity'] = val
        else:
            m = re.search(r'[:：]\s*(\d+\.?\d*)', line)
            if m:
                metadata['light_intensity'] = float(m.group(1))

    def _extract_datetime(self, line: str, metadata: Dict):
        m = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', line)
        if m:
            metadata['test_date'] = m.group(1).replace('/', '-')

    def _extract_datetime_cn(self, line: str, metadata: Dict):
        m = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', line)
        if m:
            d = m.group(1).replace('年', '-').replace('月', '-').replace('/', '-')
            if d.endswith('-'):
                d = d[:-1]
            metadata['test_date'] = d

    def _extract_device_id_cn(self, line: str, metadata: Dict):
        m = re.search(r'[:：]\s*([\w\u4e00-\u9fff\-_]+)', line)
        if m:
            metadata['device_id'] = m.group(1).strip()

    def _extract_batch_id_cn(self, line: str, metadata: Dict):
        m = re.search(r'[:：]\s*([\w\u4e00-\u9fff\-_]+)', line)
        if m:
            metadata['batch_id'] = m.group(1).strip()

    def _extract_summary_params(self, line: str, metadata: Dict):
        for key, pattern in [
            ('v_oc', r'v_oc[\s:=]+([+\-]?\d+\.?\d*)'),
            ('i_sc', r'i_sc[\s:=]+([+\-]?\d+\.?\d*)'),
            ('j_sc', r'j_sc[\s:=]+([+\-]?\d+\.?\d*)'),
            ('p_max', r'p_max[\s:=]+([+\-]?\d+\.?\d*)'),
            ('ff', r'ff[\s:=]+([+\-]?\d+\.?\d*)'),
        ]:
            m = re.search(pattern, line, re.I)
            if m:
                try:
                    metadata[key] = float(m.group(1))
                except ValueError:
                    pass

    def _extract_device_id(self, file_name: str) -> str:
        base = os.path.splitext(file_name)[0]
        m = re.search(r'[Dd]evice[_\-]?(\w+)', base)
        if m:
            return m.group(1)
        return base

    def _extract_batch_id(self, file_name: str) -> str:
        base = os.path.splitext(file_name)[0]
        m = re.search(r'[Bb]atch[_\-]?(\w+)', base)
        if m:
            return m.group(1)
        m2 = re.match(r'^([A-Za-z]{2,5}\d+)', base)
        if m2:
            return m2.group(1)
        return ''
