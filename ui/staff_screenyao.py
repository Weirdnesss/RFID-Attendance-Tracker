"""
staff_screen.py
---------------
Staff screen for the RFID Attendance Tracker.

Features:
- Browse staff with search/filter by department and role
- Paginated list (20 per page)
- Click a staff member to view their full attendance history

Embedded by main.py as a CTkFrame.

Performance fixes (mirrors students_screen.py):
- Selection highlight swaps colors on 2 widgets only — no list rebuild
- Child-widget click bindings replaced with a single propagating bind
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime

from db.staff_db import _fetch_staff, _fetch_filter_options, _fetch_staff_attendance, PAGE_SIZE, STAFF_SIZE
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
                      C_ACCENT, C_SUCCESS, C_WARNING)


# ---------------------------------------------------------------------------
# Staff detail panel
# ---------------------------------------------------------------------------

class StaffDetailPanel(ctk.CTkFrame):

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
            hdr, text="Select a staff member",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_MUTED)
        self._name_lbl.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        self._id_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._id_lbl.grid(row=0, column=1, padx=(0, 20))

        # Info row
        info = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        info.grid(row=1, column=0, sticky="ew")
        info.grid_propagate(False)

        self._role_lbl = ctk.CTkLabel(info, text="",
                                      font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._role_lbl.pack(side="left", padx=20)

        self._dept_lbl = ctk.CTkLabel(info, text="",
                                      font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._dept_lbl.pack(side="left")

        # Stats pills
        stats = ctk.CTkFrame(self, fg_color="transparent", height=72)
        stats.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        stats.grid_propagate(False)

        self._stat_labels = {}
        for key, label, color in [
            ("present", "Present", C_SUCCESS),
            ("late",    "Late",    C_WARNING),
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
            text="Select a staff member to view their attendance history",
            font=ctk.CTkFont(size=13), text_color=C_MUTED)
        self._empty_lbl.pack(pady=40)

        # Pagination footer
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

        self._page_bar.grid_remove()  # hidden until a staff member is loaded

        # internal pagination state
        self._total_records: int = 0
        self._current_staff_id: str | None = None
        self._current_page: int = 0

    def _render_page(self):
        for w in self._history_scroll.winfo_children():
            w.destroy()

        offset = self._current_page * STAFF_SIZE
        total, records = _fetch_staff_attendance(
            self._current_staff_id, offset=offset, limit=STAFF_SIZE)

        self._total_records = total
        pages = max(1, -(-total // STAFF_SIZE))

        if not records:
            ctk.CTkLabel(self._history_scroll,
                         text="No attendance records found.",
                         font=ctk.CTkFont(size=13),
                         text_color=C_MUTED).pack(pady=40)
            return

        for i, rec in enumerate(records):
            bg = "#13151c" if i % 2 == 0 else C_BG
            sc = {"present": C_SUCCESS, "late": C_WARNING}.get(rec["status"], C_MUTED)

            r = ctk.CTkFrame(self._history_scroll, fg_color=bg,
                             corner_radius=0, height=32)
            r.pack(fill="x")
            r.pack_propagate(False)

            for text, w, color, bold in [
                (rec["session_name"], 220, C_TEXT,   False),
                (rec["date"],         100, C_MUTED,  False),
                (rec["period_name"],   90, C_ACCENT, False),
                (rec["status"].upper(), 90, sc,      True),
                (rec["time_in"],       110, C_TEXT,  False),
                (rec["time_out"],      110, C_MUTED, False),
            ]:
                ctk.CTkLabel(r, text=text, width=w, anchor="w",
                             font=ctk.CTkFont(size=11,
                                             weight="bold" if bold else "normal"),
                             text_color=color).pack(side="left", padx=4)

            ctk.CTkFrame(self._history_scroll, fg_color=C_BORDER,
                         height=1, corner_radius=0).pack(fill="x")

        # update controls
        self._page_lbl.configure(
            text=f"Page {self._current_page + 1} of {pages} · {total} records")
        self._prev_btn.configure(state="normal" if self._current_page > 0 else "disabled")
        self._next_btn.configure(state="normal" if self._current_page < pages - 1 else "disabled")

        # scroll back to top on page change
        self._history_scroll._parent_canvas.yview_moveto(0)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()

    def _next_page(self):
        pages = max(1, -(-self._total_records // STAFF_SIZE))
        if self._current_page < pages - 1:
            self._current_page += 1
            self._render_page()

    def load(self, data: dict):
        name = " ".join(filter(None, [
            data["firstname"], data["middlename"], data["lastname"]
        ]))
        self._name_lbl.configure(text=name, text_color=C_TEXT)
        self._id_lbl.configure(text=f"ID: {data['staff_id']}", text_color=C_MUTED)
        self._role_lbl.configure(text=data["role"], text_color=C_TEXT)
        self._dept_lbl.configure(text=f"· {data['department']}", text_color=C_MUTED)

        self._current_staff_id = data["staff_id"]
        self._current_page = 0

        present = data.get("present", 0)
        late    = data.get("late", 0)
        self._stat_labels["present"].configure(text=str(present + late))
        self._stat_labels["late"].configure(text=str(late))

        total, _ = _fetch_staff_attendance(data["staff_id"], offset=0, limit=1)
        if total == 0:
            self._page_bar.grid_remove()
        else:
            self._page_bar.grid()

        self._render_page()

    def clear(self):
        self._name_lbl.configure(text="Select a staff member", text_color=C_MUTED)
        self._id_lbl.configure(text="")
        self._role_lbl.configure(text="")
        self._dept_lbl.configure(text="")
        for key in ("present", "late"):
            self._stat_labels[key].configure(text="—")
        self._total_records = 0
        self._current_staff_id = None
        self._current_page = 0
        self._page_bar.grid_remove()
        for w in self._history_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._history_scroll,
                     text="Select a staff member to view their attendance history",
                     font=ctk.CTkFont(size=13), text_color=C_MUTED).pack(pady=40)


# ---------------------------------------------------------------------------
# Staff list item
# ---------------------------------------------------------------------------

class StaffListItem(ctk.CTkFrame):
    """
    A single row in the staff list.
    Selection highlight is toggled via select()/deselect() which only call
    configure() on this widget and its children — no widget is destroyed or
    recreated. Mirrors StudentListItem exactly.
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

        self.bind("<Button-1>", self._clicked)

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
            (str(data["staff_id"]),                       "left"),
            (f" · {data['role']} · {data['department']}", "left"),
            (f"{data['total']} sessions",                  "right"),
        ]:
            ctk.CTkLabel(bot, text=txt,
                         font=ctk.CTkFont(size=11),
                         text_color=C_MUTED).pack(side=side)

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

        bot    = self.winfo_children()[1]
        labels = bot.winfo_children()
        labels[0].configure(text=str(data["staff_id"]))
        labels[1].configure(text=f" · {data['role']} · {data['department']}")
        labels[2].configure(text=f"{data['total']} sessions")

    def _propagate_bind(self):
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
# Staff screen
# ---------------------------------------------------------------------------

class StaffScreen(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)

        self._page           = 0
        self._total_count    = 0
        self._selected_id    = None
        self._selected_item: StaffListItem | None = None
        self._list_items:    list[StaffListItem]  = []
        self._loading        = False

        self._search_var = tk.StringVar()
        self._dept_var   = tk.StringVar(value="Department")
        self._role_var   = tk.StringVar(value="Role")

        self._search_var.trace_add("write", self._on_search_changed)
        self._dept_var.trace_add("write",   self._apply_filters)
        self._role_var.trace_add("write",   self._apply_filters)

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

        ctk.CTkLabel(hdr, text="Staff",
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

        # Filter row 1 — Department
        f1 = ctk.CTkFrame(left, fg_color="transparent")
        f1.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        f1.grid_columnconfigure(0, weight=1)

        self._dept_menu = ctk.CTkOptionMenu(
            f1, variable=self._dept_var, values=["Department"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30,
            command=lambda _: None)
        self._dept_menu.grid(row=0, column=0, sticky="ew")

        # Filter row 2 — Role
        f2 = ctk.CTkFrame(left, fg_color="transparent")
        f2.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        f2.grid_columnconfigure(0, weight=1)

        self._role_menu = ctk.CTkOptionMenu(
            f2, variable=self._role_var, values=["Role"],
            fg_color=C_BG, button_color=C_BORDER,
            button_hover_color=C_SURFACE, dropdown_fg_color=C_SURFACE,
            text_color=C_TEXT, height=30,
            command=lambda _: None)
        self._role_menu.grid(row=0, column=0, sticky="ew")

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
        self._detail = StaffDetailPanel(self)
        self._detail.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def refresh(self):
        """Reload filter options and reset to page 1."""
        self._loading = True
        departments, roles = _fetch_filter_options()
        self._dept_menu.configure(values=["Department"] + departments)
        self._role_menu.configure(values=["Role"] + roles)
        self._dept_var.set("Department")
        self._role_var.set("Role")
        self._search_var.set("")
        self._loading = False

        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()

    def _load_page(self):
        offset = self._page * PAGE_SIZE
        staff_list, total = _fetch_staff(
            search=self._search_var.get().strip(),
            department=self._dept_var.get(),
            role=self._role_var.get(),
            offset=offset,
            limit=PAGE_SIZE,
        )
        self._total_count = total
        self._render_list(staff_list)
        self._update_pagination()

    def _build_list_pool(self):
        """Create PAGE_SIZE placeholder items once, hide them all."""
        self._list_items = []
        placeholder = {
            "staff_id": "", "firstname": "", "lastname": "",
            "middlename": "", "department": "—", "role": "—",
            "is_active": True, "total": 0, "present": 0, "late": 0,
        }
        for _ in range(PAGE_SIZE):
            item = StaffListItem(
                self._list_scroll, placeholder,
                on_select=self._on_select)
            item.pack(fill="x", padx=10, pady=4)
            item.pack_forget()  # hidden until needed
            self._list_items.append(item)

    def _render_list(self, staff_list: list):
        self._selected_item = None
        self._count_lbl.configure(
            text=f"{self._total_count} staff member{'s' if self._total_count != 1 else ''}")

        for i, item in enumerate(self._list_items):
            if i < len(staff_list):
                data   = staff_list[i]
                is_sel = data["staff_id"] == self._selected_id
                item.update_data(data, selected=is_sel)
                item.pack(fill="x", padx=10, pady=4)
                if is_sel:
                    self._selected_item = item
            else:
                item.pack_forget()

        if not staff_list:
            if not hasattr(self, "_empty_lbl"):
                self._empty_lbl = ctk.CTkLabel(
                    self._list_scroll,
                    text="No staff match your search.",
                    font=ctk.CTkFont(size=13), text_color=C_MUTED)
            self._empty_lbl.pack(pady=40)
        else:
            if hasattr(self, "_empty_lbl"):
                self._empty_lbl.pack_forget()

    def _update_pagination(self):
        total_pages = max(1, -(-self._total_count // PAGE_SIZE))
        self._page_lbl.configure(text=f"{self._page + 1} / {total_pages}")
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
        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._load_page()

    def _on_select(self, data: dict):
        # ── Fast path: same staff clicked again ───────────────────────
        if data["staff_id"] == self._selected_id:
            return

        # ── Deselect old item (2 configure() calls, no widget creation) ─
        if self._selected_item is not None:
            self._selected_item.deselect()

        # ── Select new item ───────────────────────────────────────────
        self._selected_id = data["staff_id"]

        new_item = next(
            (item for item in self._list_items
             if item._data["staff_id"] == data["staff_id"]),
            None)

        if new_item:
            new_item.select()
            self._selected_item = new_item

        # ── Update detail panel ───────────────────────────────────────
        self._detail.load(data)


# ---------------------------------------------------------------------------
# Standalone launcher
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Staff — Attendance Tracker")
    app.geometry("1100x700")
    app.configure(fg_color=C_BG)

    frame = StaffScreen(app)
    frame.pack(fill="both", expand=True)

    app.mainloop()