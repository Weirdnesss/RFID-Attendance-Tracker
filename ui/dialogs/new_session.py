import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import os

from ui.theme import C_ACCENT, C_BG, C_BORDER, C_ERROR, C_MUTED, C_SURFACE, C_TEXT
from datetime import datetime
from database import SessionLocal, Student, Program, Department, AcademicPeriod, Session as EventSession, Staff, Role
from db.students_db import YEAR_LEVEL_LABELS
from db.scan_db import start_session, get_session_by_id
from ui.components.period_row import PeriodRow
from sqlalchemy import func
from sqlalchemy.orm import joinedload


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(t) -> str:
    if t is None:
        return ""
    return t.strftime("%I:%M %p").lstrip("0")


def _fetch_group_counts() -> dict:
    """
    Return a nested dict:
    { department: { (program, yearlevel): count } }
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(
                Department.code,
                Program.code,
                Student.year_level,
                func.count(Student.student_id).label("cnt"),
            )
            .join(Program, Student.program_id == Program.id)
            .join(Department, Program.department_id == Department.id)
            .group_by(Department.code, Program.code, Student.year_level)
            .order_by(Department.code, Program.code, Student.year_level)
            .all()
        )
        result: dict[str, dict[tuple, int]] = {}
        for r in rows:
            dept = r[0] or "—"
            prog = r[1] or "—"
            yr = YEAR_LEVEL_LABELS.get(r[2], "—")
            result.setdefault(dept, {})[(prog, yr)] = r.cnt
        return result
    finally:
        db.close()


def _fetch_staff_group_counts() -> dict:
    """
    Return:
    { "departments": { dept_name: count }, "roles": { role_name: count } }
    """
    db = SessionLocal()
    try:
        dept_rows = (
            db.query(Department.name, func.count(Staff.staff_id).label("cnt"))
            .join(Staff, Staff.department_id == Department.id)
            .filter(Staff.is_active == True)
            .group_by(Department.name)
            .order_by(Department.name)
            .all()
        )
        role_rows = (
            db.query(Role.name, func.count(Staff.staff_id).label("cnt"))
            .join(Staff, Staff.role_id == Role.id)
            .filter(Staff.is_active == True)
            .group_by(Role.name)
            .order_by(Role.name)
            .all()
        )
        return {
            "departments": {r.name: r.cnt for r in dept_rows},
            "roles":       {r.name: r.cnt for r in role_rows},
        }
    finally:
        db.close()


def _count_students(student_filter: dict | None) -> int:
    db = SessionLocal()
    try:
        q = db.query(func.count(Student.student_id))
        if student_filter:
            groups = student_filter.get("groups", [])  # list of (program, yearlevel)
            if groups:
                from sqlalchemy import or_, and_
                conditions = []
                for prog_code, yr_label in groups:
                    yr_int = next((k for k, v in YEAR_LEVEL_LABELS.items() if v == yr_label), None)
                    if yr_int is not None:
                        conditions.append(and_(
                            Program.code == prog_code,
                            Student.year_level == yr_int,
                        ))
                if conditions:
                    q = q.join(Program, Student.program_id == Program.id).filter(or_(*conditions))
        return q.scalar() or 0
    finally:
        db.close()


def _count_staff(staff_filter: dict | None) -> int:
    db = SessionLocal()
    try:
        q = db.query(func.count(Staff.staff_id)).filter(Staff.is_active == True)
        if staff_filter:
            depts = staff_filter.get("departments", [])
            roles = staff_filter.get("roles", [])
            if depts:
                q = q.join(Department, Staff.department_id == Department.id).filter(
                    Department.name.in_(depts))
            if roles:
                q = q.join(Role, Staff.role_id == Role.id).filter(
                    Role.name.in_(roles))
        return q.scalar() or 0
    finally:
        db.close()


def get_active_academic_period():
    db = SessionLocal()
    try:
        return db.query(AcademicPeriod).filter(AcademicPeriod.is_active == 1).first()
    finally:
        db.close()


# ── SearchChecklistDialog ─────────────────────────────────────────────────────

class SearchChecklistDialog(ctk.CTkToplevel):
    """
    Generic search + checklist dialog.
    items: list of (label, count, key)  — key is what gets stored in the result
    Returns result as list of selected keys, or None if cancelled.
    """

    def __init__(self, parent, title: str, subtitle: str,
                 items: list[tuple[str, int, any]],
                 preselected: list = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("480x540")
        self.minsize(400, 400)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result: list | None = None
        self._items = items  # [(label, count, key), ...]
        self._vars: dict = {}
        self._item_frames: dict = {}
        self._preselected = set(preselected or [])

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._filter)

        self._build_ui(title, subtitle)
        self._populate()

    def _build_ui(self, title: str, subtitle: str):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(hdr, text=subtitle,
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(anchor="w", padx=20)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # Search + select all row
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(10, 4))
        ctrl.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            ctrl, textvariable=self._search_var,
            placeholder_text="Search...",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=30, corner_radius=8,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            ctrl, text="All", width=48, height=30,
            fg_color=C_BORDER, hover_color=C_MUTED,
            text_color=C_TEXT, corner_radius=6,
            command=self._select_all,
        ).grid(row=0, column=1, padx=(0, 4))

        ctk.CTkButton(
            ctrl, text="None", width=52, height=30,
            fg_color=C_BORDER, hover_color=C_MUTED,
            text_color=C_TEXT, corner_radius=6,
            command=self._deselect_all,
        ).grid(row=0, column=2)

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._scroll.pack(fill="both", expand=True, padx=16, pady=(0, 4))
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # Footer
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=10)
        foot.grid_columnconfigure(0, weight=1)

        self._total_lbl = ctk.CTkLabel(
            foot, text="Selected: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_ACCENT)
        self._total_lbl.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            foot, text="Cancel", width=80,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            foot, text="Confirm", width=80,
            fg_color=C_ACCENT, text_color="#fff",
            command=self._confirm,
        ).grid(row=0, column=2)

    def _populate(self):
        for label, count, key in self._items:
            var = tk.BooleanVar(value=key in self._preselected)
            var.trace_add("write", lambda *_: self._update_total())
            self._vars[key] = var

            row = ctk.CTkFrame(self._scroll, fg_color="transparent", height=36)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            row.grid_columnconfigure(1, weight=1)

            cb = ctk.CTkCheckBox(
                row, text="", variable=var,
                width=20, height=20,
                fg_color=C_ACCENT, border_color=C_BORDER,
                hover_color="#8aabff",
                command=self._update_total,
            )
            cb.grid(row=0, column=0, padx=(4, 8))

            ctk.CTkLabel(
                row, text=label, anchor="w",
                font=ctk.CTkFont(size=12), text_color=C_TEXT,
            ).grid(row=0, column=1, sticky="w")

            ctk.CTkLabel(
                row, text=str(count),
                font=ctk.CTkFont(size=11), text_color=C_MUTED,
            ).grid(row=0, column=2, padx=(0, 8))

            self._item_frames[key] = (row, label.lower())

        self._update_total()

    def _filter(self, *_):
        q = self._search_var.get().strip().lower()
        for key, (frame, label_lower) in self._item_frames.items():
            if q in label_lower:
                frame.pack(fill="x", pady=1)
            else:
                frame.pack_forget()

    def _select_all(self):
        q = self._search_var.get().strip().lower()
        for key, (frame, label_lower) in self._item_frames.items():
            if q in label_lower:
                self._vars[key].set(True)
        self._update_total()

    def _deselect_all(self):
        for var in self._vars.values():
            var.set(False)
        self._update_total()

    def _update_total(self):
        total = sum(
            cnt for label, cnt, key in self._items
            if self._vars.get(key, tk.BooleanVar()).get()
        )
        selected_count = sum(1 for v in self._vars.values() if v.get())
        self._total_lbl.configure(
            text=f"{selected_count} selected · {total} people")

    def _confirm(self):
        self.result = [key for key, var in self._vars.items() if var.get()]
        self.destroy()


# ── StudentGroupSelectorDialog ────────────────────────────────────────────────

class StudentGroupSelectorDialog(SearchChecklistDialog):
    """
    Flat searchable checklist of all (program, year level) groups.
    Each item label: "BSIT · 1st Year"  count: N students
    Result: list of (program_code, yearlevel_label) tuples
    """

    def __init__(self, parent, preselected: list = None):
        data = _fetch_group_counts()

        items = []
        for dept, groups in sorted(data.items()):
            for (prog, yr), cnt in sorted(groups.items()):
                label = f"{prog} · {yr}  [{dept}]"
                items.append((label, cnt, (prog, yr)))

        super().__init__(
            parent,
            title="Select Student Groups",
            subtitle="Choose which student groups are expected to attend",
            items=items,
            preselected=preselected or [],
        )


# ── StaffGroupSelectorDialog ──────────────────────────────────────────────────

class StaffGroupSelectorDialog(ctk.CTkToplevel):
    """
    Two-section checklist: Departments + Roles.
    Both are searchable independently.
    Result: {"departments": [...], "roles": [...]}
    """

    def __init__(self, parent, preselected: dict = None):
        super().__init__(parent)
        self.title("Select Staff Groups")
        self.geometry("520x580")
        self.minsize(440, 460)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result: dict | None = None
        pre = preselected or {}
        self._pre_depts = set(pre.get("departments", []))
        self._pre_roles = set(pre.get("roles", []))

        self._data = _fetch_staff_group_counts()
        self._dept_vars: dict[str, tk.BooleanVar] = {}
        self._role_vars: dict[str, tk.BooleanVar] = {}
        self._dept_frames: dict = {}
        self._role_frames: dict = {}

        self._dept_search = tk.StringVar()
        self._role_search = tk.StringVar()
        self._dept_search.trace_add("write", self._filter_depts)
        self._role_search.trace_add("write", self._filter_roles)

        self._build_ui()
        self._populate()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Select Staff Groups",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Filter by department and/or role",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(anchor="w", padx=20)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # Two-column scrollable area
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.grid_columnconfigure((0, 1), weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ── Departments column ────────────────────────────────────────
        dept_col = ctk.CTkFrame(body, fg_color=C_BG, corner_radius=8)
        dept_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        dept_col.grid_rowconfigure(2, weight=1)
        dept_col.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dept_col, text="DEPARTMENTS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C_MUTED).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        ctk.CTkEntry(
            dept_col, textvariable=self._dept_search,
            placeholder_text="Search...",
            fg_color=C_SURFACE, border_color=C_BORDER,
            text_color=C_TEXT, height=28, corner_radius=6,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._dept_scroll = ctk.CTkScrollableFrame(
            dept_col, fg_color="transparent", corner_radius=0)
        self._dept_scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # Dept All/None buttons
        dept_ctrl = ctk.CTkFrame(dept_col, fg_color="transparent")
        dept_ctrl.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkButton(dept_ctrl, text="All", width=50, height=24,
                      fg_color=C_BORDER, hover_color=C_MUTED,
                      text_color=C_TEXT, corner_radius=4,
                      command=lambda: self._select_all(self._dept_vars, self._dept_frames, self._dept_search)
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(dept_ctrl, text="None", width=50, height=24,
                      fg_color=C_BORDER, hover_color=C_MUTED,
                      text_color=C_TEXT, corner_radius=4,
                      command=lambda: self._deselect_all(self._dept_vars)
                      ).pack(side="left")

        # ── Roles column ──────────────────────────────────────────────
        role_col = ctk.CTkFrame(body, fg_color=C_BG, corner_radius=8)
        role_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        role_col.grid_rowconfigure(2, weight=1)
        role_col.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(role_col, text="ROLES",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C_MUTED).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        ctk.CTkEntry(
            role_col, textvariable=self._role_search,
            placeholder_text="Search...",
            fg_color=C_SURFACE, border_color=C_BORDER,
            text_color=C_TEXT, height=28, corner_radius=6,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._role_scroll = ctk.CTkScrollableFrame(
            role_col, fg_color="transparent", corner_radius=0)
        self._role_scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # Role All/None buttons
        role_ctrl = ctk.CTkFrame(role_col, fg_color="transparent")
        role_ctrl.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkButton(role_ctrl, text="All", width=50, height=24,
                      fg_color=C_BORDER, hover_color=C_MUTED,
                      text_color=C_TEXT, corner_radius=4,
                      command=lambda: self._select_all(self._role_vars, self._role_frames, self._role_search)
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(role_ctrl, text="None", width=50, height=24,
                      fg_color=C_BORDER, hover_color=C_MUTED,
                      text_color=C_TEXT, corner_radius=4,
                      command=lambda: self._deselect_all(self._role_vars)
                      ).pack(side="left")

        # Footer
        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=10)
        foot.grid_columnconfigure(0, weight=1)

        self._total_lbl = ctk.CTkLabel(
            foot, text="Selected: all staff",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_ACCENT)
        self._total_lbl.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(foot, text="Cancel", width=80,
                      fg_color="transparent", border_color=C_BORDER,
                      border_width=1, text_color=C_MUTED,
                      command=self.destroy).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(foot, text="Confirm", width=80,
                      fg_color=C_ACCENT, text_color="#fff",
                      command=self._confirm).grid(row=0, column=2)

    def _populate(self):
        for name, cnt in self._data["departments"].items():
            var = tk.BooleanVar(value=name in self._pre_depts)
            var.trace_add("write", lambda *_: self._update_total())
            self._dept_vars[name] = var

            row = ctk.CTkFrame(self._dept_scroll, fg_color="transparent", height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(row, text="", variable=var, width=20, height=20,
                            fg_color=C_ACCENT, border_color=C_BORDER,
                            hover_color="#8aabff",
                            command=self._update_total,
                            ).grid(row=0, column=0, padx=(4, 6))
            ctk.CTkLabel(row, text=name, anchor="w",
                         font=ctk.CTkFont(size=11), text_color=C_TEXT,
                         ).grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(row, text=str(cnt),
                         font=ctk.CTkFont(size=10), text_color=C_MUTED,
                         ).grid(row=0, column=2, padx=(0, 4))
            self._dept_frames[name] = (row, name.lower())

        for name, cnt in self._data["roles"].items():
            var = tk.BooleanVar(value=name in self._pre_roles)
            var.trace_add("write", lambda *_: self._update_total())
            self._role_vars[name] = var

            row = ctk.CTkFrame(self._role_scroll, fg_color="transparent", height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(row, text="", variable=var, width=20, height=20,
                            fg_color=C_ACCENT, border_color=C_BORDER,
                            hover_color="#8aabff",
                            command=self._update_total,
                            ).grid(row=0, column=0, padx=(4, 6))
            ctk.CTkLabel(row, text=name, anchor="w",
                         font=ctk.CTkFont(size=11), text_color=C_TEXT,
                         ).grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(row, text=str(cnt),
                         font=ctk.CTkFont(size=10), text_color=C_MUTED,
                         ).grid(row=0, column=2, padx=(0, 4))
            self._role_frames[name] = (row, name.lower())

        self._update_total()

    def _filter_depts(self, *_):
        q = self._dept_search.get().strip().lower()
        for name, (frame, label_lower) in self._dept_frames.items():
            if q in label_lower:
                frame.pack(fill="x", pady=1)
            else:
                frame.pack_forget()

    def _filter_roles(self, *_):
        q = self._role_search.get().strip().lower()
        for name, (frame, label_lower) in self._role_frames.items():
            if q in label_lower:
                frame.pack(fill="x", pady=1)
            else:
                frame.pack_forget()

    def _select_all(self, vars_dict, frames_dict, search_var):
        q = search_var.get().strip().lower()
        for name, (frame, label_lower) in frames_dict.items():
            if q in label_lower:
                vars_dict[name].set(True)
        self._update_total()

    def _deselect_all(self, vars_dict):
        for var in vars_dict.values():
            var.set(False)
        self._update_total()

    def _update_total(self):
        selected_depts = [n for n, v in self._dept_vars.items() if v.get()]
        selected_roles = [n for n, v in self._role_vars.items() if v.get()]

        if not selected_depts and not selected_roles:
            self._total_lbl.configure(text="Selected: all staff")
        else:
            parts = []
            if selected_depts:
                parts.append(f"{len(selected_depts)} dept{'s' if len(selected_depts) != 1 else ''}")
            if selected_roles:
                parts.append(f"{len(selected_roles)} role{'s' if len(selected_roles) != 1 else ''}")
            self._total_lbl.configure(text=f"Selected: {', '.join(parts)}")

    def _confirm(self):
        self.result = {
            "departments": [n for n, v in self._dept_vars.items() if v.get()],
            "roles":       [n for n, v in self._role_vars.items() if v.get()],
        }
        self.destroy()


# ── NewSessionDialog ──────────────────────────────────────────────────────────

class NewSessionDialog(ctk.CTkToplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title("New Session")
        self.geometry("660x680")
        self.minsize(580, 680)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result = None
        self._period_rows: list[PeriodRow] = []
        self._attendee_type = "students"   # "students" | "staff" | "both"
        self._student_filter: dict | None = None   # {"groups": [(prog, yr), ...]}
        self._staff_filter: dict | None = None     # {"departments": [...], "roles": [...]}

        self._build_ui()
        self._add_period(defaults={
            "name": "Attendance Period",
            "time_in_start": "07:00",
            "time_in_end": "09:00",
            "late_enabled": False,
            "late_start": "07:30",
            "grace_minutes": "0",
            "timeout_enabled": False,
            "timeout_start": "11:00",
            "timeout_end": "12:00",
        })
        self.after(100, self._auto_estimate)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="New Session",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=24, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Configure periods and tracking rules",
                     font=ctk.CTkFont(size=12), text_color=C_MUTED).pack(anchor="w", padx=24)
        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # ── Top grid: name | estimated | date ────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(16, 8))
        top.grid_columnconfigure(0, weight=2)
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text="SESSION NAME",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED,
                     ).grid(row=0, column=0, sticky="w", pady=(0, 3))

        self._name_var = tk.StringVar()
        self._name_entry = ctk.CTkEntry(
            top, textvariable=self._name_var,
            placeholder_text="e.g. General Assembly 2025",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32)
        self._name_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12))

        # Estimated
        est_lbl_row = ctk.CTkFrame(top, fg_color="transparent")
        est_lbl_row.grid(row=0, column=1, sticky="ew", pady=(0, 3))
        ctk.CTkLabel(est_lbl_row, text="ESTIMATED",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED).pack(side="left")
        self._auto_lbl = ctk.CTkLabel(est_lbl_row, text="",
                                      font=ctk.CTkFont(size=10), text_color=C_ACCENT)
        self._auto_lbl.pack(side="left", padx=(6, 0))

        self._estimate_var = tk.StringVar(value="")
        ctk.CTkEntry(
            top, textvariable=self._estimate_var,
            placeholder_text="e.g. 120",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12))

        # Date
        ctk.CTkLabel(top, text="DATE",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED,
                     ).grid(row=0, column=2, sticky="w", pady=(0, 3))
        self._date_var = tk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        ctk.CTkEntry(
            top, textvariable=self._date_var,
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32,
        ).grid(row=1, column=2, sticky="ew")

        # ── Attendee type selector ────────────────────────────────────
        att_frame = ctk.CTkFrame(self, fg_color="transparent")
        att_frame.pack(fill="x", padx=24, pady=(4, 0))

        ctk.CTkLabel(att_frame, text="ATTENDEE TYPE",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED).pack(anchor="w", pady=(0, 4))

        btn_row = ctk.CTkFrame(att_frame, fg_color=C_BG, corner_radius=8)
        btn_row.pack(anchor="w")

        self._type_btns = {}
        for atype, label in [("students", "Students"), ("staff", "Staff"), ("both", "Both")]:
            btn = ctk.CTkButton(
                btn_row, text=label, width=90, height=30,
                fg_color=C_ACCENT if atype == "students" else "transparent",
                hover_color="#8aabff" if atype == "students" else C_SURFACE,
                text_color="#ffffff" if atype == "students" else C_MUTED,
                font=ctk.CTkFont(size=12, weight="bold"),
                corner_radius=6,
                command=lambda t=atype: self._set_attendee_type(t),
            )
            btn.pack(side="left", padx=3, pady=3)
            self._type_btns[atype] = btn

        # ── Group selector section (dynamic) ─────────────────────────
        self._group_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._group_frame.pack(fill="x", padx=24, pady=(6, 0))
        self._group_info_lbl = ctk.CTkLabel(
            self._group_frame, text="",
            font=ctk.CTkFont(size=11), text_color=C_ACCENT)
        self._group_info_lbl.pack(anchor="w", pady=(0, 2))
        self._build_group_buttons()

        # ── Periods ───────────────────────────────────────────────────
        pl = ctk.CTkFrame(self, fg_color="transparent")
        pl.pack(fill="x", padx=24, pady=(10, 6))
        ctk.CTkLabel(pl, text="PERIODS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C_MUTED).pack(side="left")

        self._period_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._period_scroll.pack(fill="both", expand=True, padx=24)
        self._period_scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            self, text="+ Add period",
            fg_color="transparent", border_color=C_BORDER, border_width=1,
            text_color=C_MUTED, hover_color=C_BG,
            font=ctk.CTkFont(size=12), height=34,
            command=lambda: self._add_period(),
        ).pack(fill="x", padx=24, pady=(8, 4))

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=24, pady=14)
        ctk.CTkButton(
            foot, text="Cancel",
            fg_color="transparent", border_color=C_BORDER, border_width=1,
            text_color=C_MUTED, hover_color=C_SURFACE,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            foot, text="Start session",
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._accept,
        ).pack(side="right")

    def _build_group_buttons(self):
        for w in self._group_frame.winfo_children():
            if w != self._group_info_lbl:
                w.destroy()

        atype = self._attendee_type
        btn_frame = ctk.CTkFrame(self._group_frame, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=(0, 2))

        if atype in ("students", "both"):
            lbl = "Filter Students" if self._student_filter is None else \
                f"Students: {len(self._student_filter.get('groups', []))} group(s)"
            ctk.CTkButton(
                btn_frame, text=lbl, height=28, width=180,
                fg_color=C_BORDER, hover_color=C_SURFACE,
                text_color=C_TEXT, corner_radius=6,
                font=ctk.CTkFont(size=11),
                command=self._open_student_selector,
            ).pack(side="left", padx=(0, 8))

        if atype in ("staff", "both"):
            sf = self._staff_filter
            if sf is None:
                lbl = "Filter Staff"
            else:
                parts = []
                if sf.get("departments"):
                    parts.append(f"{len(sf['departments'])} dept(s)")
                if sf.get("roles"):
                    parts.append(f"{len(sf['roles'])} role(s)")
                lbl = f"Staff: {', '.join(parts)}" if parts else "Staff: all"
            ctk.CTkButton(
                btn_frame, text=lbl, height=28, width=180,
                fg_color=C_BORDER, hover_color=C_SURFACE,
                text_color=C_TEXT, corner_radius=6,
                font=ctk.CTkFont(size=11),
                command=self._open_staff_selector,
            ).pack(side="left")

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _set_attendee_type(self, atype: str):
        self._attendee_type = atype
        for t, btn in self._type_btns.items():
            selected = t == atype
            btn.configure(
                fg_color=C_ACCENT if selected else "transparent",
                hover_color="#8aabff" if selected else C_SURFACE,
                text_color="#ffffff" if selected else C_MUTED,
            )
        self._build_group_buttons()
        self._auto_estimate()

    def _open_student_selector(self):
        pre = self._student_filter.get("groups", []) if self._student_filter else []
        dlg = StudentGroupSelectorDialog(self, preselected=pre)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._student_filter = {"groups": dlg.result} if dlg.result else None
            self._build_group_buttons()
            self._auto_estimate()

    def _open_staff_selector(self):
        pre = self._staff_filter or {}
        dlg = StaffGroupSelectorDialog(self, preselected=pre)
        self.wait_window(dlg)
        if dlg.result is not None:
            has_selection = dlg.result.get("departments") or dlg.result.get("roles")
            self._staff_filter = dlg.result if has_selection else None
            self._build_group_buttons()
            self._auto_estimate()

    def _auto_estimate(self):
        try:
            atype = self._attendee_type
            count = 0

            if atype in ("students", "both"):
                count += _count_students(self._student_filter)
            if atype in ("staff", "both"):
                count += _count_staff(self._staff_filter)

            self._estimate_var.set(str(count) if count else "")

            if atype == "students":
                label = "(auto: students)"
            elif atype == "staff":
                label = "(auto: staff)"
            else:
                label = "(auto: students + staff)"
            self._auto_lbl.configure(text=label)
        except Exception:
            pass

    def _add_period(self, defaults: dict = None):
        idx = len(self._period_rows)
        row = PeriodRow(
            self._period_scroll, idx,
            on_delete=self._delete_period,
            defaults=defaults,
        )
        row.pack(fill="x", pady=(0, 8))
        self._period_rows.append(row)

    def _delete_period(self, row: "PeriodRow"):
        if len(self._period_rows) <= 1:
            messagebox.showwarning("Cannot delete",
                                   "A session must have at least one period.")
            return
        self._period_rows.remove(row)
        row.destroy()

    def _accept(self):
        name = self._name_var.get().strip()
        if not name:
            self._name_entry.configure(border_color=C_ERROR)
            return

        try:
            session_date = datetime.strptime(
                self._date_var.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Invalid date", "Date must be in YYYY-MM-DD format.")
            return

        est_str = self._estimate_var.get().strip()
        if est_str:
            try:
                estimated = int(est_str)
                if estimated < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid input",
                                     "Estimated attendees must be a non-negative number.")
                return
        else:
            estimated = None

        periods = []
        for i, row in enumerate(self._period_rows):
            try:
                data = row.get_data()
                data["sort_order"] = i
                periods.append(data)
            except ValueError as e:
                messagebox.showerror("Invalid time", str(e))
                return

        ap = get_active_academic_period()

        dialog = ConfirmSessionDialog(self, {
            "name": name,
            "date": session_date,
            "estimated_attendees": estimated,
            "periods": periods,
            "attendee_type": self._attendee_type,
            "student_filter": self._student_filter,
            "staff_filter": self._staff_filter,
            "academic_period_id": ap.id if ap else None,
        })
        self.wait_window(dialog)
        if not dialog.result:
            return

        terminal_id = os.getenv("TERMINAL_ID", "PC1")
        success, session_id, message = start_session(
            name=name,
            date=session_date,
            estimated_attendees=estimated,
            periods=periods,
            academic_period_id=ap.id if ap else None,
            terminal_id=terminal_id,
            attendee_type=self._attendee_type,
            student_filter=self._student_filter,
            staff_filter=self._staff_filter,
        )

        if success:
            self.result = {
                "id": session_id,
                "name": name,
                "date": session_date,
                "estimated_attendees": estimated,
                "attendee_type": self._attendee_type,
                "periods": periods,
                "academic_period_id": ap.id if ap else None,
                "started": True,
            }
            self.destroy()
        else:
            messagebox.showinfo("Session Already Active",
                                f"{message}\n\nLoading the active session now...")
            self.result = {"id": None, "started": False}
            self.destroy()


# ── ConfirmSessionDialog ──────────────────────────────────────────────────────

class ConfirmSessionDialog(ctk.CTkToplevel):

    def __init__(self, parent, data: dict):
        super().__init__(parent)
        self.title("Confirm Session")
        self.geometry("560x560")
        self.configure(fg_color=C_SURFACE)
        self.grab_set()
        self.result = False
        self._data = data
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Confirm Session",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=20, pady=(16, 4))

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=20)
        d = self._data
        est = d["estimated_attendees"] if d["estimated_attendees"] is not None else "N/A"

        type_labels = {"students": "Students only", "staff": "Staff only", "both": "Students + Staff"}

        ctk.CTkLabel(info, text=f"Name: {d['name']}", text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Date: {d['date']}", text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Attendees: {type_labels.get(d['attendee_type'], '—')}",
                     text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Estimated: {est}", text_color=C_TEXT).pack(anchor="w")

        # Student filter summary
        sf = d.get("student_filter")
        if sf and sf.get("groups"):
            ctk.CTkLabel(info,
                         text=f"Student groups: {len(sf['groups'])} selected",
                         text_color=C_MUTED).pack(anchor="w")

        # Staff filter summary
        stf = d.get("staff_filter")
        if stf:
            parts = []
            if stf.get("departments"):
                parts.append(f"{len(stf['departments'])} dept(s)")
            if stf.get("roles"):
                parts.append(f"{len(stf['roles'])} role(s)")
            if parts:
                ctk.CTkLabel(info, text=f"Staff filter: {', '.join(parts)}",
                             text_color=C_MUTED).pack(anchor="w")

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x", padx=20, pady=10)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20)

        for i, p in enumerate(d["periods"], 1):
            self._add_period_preview(scroll, i, p)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(foot, text="Cancel",
                      fg_color="transparent", border_color=C_BORDER,
                      border_width=1, text_color=C_MUTED,
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(foot, text="Start Session",
                      fg_color=C_ACCENT, text_color="#fff",
                      command=self._confirm).pack(side="right")

    def _add_period_preview(self, parent, idx: int, p: dict):
        card = ctk.CTkFrame(parent, fg_color=C_BG, corner_radius=10)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card,
                     text=f"{idx}. {p.get('name', 'Unnamed')}",
                     font=ctk.CTkFont(weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=10, pady=(8, 4))

        tag_frame = ctk.CTkFrame(card, fg_color="transparent")
        tag_frame.pack(anchor="w", padx=10, pady=(0, 8))

        tags = []
        ts, te = p.get("time_in_start"), p.get("time_in_end")
        if ts and te:
            tags.append((f"In {_fmt_time(ts)}–{_fmt_time(te)}", "#0b1220", "#38bdf8"))
        if p.get("late_enabled"):
            ls = p.get("late_start")
            grace = p.get("grace_minutes", 0)
            if ls:
                tags.append((f"Late {_fmt_time(ls)}", "#1f1708", "#f0a843"))
            if grace:
                tags.append((f"+{grace}m", "#16181f", C_MUTED))
        if p.get("timeout_enabled"):
            tos, toe = p.get("timeout_start"), p.get("timeout_end")
            if tos and toe:
                tags.append((f"Out {_fmt_time(tos)}–{_fmt_time(toe)}", "#100e1f", "#a78bfa"))

        for text, bg, fg in tags:
            ctk.CTkLabel(tag_frame, text=text, fg_color=bg, text_color=fg,
                         corner_radius=6, padx=8, pady=2).pack(side="left", padx=(0, 6))

    def _confirm(self):
        self.result = True
        self.destroy()


# ── ChooseSessionDialog ───────────────────────────────────────────────────────

class ChooseSessionDialog(ctk.CTkToplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Choose Session")
        self.geometry("520x420")
        self.configure(fg_color=C_SURFACE)
        self.grab_set()
        self.result = None
        self._selected_id: int | None = None
        self._row_frames = {}
        self._confirm_btn = None
        self._build_ui()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Choose Session",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=24, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Select an active session to scan into",
                     font=ctk.CTkFont(size=12), text_color=C_MUTED).pack(anchor="w", padx=24)
        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x", side="bottom")
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=24, pady=14, side="bottom")

        ctk.CTkButton(foot, text="Cancel",
                      fg_color="transparent", border_color=C_BORDER,
                      border_width=1, text_color=C_MUTED, hover_color=C_SURFACE,
                      command=self.destroy).pack(side="right", padx=(8, 0))

        self._confirm_btn = ctk.CTkButton(
            foot, text="Join Session",
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._accept)
        self._confirm_btn.pack(side="right")

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.pack(fill="both", expand=True, padx=16, pady=12)
        self._list_frame.grid_columnconfigure(0, weight=1)

        self._load_sessions()

    def _load_sessions(self):
        db = SessionLocal()
        try:
            sessions = (
                db.query(EventSession)
                .options(joinedload(EventSession.periods))
                .filter(EventSession.is_active == 1)
                .order_by(EventSession.date.desc())
                .all()
            )
            for s in sessions:
                _ = len(s.periods)
        finally:
            db.close()

        if not sessions:
            ctk.CTkLabel(self._list_frame,
                         text="No active sessions found.",
                         font=ctk.CTkFont(size=13),
                         text_color=C_MUTED).pack(pady=40)
            return

        for s in sessions:
            self._build_row(s)

    def _build_row(self, s):
        type_labels = {"students": "Students", "staff": "Staff", "both": "Students + Staff"}
        type_colors = {"students": "#38bdf8", "staff": "#a78bfa", "both": "#3ecf8e"}

        row = ctk.CTkFrame(self._list_frame, fg_color=C_BG, corner_radius=8,
                           border_width=1, border_color=C_BORDER)
        row.pack(fill="x", pady=4)
        row.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text=s.name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT, anchor="w").grid(row=0, column=0, sticky="w")

        atype = getattr(s, "attendee_type", "students") or "students"
        ctk.CTkLabel(top,
                     text=type_labels.get(atype, "Students"),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=type_colors.get(atype, "#38bdf8"),
                     fg_color="#12141b", corner_radius=4,
                     padx=6, pady=2,
                     ).grid(row=0, column=1, padx=(8, 0))

        period_count = len(s.periods)
        meta = (f"{s.date} · "
                f"{s.estimated_attendees or '—'} expected · "
                f"{period_count} period{'s' if period_count != 1 else ''}")
        ctk.CTkLabel(row, text=meta,
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        row.bind("<Button-1>", lambda e, sid=s.id: self._select(sid))
        for child in row.winfo_children():
            child.bind("<Button-1>", lambda e, sid=s.id: self._select(sid))
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", lambda e, sid=s.id: self._select(sid))

        self._row_frames[s.id] = row

    def _select(self, session_id: int):
        for sid, frame in self._row_frames.items():
            frame.configure(border_color=C_BORDER, fg_color=C_BG)
        self._row_frames[session_id].configure(
            border_color=C_ACCENT, fg_color=C_SURFACE)
        self._selected_id = session_id
        self._confirm_btn.configure(state="normal")

    def _accept(self):
        if self._selected_id is None:
            return
        self.result = get_session_by_id(self._selected_id)
        self.destroy()