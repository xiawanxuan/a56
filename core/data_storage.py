import os
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


APP_DATA_DIR = os.path.join(os.path.expanduser('~'), '.pv_iv_analyzer')
DEFAULT_DB_PATH = os.path.join(APP_DATA_DIR, 'devices.db')


@dataclass
class DeviceRecord:
    """薄膜器件基础参数记录"""
    device_id: str
    batch_id: str = ""
    substrate: str = ""
    absorber_layer: str = ""
    buffer_layer: str = ""
    window_layer: str = ""
    back_contact: str = ""
    deposition_method: str = ""
    deposition_date: str = ""
    thickness_nm: float = 0.0
    cell_area_cm2: float = 1.0
    light_intensity_mwcm2: float = 100.0
    temperature_c: float = 25.0
    notes: str = ""
    tags: str = ""
    custom_params_json: str = "{}"
    created_at: str = ""
    updated_at: str = ""
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'device_id': self.device_id,
            'batch_id': self.batch_id,
            'substrate': self.substrate,
            'absorber_layer': self.absorber_layer,
            'buffer_layer': self.buffer_layer,
            'window_layer': self.window_layer,
            'back_contact': self.back_contact,
            'deposition_method': self.deposition_method,
            'deposition_date': self.deposition_date,
            'thickness_nm': self.thickness_nm,
            'cell_area_cm2': self.cell_area_cm2,
            'light_intensity_mwcm2': self.light_intensity_mwcm2,
            'temperature_c': self.temperature_c,
            'notes': self.notes,
            'tags': self.tags,
            'custom_params_json': self.custom_params_json,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'DeviceRecord':
        return cls(
            id=d.get('id'),
            device_id=d.get('device_id', ''),
            batch_id=d.get('batch_id', ''),
            substrate=d.get('substrate', ''),
            absorber_layer=d.get('absorber_layer', ''),
            buffer_layer=d.get('buffer_layer', ''),
            window_layer=d.get('window_layer', ''),
            back_contact=d.get('back_contact', ''),
            deposition_method=d.get('deposition_method', ''),
            deposition_date=d.get('deposition_date', ''),
            thickness_nm=float(d.get('thickness_nm', 0) or 0),
            cell_area_cm2=float(d.get('cell_area_cm2', 1.0) or 1.0),
            light_intensity_mwcm2=float(d.get('light_intensity_mwcm2', 100.0) or 100.0),
            temperature_c=float(d.get('temperature_c', 25.0) or 25.0),
            notes=d.get('notes', ''),
            tags=d.get('tags', ''),
            custom_params_json=d.get('custom_params_json', '{}'),
            created_at=d.get('created_at', ''),
            updated_at=d.get('updated_at', ''),
        )

    def get_custom_params(self) -> Dict[str, Any]:
        try:
            return json.loads(self.custom_params_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_custom_params(self, params: Dict[str, Any]):
        self.custom_params_json = json.dumps(params, ensure_ascii=False)


class DeviceStorage:
    """器件参数本地存储模块 (SQLite)"""

    _SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL UNIQUE,
        batch_id TEXT DEFAULT '',
        substrate TEXT DEFAULT '',
        absorber_layer TEXT DEFAULT '',
        buffer_layer TEXT DEFAULT '',
        window_layer TEXT DEFAULT '',
        back_contact TEXT DEFAULT '',
        deposition_method TEXT DEFAULT '',
        deposition_date TEXT DEFAULT '',
        thickness_nm REAL DEFAULT 0,
        cell_area_cm2 REAL DEFAULT 1.0,
        light_intensity_mwcm2 REAL DEFAULT 100.0,
        temperature_c REAL DEFAULT 25.0,
        notes TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        custom_params_json TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_batch ON devices(batch_id);
    CREATE INDEX IF NOT EXISTS idx_dep_date ON devices(deposition_date);

    CREATE TABLE IF NOT EXISTS calibration (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_name TEXT NOT NULL,
        intensity_cal REAL DEFAULT 1.0,
        area_cal REAL DEFAULT 1.0,
        current_cal REAL DEFAULT 1.0,
        voltage_cal REAL DEFAULT 1.0,
        last_cal_date TEXT,
        operator TEXT,
        notes TEXT,
        params_json TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS project_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_dir()
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_schema(self):
        self._conn.executescript(self._SCHEMA_SQL)
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def add_device(self, record: DeviceRecord) -> int:
        """新增器件记录，返回记录ID"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not record.created_at:
            record.created_at = now
        record.updated_at = now

        cur = self._conn.cursor()
        try:
            cur.execute("""
                INSERT INTO devices (
                    device_id, batch_id, substrate, absorber_layer, buffer_layer,
                    window_layer, back_contact, deposition_method, deposition_date,
                    thickness_nm, cell_area_cm2, light_intensity_mwcm2, temperature_c,
                    notes, tags, custom_params_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.device_id, record.batch_id, record.substrate,
                record.absorber_layer, record.buffer_layer, record.window_layer,
                record.back_contact, record.deposition_method, record.deposition_date,
                record.thickness_nm, record.cell_area_cm2, record.light_intensity_mwcm2,
                record.temperature_c, record.notes, record.tags, record.custom_params_json,
                record.created_at, record.updated_at
            ))
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"器件编号已存在: {record.device_id}")

    def update_device(self, record: DeviceRecord) -> bool:
        """更新器件记录"""
        if record.id is None:
            existing = self.get_by_device_id(record.device_id)
            if not existing:
                return False
            record.id = existing.id

        record.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cur = self._conn.cursor()
        cur.execute("""
            UPDATE devices SET
                batch_id=?, substrate=?, absorber_layer=?, buffer_layer=?,
                window_layer=?, back_contact=?, deposition_method=?, deposition_date=?,
                thickness_nm=?, cell_area_cm2=?, light_intensity_mwcm2=?, temperature_c=?,
                notes=?, tags=?, custom_params_json=?, updated_at=?
            WHERE id=?
        """, (
            record.batch_id, record.substrate, record.absorber_layer,
            record.buffer_layer, record.window_layer, record.back_contact,
            record.deposition_method, record.deposition_date, record.thickness_nm,
            record.cell_area_cm2, record.light_intensity_mwcm2, record.temperature_c,
            record.notes, record.tags, record.custom_params_json,
            record.updated_at, record.id
        ))
        self._conn.commit()
        return cur.rowcount > 0

    def delete_device(self, record_id: int) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM devices WHERE id=?", (record_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def delete_by_device_id(self, device_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM devices WHERE device_id=?", (device_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_by_id(self, record_id: int) -> Optional[DeviceRecord]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM devices WHERE id=?", (record_id,))
        row = cur.fetchone()
        return DeviceRecord.from_dict(dict(row)) if row else None

    def get_by_device_id(self, device_id: str) -> Optional[DeviceRecord]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM devices WHERE device_id=?", (device_id,))
        row = cur.fetchone()
        return DeviceRecord.from_dict(dict(row)) if row else None

    def list_all(self, limit: int = 500, offset: int = 0) -> List[DeviceRecord]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM devices ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [DeviceRecord.from_dict(dict(r)) for r in cur.fetchall()]

    def list_by_batch(self, batch_id: str) -> List[DeviceRecord]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM devices WHERE batch_id=? ORDER BY device_id",
            (batch_id,)
        )
        return [DeviceRecord.from_dict(dict(r)) for r in cur.fetchall()]

    def search(self, keyword: str) -> List[DeviceRecord]:
        like = f'%{keyword}%'
        cur = self._conn.cursor()
        cur.execute("""
            SELECT * FROM devices
            WHERE device_id LIKE ? OR batch_id LIKE ? OR notes LIKE ? OR tags LIKE ?
               OR absorber_layer LIKE ? OR substrate LIKE ?
            ORDER BY updated_at DESC
            LIMIT 200
        """, (like, like, like, like, like, like))
        return [DeviceRecord.from_dict(dict(r)) for r in cur.fetchall()]

    def list_batches(self) -> List[str]:
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT batch_id FROM devices WHERE batch_id != '' ORDER BY batch_id")
        return [r[0] for r in cur.fetchall()]

    def get_count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM devices")
        return cur.fetchone()[0]

    def save_calibration(self, data: Dict[str, Any]) -> int:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur = self._conn.cursor()
        cur.execute("""
            INSERT INTO calibration (
                device_name, intensity_cal, area_cal, current_cal,
                voltage_cal, last_cal_date, operator, notes, params_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('device_name', ''),
            float(data.get('intensity_cal', 1.0)),
            float(data.get('area_cal', 1.0)),
            float(data.get('current_cal', 1.0)),
            float(data.get('voltage_cal', 1.0)),
            data.get('last_cal_date', now),
            data.get('operator', ''),
            data.get('notes', ''),
            json.dumps(data.get('params', {}), ensure_ascii=False)
        ))
        self._conn.commit()
        return cur.lastrowid

    def get_latest_calibration(self, device_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        if device_name:
            cur.execute(
                "SELECT * FROM calibration WHERE device_name=? ORDER BY id DESC LIMIT 1",
                (device_name,)
            )
        else:
            cur.execute("SELECT * FROM calibration ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            d = dict(row)
            try:
                d['params'] = json.loads(d.get('params_json', '{}'))
            except (json.JSONDecodeError, TypeError):
                d['params'] = {}
            return d
        return None

    def list_calibrations(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM calibration ORDER BY id DESC LIMIT ?", (limit,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d['params'] = json.loads(d.get('params_json', '{}'))
            except Exception:
                d['params'] = {}
            results.append(d)
        return results

    def set_setting(self, key: str, value: Any):
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO project_settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False))
        )
        self._conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM project_settings WHERE key=?", (key,))
        row = cur.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return row[0]
        return default

    def export_to_json(self, file_path: str):
        devices = self.list_all(limit=10000)
        cals = self.list_calibrations()
        data = {
            'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'devices': [d.to_dict() for d in devices],
            'calibrations': cals,
        }
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_from_json(self, file_path: str, update_mode: str = 'skip') -> int:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = 0
        for d in data.get('devices', []):
            rec = DeviceRecord.from_dict(d)
            existing = self.get_by_device_id(rec.device_id)
            if existing:
                if update_mode == 'overwrite':
                    rec.id = existing.id
                    self.update_device(rec)
                    count += 1
                elif update_mode == 'skip':
                    continue
                else:
                    rec.device_id = f"{rec.device_id}_imported"
                    self.add_device(rec)
                    count += 1
            else:
                self.add_device(rec)
                count += 1
        return count
