import tkinter as tk
import customtkinter as ctk
from ui.theme import C_SURFACE, C_BORDER, C_BG, C_TEXT, C_MUTED, C_ACCENT, C_ERROR
from database import SessionLocal, Staff, Department, Role


def _fetch_departments():
    db = SessionLocal()
    try:
        return db.query(Department).order_by(Department.name).all()
    finally:
        db.close()


def _fetch_roles():
    db = SessionLocal()
    try:
        return db.query(Role).order_by(Role.name).all()
    finally:
        db.close()


class StaffDialog(ctk.CTkToplevel):
    """
    Add or edit a staff member.
    Pass staff_data=None for add, or a dict with existing values for edit.
    Result is True on success, None on cancel.
    """

    def __init__(self, parent, staff_data: dict = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._edit = staff_data is not None
        self._data = staff_data or {}

        self.title("Edit Staff" if self._edit else "Add Staff")
        self.geometry("440x640")
        self.resizable(False, False)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result = None

        # Load options
        self._departments = _fetch_departments()
        self._roles       = _fetch_roles()
        self._dept_map    = {d.name: d.id for d in self._departments}
        self._role_map    = {r.name: r.id for r in self._roles}

        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr,
                     text="Edit Staff Member" if self._edit else "Add Staff Member",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(hdr,
                     text="Update details below" if self._edit else "Fill in staff details",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(anchor="w", padx=20)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # ── Form ──────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", expand=True, padx=20, pady=12)

        def _field(label, row, var, placeholder="", width=None):
            ctk.CTkLabel(body, text=label,
                         font=ctk.CTkFont(size=10), text_color=C_MUTED
                         ).grid(row=row * 2, column=0, sticky="w", pady=(8, 2),
                                columnspan=2 if width is None else 1)
            entry = ctk.CTkEntry(body, textvariable=var,
                                 placeholder_text=placeholder,
                                 fg_color=C_BG, border_color=C_BORDER,
                                 text_color=C_TEXT, height=32,
                                 width=width or 0)
            entry.grid(row=row * 2 + 1, column=0, sticky="ew" if width is None else "w",
                       columnspan=2 if width is None else 1)
            return entry

        body.grid_columnconfigure(0, weight=1)

        # Staff ID — read-only in edit mode
        self._id_var = tk.StringVar(value=self._data.get("staff_id", ""))
        self._id_entry = _field("STAFF ID", 0, self._id_var, "e.g. EMP-001")
        if self._edit:
            self._id_entry.configure(state="disabled", fg_color=C_SURFACE,
                                     text_color=C_MUTED)

        # Name fields
        self._first_var  = tk.StringVar(value=self._data.get("firstname", ""))
        self._middle_var = tk.StringVar(value=self._data.get("middlename", ""))
        self._last_var   = tk.StringVar(value=self._data.get("lastname", ""))

        _field("FIRST NAME",  1, self._first_var,  "First name")
        _field("MIDDLE NAME", 2, self._middle_var, "Middle name (optional)")
        _field("LAST NAME",   3, self._last_var,   "Last name")

        # Department dropdown
        ctk.CTkLabel(body, text="DEPARTMENT",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED
                     ).grid(row=8, column=0, sticky="w", pady=(8, 2))

        dept_names = [d.name for d in self._departments]
        current_dept = self._data.get("department", "")
        self._dept_var = tk.StringVar(
            value=current_dept if current_dept in dept_names else
            (dept_names[0] if dept_names else ""))

        ctk.CTkOptionMenu(
            body, variable=self._dept_var,
            values=dept_names if dept_names else ["No departments"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=32,
        ).grid(row=9, column=0, sticky="ew")

        # Role dropdown
        ctk.CTkLabel(body, text="ROLE",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED
                     ).grid(row=10, column=0, sticky="w", pady=(8, 2))

        role_names = [r.name for r in self._roles]
        current_role = self._data.get("role", "")
        self._role_var = tk.StringVar(
            value=current_role if current_role in role_names else
            (role_names[0] if role_names else ""))

        ctk.CTkOptionMenu(
            body, variable=self._role_var,
            values=role_names if role_names else ["No roles"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=32,
        ).grid(row=11, column=0, sticky="ew")

        # Active toggle
        ctk.CTkLabel(body, text="STATUS",
                     font=ctk.CTkFont(size=10), text_color=C_MUTED
                     ).grid(row=12, column=0, sticky="w", pady=(8, 2))

        self._active_var = tk.BooleanVar(value=self._data.get("is_active", True))
        ctk.CTkSwitch(
            body, text="Active",
            variable=self._active_var,
            font=ctk.CTkFont(size=12), text_color=C_TEXT,
            fg_color=C_BORDER, progress_color=C_ACCENT,
        ).grid(row=13, column=0, sticky="w", pady=(4, 0))

        # ── Footer ────────────────────────────────────────────────────
        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=12)

        ctk.CTkButton(
            foot, text="Cancel", width=90,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            foot, text="Save", width=90,
            fg_color=C_ACCENT, text_color="#fff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirm,
        ).pack(side="right")

    def _confirm(self):
        staff_id  = self._id_var.get().strip()
        first     = self._first_var.get().strip()
        last      = self._last_var.get().strip()
        middle    = self._middle_var.get().strip()
        dept_name = self._dept_var.get()
        role_name = self._role_var.get()
        is_active = self._active_var.get()

        # Validate
        if not staff_id:
            self._id_entry.configure(border_color=C_ERROR)
            return
        if not first:
            return
        if not last:
            return

        dept_id = self._dept_map.get(dept_name)
        role_id = self._role_map.get(role_name)

        db = SessionLocal()
        try:
            if self._edit:
                db.query(Staff).filter(
                    Staff.staff_id == staff_id
                ).update({
                    "first_name":     first,
                    "middle_name":    middle or None,
                    "last_name":      last,
                    "department_id":  dept_id,
                    "role_id":        role_id,
                    "is_active":      is_active,
                })
            else:
                # Check for duplicate ID
                exists = db.query(Staff).filter(
                    Staff.staff_id == staff_id).first()
                if exists:
                    self._id_entry.configure(border_color=C_ERROR)
                    from tkinter import messagebox
                    messagebox.showerror(
                        "Duplicate ID",
                        f"Staff ID '{staff_id}' already exists.")
                    return

                db.add(Staff(
                    staff_id=staff_id,
                    first_name=first,
                    middle_name=middle or None,
                    last_name=last,
                    department_id=dept_id,
                    role_id=role_id,
                    is_active=is_active,
                ))
            db.commit()
            self.result = True
            self.destroy()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", str(e))
        finally:
            db.close()