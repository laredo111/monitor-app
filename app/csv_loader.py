from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class LineTarget:
    site_name: str
    role: str            # "MAIN" / "BACKUP"
    line_code: str
    ip: str
    enabled: bool = True

    @property
    def target_id(self) -> str:
        return f"{self.site_name}|{self.role}|{self.line_code}|{self.ip}"


def _to_bool(v: str) -> bool:
    v = (v or "").strip()
    if v == "":
        return True
    return v not in ("0", "false", "no", "off")


def load_targets(csv_path: Path) -> Tuple[List[LineTarget], List[str]]:
    """
    Supports 'site-per-row' format:
    SiteName, MainLineCode, MainIP, BackupLineCode, BackupIP, enabled
    """
    warnings: List[str] = []
    targets: List[LineTarget] = []

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        # Normalize header names (strip spaces)
        fieldnames = [h.strip() for h in reader.fieldnames if h]
        reader.fieldnames = fieldnames

        required = {"SiteName", "MainLineCode", "MainIP", "BackupLineCode", "BackupIP", "enabled"}
        missing = [c for c in required if c not in fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):  # header = line 1
            try:
                site = (row.get("SiteName") or "").strip()
                enabled = _to_bool(row.get("enabled") or "")

                main_code = (row.get("MainLineCode") or "").strip()
                main_ip = (row.get("MainIP") or "").strip()

                backup_code = (row.get("BackupLineCode") or "").strip()
                backup_ip = (row.get("BackupIP") or "").strip()

                if not site:
                    warnings.append(f"Line {i}: SiteName is empty (skipped)")
                    continue

                # MAIN
                if main_ip and main_code:
                    targets.append(LineTarget(site, "MAIN", main_code, main_ip, enabled))
                else:
                    warnings.append(f"Line {i} ({site}): missing MainIP/MainLineCode (MAIN skipped)")

                # BACKUP (optional)
                if backup_ip and backup_code:
                    targets.append(LineTarget(site, "BACKUP", backup_code, backup_ip, enabled))
                else:
                    # no warning when backup is empty - it's valid
                    pass

            except Exception as e:
                warnings.append(f"Line {i}: parse error: {e}")

    return targets, warnings
