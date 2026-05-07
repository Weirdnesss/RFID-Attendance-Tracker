"""
sessions_screen.py
------------------
Sessions screen for the RFID Attendance Tracker.

Browse all past sessions, view attendance detail per session.
Supports sessions with students only, staff only, or both.

Embedded by main.py as a CTkFrame.
"""

import math
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime

from utils.export_utils import (fetch_session_report, export_session_xlsx,
                                export_session_pdf)
from db.session_db import (_fetch_sessions, _fetch_session_detail,
                           _fetch_session_periods)
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
                      C_ACCENT, C_SUCCESS, C_WARNING, C_ERROR, PERIOD_COLORS)
from ui.components.pagination_bar import PaginationBar
from ui.components.base_list_item import BaseListItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_LABEL  = {"students": "Students", "staff": "Staff", "both": "Students + Staff"}
_TYPE_COLOR  = {"students": "#38bdf8",  "staff": "#a78bfa", "both": "#3ecf8e"}

# Column definitions per entity type
# (header_text, width)
_STUDENT_COLS = [
    ("#",          28), ("Student ID", 80), ("Name",    160),
    ("Program",   100), ("Year",        70), ("Period",   90),
    ("Status",     70), ("Time In",     85), ("Time Out", 85),
]
_STAFF_COLS = [
    ("#",          28), ("Staff ID",   80), ("Name",    160),
    ("Department", 110), ("Role",       90), ("Period",   90),
    ("Status",     70), ("Time In",    85), ("Time Out", 85),
]

PAGE_SIZE = 20

STATUS_COLORS = {"present": C_SUCCESS, "late": C_WARNING, "absent": C_ERROR}


# ---------------------------------------------------------------------------
# Record sub-panel (reusable for students and staff)
# ---------------------------------------------------------------------------

class RecordSubPanel(ctk.CTkFrame):
    """
    A self-contained paginated record list.
    col_defs: list of (header, width) tuples
    """

    def __init__(self, parent, col_defs: list, label: str, label_color: str,
                 **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._col_defs   = col_defs
        self._all_records: list = []
        self._page       = 0

        # Section label
        lbl_row = ctk.CTkFrame(self, fg_color="transparent", height=28)
        lbl_row.grid(row=0, column=0, sticky="ew")
        lbl_row.grid_propagate(False)

        ctk.CTkFrame(lbl_row, fg_color=label_color,
                     width=4, corner_radius=2).pack(side="left", padx=(0, 8), fill="y")
        ctk.CTkLabel(lbl_row, text=label.upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=label_color).pack(side="left")

        self._count_lbl = ctk.CTkLabel(lbl_row, text="",
                                       font=ctk.CTkFont(size=10),
                                       text_color=C_MUTED)
        self._count_lbl.pack(side="left", padx=(8, 0))

        # Column headers
        col_hdr = ctk.CTkFrame(self, fg_color=C_ACCENT,
                               corner_radius=0, height=28)
        col_hdr.grid(row=1, column=0, sticky="new")

        for text, w in col_defs:
            ctk.CTkLabel(col_hdr, text=text, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_TEXT).pack(side="left", padx=4)

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._scroll.grid(row=1, column=0, sticky="nsew", pady=(28, 0))

        self._empty_lbl = ctk.CTkLabel(
            self._scroll, text="No records.",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._empty_lbl.pack(pady=20)

        # Pagination bar
        self._pbar = PaginationBar(self, on_prev=self._prev_page, on_next=self._next_page, height=36)
        self._pbar.grid(row=2, column=0, sticky="ew")

        # Pre-build row pool
        self._row_frames  = []
        self._row_dividers = []
        self._build_pool()

    def _build_pool(self):
        for _ in range(PAGE_SIZE):
            r = ctk.CTkFrame(self._scroll, fg_color=C_BG,
                             corner_radius=0, height=32)
            r.pack_propagate(False)
            for _, w in self._col_defs:
                ctk.CTkLabel(r, text="", width=w,
                             font=ctk.CTkFont(size=11),
                             text_color=C_TEXT, anchor="w").pack(
                    side="left", padx=4)
            div = ctk.CTkFrame(self._scroll, fg_color=C_BORDER,
                               height=1, corner_radius=0)
            self._row_frames.append(r)
            self._row_dividers.append(div)
            r.pack_forget()
            div.pack_forget()

    def load(self, records: list):
        self._all_records = records
        self._page = 0
        self._count_lbl.configure(text=f"· {len(records)} record{'s' if len(records) != 1 else ''}")
        self._render()

    def clear(self):
        self._all_records = []
        self._page = 0
        self._count_lbl.configure(text="")
        for r, d in zip(self._row_frames, self._row_dividers):
            r.pack_forget()
            d.pack_forget()
        self._empty_lbl.pack(pady=20)
        # self._page_lbl.configure(text="")
        # self._prev_btn.configure(state="disabled")
        # self._next_btn.configure(state="disabled")

    def _render(self):
        self._empty_lbl.pack_forget()

        if not self._all_records:
            for r, d in zip(self._row_frames, self._row_dividers):
                r.pack_forget()
                d.pack_forget()
            self._empty_lbl.pack(pady=20)
            self._update_pagination()
            return

        start = self._page * PAGE_SIZE
        end   = start + PAGE_SIZE
        page_records = self._all_records[start:end]

        for i, frame in enumerate(self._row_frames):
            div = self._row_dividers[i]
            if i < len(page_records):
                rec = page_records[i]
                global_idx = start + i + 1
                bg = "#13151c" if i % 2 == 0 else C_BG
                sc = STATUS_COLORS.get(rec["status"], C_MUTED)

                frame.configure(fg_color=bg)
                labels = frame.winfo_children()

                configs = [
                    (str(global_idx),    C_TEXT,   False),
                    (rec["entity_id"],   C_TEXT,   False),
                    (rec["name"],        C_TEXT,   False),
                    (rec["col3"],        C_MUTED,  False),
                    (rec["col4"],        C_MUTED,  False),
                    (rec["period_name"], C_ACCENT, False),
                    (rec["status"].upper(), sc,    True),
                    (rec["time_in"],     C_TEXT,   False),
                    (rec["time_out"],    C_MUTED,  False),
                ]

                for lbl, (text, color, bold) in zip(labels, configs):
                    lbl.configure(
                        text=text, text_color=color,
                        font=ctk.CTkFont(size=11,
                                         weight="bold" if bold else "normal"))

                frame.pack(fill="x")
                div.pack(fill="x")
            else:
                frame.pack_forget()
                div.pack_forget()

        self._update_pagination()
        self._scroll._parent_canvas.yview_moveto(0)

    def _update_pagination(self):
        total = len(self._all_records)
        pages = max(1, math.ceil(total / PAGE_SIZE))

        self._pbar.update(self._page, pages)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render()

    def _next_page(self):
        if (self._page + 1) * PAGE_SIZE < len(self._all_records):
            self._page += 1
            self._render()


# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------

class SessionDetailPanel(ctk.CTkFrame):

    def __init__(self, parent, on_delete_callback, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._on_delete   = on_delete_callback
        self._session_data = None
        self._export_data  = None
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE,
                           corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(
            hdr, text="Select a session",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_MUTED)
        self._title_lbl.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        self._type_badge = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#12141b", corner_radius=4,
            text_color=C_MUTED)
        self._type_badge.grid(row=0, column=1, padx=(0, 12))

        self._xlsx_btn = ctk.CTkButton(
            hdr, text="Export Excel", width=110,
            fg_color="transparent", border_color=C_SUCCESS,
            border_width=1, text_color=C_SUCCESS,
            hover_color="#0d1f18", font=ctk.CTkFont(size=12),
            state="disabled", command=self._export_xlsx)
        self._xlsx_btn.grid(row=0, column=2, padx=(0, 8), pady=10)

        self._pdf_btn = ctk.CTkButton(
            hdr, text="Export PDF", width=100,
            fg_color="transparent", border_color=C_ERROR,
            border_width=1, text_color=C_ERROR,
            hover_color="#1f0d0d", font=ctk.CTkFont(size=12),
            state="disabled", command=self._export_pdf)
        self._pdf_btn.grid(row=0, column=3, padx=(0, 16), pady=10)

        # ── Stats row ─────────────────────────────────────────────────
        self._stats_outer = ctk.CTkFrame(
            self, fg_color="transparent", height=80)
        self._stats_outer.grid(row=1, column=0, sticky="ew",
                               padx=16, pady=(8, 4))
        self._stats_outer.grid_propagate(False)
        self._stat_labels = {}
        self._stats_section_lbls = {}
        self._build_stats_pills("students")  # default

        # ── Toggle bar (only shown for "both" sessions) ───────────────
        self._toggle_bar = ctk.CTkFrame(
            self, fg_color=C_SURFACE, corner_radius=8,
            border_width=1, border_color=C_BORDER, height=36)
        self._toggle_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._toggle_bar.grid_propagate(False)
        self._toggle_bar.grid_remove()

        self._toggle_students_btn = ctk.CTkButton(
            self._toggle_bar, text="Students", width=100, height=26,
            fg_color=C_ACCENT, text_color=C_BG,
            hover_color=C_ACCENT, corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._switch_tab("students"))
        self._toggle_students_btn.pack(side="left", padx=(4, 2), pady=4)

        self._toggle_staff_btn = ctk.CTkButton(
            self._toggle_bar, text="Staff", width=100, height=26,
            fg_color="transparent", text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(size=12),
            command=lambda: self._switch_tab("staff"))
        self._toggle_staff_btn.pack(side="left", padx=(2, 4), pady=4)

        self._active_tab = "students"

        # ── Periods strip ─────────────────────────────────────────────
        self._periods_panel = ctk.CTkFrame(
            self, fg_color=C_SURFACE, corner_radius=8,
            border_width=1, border_color=C_BORDER)
        self._periods_panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._periods_panel.grid_remove()

        # ── Record area ───────────────────────────────────────────────
        self._record_area = ctk.CTkFrame(
            self, fg_color="transparent", corner_radius=0)
        self._record_area.grid(row=4, column=0, sticky="nsew", padx=16)
        self._record_area.grid_rowconfigure(0, weight=1)
        self._record_area.grid_columnconfigure(0, weight=1)

        self._student_panel = RecordSubPanel(
            self._record_area, _STUDENT_COLS,
            label="Students", label_color="#38bdf8")
        self._staff_panel = RecordSubPanel(
            self._record_area, _STAFF_COLS,
            label="Staff", label_color="#a78bfa")

        # default: show student panel only
        self._student_panel.grid(row=0, column=0, sticky="nsew")
        self._staff_panel.grid_remove()

        # Empty label (shown when no session selected)
        self._empty_lbl = ctk.CTkLabel(
            self._record_area,
            text="Select a session from the list to view attendance",
            font=ctk.CTkFont(size=13), text_color=C_MUTED)
        self._empty_lbl.grid(row=0, column=0, pady=40)

    def _build_stats_pills(self, atype: str):
        """Rebuild stats pills based on attendee type."""
        for w in self._stats_outer.winfo_children():
            w.destroy()
        self._stat_labels.clear()
        self._stats_section_lbls.clear()

        def _section(parent, label, color):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(side="left", padx=(0, 16))
            ctk.CTkLabel(f, text=label,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=color).pack(anchor="w", pady=(0, 4))
            pills = ctk.CTkFrame(f, fg_color="transparent")
            pills.pack()
            return pills

        def _pill(parent, key, label, color):
            pill = ctk.CTkFrame(parent, fg_color=C_SURFACE,
                                corner_radius=8, border_width=1,
                                border_color=color)
            pill.pack(side="left", padx=(0, 6))
            val = ctk.CTkLabel(pill, text="—",
                               font=ctk.CTkFont(size=18, weight="bold"),
                               text_color=color)
            val.pack(padx=12, pady=(6, 0))
            ctk.CTkLabel(pill, text=label,
                         font=ctk.CTkFont(size=9),
                         text_color=C_MUTED).pack(padx=12, pady=(0, 6))
            self._stat_labels[key] = val

        if atype in ("students", "both"):
            p = _section(self._stats_outer,
                        "STUDENTS" if atype == "both" else "ATTENDANCE",
                        "#38bdf8")
            _pill(p, "student_present",  "Present",  C_SUCCESS)
            _pill(p, "student_late",     "Late",     C_WARNING)
            _pill(p, "student_expected", "Expected", C_MUTED)   # ← replaces Absent

        if atype in ("staff", "both"):
            p = _section(self._stats_outer,
                        "STAFF" if atype == "both" else "ATTENDANCE",
                        "#a78bfa")
            _pill(p, "staff_present",  "Present",  C_SUCCESS)
            _pill(p, "staff_late",     "Late",     C_WARNING)
            _pill(p, "staff_expected", "Expected", C_MUTED)     # ← replaces Absent
        # Expected + Rate always shown
        p2 = ctk.CTkFrame(self._stats_outer, fg_color="transparent")
        p2.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(p2, text="OVERALL",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color=C_MUTED).pack(anchor="w", pady=(0, 4))
        pills2 = ctk.CTkFrame(p2, fg_color="transparent")
        pills2.pack()
        _pill(pills2, "rate", "Rate %", C_TEXT)

    def _update_stats(self, session_data: dict):
        atype = session_data.get("attendee_type", "students")

        def _set(key, val):
            lbl = self._stat_labels.get(key)
            if lbl:
                lbl.configure(text=str(val))

        _set("student_present",  session_data.get("student_present",  0))
        _set("student_late",     session_data.get("student_late",     0))
        _set("student_expected", session_data.get("student_estimated") or "—")
        _set("staff_present",    session_data.get("staff_present",    0))
        _set("staff_late",       session_data.get("staff_late",       0))
        _set("staff_expected",   session_data.get("staff_estimated")  or "—")

        total_present = (session_data.get("student_present", 0)
                        + session_data.get("student_late",  0)
                        + session_data.get("staff_present", 0)
                        + session_data.get("staff_late",    0))
        est = session_data.get("estimated_attendees")
        rate_lbl = self._stat_labels.get("rate")
        if rate_lbl and est and est > 0:
            rate  = min(round(total_present / est * 100, 1), 100.0)
            color = C_SUCCESS if rate >= 75 else C_WARNING if rate >= 50 else C_ERROR
            rate_lbl.configure(text=f"{rate}%", text_color=color)
            rate_lbl.master.configure(border_color=color)
        elif rate_lbl:
            rate_lbl.configure(text="—")
    def _configure_record_panels(self, atype: str):
            self._active_tab = "students"
            if atype == "students":
                self._toggle_bar.grid_remove()
                self._student_panel.grid(row=0, column=0, sticky="nsew")
                self._staff_panel.grid_remove()
            elif atype == "staff":
                self._toggle_bar.grid_remove()
                self._student_panel.grid_remove()
                self._staff_panel.grid(row=0, column=0, sticky="nsew")
            else:  # both — show toggle, start on students tab
                self._toggle_bar.grid()
                self._switch_tab("students")

    def _switch_tab(self, tab: str):
        self._active_tab = tab
        if tab == "students":
            self._student_panel.grid(row=0, column=0, sticky="nsew")
            self._staff_panel.grid_remove()
            self._toggle_students_btn.configure(
                fg_color=C_ACCENT, text_color=C_BG,
                font=ctk.CTkFont(size=12, weight="bold"))
            self._toggle_staff_btn.configure(
                fg_color="transparent", text_color=C_MUTED,
                font=ctk.CTkFont(size=12))
        else:
            self._staff_panel.grid(row=0, column=0, sticky="nsew")
            self._student_panel.grid_remove()
            self._toggle_staff_btn.configure(
                fg_color=C_ACCENT, text_color=C_BG,
                font=ctk.CTkFont(size=12, weight="bold"))
            self._toggle_students_btn.configure(
                fg_color="transparent", text_color=C_MUTED,
                font=ctk.CTkFont(size=12))
            
    def load(self, session_data: dict):
        self._session_data = session_data
        atype = session_data.get("attendee_type", "students")

        self._empty_lbl.grid_remove()

        # Header
        self._title_lbl.configure(
            text=f"{session_data['name']} — {session_data['date']}",
            text_color=C_TEXT)
        self._type_badge.configure(
            text=_TYPE_LABEL.get(atype, "Students"),
            text_color=_TYPE_COLOR.get(atype, "#38bdf8"))

        # Export buttons
        self._export_data = fetch_session_report(session_data["id"])
        self._xlsx_btn.configure(state="normal")
        self._pdf_btn.configure(state="normal")

        # Stats
        self._build_stats_pills(atype)
        self._update_stats(session_data)

        # Periods strip
        for w in self._periods_panel.winfo_children():
            w.destroy()
        periods = _fetch_session_periods(session_data["id"])
        if periods:
            self._periods_panel.grid()
            ctk.CTkLabel(self._periods_panel, text="PERIODS",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUTED).pack(anchor="w", padx=12, pady=(8, 4))
            for i, p in enumerate(periods):
                color = PERIOD_COLORS[i % len(PERIOD_COLORS)]
                pr = ctk.CTkFrame(self._periods_panel, fg_color="transparent")
                pr.pack(fill="x", padx=12, pady=(0, 6))
                ctk.CTkFrame(pr, width=6, height=6, fg_color=color,
                             corner_radius=3).pack(side="left", padx=(0, 8))
                ctk.CTkLabel(
                    pr,
                    text=(
                        f"{p['name']} "
                        f"{p['time_in_start']}–{p['time_in_end']} "
                        + (f"· Late After {p['late_start']} " if p['late_start'] else "")
                        + (f"· Grace {p['grace_minutes']}min " if p['late_start'] else "")
                        + (f"· Track out {p['timeout_start']}–{p['timeout_end']}"
                           if p['timeout_start'] else "")
                    ),
                    font=ctk.CTkFont(size=11), text_color=C_MUTED,
                ).pack(side="left")
        else:
            self._periods_panel.grid_remove()

        # Records
        self._configure_record_panels(atype)
        detail = _fetch_session_detail(session_data["id"])
        self._student_panel.load(detail["students"])
        self._staff_panel.load(detail["staff"])

    def clear(self):
        self._session_data = None
        self._export_data  = None
        self._title_lbl.configure(text="Select a session", text_color=C_MUTED)
        self._type_badge.configure(text="")
        self._xlsx_btn.configure(state="disabled")
        self._pdf_btn.configure(state="disabled")
        self._toggle_bar.grid_remove()
        self._periods_panel.grid_remove()
        self._student_panel.clear()
        self._staff_panel.clear()
        self._student_panel.grid_remove()
        self._staff_panel.grid_remove()
        self._empty_lbl.grid(row=0, column=0, pady=40)

    def _export_xlsx(self):
        if not self._export_data:
            return
        default = f"session_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=default)
        if not path:
            return
        try:
            export_session_xlsx(self._export_data, path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _export_pdf(self):
        if not self._export_data:
            return
        default = f"session_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=default)
        if not path:
            return
        try:
            export_session_pdf(self._export_data, path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


# ---------------------------------------------------------------------------
# Session list item
# ---------------------------------------------------------------------------

class SessionListItem(BaseListItem):

    def _build_top(self, top):
        self._type_badge = ctk.CTkLabel(
            top, text="",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#12141b", corner_radius=4)
        self._type_badge.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(top, text="",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(side="right")  # scans count

    def _build_bottom(self, bot):
        ctk.CTkLabel(bot, text="",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(side="left")   # date
        ctk.CTkLabel(bot, text="",
                     font=ctk.CTkFont(size=11),
                     text_color=C_MUTED).pack(side="left")   # periods

        pills = ctk.CTkFrame(bot, fg_color="transparent")
        pills.pack(side="right")
        for label, color in [("P", C_SUCCESS), ("L", C_WARNING)]:
            p = ctk.CTkFrame(pills, fg_color="transparent")
            p.pack(side="left", padx=(4, 0))
            ctk.CTkLabel(p, text=f"{label}:—",
                         font=ctk.CTkFont(size=10),
                         text_color=color).pack()

    def _update_contents(self, data: dict):
        atype = data.get("attendee_type", "students")
        self._name_lbl.configure(text=data["name"])
        self._type_badge.configure(
            text=_TYPE_LABEL.get(atype, "Students"),
            text_color=_TYPE_COLOR.get(atype, "#38bdf8"))

        top_ch = self.winfo_children()[0].winfo_children()
        top_ch[2].configure(text=f"{data['total']} scans")

        bot    = self.winfo_children()[1]
        bot_ch = bot.winfo_children()
        bot_ch[0].configure(text=str(data["date"]))
        bot_ch[1].configure(
            text=f" · {data['period_count']} period{'s' if data['period_count'] != 1 else ''}")

        pills = bot_ch[2]
        for frame, val in zip(pills.winfo_children(), [data["present"], data["late"]]):
            frame.winfo_children()[0].configure(
                text=f"{frame.winfo_children()[0].cget('text')[0]}:{val}")

    def _get_id(self, data: dict):
        return data["id"]

# ---------------------------------------------------------------------------
# Sessions screen
# ---------------------------------------------------------------------------

class SessionsScreen(ctk.CTkFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)

        self._sessions      = []
        self._selected_id   = None
        self._selected_item: SessionListItem | None = None
        self._list_items:   list[SessionListItem]   = []
        self._search_var    = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._page          = 0
        self._page_size     = 10
        self._total_count   = 0
        self._loading       = False

        self._build_ui()
        self.after(600, self.refresh)

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── Left panel ────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=C_SURFACE,
                            corner_radius=0, width=290)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        list_hdr = ctk.CTkFrame(left, fg_color=C_SURFACE,
                                corner_radius=0, height=52)
        list_hdr.grid(row=0, column=0, sticky="ew")
        list_hdr.grid_propagate(False)
        list_hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(list_hdr, text="Sessions",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=16, pady=14)

        self._count_lbl = ctk.CTkLabel(
            list_hdr, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._count_lbl.grid(row=0, column=1, padx=(0, 16))

        search_frame = ctk.CTkFrame(left, fg_color=C_SURFACE,
                                    corner_radius=0, height=44)
        search_frame.grid(row=1, column=0, sticky="ew")
        search_frame.grid_propagate(False)

        ctk.CTkEntry(
            search_frame, textvariable=self._search_var,
            placeholder_text="Search sessions...",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=32, corner_radius=8,
        ).pack(fill="x", padx=12, pady=6)

        ctk.CTkFrame(left, fg_color=C_BORDER, height=1).grid(
            row=1, column=0, sticky="ew", pady=(44, 0))

        self._list_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0)
        self._list_scroll.grid(row=2, column=0, sticky="nsew")
        self._list_scroll.grid_columnconfigure(0, weight=1)

        self._build_list_pool()
        
        # Pagination bar
        self._pbar = PaginationBar(left, on_prev=self._prev_page, on_next=self._next_page)
        self._pbar.grid(row=6, column=0, sticky="ew")


        # ── Right panel ───────────────────────────────────────────────
        self._detail = SessionDetailPanel(
            self, on_delete_callback=self.refresh)
        self._detail.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _update_pagination(self):
        total_pages = max(1, -(-self._total_count // PAGE_SIZE))
        self._pbar.update(self._page, total_pages)

    def _next_page(self):
        if (self._page + 1) * self._page_size < self._total_count:
            self._page += 1
            self._load_page()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._load_page()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self):
        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()

    def _load_page(self):
        query = self._search_var.get().strip()
        self._sessions, self._total_count = _fetch_sessions(
            search=query,
            offset=self._page * self._page_size,
            limit=self._page_size)
        self._render_list(self._sessions)
        self._update_pagination()

    def _build_list_pool(self):
        self._list_items = []
        placeholder = {
            "id": 0, "name": "", "date": "", "created_at": None,
            "student_estimated": 0, "staff_estimated": 0, 
            "attendee_type": "students",
            "total": 0, "present": 0, "late": 0,
            "period_count": 0,
            "student_present": 0, "student_late": 0, 
            "staff_present":   0, "staff_late":   0, 
        }
        for _ in range(self._page_size):
            item = SessionListItem(
                self._list_scroll, placeholder,
                on_select=self._on_select)
            item.pack(fill="x", padx=10, pady=4)
            item.pack_forget()
            self._list_items.append(item)

    def _render_list(self, sessions: list):
        self._selected_item = None
        self._count_lbl.configure(
            text=f"{self._total_count} session{'s' if self._total_count != 1 else ''}")

        for i, item in enumerate(self._list_items):
            if i < len(sessions):
                data   = sessions[i]
                is_sel = data["id"] == self._selected_id
                item.update_data(data, selected=is_sel)
                item.pack(fill="x", padx=10, pady=4)
                if is_sel:
                    self._selected_item = item
            else:
                item.pack_forget()

        if not sessions:
            if not hasattr(self, "_empty_lbl"):
                self._empty_lbl = ctk.CTkLabel(
                    self._list_scroll,
                    text="No sessions yet.",
                    font=ctk.CTkFont(size=13), text_color=C_MUTED)
            self._empty_lbl.pack(pady=40)
        else:
            if hasattr(self, "_empty_lbl"):
                self._empty_lbl.pack_forget()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_select(self, data: dict):
        if data["id"] == self._selected_id:
            return
        if self._selected_item is not None:
            self._selected_item.deselect()

        self._selected_id = data["id"]
        new_item = next(
            (item for item in self._list_items
             if item._data["id"] == data["id"]), None)
        if new_item:
            new_item.select()
            self._selected_item = new_item

        self._detail.load(data)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self, *_):
        if self._loading:
            return
        if hasattr(self, "_search_job"):
            self.after_cancel(self._search_job)
        self._search_job = self.after(400, self._reset_and_load)

    def _reset_and_load(self):
        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()


# ---------------------------------------------------------------------------
# Standalone launcher
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = ctk.CTk()
    app.title("Sessions — Attendance Tracker")
    app.geometry("1200x700")
    app.configure(fg_color=C_BG)
    frame = SessionsScreen(app)
    frame.pack(fill="both", expand=True)
    app.mainloop()