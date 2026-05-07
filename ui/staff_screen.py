"""
staff_screen.py
---------------
Staff screen for the RFID Attendance Tracker.

Features:
- Browse staff with search/filter by department and role
- Paginated list (20 per page)
- Click a staff member to view their full attendance history

Embedded by main.py as a CTkFrame.
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime

from db.staff_db import _fetch_staff, _fetch_filter_options, _fetch_staff_attendance, PAGE_SIZE, STAFF_SIZE
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
                      C_ACCENT, C_SUCCESS, C_WARNING)
from ui.components.pagination_bar import PaginationBar
from ui.components.stats_pills import StatsPills
from ui.components.history_table import HistoryTable
from ui.components.base_list_item import BaseListItem
from ui.components.base_detail_panel import BaseDetailPanel
from db.staff_db import _fetch_staff_attendance, STAFF_SIZE
from ui.components.paginated_list_screen import PaginatedListScreen
from db.staff_db import _fetch_staff, _fetch_filter_options, PAGE_SIZE


# ---------------------------------------------------------------------------
# Staff detail panel
# ---------------------------------------------------------------------------

class StaffDetailPanel(BaseDetailPanel):

    def _empty_text(self):
        return "Select a staff member"

    def _build_info_row(self, info):
        self._role_lbl = ctk.CTkLabel(
            info, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._role_lbl.pack(side="left", padx=20)

        self._dept_lbl = ctk.CTkLabel(
            info, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._dept_lbl.pack(side="left")

    def _stats_pills(self):
        return [
            ("present", "Present", C_SUCCESS),
            ("late",    "Late",    C_WARNING),
        ]

    def _fetch_fn(self):
        return _fetch_staff_attendance

    def _page_size(self):
        return STAFF_SIZE

    def _load_header(self, data):
        name = " ".join(filter(None, [
            data["firstname"], data["middlename"], data["lastname"]]))
        self._name_lbl.configure(text=name, text_color=C_TEXT)
        self._id_lbl.configure(text=f"ID: {data['staff_id']}", text_color=C_MUTED)

    def _load_info(self, data):
        self._role_lbl.configure(text=data["role"], text_color=C_TEXT)
        self._dept_lbl.configure(text=f"· {data['department']}", text_color=C_MUTED)

    def _load_stats(self, data):
        present = data.get("present", 0)
        late    = data.get("late", 0)
        self._stats.set("present", present + late)
        self._stats.set("late", late)

    def _get_entity_id(self, data):
        return data["staff_id"]

    def _clear_info(self):
        self._role_lbl.configure(text="")
        self._dept_lbl.configure(text="")

# ---------------------------------------------------------------------------
# Staff list item
# ---------------------------------------------------------------------------

class StaffListItem(BaseListItem):

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
        labels[0].configure(text=str(data["staff_id"]))
        labels[1].configure(text=f" · {data['role']} · {data['department_code']}")
        labels[2].configure(text=f"{data['total']} sessions")

    def _get_id(self, data: dict):
        return data["staff_id"]

# ---------------------------------------------------------------------------
# Staff screen
# ---------------------------------------------------------------------------

class StaffScreen(PaginatedListScreen):

    def _title(self):           return "Staff"
    def _empty_text(self):      return "No staff match your search."
    def _id_key(self):          return "staff_id"
    def _page_size(self):       return PAGE_SIZE
    def _item_cls(self):        return StaffListItem
    def _detail_cls(self):      return StaffDetailPanel
    def _count_label(self, n):  return f"{n} staff member{'s' if n != 1 else ''}"

    def _placeholder(self):
        return {
            "staff_id": "", "firstname": "", "lastname": "",
            "middlename": "", "department_code": "", "role": "",
            "is_active": True, "total": 0, "present": 0, "late": 0,
        }

    def _init_filter_vars(self):
        self._dept_var = tk.StringVar(value="Department")
        self._role_var = tk.StringVar(value="Role")
        self._dept_var.trace_add("write", self._apply_filters)
        self._role_var.trace_add("write", self._apply_filters)

    def _build_filters(self, left):
        f1 = ctk.CTkFrame(left, fg_color="transparent")
        f1.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        f1.grid_columnconfigure(0, weight=1)
        self._dept_menu = ctk.CTkOptionMenu(
            f1, variable=self._dept_var, values=["Department"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30, command=lambda _: None)
        self._dept_menu.grid(row=0, column=0, sticky="ew")

        f2 = ctk.CTkFrame(left, fg_color="transparent")
        f2.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        f2.grid_columnconfigure(0, weight=1)
        self._role_menu = ctk.CTkOptionMenu(
            f2, variable=self._role_var, values=["Role"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30, command=lambda _: None)
        self._role_menu.grid(row=0, column=0, sticky="ew")

    def _reload_filter_options(self):
        departments, roles = _fetch_filter_options()
        self._dept_menu.configure(values=["Department"] + departments)
        self._role_menu.configure(values=["Role"] + roles)
        self._dept_var.set("Department")
        self._role_var.set("Role")

    def _fetch_page(self, search, offset, limit):
        return _fetch_staff(
            search=search,
            department=self._dept_var.get(),
            role=self._role_var.get(),
            offset=offset,
            limit=limit,
        )