import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from scipy.signal import savgol_filter
from scipy.optimize import minimize_scalar, curve_fit
from scipy.interpolate import interp1d

from .iv_parser import IVDataSet


@dataclass
class PVParams:
    """光伏电池器件特性参数集合"""
    voc: float = 0.0
    jsc: float = 0.0
    isc: float = 0.0
    vmpp: float = 0.0
    jmpp: float = 0.0
    impp: float = 0.0
    pmpp: float = 0.0
    ff: float = 0.0
    efficiency: float = 0.0
    rs: float = 0.0
    rsh: float = 0.0
    nideality: float = 1.5
    j0: float = 0.0
    vrev: float = 0.0
    irev: float = 0.0
    light_intensity: float = 100.0
    cell_area: float = 1.0
    temperature: float = 25.0
    calc_success: bool = False
    message: str = ""
    curve_id: str = ""

    def to_dict(self) -> dict:
        return {
            'Voc (V)': round(self.voc, 4),
            'Isc (mA)': round(self.isc * 1000, 4),
            'Jsc (mA/cm²)': round(self.jsc * 1000, 4),
            'Vmpp (V)': round(self.vmpp, 4),
            'Impp (mA)': round(self.impp * 1000, 4),
            'Jmpp (mA/cm²)': round(self.jmpp * 1000, 4),
            'Pmpp (mW)': round(self.pmpp * 1000, 4),
            'FF (%)': round(self.ff * 100, 2),
            'Efficiency (%)': round(self.efficiency * 100, 4),
            'Rs (Ω·cm²)': round(self.rs, 2),
            'Rsh (Ω·cm²)': round(self.rsh, 2),
            'Ideality n': round(self.nideality, 3),
            'J0 (A/cm²)': self.j0,
            'Intensity (mW/cm²)': round(self.light_intensity, 2),
            'Area (cm²)': round(self.cell_area, 4),
            'Temperature (°C)': round(self.temperature, 1),
        }


class PVCalculator:
    """光伏参数计算内核"""

    def __init__(self, smoothing: bool = True, smooth_window: int = 11):
        self.smoothing = smoothing
        self.smooth_window = smooth_window
        self._kT_q = 0.02585  # V at 300K

    def calculate(self, dataset: IVDataSet,
                  cell_area: Optional[float] = None,
                  light_intensity: Optional[float] = None,
                  temperature: float = 25.0) -> PVParams:
        """根据IV数据集计算全套光伏参数"""
        params = PVParams()
        params.curve_id = dataset.device_id or dataset.file_name
        params.temperature = temperature
        params.cell_area = cell_area if cell_area is not None else dataset.cell_area
        params.light_intensity = light_intensity if light_intensity is not None else dataset.light_intensity

        if not dataset.is_valid or len(dataset.voltages) < 5:
            params.message = "数据不足或无效"
            return params

        try:
            voltages, currents = self._preprocess_data(dataset.voltages, dataset.currents)
            if len(voltages) < 5:
                params.message = "预处理后数据不足"
                return params

            params.voc = self._calc_voc(voltages, currents)
            params.isc, params.jsc = self._calc_isc_jsc(voltages, currents, params.cell_area)
            params.vmpp, params.impp, params.jmpp, params.pmpp = self._fit_mpp(voltages, currents, params.cell_area)
            params.ff = self._calc_ff(params.voc, params.isc, params.vmpp, params.impp)
            params.efficiency = self._calc_efficiency(params.pmpp, params.light_intensity, params.cell_area)
            params.rsh = self._calc_rsh(voltages, currents, params.cell_area)
            params.rs = self._calc_rs(voltages, currents, params.voc, params.isc, params.cell_area)

            try:
                params.j0, params.nideality = self._fit_diode_params(
                    voltages, currents, params.cell_area, params.temperature
                )
            except Exception:
                pass

            params.calc_success = True
            params.message = "计算成功"

        except Exception as e:
            params.message = f"计算异常: {str(e)}"

        return params

    def _preprocess_data(self, voltages: np.ndarray, currents: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """数据预处理：排序、去重、平滑"""
        voltages = np.array(voltages, dtype=np.float64)
        currents = np.array(currents, dtype=np.float64)

        sort_idx = np.argsort(voltages)
        voltages = voltages[sort_idx]
        currents = currents[sort_idx]

        voltages, unique_idx = np.unique(voltages, return_index=True)
        currents = currents[unique_idx]

        if self.smoothing and len(currents) >= self.smooth_window:
            win = self.smooth_window if self.smooth_window % 2 == 1 else self.smooth_window + 1
            win = min(win, len(currents) - (len(currents) % 2 == 0))
            if win >= 5:
                currents = savgol_filter(currents, window_length=win, polyorder=2)

        return voltages, currents

    def _calc_voc(self, voltages: np.ndarray, currents: np.ndarray) -> float:
        """计算开路电压 - 电流为零时的电压插值"""
        if np.any(currents == 0):
            zero_idx = np.argmin(np.abs(currents))
            if currents[zero_idx] == 0:
                return voltages[zero_idx]

        sign_changes = np.where(np.diff(np.sign(currents)))[0]
        if len(sign_changes) > 0:
            idx = sign_changes[0]
            if idx + 1 < len(voltages):
                v0, v1 = voltages[idx], voltages[idx + 1]
                i0, i1 = currents[idx], currents[idx + 1]
                if i1 != i0:
                    return v0 - i0 * (v1 - v0) / (i1 - i0)

        pos_mask = currents >= 0
        neg_mask = currents < 0
        if np.any(pos_mask) and np.any(neg_mask):
            neg_v = voltages[neg_mask][-1] if len(voltages[neg_mask]) > 0 else voltages[0]
            pos_v = voltages[pos_mask][0] if len(voltages[pos_mask]) > 0 else voltages[-1]
            neg_i = currents[neg_mask][-1] if len(currents[neg_mask]) > 0 else 0
            pos_i = currents[pos_mask][0] if len(currents[pos_mask]) > 0 else 0
            if pos_i != neg_i:
                return neg_v - neg_i * (pos_v - neg_v) / (pos_i - neg_i)

        return 0.0

    def _calc_isc_jsc(self, voltages: np.ndarray, currents: np.ndarray, area: float) -> Tuple[float, float]:
        """计算短路电流和电流密度"""
        if np.any(voltages == 0):
            zero_idx = np.argmin(np.abs(voltages))
            if voltages[zero_idx] == 0:
                isc = abs(currents[zero_idx])
                return isc, isc / max(area, 1e-10)

        sign_changes = np.where(np.diff(np.sign(voltages)))[0]
        if len(sign_changes) > 0:
            idx = sign_changes[0]
            if idx + 1 < len(voltages):
                v0, v1 = voltages[idx], voltages[idx + 1]
                i0, i1 = currents[idx], currents[idx + 1]
                if v1 != v0:
                    isc = abs(i0 + (0 - v0) * (i1 - i0) / (v1 - v0))
                    return isc, isc / max(area, 1e-10)

        near_zero = np.argmin(np.abs(voltages))
        isc = abs(currents[near_zero])
        return isc, isc / max(area, 1e-10)

    def _fit_mpp(self, voltages: np.ndarray, currents: np.ndarray, area: float) -> Tuple[float, float, float, float]:
        """拟合最大功率点"""
        powers = voltages * currents
        powers = np.abs(powers)

        if len(powers) == 0:
            return 0.0, 0.0, 0.0, 0.0

        peak_idx = np.argmax(powers)
        vmpp_raw = voltages[peak_idx]
        impp_raw = abs(currents[peak_idx])

        try:
            v_min = max(voltages[0], vmpp_raw * 0.5)
            v_max = min(voltages[-1], vmpp_raw * 1.5)
            if v_max <= v_min:
                v_min = voltages[max(0, peak_idx - 2)]
                v_max = voltages[min(len(voltages) - 1, peak_idx + 2)]

            if len(voltages) >= 5:
                try:
                    interp_func = interp1d(voltages, -powers, kind='cubic', bounds_error=False, fill_value='extrapolate')
                    result = minimize_scalar(lambda v: float(interp_func(v)),
                                             bounds=(v_min, v_max), method='bounded')
                    if result.success:
                        v_opt = result.x
                        p_opt = -result.fun
                        if p_opt > powers[peak_idx] * 0.9:
                            i_interp = interp1d(voltages, currents, kind='cubic',
                                                bounds_error=False, fill_value='extrapolate')
                            i_opt = abs(float(i_interp(v_opt)))
                            vmpp_raw = v_opt
                            impp_raw = i_opt
                except Exception:
                    pass
        except Exception:
            pass

        pmpp = vmpp_raw * impp_raw
        jmpp = impp_raw / max(area, 1e-10)
        return vmpp_raw, impp_raw, jmpp, pmpp

    def _calc_ff(self, voc: float, isc: float, vmpp: float, impp: float) -> float:
        """计算填充因子"""
        if voc <= 0 or isc <= 0:
            return 0.0
        ff = (vmpp * impp) / (voc * isc)
        return min(max(ff, 0.0), 1.0)

    def _calc_efficiency(self, pmpp: float, intensity_mw_cm2: float, area_cm2: float) -> float:
        """计算光电转换效率"""
        pin = intensity_mw_cm2 * area_cm2 * 1e-3  # 输入光功率 W
        if pin <= 0:
            return 0.0
        return pmpp / pin

    def _calc_rsh(self, voltages: np.ndarray, currents: np.ndarray, area: float) -> float:
        """计算并联电阻 - 反向偏置区或V=0附近dV/dI"""
        try:
            v_near_zero = voltages[voltages <= 0]
            i_near_zero = currents[voltages <= 0]

            if len(v_near_zero) < 3:
                mask = voltages <= voltages[len(voltages) // 10]
                v_near_zero = voltages[mask]
                i_near_zero = currents[mask]

            if len(v_near_zero) >= 2:
                coeffs = np.polyfit(v_near_zero, i_near_zero, 1)
                dIdV = coeffs[0]
                if abs(dIdV) > 1e-12:
                    rsh = 1.0 / abs(dIdV)
                    return rsh * area
        except Exception:
            pass

        if len(voltages) >= 5:
            try:
                idx = np.argmin(np.abs(voltages))
                lo = max(0, idx - 2)
                hi = min(len(voltages), idx + 3)
                if hi - lo >= 2:
                    coeffs = np.polyfit(voltages[lo:hi], currents[lo:hi], 1)
                    if abs(coeffs[0]) > 1e-12:
                        return (1.0 / abs(coeffs[0])) * area
            except Exception:
                pass

        return float('inf') if not hasattr(self, '_default_rsh') else 1e6

    def _calc_rs(self, voltages: np.ndarray, currents: np.ndarray,
                 voc: float, isc: float, area: float) -> float:
        """计算串联电阻 - Voc附近dV/dI"""
        try:
            v_near_voc = voltages[voltages >= voc * 0.8]
            i_near_voc = currents[voltages >= voc * 0.8]

            if len(v_near_voc) < 3:
                mask = voltages >= voltages[int(len(voltages) * 0.85)]
                v_near_voc = voltages[mask]
                i_near_voc = currents[mask]

            if len(v_near_voc) >= 2:
                coeffs = np.polyfit(v_near_voc, i_near_voc, 1)
                dIdV = coeffs[0]
                if abs(dIdV) > 1e-15:
                    rs = abs(1.0 / dIdV)
                    return rs * area
        except Exception:
            pass

        if len(voltages) >= 5:
            try:
                idx = np.argmin(np.abs(currents))
                lo = max(0, idx - 2)
                hi = min(len(voltages), idx + 3)
                if hi - lo >= 2:
                    coeffs = np.polyfit(voltages[lo:hi], currents[lo:hi], 1)
                    if abs(coeffs[0]) > 1e-15:
                        return abs(1.0 / coeffs[0]) * area
            except Exception:
                pass

        return 0.0

    def _fit_diode_params(self, voltages: np.ndarray, currents: np.ndarray,
                          area: float, temperature: float) -> Tuple[float, float]:
        """拟合二极管理想因子和反向饱和电流"""
        kT_q = 1.380649e-23 * (273.15 + temperature) / 1.602176634e-19

        mask = (voltages > 0.1) & (voltages < 0.9 * max(voltages))
        v_sub = voltages[mask]
        i_sub = currents[mask]

        if len(v_sub) < 5:
            return 1e-10, 1.5

        i_sub_pos = np.abs(i_sub)
        j_sub = i_sub_pos / max(area, 1e-10)

        valid = j_sub > 1e-12
        if np.sum(valid) < 3:
            return 1e-10, 1.5

        v_sub = v_sub[valid]
        log_j = np.log(j_sub[valid])

        try:
            coeffs = np.polyfit(v_sub, log_j, 1)
            slope = coeffs[0]
            intercept = coeffs[1]

            if abs(slope) > 1e-6:
                n = 1.0 / (slope * kT_q)
                j0 = np.exp(intercept)
                n = min(max(n, 0.8), 5.0)
                j0 = max(j0, 1e-20)
                return j0, n
        except Exception:
            pass

        return 1e-10, 1.5

    def batch_calculate(self, datasets: List[IVDataSet],
                        cell_area: Optional[float] = None,
                        light_intensity: Optional[float] = None,
                        temperature: float = 25.0) -> List[Tuple[IVDataSet, PVParams]]:
        """批量计算多个数据集的参数"""
        results = []
        for ds in datasets:
            params = self.calculate(ds, cell_area, light_intensity, temperature)
            results.append((ds, params))
        return results
