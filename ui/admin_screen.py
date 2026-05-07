"""
admin_screen.py
---------------
Admin screen for managing sessions.
Allows creating new sessions and ending active ones.
"""

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from database import SessionLocal, Session as EventSession
from ui.dialogs.edit_session import EditSessionDialog
from ui.dialogs.staff_dialog import Staff
from ui.theme import (
    C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
    C_ACCENT, C_SUCCESS, C_ERROR
)

class SessionsPanel(ctk.CTkFrame):

    def __init__(self, parent, admin_screen, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=0, **kwargs)
        self._admin = admin_screen
        self._session_rows: dict[int, ctk.CTkFrame] = {}
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            toolbar, text="ACTIVE SESSIONS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C_MUTED).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            toolbar, text="+ New Session", width=130,
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._create_session,
        ).grid(row=0, column=1)

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

    def _load_sessions(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._session_rows.clear()

        db = SessionLocal()
        try:
            sessions = (
                db.query(EventSession)
                .filter(EventSession.is_active == 1)
                .order_by(EventSession.date.desc(), EventSession.created_at.desc())
                .all()
            )
            data = [{
                "id":               s.id,
                "name":             s.name,
                "date":             s.date,
                "created_at":       s.created_at,
                "student_estimated": s.student_estimated,
                "staff_estimated":   s.staff_estimated,
                "period_count":     len(s.periods),
            } for s in sessions]
        finally:
            db.close()

        if not data:
            ctk.CTkLabel(
                self._list_frame, text="No active sessions.",
                font=ctk.CTkFont(size=13), text_color=C_MUTED,
            ).pack(pady=40)
            return

        for s in data:
            self._build_row(s)

    def _build_row(self, s: dict):
        row = ctk.CTkFrame(
            self._list_frame, fg_color=C_SURFACE, corner_radius=8,
            border_width=1, border_color=C_BORDER)
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            row, text=s["name"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 2))

        period_count = s["period_count"]
        created      = s["created_at"].strftime("%I:%M %p") if s["created_at"] else "—"
        meta = (f"{s['date']}  ·  Started {created}  ·  "
                f"{s['student_estimated'] or '—'} expected  ·  "
                f"{period_count} period{'s' if period_count != 1 else ''}")
        ctk.CTkLabel(
            row, text=meta, font=ctk.CTkFont(size=11),
            text_color=C_MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=1, rowspan=2, padx=16, pady=10)

        ctk.CTkButton(
            btn_frame, text="Edit", width=80,
            fg_color="transparent", border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, hover_color=C_SURFACE,
            command=lambda sid=s["id"], sname=s["name"]: self._edit_session(sid, sname),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="End Session", width=110,
            fg_color="transparent", border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda sid=s["id"], sname=s["name"]: self._end_session(sid, sname),
        ).pack(side="left")

        self._session_rows[s["id"]] = row

    def _create_session(self):
        from ui.dialogs.new_session import NewSessionDialog
        dlg = NewSessionDialog(self)
        self.wait_window(dlg)
        if dlg.result and dlg.result.get("started"):
            self._load_sessions()

    def _edit_session(self, session_id, session_name):
        from ui.dialogs.edit_session import EditSessionDialog
        dlg = EditSessionDialog(self, {"id": session_id, "name": session_name})
        self.wait_window(dlg)
        if dlg.result:
            self._load_sessions()

    def _end_session(self, session_id, session_name):
        if not messagebox.askyesno(
                "End Session",
                f"End session '{session_name}'?\n\nThis cannot be undone."):
            return
        db = SessionLocal()
        try:
            db.query(EventSession).filter(
                EventSession.id == session_id
            ).update({"is_active": 0, "active_flag": None, "ended_at": datetime.now()})
            db.commit()
        finally:
            db.close()

        if session_id in self._session_rows:
            self._session_rows.pop(session_id).destroy()
        if not self._session_rows:
            ctk.CTkLabel(
                self._list_frame, text="No active sessions.",
                font=ctk.CTkFont(size=13), text_color=C_MUTED,
            ).pack(pady=40)

    def refresh(self):
        self._load_sessions()

class RolesPanel(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=0, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="ROLES",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            toolbar, text="+ Add Role", width=110,
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._add_role,
        ).grid(row=0, column=1)

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

    def _load(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        db = SessionLocal()
        try:
            from database import Role, Staff
            from sqlalchemy import func
            rows = (
                db.query(Role, func.count(Staff.staff_id).label("cnt"))
                .outerjoin(Staff, Staff.role_id == Role.id)
                .group_by(Role.id)
                .order_by(Role.name)
                .all()
            )
        finally:
            db.close()

        if not rows:
            ctk.CTkLabel(self._list_frame, text="No roles yet.",
                         font=ctk.CTkFont(size=13), text_color=C_MUTED,
                         ).pack(pady=40)
            return

        for role, cnt in rows:
            self._build_row(role.id, role.name, cnt)

    def _build_row(self, role_id, name, count):
        row = ctk.CTkFrame(self._list_frame, fg_color=C_SURFACE,
                           corner_radius=8, border_width=1, border_color=C_BORDER)
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(row, text=name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT, anchor="w",
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=12)

        ctk.CTkLabel(row, text=f"{count} staff",
                     font=ctk.CTkFont(size=11), text_color=C_MUTED,
                     ).grid(row=0, column=1, padx=12)

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=16, pady=10)

        ctk.CTkButton(
            btn_frame, text="Edit", width=70,
            fg_color="transparent", border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, hover_color=C_SURFACE,
            command=lambda: self._edit_role(role_id, name),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Delete", width=70,
            fg_color="transparent", border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            command=lambda: self._delete_role(role_id, name, count),
        ).pack(side="left")

    def _add_role(self):
        from ui.dialogs.simple_input import SimpleInputDialog
        dlg = SimpleInputDialog(self, title="Add Role", label="Role name")
        self.wait_window(dlg)
        if not dlg.result:
            return
        db = SessionLocal()
        try:
            from database import Role
            db.add(Role(name=dlg.result.strip()))
            db.commit()
        finally:
            db.close()
        self._load()

    def _edit_role(self, role_id, current_name):
        from ui.dialogs.simple_input import SimpleInputDialog
        dlg = SimpleInputDialog(self, title="Edit Role",
                                label="Role name", value=current_name)
        self.wait_window(dlg)
        if not dlg.result:
            return
        db = SessionLocal()
        try:
            from database import Role
            db.query(Role).filter(Role.id == role_id).update(
                {"name": dlg.result.strip()})
            db.commit()
        finally:
            db.close()
        self._load()

    def _delete_role(self, role_id, name, count):
        msg = f"Delete role '{name}'?"
        if count > 0:
            msg += f"\n\n{count} staff member{'s' if count != 1 else ''} will have their role cleared."
        if not messagebox.askyesno("Delete Role", msg):
            return
        db = SessionLocal()
        try:
            from database import Role
            db.query(Role).filter(Role.id == role_id).delete()
            db.commit()
        finally:
            db.close()
        self._load()

    def refresh(self):
        self._load()

class DepartmentsPanel(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=0, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="DEPARTMENTS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            toolbar, text="+ Add Department", width=140,
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._add_dept,
        ).grid(row=0, column=1)

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

    def _load(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        db = SessionLocal()
        try:
            from database import Department, Staff, Program, Student
            from sqlalchemy import func
            rows = (
                db.query(
                    Department,
                    func.count(func.distinct(Staff.staff_id)).label("staff_cnt"),
                    func.count(func.distinct(Student.student_id)).label("student_cnt"),
                )
                .outerjoin(Staff, Staff.department_id == Department.id)
                .outerjoin(Program, Program.department_id == Department.id)
                .outerjoin(Student, Student.program_id == Program.id)
                .group_by(Department.id)
                .order_by(Department.name)
                .all()
            )
        finally:
            db.close()

        if not rows:
            ctk.CTkLabel(self._list_frame, text="No departments yet.",
                         font=ctk.CTkFont(size=13), text_color=C_MUTED,
                         ).pack(pady=40)
            return

        for dept, staff_cnt, student_cnt in rows:
            self._build_row(dept.id, dept.name, dept.code, staff_cnt, student_cnt)

    def _build_row(self, dept_id, name, code, staff_cnt, student_cnt):
        row = ctk.CTkFrame(self._list_frame, fg_color=C_SURFACE,
                           corner_radius=8, border_width=1, border_color=C_BORDER)
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)

        ctk.CTkLabel(left, text=name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT).pack(side="left")
        ctk.CTkLabel(left, text=f"  {code}",
                     font=ctk.CTkFont(size=11), text_color=C_MUTED).pack(side="left")

        ctk.CTkLabel(row, text=f"{student_cnt} students · {staff_cnt} staff",
                     font=ctk.CTkFont(size=11), text_color=C_MUTED,
                     ).grid(row=0, column=1, padx=12)

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=16, pady=10)

        ctk.CTkButton(
            btn_frame, text="Edit", width=70,
            fg_color="transparent", border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, hover_color=C_SURFACE,
            command=lambda: self._edit_dept(dept_id, name, code),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Delete", width=70,
            fg_color="transparent", border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            command=lambda: self._delete_dept(dept_id, name, staff_cnt, student_cnt),
        ).pack(side="left")

    def _add_dept(self):
        from ui.dialogs.simple_input import SimpleInputDialog
        dlg = SimpleInputDialog(self, title="Add Department",
                                label="Department name", second_label="Code")
        self.wait_window(dlg)
        if not dlg.result:
            return
        db = SessionLocal()
        try:
            from database import Department
            db.add(Department(name=dlg.result[0].strip(),
                              code=dlg.result[1].strip().upper()))
            db.commit()
        finally:
            db.close()
        self._load()

    def _edit_dept(self, dept_id, name, code):
        from ui.dialogs.simple_input import SimpleInputDialog
        dlg = SimpleInputDialog(self, title="Edit Department",
                                label="Department name", value=name,
                                second_label="Code", second_value=code)
        self.wait_window(dlg)
        if not dlg.result:
            return
        db = SessionLocal()
        try:
            from database import Department
            db.query(Department).filter(Department.id == dept_id).update({
                "name": dlg.result[0].strip(),
                "code": dlg.result[1].strip().upper(),
            })
            db.commit()
        finally:
            db.close()
        self._load()

    def _delete_dept(self, dept_id, name, staff_cnt, student_cnt):
        msg = f"Delete department '{name}'?"
        if staff_cnt or student_cnt:
            msg += f"\n\n{student_cnt} student{'s' if student_cnt != 1 else ''} and {staff_cnt} staff member{'s' if staff_cnt != 1 else ''} are linked to this department."
        if not messagebox.askyesno("Delete Department", msg):
            return
        db = SessionLocal()
        try:
            from database import Department
            db.query(Department).filter(Department.id == dept_id).delete()
            db.commit()
        finally:
            db.close()
        self._load()

    def refresh(self):
        self._load()

class StaffPanel(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", corner_radius=0, **kwargs)
        self._build_ui()
        self._load()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="STAFF",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).grid(row=0, column=0, sticky="w")

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search)

        ctk.CTkEntry(toolbar, textvariable=self._search_var,
                     placeholder_text="Search name or ID...",
                     fg_color=C_BG, border_color=C_BORDER,
                     text_color=C_TEXT, height=32, width=200,
                     corner_radius=8,
                     ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            toolbar, text="+ Add Staff", width=110,
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._add_staff,
        ).grid(row=0, column=2)

        # List
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

    def _load(self, search=""):
        for w in self._list_frame.winfo_children():
            w.destroy()

        db = SessionLocal()
        try:
            from database import Staff, Department, Role
            q = (db.query(Staff)
                .outerjoin(Department, Staff.department_id == Department.id)
                .outerjoin(Role, Staff.role_id == Role.id)
                .order_by(Staff.last_name, Staff.first_name))

            if search:
                like = f"%{search}%"
                q = q.filter(
                    Staff.first_name.ilike(like) |
                    Staff.last_name.ilike(like)  |
                    Staff.staff_id.ilike(like))

            staff_list = [{
                "staff_id":   s.staff_id,
                "full_name":  f"{s.last_name}, {s.first_name}" + (f" {s.middle_name}" if s.middle_name else ""),
                "role":       s.role,        # accesses role_ref.name HERE while session is open
                "department": s.department,  # same
                "is_active":  s.is_active,
            } for s in q.all()]
        finally:
            db.close()

        if not staff_list:
            ctk.CTkLabel(self._list_frame,
                        text="No staff found.",
                        font=ctk.CTkFont(size=13),
                        text_color=C_MUTED).pack(pady=40)
            return

        for s in staff_list:
            self._build_row(s)

    def _build_row(self, s: dict):
        row = ctk.CTkFrame(
            self._list_frame,
            fg_color=C_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=C_BORDER
        )
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)

        # Left side
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=16, pady=10)

        dot_color = C_SUCCESS if s["is_active"] else C_MUTED

        ctk.CTkFrame(
            left,
            fg_color=dot_color,
            width=8,
            height=8,
            corner_radius=4
        ).pack(side="left", padx=(0, 10))

        info = ctk.CTkFrame(left, fg_color="transparent")
        info.pack(side="left")

        ctk.CTkLabel(
            info,
            text=s["full_name"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT
        ).pack(anchor="w")

        ctk.CTkLabel(
            info,
            text=f"{s['staff_id']}  ·  {s['role']}  ·  {s['department']}",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED
        ).pack(anchor="w")

        # Buttons
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=16, pady=10)

        ctk.CTkButton(
            btn_frame,
            text="Edit",
            width=70,
            fg_color="transparent",
            border_color=C_BORDER,
            border_width=1,
            text_color=C_TEXT,
            hover_color=C_SURFACE,
            command=lambda sid=s["staff_id"]: self._edit_staff(sid),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Delete",
            width=70,
            fg_color="transparent",
            border_color=C_ERROR,
            border_width=1,
            text_color=C_ERROR,
            hover_color="#2a1a1a",
            command=lambda sid=s["staff_id"], n=s["full_name"]: self._delete_staff(sid, n),
        ).pack(side="left")
    
    def _add_staff(self):
        from ui.dialogs.staff_dialog import StaffDialog
        dlg = StaffDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self._load(self._search_var.get().strip())

    def _edit_staff(self, staff_id: str):
        db = SessionLocal()
        try:
            from database import Staff
            s = db.query(Staff).filter(Staff.staff_id == staff_id).first()
            if not s:
                return
            data = {
                "staff_id":   s.staff_id,
                "firstname":  s.first_name,
                "middlename": s.middle_name or "",
                "lastname":   s.last_name,
                "department": s.department,
                "role":       s.role,
                "is_active":  s.is_active,
            }
        finally:
            db.close()

        from ui.dialogs.staff_dialog import StaffDialog
        dlg = StaffDialog(self, staff_data=data)
        self.wait_window(dlg)
        if dlg.result:
            self._load(self._search_var.get().strip())

    def _delete_staff(self, staff_id: str, name: str):
        # Check for attendance records first
        db = SessionLocal()
        try:
            from database import StaffAttendance
            count = db.query(StaffAttendance).filter(
                StaffAttendance.staff_id == staff_id).count()
        finally:
            db.close()

        msg = f"Delete '{name}'?"
        if count > 0:
            msg += f"\n\nThis staff member has {count} attendance record{'s' if count != 1 else ''}. These will also be deleted."

        if not messagebox.askyesno("Delete Staff", msg):
            return

        db = SessionLocal()
        try:
            from database import Staff, StaffAttendance
            db.query(StaffAttendance).filter(
                StaffAttendance.staff_id == staff_id).delete()
            db.query(Staff).filter(Staff.staff_id == staff_id).delete()
            db.commit()
        finally:
            db.close()

        self._load(self._search_var.get().strip())

    def _on_search(self, *_):
        if hasattr(self, "_search_job"):
            self.after_cancel(self._search_job)
        self._search_job = self.after(
            400, lambda: self._load(self._search_var.get().strip()))

    def refresh(self):
        self._search_var.set("")
        self._load()

class AdminScreen(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._session_rows: dict[int, ctk.CTkFrame] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr, text="Admin",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(10, 0))
        ctk.CTkLabel(
            hdr, text="Manage sessions, staff, roles, and departments",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=24)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).grid(
            row=0, column=0, sticky="sew")

        # ── Tab bar ───────────────────────────────────────────────────────
        tab_bar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=40)
        tab_bar.grid(row=1, column=0, sticky="ew")
        tab_bar.grid_propagate(False)

        self._tab_btns = {}
        self._active_tab = None

        for name in ["Sessions", "Staff", "Roles", "Departments"]:
            btn = ctk.CTkButton(
                tab_bar, text=name, width=110, height=32,
                fg_color="transparent", text_color=C_MUTED,
                hover_color=C_BG, corner_radius=6,
                font=ctk.CTkFont(size=12),
                command=lambda n=name: self._switch_tab(n))
            btn.pack(side="left", padx=(8, 0), pady=4)
            self._tab_btns[name] = btn

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).grid(
            row=1, column=0, sticky="sew")

        # ── Tab content area ──────────────────────────────────────────────
        self._content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._content.grid(row=2, column=0, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Build all tab panels ──────────────────────────────────────────
        self._panels = {
            "Sessions":    SessionsPanel(self._content, self),
            "Staff":       StaffPanel(self._content),
            "Roles":       RolesPanel(self._content),
            "Departments": DepartmentsPanel(self._content),
        }
        for panel in self._panels.values():
            panel.grid(row=0, column=0, sticky="nsew")
            panel.grid_remove()

        self._switch_tab("Sessions")

    def _switch_tab(self, name: str):
        if self._active_tab:
            self._panels[self._active_tab].grid_remove()
            self._tab_btns[self._active_tab].configure(
                fg_color="transparent", text_color=C_MUTED,
                font=ctk.CTkFont(size=12))

        self._active_tab = name
        self._panels[name].grid()
        self._panels[name].refresh()
        self._tab_btns[name].configure(
            fg_color=C_BG, text_color=C_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"))

    def refresh(self):
        if self._active_tab:
            self._panels[self._active_tab].refresh()
        # self._load_sessions()
    # ------------------------------------------------------------------
    # Session rows
    # ------------------------------------------------------------------

    # def _load_sessions(self):
    #     # Clear existing rows
    #     for w in self._list_frame.winfo_children():
    #         w.destroy()
    #     self._session_rows.clear()

    #     db = SessionLocal()
    #     try:
    #         sessions = (
    #             db.query(EventSession)
    #             .filter(EventSession.is_active == 1)
    #             .order_by(EventSession.date.desc(), EventSession.created_at.desc())
    #             .all()
    #         )
    #         # Eagerly load what we need
    #         data = [
    #             {
    #                 "id":                  s.id,
    #                 "name":                s.name,
    #                 "date":                s.date,
    #                 "created_at":          s.created_at,
    #                 "student_estimated":     s.student_estimated,
    #                 "staff_estimated":       s.staff_estimated,
    #                 "period_count":        len(s.periods),
    #             }
    #             for s in sessions
    #         ]
    #     finally:
    #         db.close()

    #     if not data:
    #         ctk.CTkLabel(
    #             self._list_frame,
    #             text="No active sessions.",
    #             font=ctk.CTkFont(size=13),
    #             text_color=C_MUTED,
    #         ).pack(pady=40)
    #         return

    #     for s in data:
    #         self._build_row(s)

    # def _build_row(self, s: dict):
    #     row = ctk.CTkFrame(
    #         self._list_frame,
    #         fg_color=C_SURFACE, corner_radius=8,
    #         border_width=1, border_color=C_BORDER,
    #     )
    #     row.pack(fill="x", padx=8, pady=4)
    #     row.grid_columnconfigure(0, weight=1)

    #     # Left — session info
    #     ctk.CTkLabel(
    #         row, text=s["name"],
    #         font=ctk.CTkFont(size=13, weight="bold"),
    #         text_color=C_TEXT, anchor="w",
    #     ).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 2))

    #     period_count = s["period_count"]
    #     created      = s["created_at"].strftime("%I:%M %p") if s["created_at"] else "—"
    #     meta = (f"{s['date']}  ·  "
    #             f"Started {created}  ·  "
    #             f"{s['student_estimated'] or '—'} expected  ·  "
    #             f"{period_count} period{'s' if period_count != 1 else ''}")
    #     ctk.CTkLabel(
    #         row, text=meta,
    #         font=ctk.CTkFont(size=11),
    #         text_color=C_MUTED, anchor="w",
    #     ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

    #     btn_frame = ctk.CTkFrame(row, fg_color="transparent")
    #     btn_frame.grid(row=0, column=1, rowspan=2, padx=16, pady=10)

    #     ctk.CTkButton(
    #         btn_frame, text="Edit", width=80,
    #         fg_color="transparent",
    #         border_color=C_BORDER, border_width=1,
    #         text_color=C_TEXT, hover_color=C_SURFACE,
    #         font=ctk.CTkFont(size=12),
    #         command=lambda sid=s["id"], sname=s["name"]: self._edit_session(sid, sname),
    #     ).pack(side="left", padx=(0, 8))

    #     ctk.CTkButton(
    #         btn_frame, text="End Session", width=110,
    #         fg_color="transparent",
    #         border_color=C_ERROR, border_width=1,
    #         text_color=C_ERROR, hover_color="#2a1a1a",
    #         font=ctk.CTkFont(size=12, weight="bold"),
    #         command=lambda sid=s["id"], sname=s["name"]: self._end_session(sid, sname),
    #     ).pack(side="left")

    #     self._session_rows[s["id"]] = row

    # # ------------------------------------------------------------------
    # # Actions
    # # ------------------------------------------------------------------

    # def _create_session(self):
    #     from ui.dialogs.new_session import NewSessionDialog
    #     dlg = NewSessionDialog(self)
    #     self.wait_window(dlg)
    #     if dlg.result and dlg.result.get("started"):
    #         self._load_sessions()

    # def _edit_session(self, session_id: int, session_name: str):
    #     dlg = EditSessionDialog(self, {"id": session_id, "name": session_name})
    #     self.wait_window(dlg)
    #     if dlg.result:
    #         self._load_sessions()

    # def _end_session(self, session_id: int, session_name: str):
    #     if not messagebox.askyesno(
    #             "End Session",
    #             f"End session '{session_name}'?\n\nThis cannot be undone."):
    #         return

    #     db = SessionLocal()
    #     try:
    #         db.query(EventSession).filter(
    #             EventSession.id == session_id
    #         ).update({
    #             "is_active":  0,
    #             "active_flag": None,
    #             "ended_at":   datetime.now(),
    #         })
    #         db.commit()
    #     finally:
    #         db.close()

    #     # Remove the row without reloading everything
    #     if session_id in self._session_rows:
    #         self._session_rows.pop(session_id).destroy()

    #     # Show empty state if no sessions left
    #     if not self._session_rows:
    #         ctk.CTkLabel(
    #             self._list_frame,
    #             text="No active sessions.",
    #             font=ctk.CTkFont(size=13),
    #             text_color=C_MUTED,
    #         ).pack(pady=40)
