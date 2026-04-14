from sqlalchemy import func
from database import SessionLocal, Student, Program
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
        