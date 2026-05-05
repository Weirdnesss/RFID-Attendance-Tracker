"""Staff-related database queries."""

from sqlalchemy import func, case
from database import (SessionLocal, Session as EventSession,
                      SessionPeriod, StaffAttendance, Staff, Department, Role)

PAGE_SIZE = 20
STAFF_SIZE = 10


def _fetch_staff(search="", department="Department", role="Role",
                 offset=0, limit=PAGE_SIZE):
    db = SessionLocal()
    try:
        # ── Base queries ──────────────────────────────────────────────
        q = db.query(Staff)
        total_q = db.query(func.count(Staff.staff_id))

        # ── Filters ───────────────────────────────────────────────────
        if search:
            like = f"%{search}%"
            cond = (
                (Staff.first_name.ilike(like)) |
                (Staff.last_name.ilike(like)) |
                (Staff.staff_id.like(like))
            )
            q = q.filter(cond)
            total_q = total_q.filter(cond)

        if department != "Department":
            q = q.join(Staff.department_ref).filter(Department.code == department)
            total_q = total_q.join(Staff.department_ref).filter(Department.code == department)

        if role != "Role":
            q = q.join(Staff.role_ref).filter(Role.name == role)
            total_q = total_q.join(Staff.role_ref).filter(Role.name == role)

        # ── Total count ───────────────────────────────────────────────
        total_count = total_q.scalar()

        # ── Get current page ──────────────────────────────────────────
        staff_list = (
            q.order_by(Staff.last_name, Staff.first_name)
            .offset(offset)
            .limit(limit)
            .all()
        )

        if not staff_list:
            return [], total_count

        # ── Fetch stats ONLY for current page ─────────────────────────
        staff_ids = [s.staff_id for s in staff_list]

        present_case = case((StaffAttendance.status == "present", 1), else_=0)
        late_case    = case((StaffAttendance.status == "late",    1), else_=0)

        stats = (
            db.query(
                StaffAttendance.staff_id,
                func.count(StaffAttendance.id).label("total"),
                func.sum(present_case).label("present"),
                func.sum(late_case).label("late"),
            )
            .filter(StaffAttendance.staff_id.in_(staff_ids))
            .group_by(StaffAttendance.staff_id)
            .all()
        )

        stats_map = {
            s.staff_id: {
                "total":   s.total   or 0,
                "present": s.present or 0,
                "late":    s.late    or 0,
            }
            for s in stats
        }

        # ── Build result ──────────────────────────────────────────────
        result = []
        for st in staff_list:
            s = stats_map.get(st.staff_id, {"total": 0, "present": 0, "late": 0})
            result.append({
                "staff_id":   st.staff_id,
                "firstname":  st.first_name  or "",
                "lastname":   st.last_name   or "",
                "middlename": st.middle_name or "",
                "department":      st.department_ref.name if st.department_ref else "—",
                "department_code": st.department_ref.code if st.department_ref else "—",
                "role":       st.role        or "—",
                "is_active":  st.is_active,
                "total":      s["total"],
                "present":    s["present"],
                "late":       s["late"],
            })

        return result, total_count

    finally:
        db.close()


def _fetch_filter_options():    
    """Return unique department and role values for filter dropdowns."""
    db = SessionLocal()
    try:
        from database import Department, Role

        departments = sorted({
            r[0] for r in db.query(Department.code)
            .join(Staff, Staff.department_id == Department.id)
            .distinct() if r[0]
        })
        roles = sorted({
            r[0] for r in db.query(Role.name)
            .join(Staff, Staff.role_id == Role.id)
            .distinct() if r[0]
        })
        return departments, roles
    finally:
        db.close()


def _fetch_staff_attendance(staff_id: str, offset: int = 0, limit: int = STAFF_SIZE):
    db = SessionLocal()
    try:
        total = (
            db.query(func.count(StaffAttendance.id))
            .filter(StaffAttendance.staff_id == staff_id)
            .scalar()
        )

        records = (
            db.query(StaffAttendance, EventSession, SessionPeriod)
            .join(EventSession, StaffAttendance.session_id == EventSession.id)
            .join(SessionPeriod, StaffAttendance.period_id == SessionPeriod.id)
            .filter(StaffAttendance.staff_id == staff_id)
            .order_by(StaffAttendance.time_in.desc())
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
                "time_in":      att.time_in.strftime("%I:%M:%S %p")  if att.time_in  else "—",
                "time_out":     att.time_out.strftime("%I:%M:%S %p") if att.time_out else "—",
            }
            for att, sess, period in records
        ]

    finally:
        db.close()