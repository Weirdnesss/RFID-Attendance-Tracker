import os
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from database import SessionLocal, Session as EventSession, SessionPeriod, Attendance, Program, Student
from db.students_db import YEAR_LEVEL_LABELS

def _fetch_group_counts():
    """Return {(program, yearlevel): count} from DB."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Program.code, Student.year_level,
                    func.count(Student.student_id).label("cnt"))
            .join(Program)
            .group_by(Program.code, Student.year_level)
            .order_by(Program.code, Student.year_level)
            .all()
        )
        return {(r.code or "—", YEAR_LEVEL_LABELS.get(r.year_level, "—")): r.cnt for r in rows}
    finally:
        db.close()


def get_active_session():
    """
    Returns the currently active session as a dict,
    or None if no active session exists.

    Shape matches ScanScreen.active_session.
    """
    db = SessionLocal()
    try:
        # ── Get active session with periods ─────────────────────────────
        ev = (
            db.query(EventSession)
            .options(joinedload(EventSession.periods))
            .filter(EventSession.is_active == 1)
            .first()
        )

        if not ev:
            return None

        # ── Build periods list ──────────────────────────────────────────
        periods = []
        period_ids = []

        for p in sorted(ev.periods, key=lambda x: x.sort_order):
            periods.append({
                "id":              p.id,
                "name":            p.name,
                "sort_order":      p.sort_order,
                "time_in_start":   p.time_in_start,
                "time_in_end":     p.time_in_end,
                "grace_minutes":   p.grace_minutes,
                "late_enabled":    p.late_enabled,
                "late_start":      p.late_start,
                "timeout_enabled": p.timeout_enabled,
                "timeout_start":   p.timeout_start,
                "timeout_end":     p.timeout_end,
            })
            period_ids.append(p.id)

        # ── Total scan count ────────────────────────────────────────────
        total_count = (
            db.query(func.count(Attendance.id))
            .filter(Attendance.session_id == ev.id)
            .scalar()
        )

        # ── Period stats (lightweight aggregation) ──────────────────────
        stats_rows = (
            db.query(
                Attendance.period_id,
                Attendance.status,
                func.count().label("cnt")
            )
            .filter(Attendance.session_id == ev.id)
            .group_by(Attendance.period_id, Attendance.status)
            .all()
        )

        period_stats = {}

        for row in stats_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = {"scanned": 0, "late": 0, "timed_out": 0}

            if row.status == "late":
                period_stats[pid]["late"] += row.cnt
            else:
                period_stats[pid]["scanned"] += row.cnt

        # ── Timed-out count (separate because it's time_out based) ──────
        timeout_rows = (
            db.query(
                Attendance.period_id,
                func.count().label("cnt")
            )
            .filter(
                Attendance.session_id == ev.id,
                Attendance.time_out.isnot(None)
            )
            .group_by(Attendance.period_id)
            .all()
        )

        for row in timeout_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = {"scanned": 0, "late": 0, "timed_out": 0}
            period_stats[pid]["timed_out"] = row.cnt

        # ── Build final dict ────────────────────────────────────────────
        return {
            "id": ev.id,
            "name": ev.name,
            "periods": periods,
            "count": total_count or 0,
            "estimated_attendees": ev.estimated_attendees,
            "breakdown": {
                "present": total_count or 0,  # optional refinement later
                "late": sum(v["late"] for v in period_stats.values())
            },
            "period_stats": period_stats
        }

    finally:
        db.close()