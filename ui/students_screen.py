"""
students_screen.py
------------------
Students screen for the RFID Attendance Tracker.

Features:
    - Browse students with search/filter
    - Paginated list (50 per page) — handles 4000+ rows without freezing
    - Single efficient SQL query with GROUP BY for attendance counts
    - Click a student to view their full attendance history

Embedded by main.py as a CTkFrame.

Performance fixes (Windows):
    - Selection highlight swaps colors on 2 widgets only — no list rebuild
    - Attendance history is cached; re-clicking the same student skips the DB
    - Child-widget click bindings replaced with a single propagating bind
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime

from db.students_db import _fetch_students, _fetch_filter_options, _fetch_student_attendance, PAGE_SIZE, STUDENT_SIZE
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED, C_ACCENT, C_SUCCESS, C_WARNING)
# ---------------------------------------------------------------------------
# Student detail panel
# ---------------------------------------------------------------------------

class StudentDetailPanel(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        self._name_lbl = ctk.CTkLabel(
            hdr, text="Select a student",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_MUTED)
        self._name_lbl.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        self._id_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._id_lbl.grid(row=0, column=1, padx=(0, 20))

        # Info row
        info = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        info.grid(row=1, column=0, sticky="ew")
        info.grid_propagate(False)

        self._program_lbl = ctk.CTkLabel(info, text="",
                                        font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._program_lbl.pack(side="left", padx=20)
        self._yearlevel_lbl = ctk.CTkLabel(info, text="",
                                            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._yearlevel_lbl.pack(side="left")
        self._term_lbl = ctk.CTkLabel(info, text="",
                                    font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._term_lbl.pack(side="left", padx=(8, 0))

        # Stats pills
        stats = ctk.CTkFrame(self, fg_color="transparent", height=72)
        stats.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        stats.grid_propagate(False)

        self._stat_labels = {}
        for key, label, color in [
            ("present", "Present",  C_SUCCESS),
            ("late",    "Late",     C_WARNING),
            ("total",   "Sessions", C_ACCENT),
        ]:
            pill = ctk.CTkFrame(stats, fg_color=C_SURFACE,
                                corner_radius=8, border_width=1, border_color=color)
            pill.pack(side="left", padx=(0, 8))
            val = ctk.CTkLabel(pill, text="—",
                                font=ctk.CTkFont(size=18, weight="bold"),
                                text_color=color)
            val.pack(padx=14, pady=(8, 0))
            ctk.CTkLabel(pill, text=label,
                        font=ctk.CTkFont(size=10),
                        text_color=C_MUTED).pack(padx=14, pady=(0, 8))
            self._stat_labels[key] = val

        # History column headers
        col_hdr = ctk.CTkFrame(self, fg_color=C_ACCENT, corner_radius=0, height=30)
        col_hdr.grid(row=3, column=0, sticky="new", padx=16, pady=(12, 0))
        for text, w in [("Session", 220), ("Date", 100), ("Period", 90),
                        ("Status", 90), ("Time In", 110), ("Time Out", 110)]:
            ctk.CTkLabel(col_hdr, text=text, width=w,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=C_TEXT).pack(side="left", padx=4)

        self._history_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._history_scroll.grid(row=3, column=0, sticky="nsew",
                                padx=16, pady=(40, 0))
        self._history_scroll.grid_columnconfigure(0, weight=1)

        self._empty_lbl = ctk.CTkLabel(
            self._history_scroll,
            text="Select a student to view their attendance history",
            font=ctk.CTkFont(size=13), text_color=C_MUTED)
        self._empty_lbl.pack(pady=40)

        # ── Pagination footer ────────────────────────────────────────────────
        self._page_bar = ctk.CTkFrame(self, fg_color=C_SURFACE,
                                    corner_radius=0, height=40)
        self._page_bar.grid(row=4, column=0, sticky="ew")
        self._page_bar.grid_propagate(False)
        self._page_bar.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            self._page_bar, text="← Prev", width=80, height=28,
            fg_color="transparent", border_width=1, border_color=C_BORDER,
            text_color=C_MUTED, hover_color=C_SURFACE,
            font=ctk.CTkFont(size=11),
            command=self._prev_page)
        self._prev_btn.grid(row=0, column=0, padx=(12, 4), pady=6)

        self._page_lbl = ctk.CTkLabel(
            self._page_bar, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._page_lbl.grid(row=0, column=1)

        self._next_btn = ctk.CTkButton(
            self._page_bar, text="Next →", width=80, height=28,
            fg_color="transparent", border_width=1, border_color=C_BORDER,
            text_color=C_MUTED, hover_color=C_SURFACE,
            font=ctk.CTkFont(size=11),
            command=self._next_page)
        self._next_btn.grid(row=0, column=2, padx=(4, 12), pady=6)

        self._page_bar.grid_remove()    # hidden until a student is loaded

        # internal pagination state
        self._total_records: int = 0
        self._current_student_id: int | None = None
        self._current_page: int = 0

    def _render_page(self):
        for w in self._history_scroll.winfo_children():
            w.destroy()

        offset = self._current_page * STUDENT_SIZE
        total, records = _fetch_student_attendance(
            self._current_student_id, offset=offset, limit=STUDENT_SIZE)
        self._total_records = total

        pages = max(1, -(-total // STUDENT_SIZE))

        if not records:
            ctk.CTkLabel(self._history_scroll,
                        text="No attendance records found.",
                        font=ctk.CTkFont(size=13),
                        text_color=C_MUTED).pack(pady=40)
            return

        for i, rec in enumerate(records):
            bg = "#13151c" if i % 2 == 0 else C_BG
            sc = {"present": C_SUCCESS, "late": C_WARNING}.get(rec["status"], C_MUTED)
            r  = ctk.CTkFrame(self._history_scroll, fg_color=bg,
                            corner_radius=0, height=32)
            r.pack(fill="x")
            r.pack_propagate(False)
            for text, w, color, bold in [
                (rec["session_name"],    220, C_TEXT,   False),
                (rec["date"],            100, C_MUTED,  False),
                (rec["period_name"],      90, C_ACCENT, False),
                (rec["status"].upper(),   90, sc,       True),
                (rec["time_in"],         110, C_TEXT,   False),
                (rec["time_out"],        110, C_MUTED,  False),
            ]:
                ctk.CTkLabel(r, text=text, width=w, anchor="w",
                            font=ctk.CTkFont(size=11,
                                            weight="bold" if bold else "normal"),
                            text_color=color).pack(side="left", padx=4)
            ctk.CTkFrame(self._history_scroll, fg_color=C_BORDER,
                        height=1, corner_radius=0).pack(fill="x")

        # update controls
        self._page_lbl.configure(
            text=f"Page {self._current_page + 1} of {pages}  ·  {total} records")
        self._prev_btn.configure(state="normal" if self._current_page > 0 else "disabled")
        self._next_btn.configure(state="normal" if self._current_page < pages - 1 else "disabled")

        # scroll back to top on page change
        self._history_scroll._parent_canvas.yview_moveto(0)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()

    def _next_page(self):
        pages = max(1, -(-self._total_records // STUDENT_SIZE))
        if self._current_page < pages - 1:
            self._current_page += 1
            self._render_page()

    def load(self, data: dict):
        name = " ".join(filter(None, [
            data["firstname"], data["middlename"], data["lastname"]
        ]))
        self._name_lbl.configure(text=name, text_color=C_TEXT)
        self._id_lbl.configure(text=f"ID: {data['student_id']}", text_color=C_MUTED)
        self._program_lbl.configure(
            text=f"{data['program']}  ({data['code']})", text_color=C_TEXT)
        self._yearlevel_lbl.configure(
            text=f"·  {data['yearlevel']}", text_color=C_MUTED)


        for key in ("present", "late", "total"):
            self._stat_labels[key].configure(text=str(data.get(key, 0)))

        self._current_student_id = data["student_id"]   # ← store ID, not records
        self._current_page = 0
        self._total_records = 0

        # peek at total to decide whether to show page bar
        total, _ = _fetch_student_attendance(data["student_id"], offset=0, limit=1)
        if total == 0:
            self._page_bar.grid_remove()
        else:
            self._page_bar.grid()

        self._render_page()

    def clear(self):
        self._name_lbl.configure(text="Select a student", text_color=C_MUTED)
        self._id_lbl.configure(text="")
        self._program_lbl.configure(text="")
        self._yearlevel_lbl.configure(text="")
        self._term_lbl.configure(text="")
        for key in ("present", "late", "total"):
            self._stat_labels[key].configure(text="—")

        self._total_records    = 0
        self._current_student_id = None
        self._current_page = 0
        self._page_bar.grid_remove()

        for w in self._history_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._history_scroll,
                    text="Select a student to view their attendance history",
                    font=ctk.CTkFont(size=13), text_color=C_MUTED).pack(pady=40)

# ---------------------------------------------------------------------------
# Student list item
# ---------------------------------------------------------------------------

class StudentListItem(ctk.CTkFrame):
    """
    A single row in the student list.

    Selection highlight is toggled via select()/deselect() which only call
    configure() on this widget and its children — no widget is destroyed or
    recreated.  This is the key fix for Windows sluggishness.
    """

    def __init__(self, parent, data: dict, on_select, selected=False, **kwargs):
        super().__init__(
            parent,
            fg_color="#1e2130" if selected else C_SURFACE,
            corner_radius=10, border_width=1,
            border_color=C_ACCENT if selected else C_BORDER,
            **kwargs)

        self._data      = data
        self._on_select = on_select
        self._selected  = selected

        # Bind on the container only; use bindtags so child widgets bubble up.
        # This replaces the previous per-child bind loop.
        self.bind("<Button-1>", self._clicked)
        # self._propagate_bind()

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))

        self._name_lbl = ctk.CTkLabel(
            top,
            text=f"{data['lastname']}, {data['firstname']}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_ACCENT if selected else C_TEXT,
            anchor="w")
        self._name_lbl.pack(side="left")

        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=14, pady=(0, 10))

        for txt, side in [
            (str(data["student_id"]), "left"),
            (f"  ·  {data['code']}  {data['yearlevel']}", "left"),
            (f"{data['total']} sessions", "right"),
        ]:
            ctk.CTkLabel(bot, text=txt,
                          font=ctk.CTkFont(size=11),
                          text_color=C_MUTED).pack(side=side)

        # Store sub-frames so we can re-bind after creation
        self._sub_frames = [top, bot]
        for f in self._sub_frames:
            f.bind("<Button-1>", self._clicked)
            for child in f.winfo_children():
                child.bind("<Button-1>", self._clicked)

    def _clicked(self, _event=None):
        self._on_select(self._data)

    def update_data(self, data: dict, selected: bool = False):
        self._data     = data
        self._selected = selected
        self._name_lbl.configure(
            text=f"{data['lastname']}, {data['firstname']}",
            text_color=C_ACCENT if selected else C_TEXT)
        self.configure(
            fg_color="#1e2130" if selected else C_SURFACE,
            border_color=C_ACCENT if selected else C_BORDER)
        # update the muted labels in bot frame
        bot = self.winfo_children()[1]   # second child is the bot frame
        labels = bot.winfo_children()
        labels[0].configure(text=str(data["student_id"]))
        labels[1].configure(text=f"  ·  {data['code']}  {data['yearlevel']}")
        labels[2].configure(text=f"{data['total']} sessions")

    def _propagate_bind(self):
        """Make all current children forward clicks to the container."""
        for child in self.winfo_children():
            child.bind("<Button-1>", self._clicked)

    # ------------------------------------------------------------------
    # Highlight toggling — zero widget creation/destruction
    # ------------------------------------------------------------------

    def select(self):
        if self._selected:
            return
        self._selected = True
        self.configure(fg_color="#1e2130", border_color=C_ACCENT)
        self._name_lbl.configure(text_color=C_ACCENT)

    def deselect(self):
        if not self._selected:
            return
        self._selected = False
        self.configure(fg_color=C_SURFACE, border_color=C_BORDER)
        self._name_lbl.configure(text_color=C_TEXT)

# ---------------------------------------------------------------------------
# Students screen
# ---------------------------------------------------------------------------

class StudentsScreen(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._page         = 0
        self._total_count  = 0
        self._selected_id  = None
        self._selected_item: StudentListItem | None = None  # direct ref — no scan needed
        self._list_items: list[StudentListItem] = []
        self._loading      = False

        self._search_var    = tk.StringVar()
        self._program_var   = tk.StringVar(value="Course")
        self._yearlevel_var = tk.StringVar(value="Year")

        self._search_var.trace_add("write",    self._on_search_changed)
        self._program_var.trace_add("write",   self._apply_filters)
        self._yearlevel_var.trace_add("write", self._apply_filters)

        self._build_ui()
        self.after(600, self.refresh)

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── Left panel ────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=C_SURFACE,
                             corner_radius=0, width=300)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(5, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(left, fg_color=C_SURFACE,
                            corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Students",
                      font=ctk.CTkFont(size=15, weight="bold"),
                      text_color=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=16, pady=14)

        self._count_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._count_lbl.grid(row=0, column=1, padx=(0, 16))

        # Search
        ctk.CTkEntry(
            left, textvariable=self._search_var,
            placeholder_text="Search name or ID...",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32, corner_radius=8
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 4))

        # Filters row 1
        f1 = ctk.CTkFrame(left, fg_color="transparent")
        f1.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        f1.grid_columnconfigure((0, 1), weight=1)

        self._program_menu = ctk.CTkOptionMenu(
            f1, variable=self._program_var, values=["Course"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, width=130, height=30,
            command=lambda _: None)
        self._program_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        # Filters row 2
        f2 = ctk.CTkFrame(left, fg_color="transparent")
        f2.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        f2.grid_columnconfigure((0, 1), weight=1)

        self._yearlevel_menu = ctk.CTkOptionMenu(
            f2, variable=self._yearlevel_var, values=["Year"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, width=130, height=30,
            command=lambda _: None)
        self._yearlevel_menu.grid(row=0, column=0, sticky="ew")

        ctk.CTkFrame(left, fg_color=C_BORDER,
                      height=1).grid(row=4, column=0, sticky="ew")

        # Scrollable list
        self._list_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0)
        self._list_scroll.grid(row=5, column=0, sticky="nsew")
        self._list_scroll.grid_columnconfigure(0, weight=1)

        self._build_list_pool()

        # Pagination bar
        pbar = ctk.CTkFrame(left, fg_color=C_SURFACE,
                             corner_radius=0, height=38)
        pbar.grid(row=6, column=0, sticky="ew")
        pbar.grid_propagate(False)
        pbar.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            pbar, text="← Prev", width=70, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            command=self._prev_page)
        self._prev_btn.grid(row=0, column=0, padx=(8, 4), pady=5)

        self._page_lbl = ctk.CTkLabel(
            pbar, text="Page", font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._page_lbl.grid(row=0, column=1)

        self._next_btn = ctk.CTkButton(
            pbar, text="Next →", width=70, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            command=self._next_page)
        self._next_btn.grid(row=0, column=2, padx=(4, 8), pady=5)

        # ── Right panel ───────────────────────────────────────────────
        self._detail = StudentDetailPanel(self)
        self._detail.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def refresh(self):
        """Reload filter options and reset to page 1."""
        self._loading = True
        programs, yearlevels = _fetch_filter_options()
        self._program_menu.configure(values=["Course"] + programs)
        self._yearlevel_menu.configure(values=["Year"] + yearlevels)

        self._program_var.set("Course")
        self._yearlevel_var.set("Year")
        self._search_var.set("")
        self._loading = False

        self._page = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()

    def _load_page(self):
        """Fetch and render the current page from DB."""
        offset = self._page * PAGE_SIZE
        students, total = _fetch_students(
            search=self._search_var.get().strip(),
            program=self._program_var.get(),
            yearlevel=self._yearlevel_var.get(),
            offset=offset,
            limit=PAGE_SIZE,
        )
        self._total_count = total
        self._render_list(students)
        self._update_pagination()

    def _build_list_pool(self):
        """Create PAGE_SIZE placeholder items once, hide them all."""
        self._list_items: list[StudentListItem] = []
        placeholder = {
            "student_id": 0, "firstname": "", "lastname": "",
            "middlename": "", "program": "", "code": "", "yearlevel": "",
            "total": 0, "present": 0, "late": 0,
        }
        for _ in range(PAGE_SIZE):
            item = StudentListItem(
                self._list_scroll, placeholder,
                on_select=self._on_select)
            item.pack(fill="x", padx=10, pady=4)
            item.pack_forget()   # hidden until needed
            self._list_items.append(item)

    def _render_list(self, students: list):
        self._selected_item = None
        self._count_lbl.configure(
            text=f"{self._total_count} student{'s' if self._total_count != 1 else ''}")

        # Show/update only as many slots as we have students
        for i, item in enumerate(self._list_items):
            if i < len(students):
                data       = students[i]
                is_sel     = data["student_id"] == self._selected_id
                item.update_data(data, selected=is_sel)
                item.pack(fill="x", padx=10, pady=4)
                if is_sel:
                    self._selected_item = item
            else:
                item.pack_forget()   # hide unused slots

        if not students:
            # reuse or show a no-results label
            if not hasattr(self, "_empty_lbl"):
                self._empty_lbl = ctk.CTkLabel(
                    self._list_scroll,
                    text="No students match your search.",
                    font=ctk.CTkFont(size=13), text_color=C_MUTED)
            self._empty_lbl.pack(pady=40)
        else:
            if hasattr(self, "_empty_lbl"):
                self._empty_lbl.pack_forget()

    def _update_pagination(self):
        total_pages = max(1, -(-self._total_count // PAGE_SIZE))
        self._page_lbl.configure(
            text=f"{self._page + 1} / {total_pages}")
        self._prev_btn.configure(
            state="normal" if self._page > 0 else "disabled",
            text_color=C_TEXT if self._page > 0 else C_MUTED)
        self._next_btn.configure(
            state="normal" if self._page < total_pages - 1 else "disabled",
            text_color=C_TEXT if self._page < total_pages - 1 else C_MUTED)

    # ------------------------------------------------------------------
    # Navigation + filters
    # ------------------------------------------------------------------

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._load_page()

    def _next_page(self):
        total_pages = max(1, -(-self._total_count // PAGE_SIZE))
        if self._page < total_pages - 1:
            self._page += 1
            self._load_page()

    def _on_search_changed(self, *_):
        """Debounce search — wait 400ms after last keystroke."""
        if self._loading:
            return
        if hasattr(self, "_search_job"):
            self.after_cancel(self._search_job)
        self._search_job = self.after(400, self._reset_and_load)

    def _apply_filters(self, *_):
        if self._loading:
            return
        self._reset_and_load()

    def _reset_and_load(self):
        self._page = 0
        self._selected_id   = None
        self._selected_item = None
        self._load_page()

    def _on_select(self, data: dict):
        # ── Fast path: same student clicked again ──────────────────────
        if data["student_id"] == self._selected_id:
            return

        # ── Deselect old item (2 configure() calls, no widget creation) ─
        if self._selected_item is not None:
            self._selected_item.deselect()

        # ── Select new item ────────────────────────────────────────────
        self._selected_id = data["student_id"]

        # Find the matching item in the current page
        new_item = next(
            (item for item in self._list_items
             if item._data["student_id"] == data["student_id"]),
            None)
        if new_item:
            new_item.select()
        self._selected_item = new_item

        # ── Update detail panel (DB call only for attendance history) ──
        self._detail.load(data)

# ---------------------------------------------------------------------------
# Standalone launcher
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Students — Attendance Tracker")
    app.geometry("1100x700")
    app.configure(fg_color=C_BG)

    frame = StudentsScreen(app)
    frame.pack(fill="both", expand=True)

    app.mainloop()
