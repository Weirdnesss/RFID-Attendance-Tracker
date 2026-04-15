"""
database.py
-----------
SQLAlchemy models and database connection for the RFID Attendance Tracker.

Tables:
    academic_years    — school year ranges (e.g. 2025–2026)
    academic_terms    — semester/term labels (e.g. First Semester)
    academic_periods  — active combinations of year + term
    departments       — college/department records
    programs          — degree programs, linked to a department
    students          — normalised student records (linked to program)
    studentssss       — denormalised student view (department/program as text)
    sessions          — session header (name, date, academic period)
    session_periods   — per-period tracking rules
    attendance        — scan records, linked to a period
"""

from datetime import date, time, datetime, timedelta
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    Date, Time, DateTime, Enum, ForeignKey, SmallInteger, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from dotenv import load_dotenv
import os
load_dotenv()

DATABASE_URL = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Academic structure
# ---------------------------------------------------------------------------

class AcademicYear(Base):
    __tablename__ = "academic_years"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    year_start = Column(Integer, nullable=True)
    year_end   = Column(Integer, nullable=True)

    periods = relationship("AcademicPeriod", back_populates="academic_year")

    @property
    def label(self) -> str:
        return f"{self.year_start}–{self.year_end}"

    def __repr__(self):
        return f"<AcademicYear {self.id} — {self.label}>"


class AcademicTerm(Base):
    __tablename__ = "academic_terms"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=True)

    periods = relationship("AcademicPeriod", back_populates="term")

    def __repr__(self):
        return f"<AcademicTerm {self.id} — {self.name}>"


class AcademicPeriod(Base):
    __tablename__ = "academic_periods"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"),
                              nullable=True)
    term_id          = Column(Integer, ForeignKey("academic_terms.id"),
                              nullable=True)
    is_active        = Column(Boolean, nullable=True, default=False)

    academic_year = relationship("AcademicYear", back_populates="periods")
    term          = relationship("AcademicTerm",  back_populates="periods")
    sessions      = relationship("Session", back_populates="academic_period")

    def __repr__(self):
        return f"<AcademicPeriod {self.id} active={self.is_active}>"


# ---------------------------------------------------------------------------
# Departments & Programs
# ---------------------------------------------------------------------------

class Department(Base):
    __tablename__ = "departments"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(100), nullable=False)

    programs = relationship("Program", back_populates="department")

    def __repr__(self):
        return f"<Department {self.id} — {self.code}>"


class Program(Base):
    __tablename__ = "programs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    code          = Column(String(20), nullable=False, unique=True)
    name          = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)

    department = relationship("Department", back_populates="programs")
    students   = relationship("Student",    back_populates="program")

    def __repr__(self):
        return f"<Program {self.id} — {self.code}>"


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

class Student(Base):
    """
    Normalised student table.
    year_level is stored as a tinyint (1 = 1st Year, etc.).
    """
    __tablename__ = "students"

    student_id = Column(Integer, primary_key=True)
    first_name  = Column(String(512), nullable=True)
    last_name   = Column(String(512), nullable=True)
    middle_name = Column(String(512), nullable=True)
    year_level  = Column(SmallInteger, nullable=False)
    program_id  = Column(Integer, ForeignKey("programs.id"), nullable=True)

    program            = relationship("Program",    back_populates="students")
    attendance_records = relationship("Attendance", back_populates="student")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    def __repr__(self):
        return f"<Student {self.student_id} — {self.full_name}>"


# ---------------------------------------------------------------------------
# Sessions — header only (name + date + academic period)
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "sessions"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    name                = Column(String(255), nullable=False)
    date                = Column(Date, nullable=False, default=date.today)
    estimated_attendees = Column(Integer, nullable=True)
    created_at          = Column(DateTime, default=datetime.now)
    academic_period_id  = Column(Integer,
                                 ForeignKey("academic_periods.id"),
                                 nullable=True)
    is_active = Column(Integer, default=0)

    academic_period    = relationship("AcademicPeriod", back_populates="sessions")
    periods            = relationship(
        "SessionPeriod",
        back_populates="session",
        order_by="SessionPeriod.sort_order",
        cascade="all, delete-orphan",
    )
    attendance_records = relationship("Attendance", back_populates="session")

    def __repr__(self):
        return f"<Session {self.id} — {self.name} ({self.date})>"


# ---------------------------------------------------------------------------
# Session periods — per-period tracking rules
# ---------------------------------------------------------------------------

class SessionPeriod(Base):
    """
    One row per period (e.g. Morning, Afternoon) within a session.

    Attendance window
    -----------------
    time_in_start / time_in_end
        Scans are only accepted inside this range.

    grace_minutes
        Extra minutes of leniency applied on top of late_start before a
        scan is recorded as late.
        Effective late threshold = late_start + grace_minutes.

    Late tracking  (optional)
    -------------------------
    late_enabled    Whether late marking is active for this period.
    late_start      Time after which a scan is considered late.
                    NULL when late_enabled = False.

    Time-out tracking  (optional)
    ------------------------------
    timeout_enabled Whether SCAN OUT is tracked for this period.
    timeout_start   Earliest time a sign-out scan is accepted.
                    NULL when timeout_enabled = False.
    timeout_end     Latest time a sign-out scan is accepted.
                    NULL when timeout_enabled = False.

    sort_order      Display / evaluation order within the session.
    """

    __tablename__ = "session_periods"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    name       = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    # Attendance window
    time_in_start = Column(Time, nullable=False)
    time_in_end   = Column(Time, nullable=False)
    grace_minutes = Column(Integer, nullable=False, default=0)

    # Late
    late_enabled  = Column(Boolean, nullable=False, default=True)
    late_start    = Column(Time, nullable=True)     # NULL when disabled

    # Time-out
    timeout_enabled = Column(Boolean, nullable=False, default=False)
    timeout_start   = Column(Time, nullable=True)   # NULL when disabled
    timeout_end     = Column(Time, nullable=True)   # NULL when disabled

    session            = relationship("Session",    back_populates="periods")
    attendance_records = relationship("Attendance", back_populates="period")

    # ── convenience properties ────────────────────────────────────────

    @property
    def effective_late_threshold(self) -> time | None:
        """
        late_start + grace_minutes.
        Returns None if late tracking is disabled or late_start is unset.
        """
        if not self.late_enabled or self.late_start is None:
            return None
        dt = datetime.combine(datetime.today(), self.late_start)
        dt += timedelta(minutes=self.grace_minutes)
        return dt.time()

    def is_open(self, now: time = None) -> bool:
        """True if the current time is within the attendance window."""
        now = now or datetime.now().time()
        return self.time_in_start <= now <= self.time_in_end

    def scan_status(self, scan_time: datetime = None) -> str:
        """
        Return 'present', 'late', or 'absent' for a given scan time.
        Falls back to 'present' if late tracking is disabled.
        """
        scan_time = scan_time or datetime.now()
        threshold = self.effective_late_threshold
        if threshold is None:
            return "present"
        return "late" if scan_time.time() > threshold else "present"

    def timeout_open(self, now: time = None) -> bool:
        """True if SCAN OUT is enabled and the current time is in window."""
        if not self.timeout_enabled:
            return False
        if self.timeout_start is None or self.timeout_end is None:
            return False
        now = now or datetime.now().time()
        return self.timeout_start <= now <= self.timeout_end

    def __repr__(self):
        return (f"<SessionPeriod {self.id} — {self.name} "
                f"[{self.time_in_start}–{self.time_in_end}]>")


# ---------------------------------------------------------------------------
# Attendance — one row per student per period
# ---------------------------------------------------------------------------

class Attendance(Base):
    __tablename__ = "attendance"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.student_id"),
                        nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"),       nullable=False)
    period_id  = Column(Integer, ForeignKey("session_periods.id"), nullable=False)
    status     = Column(
        Enum("present", "late", "absent"),
        nullable=False,
        default="present",
    )
    time_in  = Column(DateTime, nullable=True)
    time_out = Column(DateTime, nullable=True)
    terminal_id = Column(String(50), nullable=True)

    student = relationship("Student", back_populates="attendance_records")
    session = relationship("Session",       back_populates="attendance_records")
    period  = relationship("SessionPeriod", back_populates="attendance_records")

    def __repr__(self):
        return (f"<Attendance student={self.student_id} "
                f"period={self.period_id} status={self.status}>")


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def create_tables():
    """
    Create new tables if they don't exist.
    Reference/lookup tables (academic_years, academic_terms, departments,
    programs, students, studentssss) are never touched.
    """
    AcademicPeriod.__table__.create(bind=engine, checkfirst=True)
    Session.__table__.create(bind=engine, checkfirst=True)
    SessionPeriod.__table__.create(bind=engine, checkfirst=True)
    Attendance.__table__.create(bind=engine, checkfirst=True)
    print("Tables ready: academic_periods, sessions, session_periods, attendance")


def test_connection():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Connected to attendance_db successfully.")
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure XAMPP MySQL is running on localhost:3306")
        return False