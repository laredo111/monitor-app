from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .csv_loader import LineTarget


@dataclass
class LineState:
    is_down: bool = False
    fail_streak: int = 0
    ok_streak: int = 0
    down_since: Optional[datetime] = None
    recovered_at: Optional[datetime] = None  # כאשר הקו חזר לעבוד


@dataclass(frozen=True)
class ActiveAlert:
    site_name: str
    role: str           # "MAIN"/"BACKUP"
    line_code: str
    ip: str
    down_since: datetime
    fail_streak: int
    severity: str       # "CRITICAL" / "DEGRADED"
    is_recovered: bool = False  # האם הקו חזר לעבוד?
    recovered_at: Optional[datetime] = None  # מתי התחיל להחזיר


class MonitorCore:
    def __init__(self, down_after: int = 3, up_after: int = 2, recovery_mode: bool = False) -> None:
        self.down_after = down_after
        self.up_after = up_after
        self.recovery_mode = recovery_mode  # True = התראות מחוזרות יסתמנו בירוק 7 דקות ויעלמו
        self.state: Dict[str, LineState] = {}

    def ensure_targets(self, targets: List[LineTarget]) -> None:
        for t in targets:
            self.state.setdefault(t.target_id, LineState())
    def disable_targets(self, disabled_ids: set[str]) -> None:
        for tid in disabled_ids:
            st = self.state.get(tid)
            if not st:
                continue
            st.is_down = False
            st.fail_streak = 0
            st.ok_streak = 0
            st.down_since = None


    def update_one(self, target: LineTarget, ok: bool, now: Optional[datetime] = None) -> Tuple[bool, bool]:
        now = now or datetime.now()
        st = self.state.setdefault(target.target_id, LineState())

        went_down = False
        went_up = False

        if ok:
            st.ok_streak += 1
            st.fail_streak = 0
            if st.is_down and st.ok_streak >= self.up_after:
                if self.recovery_mode:
                    # Recovery mode: סמן את הזמן שהחזיר, אבל אל תמחק את ההתראה עדיין
                    st.recovered_at = now
                    went_up = True
                else:
                    # Mode רגיל: מחק מיד
                    st.is_down = False
                    st.down_since = None
                    st.ok_streak = 0
                    went_up = True
        else:
            st.fail_streak += 1
            st.ok_streak = 0
            # כשיש כישלון חדש, טוהר את recovered_at
            st.recovered_at = None
            if (not st.is_down) and st.fail_streak >= self.down_after:
                st.is_down = True
                st.down_since = now
                went_down = True

        return went_down, went_up

    def _site_severity_map(self, targets: List[LineTarget]) -> Dict[str, str]:
        """
        CRITICAL:
          - MAIN down AND BACKUP down
          - MAIN down AND no backup exists
        DEGRADED:
          - only one of the lines is down (while the other exists and is up)
        """
        per_site: Dict[str, dict] = {}

        for t in targets:
            info = per_site.setdefault(
                t.site_name,
                {"has_backup": False, "main_down": False, "backup_down": False},
            )
            if t.role == "BACKUP":
                info["has_backup"] = True

            st = self.state.get(t.target_id)
            if st and st.is_down:
                if t.role == "MAIN":
                    info["main_down"] = True
                elif t.role == "BACKUP":
                    info["backup_down"] = True

        severity: Dict[str, str] = {}
        for site, info in per_site.items():
            md = info["main_down"]
            bd = info["backup_down"]
            hb = info["has_backup"]

            if not md and not bd:
                continue

            # 🔴 אדום: שני הקווים למטה, או אין גיבוי והראשי למטה
            if (md and bd) or (md and not hb):
                severity[site] = "CRITICAL"
            else:
                severity[site] = "DEGRADED"

        return severity

    def get_active_alerts(self, targets: List[LineTarget]) -> List[ActiveAlert]:
        sev_map = self._site_severity_map(targets)
        now = datetime.now()

        alerts: List[ActiveAlert] = []
        for t in targets:
            st = self.state.get(t.target_id)
            if not st or not st.down_since:
                continue

            # אם הקו אינו בstatus down, בדוק אם הוא recovered
            if not st.is_down:
                if self.recovery_mode and st.recovered_at:
                    # בrecovery mode - החזק התראה ירוקה למשך 7 דקות
                    elapsed_seconds = (now - st.recovered_at).total_seconds()
                    if elapsed_seconds < 420:  # 420 = 7 דקות
                        alerts.append(
                            ActiveAlert(
                                site_name=t.site_name,
                                role=t.role,
                                line_code=t.line_code,
                                ip=t.ip,
                                down_since=st.down_since,
                                fail_streak=st.fail_streak,
                                severity=sev_map.get(t.site_name, "DEGRADED"),
                                is_recovered=True,
                                recovered_at=st.recovered_at,
                            )
                        )
                    else:
                        # הסר את ההתראה בשלמותה אחרי 7 דקות
                        st.is_down = False
                        st.down_since = None
                        st.recovered_at = None
                        st.fail_streak = 0
                        st.ok_streak = 0
                continue

            # קו עדיין למטה
            if st.is_down:
                alerts.append(
                    ActiveAlert(
                        site_name=t.site_name,
                        role=t.role,
                        line_code=t.line_code,
                        ip=t.ip,
                        down_since=st.down_since,
                        fail_streak=st.fail_streak,
                        severity=sev_map.get(t.site_name, "DEGRADED"),
                        is_recovered=False,
                    )
                )

        alerts.sort(key=lambda a: a.down_since)
        return alerts
