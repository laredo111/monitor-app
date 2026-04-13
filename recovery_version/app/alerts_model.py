from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor


@dataclass(frozen=True)
class AlertRow:
    site_name: str
    role: str
    line_code: str
    ip: str
    down_since: datetime
    fail_streak: int
    severity: str  # "CRITICAL" / "DEGRADED"
    is_recovered: bool = False  # האם הקו חזר (צבע ירוק)?


class AlertsTableModel(QAbstractTableModel):
    headers = ["אתר", "סוג קו", "קוד קו", "IP", "נפל ב-", "משך נפילה"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[AlertRow] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.headers[section]
        return section + 1

    def set_alerts(self, alerts: List[AlertRow]) -> None:
        self.beginResetModel()
        self._rows = list(alerts)
        self.endResetModel()

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return row.site_name
            if col == 1:
                return "ראשי" if row.role == "MAIN" else "גיבוי"
            if col == 2:
                return row.line_code
            if col == 3:
                return row.ip
            if col == 4:
                return row.down_since.strftime("%d/%m/%Y %H:%M:%S")
            if col == 5:
                total = int((datetime.now() - row.down_since).total_seconds())
                hh = total // 3600
                mm = (total % 3600) // 60
                ss = total % 60
                return f"{hh:02d}:{mm:02d}:{ss:02d}"


        if role == Qt.TextAlignmentRole:
            if col == 0:
                return Qt.AlignVCenter | Qt.AlignCenter

            return Qt.AlignVCenter | Qt.AlignCenter

        # צבע שורה לפי חומרה
        if role == Qt.BackgroundRole:
            if row.is_recovered:
                return QColor("#004d00")   # ירוק כהה (חזרה לעבוד)
            if row.severity == "CRITICAL":
                return QColor("#7a0000")   # אדום כהה
            return QColor("#8a5a00")       # כתום כהה

        return None
