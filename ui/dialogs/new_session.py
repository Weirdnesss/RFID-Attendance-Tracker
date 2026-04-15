import tkinter as tk
from tkinter import messagebox
from webbrowser import get
import customtkinter as ctk

from ui.theme import C_ACCENT, C_BG, C_BORDER, C_ERROR, C_MUTED, C_SURFACE, C_TEXT
from datetime import datetime
from database import SessionLocal, Student, Program, Department, AcademicPeriod
from db.students_db import YEAR_LEVEL_LABELS
from ui.components.period_row import PeriodRow
from sqlalchemy import func


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(t) -> str:
    """Format a datetime.time object as '7:30 AM' (no leading zero on hour)."""
    if t is None:
        return ""
    return t.strftime("%I:%M %p").lstrip("0")


def _fetch_group_counts() -> dict:
    """
    Return a nested dict:
        { department: { (program, yearlevel): count } }

    Students with no department are grouped under '—'.
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
            yr   = YEAR_LEVEL_LABELS.get(r[2], "—")
            result.setdefault(dept, {})[(prog, yr)] = r.cnt
        return result
    finally:
        db.close()


def get_active_academic_period():
    """
    Returns the active AcademicPeriod object, or None.
    """
    db = SessionLocal()
    try:
        return (
            db.query(AcademicPeriod)
            .filter(AcademicPeriod.is_active == 1)
            .first()
        )
    finally:
        db.close()

# ── NewSessionDialog ──────────────────────────────────────────────────────────

class NewSessionDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("New Session")
        self.geometry("660x600")
        self.minsize(580, 800)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result = None
        self._period_rows: list[PeriodRow] = []
        self._estimate_mode = tk.StringVar(value="auto")
        self._selected_group_count: int | None = None

        self._build_ui()
        self._add_period(defaults={
            "name":            "Attendance Period",
            "time_in_start":   "07:00",
            "time_in_end":     "09:00",
            "late_enabled":    False,
            "late_start":      "07:30",
            "grace_minutes":   "0",
            "timeout_enabled": False,
            "timeout_start":   "11:00",
            "timeout_end":     "12:00",
        })

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="New Session",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", padx=24, pady=(14, 2))
        ctk.CTkLabel(
            hdr, text="Configure periods and tracking rules",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(anchor="w", padx=24)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # ── top grid: session name | estimated | date ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(16, 8))
        top.grid_columnconfigure(0, weight=2)
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            top, text="SESSION NAME",
            font=ctk.CTkFont(size=10), text_color=C_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(0, 3))

        self._name_var = tk.StringVar()
        self._name_entry = ctk.CTkEntry(
            top, textvariable=self._name_var,
            placeholder_text="e.g. General Assembly 2025",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32,
        )
        self._name_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12))

        est_lbl_row = ctk.CTkFrame(top, fg_color="transparent")
        est_lbl_row.grid(row=0, column=1, sticky="ew", pady=(0, 3))
        ctk.CTkLabel(
            est_lbl_row, text="ESTIMATED",
            font=ctk.CTkFont(size=10), text_color=C_MUTED,
        ).pack(side="left")
        self._auto_lbl = ctk.CTkLabel(
            est_lbl_row, text="",
            font=ctk.CTkFont(size=10), text_color=C_ACCENT,
        )
        self._auto_lbl.pack(side="left", padx=(6, 0))

        est_field_row = ctk.CTkFrame(top, fg_color="transparent")
        est_field_row.grid(row=1, column=1, sticky="ew")
        est_field_row.grid_columnconfigure(0, weight=1)

        self._estimate_var = tk.StringVar(value="")
        ctk.CTkEntry(
            est_field_row, textvariable=self._estimate_var,
            placeholder_text="e.g. 120",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._group_btn = ctk.CTkButton(
            est_field_row,
            text="Select Groups",
            width=120,
            fg_color=C_BORDER,
            hover_color=C_MUTED,
            text_color=C_TEXT,
            command=self._open_group_selector,
        )
        self._group_btn.grid(row=0, column=1)

        self._group_info_lbl = ctk.CTkLabel(
            top, text="",
            font=ctk.CTkFont(size=10), text_color=C_ACCENT,
        )
        self._group_info_lbl.grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 0))

        ctk.CTkLabel(
            top, text="DATE",
            font=ctk.CTkFont(size=10), text_color=C_MUTED,
        ).grid(row=2, column=0, sticky="w", pady=(8, 3))
        self._date_var = tk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        ctk.CTkEntry(
            top, textvariable=self._date_var,
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32,
        ).grid(row=3, column=0, sticky="ew", padx=(0, 12))

        self.after(100, self._auto_estimate)

        pl = ctk.CTkFrame(self, fg_color="transparent")
        pl.pack(fill="x", padx=24, pady=(8, 6))
        ctk.CTkLabel(
            pl, text="PERIODS",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=C_MUTED,
        ).pack(side="left")

        self._period_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._period_scroll.pack(fill="both", expand=True, padx=24)
        self._period_scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            self, text="+ Add period",
            fg_color="transparent",
            border_color=C_BORDER, border_width=1,
            text_color=C_MUTED, hover_color=C_BG,
            font=ctk.CTkFont(size=12), height=34,
            command=lambda: self._add_period(),
        ).pack(fill="x", padx=24, pady=(8, 4))

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=24, pady=14)
        ctk.CTkButton(
            foot, text="Cancel",
            fg_color="transparent",
            border_color=C_BORDER, border_width=1,
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

    # ── logic ─────────────────────────────────────────────────────────────────

    def _auto_estimate(self):
        """Populate the estimate field with the headcount of the latest school term."""
        if self._estimate_mode.get() != "auto":
            return
        try:
            from database import AcademicPeriod, AcademicYear, AcademicTerm
            db = SessionLocal()
            try:
                count = db.query(func.count(Student.student_id)).scalar()
                if count:
                    self._estimate_var.set(str(count))
                    self._auto_lbl.configure(text="(auto: all students)")
            finally:
                db.close()
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
            messagebox.showwarning(
                "Cannot delete",
                "A session must have at least one period.",
            )
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
                messagebox.showerror(
                    "Invalid input",
                    "Estimated attendees must be a non-negative number.",
                )
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

        dialog = ConfirmSessionDialog(self, {
            "name": name,
            "date": session_date,
            "estimated_attendees": estimated,
            "periods": periods,
            "academic_period_id": get_active_academic_period().id if get_active_academic_period() else None,
        })
        self.wait_window(dialog)

        if not dialog.result:
            return

        self.result = {
            "name": name,
            "date": session_date,
            "estimated_attendees": estimated,
            "periods": periods,
            "academic_period_id": get_active_academic_period().id if get_active_academic_period() else None,
        }
        self.destroy()

    # TODO: wire to radio buttons when added to the UI
    def _on_estimate_mode_change(self):
        mode = self._estimate_mode.get()
        if mode == "auto":
            self._group_btn.configure(state="disabled")
            self._group_info_lbl.configure(text="")
            self._auto_estimate()
        else:
            self._group_btn.configure(state="normal")
            self._auto_lbl.configure(text="")
            if self._selected_group_count is not None:
                self._estimate_var.set(str(self._selected_group_count))

    def _open_group_selector(self):
        try:
            current = int(self._estimate_var.get())
        except ValueError:
            current = 0

        dialog = StudentGroupSelectorDialog(self, current)
        self.wait_window(dialog)

        if dialog.result is not None:
            self._selected_group_count = dialog.result
            self._estimate_var.set(str(dialog.result))
            self._group_info_lbl.configure(
                text=f"Selected: {dialog.result} students")


# ── ConfirmSessionDialog ──────────────────────────────────────────────────────

class ConfirmSessionDialog(ctk.CTkToplevel):
    def __init__(self, parent, data: dict):
        super().__init__(parent)
        self.title("Confirm Session")
        self.geometry("560x520")
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result = False
        self._data = data
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Confirm Session",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", padx=20, pady=(16, 4))

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=20)

        d = self._data
        est = d["estimated_attendees"] if d["estimated_attendees"] is not None else "N/A"
        ctk.CTkLabel(info, text=f"Name: {d['name']}", text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Date: {d['date']}", text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Estimated: {est}", text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"Academic Period: {d['academic_period_id']}", text_color=C_TEXT).pack(anchor="w")

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x", padx=20, pady=10)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20)

        for i, p in enumerate(d["periods"], 1):
            self._add_period_preview(scroll, i, p)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(
            foot, text="Cancel",
            fg_color="transparent",
            border_color=C_BORDER, border_width=1,
            text_color=C_MUTED,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            foot, text="Start Session",
            fg_color=C_ACCENT, text_color="#fff",
            command=self._confirm,
        ).pack(side="right")

    def _add_period_preview(self, parent, idx: int, p: dict):
        card = ctk.CTkFrame(parent, fg_color=C_BG, corner_radius=10)
        card.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            card,
            text=f"{idx}. {p.get('name', 'Unnamed')}",
            font=ctk.CTkFont(weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        tag_frame = ctk.CTkFrame(card, fg_color="transparent")
        tag_frame.pack(anchor="w", padx=10, pady=(0, 8))

        tags: list[tuple[str, str, str]] = []

        ts = p.get("time_in_start")
        te = p.get("time_in_end")
        if ts and te:
            tags.append((f"In {_fmt_time(ts)}–{_fmt_time(te)}", "#0b1220", "#38bdf8"))

        if p.get("late_enabled"):
            ls    = p.get("late_start")
            grace = p.get("grace_minutes", 0)
            if ls:
                tags.append((f"Late {_fmt_time(ls)}", "#1f1708", "#f0a843"))
            if grace:
                tags.append((f"+{grace}m", "#16181f", C_MUTED))

        if p.get("timeout_enabled"):
            tos = p.get("timeout_start")
            toe = p.get("timeout_end")
            if tos and toe:
                tags.append((f"Out {_fmt_time(tos)}–{_fmt_time(toe)}", "#100e1f", "#a78bfa"))

        for text, bg, fg in tags:
            ctk.CTkLabel(
                tag_frame,
                text=text,
                fg_color=bg,
                text_color=fg,
                corner_radius=6,
                padx=8, pady=2,
            ).pack(side="left", padx=(0, 6))

    def _confirm(self):
        self.result = True
        self.destroy()


# ── SelectChip ────────────────────────────────────────────────────────────────

class SelectChip(ctk.CTkFrame):
    """
    Toggleable chip using composition (wraps CTkButton) rather than
    subclassing it, avoiding callback signature conflicts.
    """
    def __init__(self, parent, text: str, on_toggle):
        super().__init__(parent, fg_color=C_BG, corner_radius=15, cursor="hand2")
        self.selected = False
        self._on_toggle = on_toggle

        self._btn = ctk.CTkButton(
            self,
            text=text,
            height=30, width=42,
            corner_radius=15,
            fg_color="transparent",
            hover_color="#2a2d36",
            text_color=C_TEXT,
            command=self._clicked,
        )
        self._btn.pack()

    def set_selected(self, value: bool):
        self.selected = value
        self.configure(fg_color=C_ACCENT if value else C_BG)
        self._btn.configure(
            text_color="#ffffff" if value else C_TEXT,
            hover_color="#8aabff" if value else "#2a2d36",
        )

    def _clicked(self):
        self.set_selected(not self.selected)
        self._on_toggle(self)


# ── StudentGroupSelectorDialog ────────────────────────────────────────────────

class StudentGroupSelectorDialog(ctk.CTkToplevel):
    """
    Two-level drill-down group selector.

    Screen 1 — department tiles, each showing total + selected count.
    Screen 2 — programs within the chosen department, with year-level chips.

    Selections persist across departments. Confirm returns the total
    student count of all selected (program, yearlevel) groups.
    """

    def __init__(self, parent, current_estimate: int = 0):
        super().__init__(parent)
        self.title("Select Student Groups")
        self.geometry("520x500")
        self.minsize(440, 380)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result: int | None = None

        # { dept: { (prog, yr): count } }
        self._data: dict[str, dict[tuple, int]] = _fetch_group_counts()

        # flat selection state — persists across both screens
        self._check_vars: dict[tuple, tk.BooleanVar] = {
            key: tk.BooleanVar(value=False)
            for dept_map in self._data.values()
            for key in dept_map
        }

        # chips only exist while the program screen is visible
        self._chips: dict[tuple, SelectChip] = {}

        self._build_shell()
        self._show_departments()

    # ── persistent shell ──────────────────────────────────────────────────────

    def _build_shell(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        self._hdr = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        self._hdr.grid(row=0, column=0, sticky="ew")
        self._hdr.grid_columnconfigure(1, weight=1)

        self._back_btn = ctk.CTkButton(
            self._hdr,
            text="←",
            width=32, height=32,
            fg_color="transparent",
            hover_color=C_BORDER,
            text_color=C_TEXT,
            command=self._show_departments,
        )
        self._back_btn.grid(row=0, column=0, padx=(10, 0), pady=10)
        self._back_btn.grid_remove()   # hidden on the department screen

        self._title_lbl = ctk.CTkLabel(
            self._hdr, text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_TEXT,
        )
        self._title_lbl.grid(row=0, column=1, sticky="w", padx=14, pady=12)

        # Swappable content area
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 4))
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # Footer
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 14))
        foot.grid_columnconfigure(1, weight=1)

        self._total_lbl = ctk.CTkLabel(
            foot, text="Selected: 0 students",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_ACCENT,
        )
        self._total_lbl.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            foot, text="Cancel", width=90,
            fg_color=C_BORDER, hover_color=C_MUTED,
            text_color=C_TEXT, command=self.destroy,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            foot, text="Confirm", width=90,
            fg_color=C_ACCENT, command=self._confirm,
        ).grid(row=0, column=2, sticky="e")

    def _clear_content(self):
        for w in self._content.winfo_children():
            w.destroy()
        self._chips.clear()

    # ── screen 1: department tiles ────────────────────────────────────────────

    def _show_departments(self):
        self._clear_content()
        self._title_lbl.configure(text="Select department")
        self._back_btn.grid_remove()

        scroll = ctk.CTkScrollableFrame(
            self._content, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1)

        for i, dept in enumerate(sorted(self._data)):
            dept_map = self._data[dept]
            total    = sum(dept_map.values())
            selected = sum(
                cnt for key, cnt in dept_map.items()
                if self._check_vars[key].get()
            )

            card = ctk.CTkButton(
                scroll,
                text="",
                fg_color=C_BG,
                hover_color="#1e2130",
                corner_radius=10,
                height=72,
                command=lambda d=dept: self._show_programs(d),
            )
            card.grid(row=i // 2, column=i % 2, padx=6, pady=6, sticky="ew")

            # Place labels on top of the button via a transparent overlay frame
            inner = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
            inner.place(relx=0, rely=0, relwidth=1, relheight=1)
            inner.bind("<Button-1>", lambda e, d=dept: self._show_programs(d))

            ctk.CTkLabel(
                inner,
                text=dept,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=C_TEXT,
            ).pack(anchor="w", padx=12, pady=(10, 0))

            sub = f"{total} students"
            if selected:
                sub += f"  ·  {selected} selected"
            ctk.CTkLabel(
                inner,
                text=sub,
                font=ctk.CTkFont(size=11),
                text_color=C_ACCENT if selected else C_MUTED,
            ).pack(anchor="w", padx=12)

        self._update_total()

    # ── screen 2: programs within a department ────────────────────────────────

    def _show_programs(self, dept: str):
        self._clear_content()
        self._title_lbl.configure(text=dept)
        self._back_btn.grid()

        dept_map = self._data[dept]

        # { program: { yr: count } }
        tree: dict[str, dict] = {}
        for (prog, yr), cnt in dept_map.items():
            tree.setdefault(prog, {})[yr] = cnt

        scroll = ctk.CTkScrollableFrame(
            self._content, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for row_idx, prog in enumerate(sorted(tree)):
            yr_map     = tree[prog]
            prog_total = sum(yr_map.values())

            card = ctk.CTkFrame(scroll, fg_color=C_BG, corner_radius=10)
            card.grid(row=row_idx, column=0, sticky="ew", pady=(0, 8))

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(8, 4))

            ctk.CTkLabel(
                header, text=prog,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=C_TEXT,
            ).pack(side="left")
            ctk.CTkLabel(
                header, text=f"{prog_total} students",
                font=ctk.CTkFont(size=10), text_color=C_MUTED,
            ).pack(side="right")

            def _select_all(p=prog, ym=yr_map):
                keys      = [(p, yr) for yr in ym]
                new_state = not all(self._check_vars[k].get() for k in keys)
                for k in keys:
                    self._check_vars[k].set(new_state)
                    if k in self._chips:
                        self._chips[k].set_selected(new_state)
                self._update_total()

            ctk.CTkButton(
                header, text="All", width=40, height=24,
                fg_color=C_BORDER, hover_color=C_MUTED,
                text_color=C_TEXT, command=_select_all,
            ).pack(side="right", padx=(0, 6))

            chip_row = ctk.CTkFrame(card, fg_color="transparent")
            chip_row.pack(fill="x", padx=10, pady=(0, 10))

            for yr in sorted(yr_map):
                key = (prog, yr)
                cnt = yr_map[yr]

                item = ctk.CTkFrame(chip_row, fg_color="transparent")
                item.pack(side="left", padx=(0, 10))

                def _make_toggle(k=key):
                    def _toggle(_chip: SelectChip):
                        self._check_vars[k].set(_chip.selected)
                        self._update_total()
                    return _toggle

                chip = SelectChip(item, text=str(yr), on_toggle=_make_toggle())
                chip.set_selected(self._check_vars[key].get())
                chip.pack()
                self._chips[key] = chip

                ctk.CTkLabel(
                    item, text=str(cnt),
                    font=ctk.CTkFont(size=9), text_color=C_MUTED,
                ).pack()

        self._update_total()

    # ── logic ─────────────────────────────────────────────────────────────────

    def _update_total(self):
        total = sum(
            cnt
            for dept_map in self._data.values()
            for key, cnt in dept_map.items()
            if self._check_vars[key].get()
        )
        self._total_lbl.configure(text=f"Selected: {total} students")

    def _confirm(self):
        self.result = sum(
            cnt
            for dept_map in self._data.values()
            for key, cnt in dept_map.items()
            if self._check_vars[key].get()
        )
        self.destroy()