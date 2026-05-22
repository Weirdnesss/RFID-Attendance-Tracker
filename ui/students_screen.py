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
from ui.components.pagination_bar import PaginationBar
from ui.components.stats_pills import StatsPills
from ui.components.history_table import HistoryTable
from ui.components.base_list_item import BaseListItem
from ui.components.base_detail_panel import BaseDetailPanel
from db.students_db import _fetch_student_attendance, STUDENT_SIZE
from ui.components.paginated_list_screen import PaginatedListScreen
from db.students_db import _fetch_students, _fetch_filter_options, PAGE_SIZE

# ---------------------------------------------------------------------------
# Student detail panel
# ---------------------------------------------------------------------------

class StudentDetailPanel(BaseDetailPanel):

    def _empty_text(self):
        return "Select a student"

    def _build_info_row(self, info):
        self._program_lbl = ctk.CTkLabel(
            info, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._program_lbl.pack(side="left", padx=20)

        self._yearlevel_lbl = ctk.CTkLabel(
            info, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._yearlevel_lbl.pack(side="left")

    def _stats_pills(self):
        return [
            ("present", "Present", C_SUCCESS),
            ("late",    "Late",    C_WARNING),
        ]

    def _fetch_fn(self):
        return _fetch_student_attendance

    def _page_size(self):
        return STUDENT_SIZE

    def _load_header(self, data):
        name = " ".join(filter(None, [
            data["firstname"], data["middlename"], data["lastname"]]))
        self._name_lbl.configure(text=name, text_color=C_TEXT)
        self._id_lbl.configure(text=f"ID: {data['student_id']}", text_color=C_MUTED)

    def _load_info(self, data):
        self._program_lbl.configure(
            text=f"{data['program']}  ({data['code']})", text_color=C_TEXT)
        self._yearlevel_lbl.configure(
            text=f"·  {data['yearlevel']}", text_color=C_MUTED)

    def _load_stats(self, data):
        present = data.get("present", 0)
        late    = data.get("late", 0)
        self._stats.set("present", present + late)
        self._stats.set("late", late)

    def _get_entity_id(self, data):
        return data["student_id"]

    def _clear_info(self):
        self._program_lbl.configure(text="")
        self._yearlevel_lbl.configure(text="")
# ---------------------------------------------------------------------------
# Student list item
# ---------------------------------------------------------------------------

class StudentListItem(BaseListItem):

    def _build_bottom(self, bot):
        for side in ["left", "left", "right"]:
            ctk.CTkLabel(bot, text="",
                         font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side=side)

    def _update_contents(self, data: dict):
        self._name_lbl.configure(
            text=f"{data['lastname']}, {data['firstname']}")
        bot    = self.winfo_children()[1]
        labels = bot.winfo_children()
        labels[0].configure(text=str(data["student_id"]))
        labels[1].configure(text=f"  ·  {data['code']}  {data['yearlevel']}")
        labels[2].configure(text=f"{data['total']} sessions")

    def _get_id(self, data: dict):
        return data["student_id"]
# ---------------------------------------------------------------------------
# Students screen
# ---------------------------------------------------------------------------

class StudentsScreen(PaginatedListScreen):

    def _title(self):           return "Students"
    def _empty_text(self):      return "No students match your search."
    def _id_key(self):          return "student_id"
    def _page_size(self):       return PAGE_SIZE
    def _item_cls(self):        return StudentListItem
    def _detail_cls(self):      return StudentDetailPanel
    def _count_label(self, n):  return f"{n} student{'s' if n != 1 else ''}"

    def _placeholder(self):
        return {
            "student_id": 0, "firstname": "", "lastname": "",
            "middlename": "", "program": "", "code": "",
            "yearlevel": "", "total": 0, "present": 0, "late": 0,
        }

    def _init_filter_vars(self):
        self._program_var   = tk.StringVar(value="Course")
        self._yearlevel_var = tk.StringVar(value="Year")
        self._program_var.trace_add("write",   self._apply_filters)
        self._yearlevel_var.trace_add("write", self._apply_filters)

    def _build_filters(self, left):
        f1 = ctk.CTkFrame(left, fg_color="transparent")
        f1.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        f1.grid_columnconfigure(0, weight=1)
        self._program_menu = ctk.CTkOptionMenu(
            f1, variable=self._program_var, values=["Course"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30, command=lambda _: None)
        self._program_menu.grid(row=0, column=0, sticky="ew")

        f2 = ctk.CTkFrame(left, fg_color="transparent")
        f2.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        f2.grid_columnconfigure(0, weight=1)
        self._yearlevel_menu = ctk.CTkOptionMenu(
            f2, variable=self._yearlevel_var, values=["Year"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30, command=lambda _: None)
        self._yearlevel_menu.grid(row=0, column=0, sticky="ew")

    def _reload_filter_options(self):
        programs, yearlevels = _fetch_filter_options()
        self._program_menu.configure(values=["Course"] + programs)
        self._yearlevel_menu.configure(values=["Year"] + yearlevels)
        self._program_var.set("Course")
        self._yearlevel_var.set("Year")

    def _fetch_page(self, search, offset, limit):
        return _fetch_students(
            search=search,
            program=self._program_var.get(),
            yearlevel=self._yearlevel_var.get(),
            offset=offset,
            limit=limit,
        )
    
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
