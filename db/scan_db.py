import os
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from database import SessionLocal, Session as EventSession, SessionPeriod, Attendance, Program, Student, StaffAttendance, Staff
from db.students_db import YEAR_LEVEL_LABELS

from sqlalchemy.exc import IntegrityError

def start_session(name, date, periods, academic_period_id,
                  terminal_id, attendee_type="students",
                  student_filter=None, staff_filter=None, 
                  student_estimated=0, staff_estimated=0):
    db = SessionLocal()
    try:
        new_session = EventSession(
            name=name,
            date=date,
            student_estimated=student_estimated,
            staff_estimated=staff_estimated,
            academic_period_id=academic_period_id,
            is_active=1,
            active_flag=1,
            attendee_type=attendee_type,
            student_filter=student_filter,
            staff_filter=staff_filter,
        )
        db.add(new_session)
        db.flush()

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
            session.active_flag = None
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


def _empty_type_stats():
    return {"scanned": 0, "late": 0, "timed_out": 0}


def _empty_period_stats():
    return {"students": _empty_type_stats(), "staff": _empty_type_stats()}


def get_session_by_id(session_id: int):
    """
    Returns a session as a dict by ID, or None if not found.
    Shape matches ScanScreen.active_session.

    period_stats shape:
        {
            period_id: {
                "students": {"scanned": N, "late": N, "timed_out": N},
                "staff":    {"scanned": N, "late": N, "timed_out": N},
            },
            ...
        }
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

        # ── Initialise period_stats with the split shape ────────────────
        period_stats = {pid: _empty_period_stats() for pid in period_ids}

        # ── Student scan-in counts (grouped by period + status) ─────────
        student_rows = (
            db.query(
                Attendance.period_id,
                Attendance.status,
                func.count().label("cnt")
            )
            .filter(Attendance.session_id == ev.id)
            .group_by(Attendance.period_id, Attendance.status)
            .all()
        )

        for row in student_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = _empty_period_stats()
            stu = period_stats[pid]["students"]
            if row.status == "late":
                stu["late"] += row.cnt
            stu["scanned"] += row.cnt   # every scan-in counts (present + late)

        # ── Student scan-out counts ─────────────────────────────────────
        student_out_rows = (
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

        for row in student_out_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = _empty_period_stats()
            period_stats[pid]["students"]["timed_out"] = row.cnt

        # ── Staff scan-in counts ────────────────────────────────────────
        staff_rows = (
            db.query(
                StaffAttendance.period_id,
                StaffAttendance.status,
                func.count().label("cnt")
            )
            .filter(StaffAttendance.session_id == ev.id)
            .group_by(StaffAttendance.period_id, StaffAttendance.status)
            .all()
        )

        for row in staff_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = _empty_period_stats()
            stf = period_stats[pid]["staff"]
            if row.status == "late":
                stf["late"] += row.cnt
            stf["scanned"] += row.cnt

        # ── Staff scan-out counts ───────────────────────────────────────
        staff_out_rows = (
            db.query(
                StaffAttendance.period_id,
                func.count().label("cnt")
            )
            .filter(
                StaffAttendance.session_id == ev.id,
                StaffAttendance.time_out.isnot(None)
            )
            .group_by(StaffAttendance.period_id)
            .all()
        )

        for row in staff_out_rows:
            pid = row.period_id
            if pid not in period_stats:
                period_stats[pid] = _empty_period_stats()
            period_stats[pid]["staff"]["timed_out"] = row.cnt

        # ── Total counts ────────────────────────────────────────────────
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
        total_late = sum(
            v["students"]["late"] + v["staff"]["late"]
            for v in period_stats.values()
        )

        # ── Build final dict ────────────────────────────────────────────
        return {
            "id":               ev.id,
            "name":             ev.name,
            "attendee_type":    ev.attendee_type,
            "periods":          periods,
            "count":            total_count,
            "breakdown": {
                "present": total_count,
                "late":    total_late,
            },
            "period_stats":      period_stats,
            "student_filter":    ev.student_filter,
            "staff_filter":      ev.staff_filter,
            "student_estimated": ev.student_estimated or 0,
            "staff_estimated":   ev.staff_estimated   or 0,
        }

    finally:
        db.close()