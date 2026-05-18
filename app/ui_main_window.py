from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QTableView,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHeaderView,
    QMessageBox,
)

from .alerts_model import AlertsTableModel, AlertRow
from .csv_loader import load_targets, LineTarget
from .logger_setup import setup_logger
from .monitor_core import MonitorCore
from .ping_engine import ping_once_windows
import winsound


# ---------------------------------------------------------------------------
# Background worker – runs the ping cycle off the main thread
# ---------------------------------------------------------------------------

class _PingWorker(QThread):
    """
    Submits pings to the thread pool and collects results in a background
    thread, so the Qt main thread (and its event loop) is never blocked.
    """

    done = Signal(object)  # emits list[tuple[LineTarget, bool]]

    def __init__(
        self,
        targets: list[LineTarget],
        pool: ThreadPoolExecutor,
        logger,
    ) -> None:
        super().__init__()
        self._targets = targets
        self._pool = pool
        self._logger = logger

    def run(self) -> None:
        futures = []
        for t in self._targets:
            futures.append((t, self._pool.submit(ping_once_windows, t.ip, 1000)))
            time.sleep(0.05)  # stagger ICMP packets to avoid burst-load on switches
        results: list[tuple[LineTarget, bool]] = []
        for t, fut in futures:
            try:
                res = fut.result(timeout=6)
                results.append((t, res.ok))
            except Exception:
                self._logger.exception(
                    'Ping exception site="%s" role=%s ip=%s',
                    t.site_name, t.role, t.ip,
                )
                results.append((t, False))
        self.done.emit(results)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._prev_active_alert_ids: set[str] = set()
        self.setWindowTitle("ניטור קווי תקשורת – תקלות פעילות")
        self.setMinimumSize(1100, 650)
        # בסיס + לוגים
        self.base_dir = Path.cwd()
        self.logger = setup_logger(self.base_dir)
        self.logger.info("START | app booting | base_dir=%s", str(self.base_dir))
        self.logger.info(
            "CONFIG | ping_interval_sec=%s down_after=%s up_after=%s workers=%s",
            10, 3, 2, 60
        )
        self.logger.info(
            "FILES | csv=%s log_file=%s",
            str(self.base_dir / "sites.csv"),
            str(self.base_dir / "logs" / "monitor.log"),
        )

        # טוענים targets מה-CSV
        self.targets: list[LineTarget] = []
        self._load_csv()

        # Core state
        self.core = MonitorCore(down_after=3, up_after=2)
        self.core.ensure_targets(self.targets)
        self._apply_disabled_now()  # ✅ מוחק התראות לקווים disabled מיד

        # ThreadPool for pings – size matched to actual target count (never more
        # than needed, never fewer than 4).  Significantly reduces thread
        # overhead compared to the old hard-coded 60-worker pool.
        n_workers = min(max(len(self.targets), 4), 60)
        self.pool = ThreadPoolExecutor(max_workers=n_workers)

        # Background ping worker state
        self._ping_worker: _PingWorker | None = None
        self._ping_now: datetime = datetime.now()

        # CSV reload tracking
        self.csv_path = self.base_dir / "sites.csv"
        self.csv_mtime = self.csv_path.stat().st_mtime if self.csv_path.exists() else 0

        # Model + View
        self.model = AlertsTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)

        # ✅ הסתרה מלאה של "עמודת מספרי השורות"
        vh = self.table.verticalHeader()
        vh.hide()
        vh.setFixedWidth(0)

        # hide row header completely + no frame
        self.table.setFrameShape(QTableView.NoFrame)

        # hide scrollbars (TV mode)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # avoid layout margins that can look like a column
        self.table.setContentsMargins(0, 0, 0, 0)

        # RTL + TV
        self.table.setLayoutDirection(Qt.RightToLeft)

        font = self.table.font()
        font.setPointSize(20)
        font.setBold(True)
        self.table.setFont(font)

        # גובה שורות
        self.table.verticalHeader().setDefaultSectionSize(52)

        self.table.setTextElideMode(Qt.ElideNone)
        self.table.horizontalHeader().setTextElideMode(Qt.ElideNone)
        self.table.setWordWrap(False)

        # צבעים כלליים לטבלה
        pal = self.table.palette()
        pal.setColor(QPalette.Base, QColor("#1e1e1e"))
        pal.setColor(QPalette.AlternateBase, QColor("#2a2a2a"))
        pal.setColor(QPalette.Text, QColor("#ffffff"))
        pal.setColor(QPalette.Highlight, QColor("#3d3d3d"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.table.setPalette(pal)

        self.table.setAlternatingRowColors(True)

        header_font = self.table.horizontalHeader().font()
        header_font.setPointSize(18)
        header_font.setBold(True)
        self.table.horizontalHeader().setFont(header_font)
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { color: white; background-color: #333333; }"
        )

        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # אתר
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 140)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 140)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 210)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 340)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 190)

        # Layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.table)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_last = QLabel("בדיקה אחרונה: --:--:--")
        self.lbl_last.setStyleSheet("color: white; font-size: 16px;")

        self.lbl_counts = QLabel("")
        self.lbl_counts.setStyleSheet("color: white; font-size: 16px;")

        self.status.addPermanentWidget(self.lbl_last)
        self.status.addPermanentWidget(self.lbl_counts)

        # Timer לעדכון duration (כל שניה)
        self.ui_tick = QTimer(self)
        self.ui_tick.setInterval(1000)
        self.ui_tick.timeout.connect(self._tick_ui)
        self.ui_tick.start()

        # Timer לבדיקות ping (כל 10 שניות)
        self.ping_timer = QTimer(self)
        self.ping_timer.setInterval(10_000)
        self.ping_timer.timeout.connect(self._run_ping_cycle)
        self.ping_timer.start()

        # CSV auto reload every 30 seconds
        self.csv_timer = QTimer(self)
        self.csv_timer.setInterval(30_000)
        self.csv_timer.timeout.connect(self._check_csv_reload)
        self.csv_timer.start()

        # ריצה ראשונה מיד
        QTimer.singleShot(200, self._run_ping_cycle)

        self._refresh_status_bar()

    def closeEvent(self, event) -> None:
        try:
            self.pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        super().closeEvent(event)

    def _base_dir(self) -> Path:
        return self.base_dir

    def _apply_disabled_now(self) -> None:
        """
        ✅ מוחק מצב DOWN לקווים שהוגדרו enabled=0
        כך שההתראות ייעלמו מיד.
        """
        try:
            disabled_ids = {t.target_id for t in self.targets if not getattr(t, "enabled", True)}
            if disabled_ids:
                self.core.disable_targets(disabled_ids)
        except Exception:
            # לא להפיל UI על זה
            self.logger.exception("Failed applying disabled targets")

    def _check_csv_reload(self) -> None:
        if not self.csv_path.exists():
            return

        try:
            mtime = self.csv_path.stat().st_mtime
        except OSError:
            return

        if mtime <= self.csv_mtime:
            return

        self.csv_mtime = mtime
        self.logger.info("CSV CHANGE DETECTED – reloading")

        try:
            targets, warnings_list = load_targets(self.csv_path)
        except Exception as e:
            self.logger.error("CSV reload failed: %s", e)
            return

        old_count = len(self.targets)
        self.targets = targets

        # חשוב: לא מאפס state, רק מוסיף state לחדשים
        self.core.ensure_targets(self.targets)

        # ✅ מוחק מיד התראות לקווים שהפכו ל-enabled=0
        self._apply_disabled_now()

        self.logger.info("CSV RELOADED | targets: %d -> %d", old_count, len(self.targets))

        if warnings_list:
            self.logger.warning("CSV reload warnings: %s", " | ".join(warnings_list))

        # אופציונלי: ריצה מיידית אחרי שינוי CSV
        self._run_ping_cycle()

    def _load_csv(self) -> None:
        csv_path = self._base_dir() / "sites.csv"
        try:
            self.targets, warnings_list = load_targets(csv_path)
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בטעינת CSV", f"לא הצלחתי לקרוא את sites.csv\n\n{e}")
            self.targets = []
            return

        if warnings_list:
            self.logger.warning("CSV warnings: %s", " | ".join(warnings_list))
            QMessageBox.warning(
                self,
                "אזהרות בטעינת CSV",
                "הקובץ נטען, אבל יש אזהרות.\nנמשיך בכל זאת.\n\n"
                + "\n".join(warnings_list[:12])
                + ("\n..." if len(warnings_list) > 12 else "")
            )

        self.logger.info(
            "Loaded CSV: sites=%d lines=%d",
            len({t.site_name for t in self.targets}),
            len(self.targets),
        )
        main_count = sum(1 for t in self.targets if t.role == "MAIN")
        backup_count = sum(1 for t in self.targets if t.role == "BACKUP")
        enabled_count = sum(1 for t in self.targets if getattr(t, "enabled", True))
        self.logger.info(
            "Loaded CSV details: main=%d backup=%d enabled=%d disabled=%d",
            main_count, backup_count, enabled_count, len(self.targets) - enabled_count
        )

    def _run_ping_cycle(self) -> None:
        """
        Start a ping cycle in a background thread.
        If the previous cycle is still running, skip this tick to avoid
        piling up workers (can happen if targets are all timing out).
        """
        if not self.targets:
            return

        # Skip if a worker is still busy from the previous cycle
        if self._ping_worker is not None and self._ping_worker.isRunning():
            return

        # ✅ מנטרים רק enabled
        active_targets = [t for t in self.targets if getattr(t, "enabled", True)]

        # אם אין קווים פעילים – מנקים תצוגה ומעדכנים סטטוס
        if not active_targets:
            self.model.set_alerts([])
            self.lbl_last.setText("בדיקה אחרונה: " + datetime.now().strftime("%H:%M:%S"))
            self._refresh_status_bar()
            return

        # Snapshot "now" so all results in this cycle share the same timestamp
        self._ping_now = datetime.now()

        # Launch worker – result collection happens off the main thread
        self._ping_worker = _PingWorker(active_targets, self.pool, self.logger)
        self._ping_worker.done.connect(self._on_ping_results)
        self._ping_worker.start()

    def _on_ping_results(self, results: list) -> None:
        """
        Called on the main thread (via Qt signal) when the background
        ping worker has collected all results.
        """
        now = self._ping_now
        went_down_events: list[str] = []
        went_up_events: list[str] = []

        for t, res_ok in results:
            went_down, went_up = self.core.update_one(t, ok=res_ok, now=now)
            if went_down:
                went_down_events.append(f'{t.site_name} {t.role} {t.line_code} {t.ip}')
            if went_up:
                went_up_events.append(f'{t.site_name} {t.role} {t.line_code} {t.ip}')

        # לוג אירועים בלבד
        for msg in went_down_events:
            self.logger.error("DOWN | %s", msg)
        for msg in went_up_events:
            self.logger.info("UP   | %s", msg)

        # ✅ בונים רשימת התראות להצגה (רק קווים פעילים)
        active_targets = [t for t in self.targets if getattr(t, "enabled", True)]
        active_alerts = self.core.get_active_alerts(active_targets)

        rows = [
            AlertRow(
                site_name=a.site_name,
                role=a.role,
                line_code=a.line_code,
                ip=a.ip,
                down_since=a.down_since,
                fail_streak=a.fail_streak,
                severity=getattr(a, "severity", "DEGRADED"),
            )
            for a in active_alerts
        ]

        # ---- Beep once per cycle if NEW alerts appeared ----
        current_ids = {
            f"{r.site_name}|{r.role}|{r.line_code}|{r.ip}"
            for r in rows
        }
        new_ids = current_ids - self._prev_active_alert_ids
        if new_ids:
            try:
                winsound.Beep(1000, 800)
            except Exception:
                pass
        self._prev_active_alert_ids = current_ids
        # -----------------------------------------------------

        self.model.set_alerts(rows)
        self.lbl_last.setText("בדיקה אחרונה: " + now.strftime("%H:%M:%S"))
        self._refresh_status_bar()

    def _tick_ui(self) -> None:
        # רענון "משך נפילה" (עמודה 5)
        if self.model.rowCount() > 0:
            top_left = self.model.index(0, 5)
            bottom_right = self.model.index(self.model.rowCount() - 1, 5)
            self.model.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])

    def _refresh_status_bar(self) -> None:
        active_alerts = self.model.rowCount()
        sites = len({t.site_name for t in self.targets})
        enabled_count = sum(1 for t in self.targets if getattr(t, "enabled", True))
        disabled_count = len(self.targets) - enabled_count
        self.lbl_counts.setText(
            f"תקלות פעילות: {active_alerts} | אתרים: {sites} | פעילים: {enabled_count} | מושבתים: {disabled_count}"
        )
