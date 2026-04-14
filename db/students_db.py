"""Student-related database queries."""

from sqlalchemy import func, case
from database import (SessionLocal, Session as EventSession, SessionPeriod, Attendance, Student, Program)

PAGE_SIZE = 20
STUDENT_SIZE = 10
YEAR_LEVEL_LABELS = {
    1: "1st Year",
    2: "2nd Year",
    3: "3rd Year",
    4: "4th Year",
    5: "5th Year",
}

def _fetch_students(search="", program="Course", yearlevel="Year",
                    offset=0, limit=PAGE_SIZE):

    db = SessionLocal()
    try:
        # ── Base queries ──────────────────────────────────────────────
        q = db.query(Student)
        total_q = db.query(func.count(Student.student_id))

        # ── Filters ───────────────────────────────────────────────────
        if search:
            like = f"%{search}%"
            cond = (
                (Student.first_name.ilike(like)) |
                (Student.last_name.ilike(like)) |
                (Student.student_id.like(like))
            )
            q = q.filter(cond)
            total_q = total_q.filter(cond)

        if program != "Course":
            q = q.join(Program).filter(Program.code == program)
            total_q = total_q.join(Program).filter(Program.code == program)

        if yearlevel != "Year":
            level_int = next(k for k, v in YEAR_LEVEL_LABELS.items() if v == yearlevel)
            q = q.filter(Student.year_level == level_int)
            total_q = total_q.filter(Student.year_level == level_int)

        # ── Total count (FAST) ────────────────────────────────────────
        total_count = total_q.scalar()

        # ── Get current page students ─────────────────────────────────
        students = (
            q.order_by(Student.last_name, Student.first_name)
             .offset(offset)
             .limit(limit)
             .all()
        )

        if not students:
            return [], total_count

        # ── Fetch stats ONLY for current page ─────────────────────────
        student_ids = [s.student_id for s in students]

        present_case = case((Attendance.status == "present", 1), else_=0)
        late_case    = case((Attendance.status == "late",    1), else_=0)

        stats = (
            db.query(
                Attendance.student_id,
                func.count(Attendance.id).label("total"),
                func.sum(present_case).label("present"),
                func.sum(late_case).label("late"),
            )
            .filter(Attendance.student_id.in_(student_ids))
            .group_by(Attendance.student_id)
            .all()
        )

        # Convert stats to dict for fast lookup
        stats_map = {
            s.student_id: {
                "total": s.total or 0,
                "present": s.present or 0,
                "late": s.late or 0,
            }
            for s in stats
        }

        # ── Build result ──────────────────────────────────────────────
        result = []
        for stu in students:
            s = stats_map.get(stu.student_id, {"total": 0, "present": 0, "late": 0})

            result.append({
                "student_id":  stu.student_id,
                "firstname":   stu.first_name  or "",
                "lastname":    stu.last_name   or "",
                "middlename":  stu.middle_name or "",
                "program":     stu.program.name if stu.program else "—",
                "code":        stu.program.code if stu.program else "—",
                "yearlevel":   YEAR_LEVEL_LABELS.get(stu.year_level, "—"),
                "total":       s["total"],
                "present":     s["present"],
                "late":        s["late"],
            })

        return result, total_count

    finally:
        db.close()

def _fetch_filter_options():
    """Return unique values for filter dropdowns."""
    db = SessionLocal()
    try:
        programs = sorted({
            r[0] for r in db.query(Program.code).distinct() if r[0]})
        yearlevels = sorted({
            YEAR_LEVEL_LABELS[r[0]] for r in db.query(Student.year_level).distinct() if r[0]})
        return programs, yearlevels
    finally:
        db.close()

def _fetch_student_attendance(student_id: int, offset: int = 0, limit: int = STUDENT_SIZE):
    db = SessionLocal()
    try:
        total = (
            db.query(func.count(Attendance.id))
            .filter(Attendance.student_id == student_id)
            .scalar()
        )
        records = (
            db.query(Attendance, EventSession, SessionPeriod)
            .join(EventSession, Attendance.session_id == EventSession.id)
            .join(SessionPeriod, Attendance.period_id == SessionPeriod.id)
            .filter(Attendance.student_id == student_id)
            .order_by(Attendance.time_in.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return total, [
            {
                "session_name": sess.name,
                "date":         str(sess.date),
                "period_name":  period.name,
                "status":       att.status,
                "time_in":      att.time_in.strftime("%I:%M:%S %p") if att.time_in else "—",
                "time_out":     att.time_out.strftime("%I:%M:%S %p") if att.time_out else "—",
            }
            for att, sess, period in records
        ]
    finally:
        db.close()
