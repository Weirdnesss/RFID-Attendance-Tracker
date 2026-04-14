"""Session-related database queries."""

from sqlalchemy import func, case
from database import (SessionLocal, Session as EventSession, SessionPeriod, Attendance, Student)
from db.students_db import YEAR_LEVEL_LABELS

def _fetch_sessions(search="", offset=0, limit=10):
    db = SessionLocal()
    try:
        q = (
            db.query(
                EventSession,
                func.count(func.distinct(Attendance.id)).label("total"),
                func.count(func.distinct(
                    case((Attendance.status == "present", Attendance.id))
                )).label("present"),
                func.count(func.distinct(
                    case((Attendance.status == "late", Attendance.id))
                )).label("late"),
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

        result = []
        for s, total, present, late, period_count in rows:
            total     = total or 0
            present   = present or 0
            late      = late or 0
            estimated = s.estimated_attendees or 0

            result.append({
                "id":                  s.id,
                "name":                s.name,
                "date":                s.date,
                "created_at":          s.created_at,
                "estimated_attendees": estimated,
                "total":               total,
                "present":             present,
                "late":                late,
                "absent":              max(0, estimated - present - late),
                "period_count":        period_count or 0,
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

def _fetch_session_detail(session_id: int):
    db = SessionLocal()
    try:
        records = (
            db.query(Attendance, Student, SessionPeriod)
            .join(Student, Attendance.student_id == Student.student_id)
            .join(SessionPeriod, Attendance.period_id == SessionPeriod.id)
            .filter(Attendance.session_id == session_id)
            .order_by(SessionPeriod.sort_order, Attendance.time_in)
            .all()
        )
        return [
            {
                "student_id":  stu.student_id,
                "name":        f"{stu.first_name} {stu.last_name}",
                "program":     stu.program.code if stu.program else "—",
                "yearlevel":   YEAR_LEVEL_LABELS.get(stu.year_level, "—"),
                "period_name": period.name,
                "status":      att.status,
                "time_in":     att.time_in.strftime("%I:%M:%S %p")
                               if att.time_in else "—",
                "time_out":    att.time_out.strftime("%I:%M:%S %p")
                               if att.time_out else "—",
            }
            for att, stu, period in records
        ]
    finally:
        db.close()
