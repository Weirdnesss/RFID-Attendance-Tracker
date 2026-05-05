import os
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from database import SessionLocal, Session as EventSession, SessionPeriod, Attendance, Program, Student, StaffAttendance, Staff
from db.students_db import YEAR_LEVEL_LABELS

from sqlalchemy.exc import IntegrityError

def start_session(name, date, estimated_attendees, periods, academic_period_id,
                  terminal_id, attendee_type="students",
                  student_filter=None, staff_filter=None):
    db = SessionLocal()
    try:
        new_session = EventSession(
            name=name,
            date=date,
            estimated_attendees=estimated_attendees,
            academic_period_id=academic_period_id,
            is_active=1,
            active_flag=1,
            attendee_type=attendee_type,       # ← new
            student_filter=student_filter,     # ← new
            staff_filter=staff_filter,         # ← new
        )
        db.add(new_session)
        db.flush()  # get the new session ID before adding periods

        for p in periods:
            db.add(SessionPeriod(
                session_id=new_session.id,
                **p
            ))

        db.commit()
        return True, new_session.id, "Session started"

    except IntegrityError:
        db.rollback()
        return False, None, "A session is already active on another PC"
    finally:
        db.close()

def end_session(session_id):
    db = SessionLocal()
    try:
        session = db.query(EventSession).filter(EventSession.id == session_id).first()
        if session:
            session.is_active = 0
            session.active_flag = None  # releases the unique slot
            db.commit()
            return True
        return False
    finally:
        db.close()

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

def get_session_by_id(session_id: int):
    """
    Returns a session as a dict by ID, or None if not found.
    Shape matches ScanScreen.active_session.
    """
    db = SessionLocal()
    try:
        ev = (
            db.query(EventSession)
            .options(joinedload(EventSession.periods))
            .filter(EventSession.id == session_id)
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
        student_count = (
            db.query(func.count(Attendance.id))
            .filter(Attendance.session_id == ev.id)
            .scalar()
        ) or 0

        staff_count = (
            db.query(func.count(StaffAttendance.id))
            .filter(StaffAttendance.session_id == ev.id)
            .scalar()
        ) or 0

        total_count = student_count + staff_count

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
            "attendee_type": ev.attendee_type,
            "periods": periods,
            "count": total_count or 0,
            "estimated_attendees": ev.estimated_attendees,
            "breakdown": {
                "present": total_count or 0,  # optional refinement later
                "late": sum(v["late"] for v in period_stats.values())
            },
            "period_stats": period_stats,
            "student_filter": ev.student_filter,
            "staff_filter":   ev.staff_filter, 
                }

    finally:
        db.close()