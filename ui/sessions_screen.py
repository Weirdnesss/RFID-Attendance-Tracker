"""
sessions_screen.py
------------------
Sessions screen for the RFID Attendance Tracker.
Browse all past sessions, view attendance detail per session.

Embedded by main.py as a CTkFrame.

Performance improvements (v2):
    - SessionListItem gains select()/deselect() methods — no list rebuild on click
    - _selected_item holds a direct reference; selection toggle is 2 configure() calls
    - Fast-path guard skips all work when the same session is re-clicked
    - Search is debounced 400 ms — no DB hit on every keystroke
    - _on_select no longer calls _render_list(); only the detail panel updates
    - Export data is fetched lazily (only when a session is first selected, cached)
"""
import math
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime

from utils.export_utils import (fetch_session_report, export_session_xlsx, export_session_pdf)
from db.session_db import _fetch_sessions, _fetch_session_detail, _fetch_session_periods
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED, C_ACCENT, C_SUCCESS, C_WARNING, C_ERROR, PERIOD_COLORS,)

from sqlalchemy import func, case

# ---------------------------------------------------------------------------
# Detail panel — shown on the right when a session is selected
# ---------------------------------------------------------------------------

class SessionDetailPanel(ctk.CTkFrame):
    STATUS_COLORS = {
        "present": C_SUCCESS,
        "late":    C_WARNING,
        "absent":  C_ERROR,
    }

    _RECORD_PAGE_SIZE = 20

    def __init__(self, parent, on_delete_callback, **kwargs):
        super().__init__(parent, fg_color=C_BG,
                         corner_radius=0, **kwargs)
        self._on_delete    = on_delete_callback
        self._session_data = None
        self._export_data  = None
        self._all_records  = []
        self._rec_page     = 0
        self._build_ui()
        self._build_record_pool()

    def _build_ui(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE,
                            corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(
            hdr, text="Select a session",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_MUTED)
        self._title_lbl.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        self._xlsx_btn = ctk.CTkButton(
            hdr, text="Export Excel", width=110,
            fg_color="transparent", border_color=C_SUCCESS,
            border_width=1, text_color=C_SUCCESS,
            hover_color="#0d1f18",
            font=ctk.CTkFont(size=12),
            state="disabled",
            command=self._export_xlsx)
        self._xlsx_btn.grid(row=0, column=1, padx=(0, 8), pady=10)

        self._pdf_btn = ctk.CTkButton(
            hdr, text="Export PDF", width=100,
            fg_color="transparent", border_color=C_ERROR,
            border_width=1, text_color=C_ERROR,
            hover_color="#1f0d0d",
            font=ctk.CTkFont(size=12),
            state="disabled",
            command=self._export_pdf)
        self._pdf_btn.grid(row=0, column=2, padx=(0, 16), pady=10)

        # ── Stats row ─────────────────────────────────────────────────
        self._stats_frame = ctk.CTkFrame(
            self, fg_color="transparent", height=60)
        self._stats_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 4))
        self._stats_frame.grid_propagate(False)

        self._stat_labels = {}
        for i, (key, label, color) in enumerate([
            ("total",   "Present",   C_SUCCESS),
            ("late",      "Late",      C_WARNING),
            ("absent",    "Absent",    C_ERROR),
            ("estimated", "Expected",  C_MUTED),
            ("rate",      "Rate %",    C_TEXT),
        ]):
            pill = ctk.CTkFrame(self._stats_frame, fg_color=C_SURFACE,
                                corner_radius=8, border_width=1,
                                border_color=color)
            pill.pack(side="left", padx=(0, 8))
            val_lbl = ctk.CTkLabel(pill, text="—",
                                    font=ctk.CTkFont(size=20, weight="bold"),
                                    text_color=color)
            val_lbl.pack(padx=16, pady=(8, 0))
            ctk.CTkLabel(pill, text=label,
                          font=ctk.CTkFont(size=10),
                          text_color=C_MUTED).pack(padx=16, pady=(0, 8))
            self._stat_labels[key] = val_lbl

        # ── Column headers ────────────────────────────────────────────
        col_hdr = ctk.CTkFrame(self, fg_color=C_ACCENT,
                                corner_radius=0, height=30)
        col_hdr.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))
        col_hdr.grid_propagate(False)
        for text, w in [("#", 28), ("Student ID", 75), ("Name", 160),
                         ("Program", 130), ("Period", 90),
                         ("Status", 75), ("Time In", 85), ("Time Out", 85)]:
            ctk.CTkLabel(col_hdr, text=text, width=w,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=C_TEXT).pack(side="left", padx=4)

        # ── Scrollable record list ────────────────────────────────────
        self._record_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._record_scroll.grid(row=3, column=0, sticky="nsew",
                                  padx=16, pady=(0, 0))
        self._record_scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._empty_lbl = ctk.CTkLabel(
            self._record_scroll,
            text="Select a session from the list to view attendance",
            font=ctk.CTkFont(size=13), text_color=C_MUTED)
        self._empty_lbl.pack(pady=40)

        # ── Record pagination bar ─────────────────────────────────────
        rec_pbar = ctk.CTkFrame(self, fg_color=C_SURFACE,
                                 corner_radius=0, height=40)
        rec_pbar.grid(row=4, column=0, sticky="ew")
        rec_pbar.grid_propagate(False)
        rec_pbar.grid_columnconfigure(1, weight=1)

        self._rec_prev_btn = ctk.CTkButton(
            rec_pbar, text="← Prev", width=80, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_SURFACE, corner_radius=6,
            state="disabled",
            command=self._rec_prev_page)
        self._rec_prev_btn.grid(row=0, column=0, padx=(8, 4), pady=5)

        self._rec_page_lbl = ctk.CTkLabel(
            rec_pbar, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._rec_page_lbl.grid(row=0, column=1)

        self._rec_next_btn = ctk.CTkButton(
            rec_pbar, text="Next →", width=80, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            state="disabled",
            command=self._rec_next_page)
        self._rec_next_btn.grid(row=0, column=2, padx=(4, 8), pady=5)

    # ------------------------------------------------------------------
    # Record pagination helpers
    # ------------------------------------------------------------------

    def _rec_total_pages(self) -> int:
        return max(1, math.ceil(len(self._all_records) / self._RECORD_PAGE_SIZE))

    def _update_rec_pagination(self):
        total = len(self._all_records)
        pages = self._rec_total_pages()
        start = self._rec_page * self._RECORD_PAGE_SIZE + 1
        end   = min((self._rec_page + 1) * self._RECORD_PAGE_SIZE, total)

        if total == 0:
            self._rec_page_lbl.configure(text="No records")
        else:
            self._rec_page_lbl.configure(
                text=f"Page {self._rec_page + 1} / {pages}  "
                     f"({start}–{end} of {total})")

        self._rec_prev_btn.configure(
            state="normal" if self._rec_page > 0 else "disabled")
        self._rec_next_btn.configure(
            state="normal"
            if (self._rec_page + 1) * self._RECORD_PAGE_SIZE < total
            else "disabled")

    def _rec_prev_page(self):
        if self._rec_page > 0:
            self._rec_page -= 1
            self._render_records()

    def _rec_next_page(self):
        if (self._rec_page + 1) * self._RECORD_PAGE_SIZE < len(self._all_records):
            self._rec_page += 1
            self._render_records()

    # ------------------------------------------------------------------
    # Record rendering
    # ------------------------------------------------------------------

    def _build_record_pool(self):
        self._row_frames: list[ctk.CTkFrame] = []
        self._row_dividers: list[ctk.CTkFrame] = []

        for _ in range(self._RECORD_PAGE_SIZE):
            r = ctk.CTkFrame(self._record_scroll, fg_color=C_BG,
                                corner_radius=0, height=34)
            r.pack_propagate(False)
            for text, w in [("", 28), ("", 75), ("", 160),
                            ("", 130), ("", 90), ("", 75), ("", 85), ("", 85)]:
                ctk.CTkLabel(r, text=text, width=w,
                                font=ctk.CTkFont(size=11),
                                text_color=C_TEXT,
                                anchor="w").pack(side="left", padx=4)
            div = ctk.CTkFrame(self._record_scroll, fg_color=C_BORDER,
                                height=1, corner_radius=0)
            self._row_frames.append(r)
            self._row_dividers.append(div)
            r.pack_forget()
            div.pack_forget()

        self._periods_panel = ctk.CTkFrame(
            self._record_scroll, fg_color=C_SURFACE,
            corner_radius=8, border_width=1, border_color=C_BORDER)
        self._periods_panel.pack_forget()

    def _render_records(self):
        # hide the empty label if showing
        self._empty_lbl.pack_forget()

        if not self._all_records:
            for r, d in zip(self._row_frames, self._row_dividers):
                r.pack_forget()
                d.pack_forget()
            self._empty_lbl.pack(pady=40)
            self._update_rec_pagination()
            return

        start        = self._rec_page * self._RECORD_PAGE_SIZE
        end          = start + self._RECORD_PAGE_SIZE
        page_records = self._all_records[start:end]

        for i, frame in enumerate(self._row_frames):
            div = self._row_dividers[i]
            if i < len(page_records):
                row          = page_records[i]
                global_idx   = start + i + 1
                bg           = "#13151c" if i % 2 == 0 else C_BG
                status_color = self.STATUS_COLORS.get(row["status"], C_MUTED)

                frame.configure(fg_color=bg)
                labels = frame.winfo_children()
                configs = [
                    (str(global_idx),        C_TEXT,       False),
                    (str(row["student_id"]), C_TEXT,       False),
                    (row["name"],            C_TEXT,       False),
                    (row["program"],         C_MUTED,      False),
                    (row["period_name"],     C_ACCENT,     False),
                    (row["status"].upper(),  status_color, True),
                    (row["time_in"],         C_TEXT,       False),
                    (row["time_out"],        C_MUTED,      False),
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

        self._update_rec_pagination()
        self._record_scroll._parent_canvas.yview_moveto(0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, session_data: dict):
        self._session_data = session_data
        self._rec_page     = 0

        self._title_lbl.configure(
            text=f"{session_data['name']}  —  {session_data['date']}",
            text_color=C_TEXT)

        self._export_data = fetch_session_report(session_data["id"])
        self._xlsx_btn.configure(state="normal")
        self._pdf_btn.configure(state="normal")

        total_present = session_data["present"] + session_data["late"]

        self._stat_labels["total"].configure(
            text=str(total_present)
        )

        self._stat_labels["late"].configure(text=str(session_data["late"]))
        self._stat_labels["absent"].configure(text=str(session_data["absent"]))

        est = session_data.get("estimated_attendees")
        self._stat_labels["estimated"].configure(
            text=str(est) if est else "—")
        if est and est > 0:
            rate = min(round(total_present / est * 100, 1), 100.0)
            rate_color = (C_SUCCESS if rate >= 75
                          else C_WARNING if rate >= 50 else C_ERROR)
            self._stat_labels["rate"].configure(
                text=f"{rate}%", text_color=rate_color)
            self._stat_labels["rate"].master.configure(border_color=rate_color)
        else:
            self._stat_labels["rate"].configure(text="—")

        for w in self._periods_panel.winfo_children():
            w.destroy()

        periods = _fetch_session_periods(session_data["id"])
        if periods:
            self._periods_panel.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(self._periods_panel, text="PERIODS",
                          font=ctk.CTkFont(size=10, weight="bold"),
                          text_color=C_MUTED).pack(anchor="w", padx=12, pady=(8, 4))
            for i, p in enumerate(periods):
                color = PERIOD_COLORS[i % len(PERIOD_COLORS)]
                pr = ctk.CTkFrame(self._periods_panel, fg_color="transparent")
                pr.pack(fill="x", padx=12, pady=(0, 6))
                ctk.CTkFrame(pr, width=6, height=6,
                              fg_color=color, corner_radius=3).pack(side="left", padx=(0, 8))
                ctk.CTkLabel(
                    pr,
                    text=(
                        f"{p['name']}  "
                        f"{p['time_in_start']}–{p['time_in_end']}  "
                        + (f"· Late After {p['late_start']}  " if p['late_start'] else "")
                        + (f"· Grace {p['grace_minutes']}min  " if p['late_start'] else "")
                        + (f"· Track out {p['timeout_start']}-{p['timeout_end']}" if p['timeout_start'] else "")
                    ),
                    font=ctk.CTkFont(size=11),
                    text_color=C_MUTED).pack(side="left")
        else:
            self._periods_panel.pack_forget()

        self._all_records = _fetch_session_detail(session_data["id"])  # ← once, at the end
        self._render_records()

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

    def clear(self):
        self._session_data = None
        self._export_data  = None
        self._all_records  = []
        self._rec_page     = 0
        self._title_lbl.configure(text="Select a session", text_color=C_MUTED)
        self._xlsx_btn.configure(state="disabled")
        self._pdf_btn.configure(state="disabled")
        for key in ("total", "late", "estimated", "rate", "absent"):
            self._stat_labels[key].configure(text="—")
        for r, d in zip(self._row_frames, self._row_dividers):
            r.pack_forget()
            d.pack_forget()
        self._empty_lbl.pack(pady=40)          # ← this is enough
        self._rec_page_lbl.configure(text="")
        self._rec_prev_btn.configure(state="disabled")
        self._rec_next_btn.configure(state="disabled")
        self._periods_panel.pack_forget()

# ---------------------------------------------------------------------------
# Session list item
# ---------------------------------------------------------------------------

class SessionListItem(ctk.CTkFrame):
    """
    A single row in the session list.

    Selection highlight is toggled via select()/deselect() — only configure()
    calls, zero widget creation or destruction.  This matches the pattern from
    StudentListItem and is the key fix for Windows sluggishness.
    """

    def __init__(self, parent, data: dict, on_select, selected=False, **kwargs):
        super().__init__(
            parent,
            fg_color="#1e2130" if selected else C_SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=C_ACCENT if selected else C_BORDER,
            **kwargs)

        self._data      = data
        self._on_select = on_select
        self._selected  = selected

        self.bind("<Button-1>", self._clicked)

        # Top row: name + total count
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))

        self._name_lbl = ctk.CTkLabel(
            top, text=data["name"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_ACCENT if selected else C_TEXT,
            anchor="w")
        self._name_lbl.pack(side="left")

        total_lbl = ctk.CTkLabel(
            top, text=f"{data['total']} scans",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED)
        total_lbl.pack(side="right")

        # Bottom row: date + status pills
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(anchor="n", padx=14, pady=(0, 10))

        date_lbl = ctk.CTkLabel(
            bot, text=str(data["date"]),
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED)
        date_lbl.pack(side="left")

        period_lbl = ctk.CTkLabel(
            bot,
            text=f"  ·  {data['period_count']} period{'s' if data['period_count'] != 1 else ''}",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED)
        period_lbl.pack(side="left")

        pills = ctk.CTkFrame(bot, fg_color="transparent")
        pills.pack(side="right")

        for label, val, color in [
            ("P", data["present"], C_SUCCESS),
            ("L", data["late"],    C_WARNING),
            ("A", data["absent"],  C_ERROR),
        ]:
            p = ctk.CTkFrame(pills, fg_color="transparent")
            p.pack(side="left", padx=(4, 0))
            ctk.CTkLabel(p, text=f"{label}:{val}",
                          font=ctk.CTkFont(size=10),
                          text_color=color).pack()

        # Propagate clicks from all child widgets up to _clicked
        self._sub_frames = [top, bot, pills]
        for frame in self._sub_frames:
            frame.bind("<Button-1>", self._clicked)
            for child in frame.winfo_children():
                child.bind("<Button-1>", self._clicked)

    def _clicked(self, _event=None):
        self._on_select(self._data)

    def update_data(self, data: dict, selected: bool = False):
        self._data     = data
        self._selected = selected
        self._name_lbl.configure(
            text=data["name"],
            text_color=C_ACCENT if selected else C_TEXT)
        self.configure(
            fg_color="#1e2130" if selected else C_SURFACE,
            border_color=C_ACCENT if selected else C_BORDER)

        top = self.winfo_children()[0]
        bot = self.winfo_children()[1]

        top_children = top.winfo_children()
        top_children[1].configure(text=f"{data['total']} scans")   # total_lbl

        bot_children = bot.winfo_children()
        bot_children[0].configure(text=str(data["date"]))           # date_lbl
        bot_children[1].configure(                                  # period_lbl
            text=f"  ·  {data['period_count']} period{'s' if data['period_count'] != 1 else ''}")

        pills = bot_children[2]
        pill_frames = pills.winfo_children()
        for frame, val in zip(pill_frames, [data["present"], data["late"], data["absent"]]):
            frame.winfo_children()[0].configure(
                text=f"{frame.winfo_children()[0].cget('text')[0]}:{val}")

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
# Sessions screen
# ---------------------------------------------------------------------------

class SessionsScreen(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG,
                          corner_radius=0, **kwargs)
        self._sessions        = []
        self._selected_id     = None
        self._selected_item: SessionListItem | None = None  # direct ref — no scan needed
        self._list_items: list[SessionListItem] = []
        self._search_var      = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._page        = 0
        self._page_size   = 10
        self._total_count = 0
        self._loading     = False

        self._build_ui()
        self.after(600, self.refresh)

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── Left panel: session list ──────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=C_SURFACE,
                             corner_radius=0, width=290,
                             border_width=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # List header
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

        # Search box
        search_frame = ctk.CTkFrame(left, fg_color=C_SURFACE,
                                     corner_radius=0, height=44)
        search_frame.grid(row=1, column=0, sticky="ew")
        search_frame.grid_propagate(False)

        ctk.CTkEntry(
            search_frame,
            textvariable=self._search_var,
            placeholder_text="Search sessions...",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT,
            height=32, corner_radius=8
        ).pack(fill="x", padx=12, pady=6)

        ctk.CTkFrame(left, fg_color=C_BORDER,
                      height=1).grid(row=1, column=0, sticky="ew",
                                      pady=(44, 0))

        # Scrollable session list
        self._list_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0)
        self._list_scroll.grid(row=2, column=0, sticky="nsew")
        self._list_scroll.grid_columnconfigure(0, weight=1)

        self._build_list_pool()

        # ── Session list pagination bar ───────────────────────────────
        pbar = ctk.CTkFrame(left, fg_color=C_SURFACE,
                             corner_radius=0, height=38)
        pbar.grid(row=3, column=0, sticky="ew")
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
            pbar, text="", font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._page_lbl.grid(row=0, column=1)

        self._next_btn = ctk.CTkButton(
            pbar, text="Next →", width=70, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            command=self._next_page)
        self._next_btn.grid(row=0, column=2, padx=(4, 8), pady=5)

        # Refresh button
        ctk.CTkButton(
            left, text="↻  Refresh", height=36,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=0,
            command=self.refresh
        ).grid(row=4, column=0, sticky="ew")

        # ── Right panel: detail ───────────────────────────────────────
        self._detail = SessionDetailPanel(
            self, on_delete_callback=self.refresh)
        self._detail.grid(row=0, column=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Session list pagination
    # ------------------------------------------------------------------

    def _update_pagination(self):
        total_pages = max(1, math.ceil(self._total_count / self._page_size))
        self._page_lbl.configure(text=f"Page {self._page + 1} / {total_pages}")
        self._prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self._next_btn.configure(
            state="normal"
            if (self._page + 1) * self._page_size < self._total_count
            else "disabled")

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
        """Full reload — resets selection, page, and detail panel."""
        self._page          = 0
        self._selected_id   = None
        self._selected_item = None
        self._detail.clear()
        self._load_page()

    def _load_page(self):
        """Fetch the current page from DB and render it."""
        query = self._search_var.get().strip()
        self._sessions, self._total_count = _fetch_sessions(
            search=query,
            offset=self._page * self._page_size,
            limit=self._page_size)
        self._render_list(self._sessions)
        self._update_pagination()

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
    
    def _build_list_pool(self):
        """Pre-create page_size SessionListItem widgets, hide them all."""
        self._list_items: list[SessionListItem] = []
        placeholder = {
            "id": 0, "name": "", "date": "", "created_at": None,
            "estimated_attendees": 0, "total": 0, "present": 0,
            "late": 0, "absent": 0, "period_count": 0,
        }
        for _ in range(self._page_size):
            item = SessionListItem(
                self._list_scroll, placeholder,
                on_select=self._on_select)
            item.pack(fill="x", padx=10, pady=4)
            item.pack_forget()
            self._list_items.append(item)

    # ------------------------------------------------------------------
    # Selection — O(1), no list rebuild
    # ------------------------------------------------------------------

    def _on_select(self, data: dict):
        # ── Fast path: same session clicked again ──────────────────────
        if data["id"] == self._selected_id:
            return

        # ── Deselect old item (2 configure() calls, no widget creation) ─
        if self._selected_item is not None:
            self._selected_item.deselect()

        # ── Select new item ────────────────────────────────────────────
        self._selected_id = data["id"]

        new_item = next(
            (item for item in self._list_items
             if item._data["id"] == data["id"]),
            None)
        if new_item:
            new_item.select()
        self._selected_item = new_item

        # ── Update detail panel only — list stays untouched ───────────
        self._detail.load(data)

    # ------------------------------------------------------------------
    # Search — debounced 400 ms, same pattern as StudentsScreen
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
# Standalone launcher (for testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Sessions — Attendance Tracker")
    app.geometry("1100x700")
    app.configure(fg_color=C_BG)

    frame = SessionsScreen(app)
    frame.pack(fill="both", expand=True)

    app.mainloop()
    