"""Session-related database queries."""

from sqlalchemy import func, case
from database import (SessionLocal, Session as EventSession, SessionPeriod,
                      Attendance, Student, StaffAttendance, Staff,
                      Department, Role)
from db.students_db import YEAR_LEVEL_LABELS


def _fetch_sessions(search="", offset=0, limit=10):
    db = SessionLocal()
    try:
        q = (
            db.query(
                EventSession,
                func.count(func.distinct(Attendance.id)).label("student_total"),
                func.count(func.distinct(
                    case((Attendance.status == "present", Attendance.id))
                )).label("student_present"),
                func.count(func.distinct(
                    case((Attendance.status == "late", Attendance.id))
                )).label("student_late"),
                func.count(func.distinct(SessionPeriod.id)).label("period_count"),
            )
            .outerjoin(Attendance, Attendance.session_id == EventSession.id)
            .outerjoin(SessionPeriod, SessionPeriod.session_id == EventSession.id)
            .group_by(EventSession.id)
        )

        if search:
            like = f"%{search}%"
            q = q.filter(
                (EventSession.name.ilike(like)) |
                (EventSession.date.like(like))
            )

        total_count = q.count()

        rows = (
            q.order_by(EventSession.date.desc(), EventSession.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Fetch staff counts separately for sessions in this page
        session_ids = [s.id for s, *_ in rows]

        staff_stats = {}
        if session_ids:
            staff_rows = (
                db.query(
                    StaffAttendance.session_id,
                    func.count(StaffAttendance.id).label("total"),
                    func.count(case((StaffAttendance.status == "present",
                                     StaffAttendance.id))).label("present"),
                    func.count(case((StaffAttendance.status == "late",
                                     StaffAttendance.id))).label("late"),
                )
                .filter(StaffAttendance.session_id.in_(session_ids))
                .group_by(StaffAttendance.session_id)
                .all()
            )
            for r in staff_rows:
                staff_stats[r.session_id] = {
                    "total":   r.total   or 0,
                    "present": r.present or 0,
                    "late":    r.late    or 0,
                }

        result = []
        for s, student_total, student_present, student_late, period_count in rows:
            student_total   = student_total   or 0
            student_present = student_present or 0
            student_late    = student_late    or 0
            student_estimated = getattr(s, "estimated_attendees", None)
            atype           = getattr(s, "attendee_type", "students") or "students"

            ss = staff_stats.get(s.id, {"total": 0, "present": 0, "late": 0})

            total_present = student_present + student_late + ss["present"] + ss["late"]
            total         = student_total + ss["total"]
            #absent        = max(0, estimated - total_present) if estimated else 0

            result.append({
                "id":                  s.id,
                "name":                s.name,
                "date":                s.date,
                "created_at":          s.created_at,
                "student_estimated":   student_estimated,
                "attendee_type":       atype,
                # combined (for list item display)
                "total":               total,
                "present":             student_present + ss["present"],
                "late":                student_late    + ss["late"],
                # "absent":              absent,
                "period_count":        period_count or 0,
                # per-type breakdown (for detail panel)
                "student_present":     student_present,
                "student_late":        student_late,      
                "staff_present":       ss["present"],
                "staff_late":          ss["late"],
            })

        return result, total_count

    finally:
        db.close()


def _fetch_session_periods(session_id: int):
    db = SessionLocal()
    try:
        periods = (
            db.query(SessionPeriod)
            .filter_by(session_id=session_id)
            .order_by(SessionPeriod.sort_order)
            .all()
        )
        return [
            {
                "id":              p.id,
                "name":            p.name,
                "sort_order":      p.sort_order,
                "time_in_start":   p.time_in_start.strftime("%I:%M %p"),
                "time_in_end":     p.time_in_end.strftime("%I:%M %p"),
                "grace_minutes":   p.grace_minutes,
                "late_enabled":    p.late_enabled,
                "late_start":      p.late_start.strftime("%I:%M %p") if p.late_start else None,
                "timeout_enabled": p.timeout_enabled,
                "timeout_start":   p.timeout_start.strftime("%I:%M %p") if p.timeout_start else None,
                "timeout_end":     p.timeout_end.strftime("%I:%M %p") if p.timeout_end else None,
            }
            for p in periods
        ]
    finally:
        db.close()


def _fetch_session_detail(session_id: int) -> dict:
    """
    Returns {"students": [...], "staff": [...]}
    Each list contains dicts ready for the record pool renderer.
    """
    db = SessionLocal()
    try:
        # ── Students ──────────────────────────────────────────────────
        student_records = (
            db.query(Attendance, Student, SessionPeriod)
            .join(Student, Attendance.student_id == Student.student_id)
            .join(SessionPeriod, Attendance.period_id == SessionPeriod.id)
            .filter(Attendance.session_id == session_id)
            .order_by(SessionPeriod.sort_order, Attendance.time_in)
            .all()
        )

        students = [
            {
                "entity_id":   str(stu.student_id),
                "name":        f"{stu.first_name} {stu.last_name}",
                "col3":        stu.program.code if stu.program else "—",
                "col4":        YEAR_LEVEL_LABELS.get(stu.year_level, "—"),
                "period_name": period.name,
                "status":      att.status,
                "time_in":     att.time_in.strftime("%I:%M:%S %p")  if att.time_in  else "—",
                "time_out":    att.time_out.strftime("%I:%M:%S %p") if att.time_out else "—",
            }
            for att, stu, period in student_records
        ]

        # ── Staff ─────────────────────────────────────────────────────
        staff_records = (
            db.query(StaffAttendance, Staff, SessionPeriod)
            .join(Staff, StaffAttendance.staff_id == Staff.staff_id)
            .join(SessionPeriod, StaffAttendance.period_id == SessionPeriod.id)
            .filter(StaffAttendance.session_id == session_id)
            .order_by(SessionPeriod.sort_order, StaffAttendance.time_in)
            .all()
        )

        staff = [
            {
                "entity_id":   str(st.staff_id),
                "name":        f"{st.first_name} {st.last_name}",
                "col3":        st.department_ref.code if st.department_ref else (st.department or "—"),
                "col4":        st.role_ref.name if st.role_ref else (st.role or "—"),
                "period_name": period.name,
                "status":      att.status,
                "time_in":     att.time_in.strftime("%I:%M:%S %p")  if att.time_in  else "—",
                "time_out":    att.time_out.strftime("%I:%M:%S %p") if att.time_out else "—",
            }
            for att, st, period in staff_records
        ]

        return {"students": students, "staff": staff}

    finally:
        db.close()