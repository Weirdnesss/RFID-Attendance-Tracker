"""
scan_screen.py
--------------
Scan screen as a reusable CTkFrame.
Embedded by main.py — no longer a standalone root window.

Requires:
    pip install customtkinter pyscard SQLAlchemy PyMySQL
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime, time as dtime
import os
from db.scan_db import get_session_by_id

terminal_id = os.getenv("TERMINAL_ID", "UNKNOWN")

from ui.components.scan_area import ScanArea
from ui.components.log_entry import LogEntry
from ui.dialogs.new_session import NewSessionDialog, ConfirmSessionDialog, StudentGroupSelectorDialog, ChooseSessionDialog
from db.scan_db import _fetch_group_counts

from sqlalchemy import func

from database import (AcademicPeriod, SessionLocal, Student, Attendance,
                      Session as EventSession, SessionPeriod)

from hardware.rfid_listener import RFIDListener
from hardware.rfid_reader import CardData
from ui.components.clock_picker import TimeEntry
from ui.components.period_row import PeriodRow
from ui.theme import (
    C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
    C_ACCENT, C_SUCCESS, C_WARNING, C_ERROR,
    C_SUCCESS_BG, C_WARNING_BG, C_ERROR_BG,
)

# Period colours cycling through for visual distinction
_PERIOD_COLORS = ["#3ecf8e", "#6c8fff", "#f0a843", "#e05c5c",
                  "#a78bfa", "#5DCAA5", "#F0997B"]


class ScanScreen(ctk.CTkFrame):
    """
    Reusable frame embedded in main.py.
    The RFID listener is owned here and must be stopped on app close
    via stop_rfid().
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self.active_session     = None
        self._log_entries       = []
        self._listener          = None
        self._scan_mode         = "in"   # "in" or "out"
        self._after_ids         = []
        self._selected_session_id   = None
        self._last_session_id     = None
        self._last_render_state = None
        self._pill_widgets      = {}   # {period_id: {frame, scanned, late, timed_out, ...}}
        self._summary_widgets   = {}   # holds the rightmost summary pill widgets
        self._build_ui()
        self._safe_after(500,  self._start_rfid)
        self._safe_after(1000, self._tick)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_after(self, delay, callback):
        if not self.winfo_exists():
            return None
        aid = self.after(delay, callback)
        self._after_ids.append(aid)
        return aid

    def _get_render_state(self, session):
        if not session:
            return None
        return (
            session["id"],
            session.get("count"),
            tuple(
                (
                    p["id"],
                    p["time_in_start"],
                    p["time_in_end"],
                    p["late_enabled"],
                    p["late_start"],
                    p["grace_minutes"],
                    p["timeout_enabled"],
                    p["timeout_start"],
                    p["timeout_end"],
                    session.get("period_stats", {}).get(p["id"], {}).get("scanned", 0),
                    session.get("period_stats", {}).get(p["id"], {}).get("late", 0),
                    session.get("period_stats", {}).get(p["id"], {}).get("timed_out", 0),
                )
                for p in session.get("periods", [])
            ),
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # rows: 0=sbar  1=info strip  2=scan area  3=log  4=rbar
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Session bar ──────────────────────────────────────────────────────
        sbar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=48)
        sbar.grid(row=0, column=0, sticky="ew")
        sbar.grid_propagate(False)
        sbar.grid_columnconfigure(1, weight=1)

        self._dot = ctk.CTkLabel(sbar, text="●",
                                 font=ctk.CTkFont(size=9), text_color=C_MUTED)
        self._dot.grid(row=0, column=0, padx=(20, 6), pady=14)

        self._session_lbl = ctk.CTkLabel(
            sbar, text="No active session",
            font=ctk.CTkFont(size=13), text_color=C_MUTED)
        self._session_lbl.grid(row=0, column=1, sticky="w")

        self._cutoff_lbl = ctk.CTkLabel(
            sbar, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._cutoff_lbl.grid(row=0, column=2, padx=12)

        self._start_btn = ctk.CTkButton(
            sbar, text="Choose Session", width=130,
            fg_color=C_ACCENT, hover_color="#8aabff", text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._choose_session)
        self._start_btn.grid(row=0, column=3, padx=(0, 8))

        self._end_btn = ctk.CTkButton(
            sbar, text="Leave Session", width=110,
            fg_color="transparent", border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._leave_session)
        self._end_btn.grid(row=0, column=4, padx=(0, 8))
        self._end_btn.grid_remove()

        mode_frame = ctk.CTkFrame(sbar, fg_color=C_BG, corner_radius=6)
        mode_frame.grid(row=0, column=5, padx=(0, 16))

        self._in_btn = ctk.CTkButton(
            mode_frame, text="SCAN IN", width=88, height=28,
            fg_color=C_SUCCESS, hover_color="#2eaf78", text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
            command=lambda: self._set_mode("in"))
        self._in_btn.pack(side="left", padx=(2, 1), pady=2)

        self._out_btn = ctk.CTkButton(
            mode_frame, text="SCAN OUT", width=88, height=28,
            fg_color="transparent", hover_color=C_SURFACE, text_color=C_MUTED,
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
            command=lambda: self._set_mode("out"))
        self._out_btn.pack(side="left", padx=(1, 2), pady=2)

        # ── DEV: manual scan input ───────────────────────────────────────────
        self._dev_id_var = tk.StringVar()
        self._dev_entry = ctk.CTkEntry(
            sbar, textvariable=self._dev_id_var,
            placeholder_text="Student ID",
            fg_color=C_BG, border_color=C_BORDER,
            text_color=C_TEXT, height=28, width=100)
        self._dev_entry.grid(row=0, column=6, padx=(8, 2))
        self._dev_entry.bind("<Return>", lambda e: self._dev_scan())

        ctk.CTkButton(
            sbar, text="Simulate Scan", width=110, height=28,
            fg_color="#2a2d3a", hover_color=C_BORDER,
            text_color=C_MUTED, border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(size=11),
            command=self._dev_scan,
        ).grid(row=0, column=7, padx=(2, 16))

        # ── Info strip (hidden until session starts) ─────────────────────────
        self._info_strip = ctk.CTkFrame(self, fg_color="#12141b", corner_radius=0)
        self._info_strip.grid(row=1, column=0, sticky="ew")
        self._info_strip.grid_remove()
        self._build_info_strip()

        # ── Scan area ────────────────────────────────────────────────────────
        self._scan_area = ScanArea(self)
        self._scan_area.grid(row=2, column=0, sticky="ew", padx=24, pady=(20, 0))
        self._scan_area.configure(height=220)
        self._scan_area.grid_propagate(False)

        # ── Log ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="RECENT SCANS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED).grid(
            row=3, column=0, sticky="nw", padx=28, pady=(14, 4))

        self._log_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._log_frame.grid(row=3, column=0, sticky="nsew", padx=0, pady=(36, 0))
        self._log_frame.grid_columnconfigure(0, weight=1)

        # ── Reader status bar ────────────────────────────────────────────────
        rbar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        rbar.grid(row=4, column=0, sticky="ew")
        rbar.grid_propagate(False)
        rbar.grid_columnconfigure(1, weight=1)

        self._reader_lbl = ctk.CTkLabel(
            rbar, text="● Waiting for reader...",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._reader_lbl.grid(row=0, column=0, padx=20, pady=8)

    def _dev_scan(self):
        sid = self._dev_id_var.get().strip()
        if not sid:
            return
        fake_card = CardData(raw="DEV_MODE", uid=f"DEV-{sid}", student_id=int(sid))
        self._on_card(fake_card)
        self._dev_id_var.set("")

    def _build_info_strip(self):
        inner = ctk.CTkFrame(self._info_strip, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=8)

        self._pills_scroll = ctk.CTkScrollableFrame(
            inner,
            fg_color="transparent",
            orientation="horizontal",
            height=90,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_MUTED,
        )
        self._pills_scroll.pack(fill="x", expand=True)
        self._pills_frame = self._pills_scroll

    # ------------------------------------------------------------------
    # Pills — build once, update in-place (no flicker)
    # ------------------------------------------------------------------

    def _build_pills(self):
        """Destroy and recreate all pill widgets. Called only when the session
        changes (new session or different session), NOT on every tick."""
        for w in self._pills_frame.winfo_children():
            w.destroy()

        self._pill_widgets.clear()
        self._summary_widgets.clear()

        now = datetime.now().time()
        periods = self.active_session.get("periods", [])

        for i, p in enumerate(periods):
            pid    = p["id"]
            color  = _PERIOD_COLORS[i % len(_PERIOD_COLORS)]
            t_in_s = p.get("time_in_start")
            t_in_e = p.get("time_in_end")
            active = t_in_s and t_in_e and t_in_s <= now <= t_in_e

            pill = ctk.CTkFrame(
                self._pills_frame,
                fg_color="#0d1f18" if active else "#1a1d27",
                corner_radius=8, border_width=1,
                border_color=color if active else C_BORDER,
            )
            pill.pack(side="left", padx=(0, 6), anchor="n")

            # ── Name row ────────────────────────────────────────────────────
            name_row = ctk.CTkFrame(pill, fg_color="transparent")
            name_row.pack(anchor="w", padx=8, pady=(5, 0))

            # Active dot — stored so we can show/hide it
            active_dot = ctk.CTkFrame(
                name_row, width=5, height=5,
                fg_color=C_SUCCESS, corner_radius=3)
            if active:
                active_dot.pack(side="left", padx=(0, 5))

            ctk.CTkLabel(
                name_row,
                text=p.get("name", f"Period {i+1}"),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=C_TEXT,
            ).pack(side="left")

            # ── Time tags row ────────────────────────────────────────────────
            tags = []
            if t_in_s and t_in_e:
                tags.append((
                    f"In {t_in_s.strftime('%I:%M %p').lstrip('0')}"
                    f"–{t_in_e.strftime('%I:%M %p').lstrip('0')}",
                    "#0b1220", "#38bdf8"))
            if p.get("late_enabled") and p.get("late_start"):
                ls    = p["late_start"]
                grace = p.get("grace_minutes", 0)
                tags.append((
                    f"Late {ls.strftime('%I:%M %p').lstrip('0')}",
                    "#1f1708", "#f0a843"))
                if grace:
                    tags.append((f"+{grace}m", "#16181f", C_MUTED))
            if (p.get("timeout_enabled")
                    and p.get("timeout_start") and p.get("timeout_end")):
                ts = p["timeout_start"]
                te = p["timeout_end"]
                tags.append((
                    f"Out {ts.strftime('%I:%M %p').lstrip('0')}"
                    f"–{te.strftime('%I:%M %p').lstrip('0')}",
                    "#100e1f", "#a78bfa"))

            if tags:
                tags_row = ctk.CTkFrame(pill, fg_color="transparent")
                tags_row.pack(anchor="w", padx=8, pady=(2, 0))
                for text, fg, tc in tags:
                    ctk.CTkLabel(
                        tags_row, text=text,
                        font=ctk.CTkFont(size=9, weight="bold"),
                        fg_color=fg, text_color=tc, corner_radius=3,
                    ).pack(side="left", padx=(0, 3))

            # ── Stat row ────────────────────────────────────────────────────
            stat_row = ctk.CTkFrame(pill, fg_color="transparent")
            stat_row.pack(anchor="w", padx=8, pady=(4, 6))

            scanned_lbl = ctk.CTkLabel(
                stat_row, text="0",
                font=ctk.CTkFont(size=11, weight="bold"), text_color=C_ACCENT)
            scanned_lbl.pack(side="left", padx=(0, 2))
            ctk.CTkLabel(stat_row, text="signed in",
                         font=ctk.CTkFont(size=9), text_color=C_MUTED).pack(
                side="left", padx=(0, 8))

            late_lbl = timed_out_lbl = None

            if p.get("late_enabled"):
                late_lbl = ctk.CTkLabel(
                    stat_row, text="0",
                    font=ctk.CTkFont(size=11, weight="bold"), text_color=C_WARNING)
                late_lbl.pack(side="left", padx=(0, 2))
                ctk.CTkLabel(stat_row, text="late",
                             font=ctk.CTkFont(size=9), text_color=C_MUTED).pack(
                    side="left", padx=(0, 8))

            if p.get("timeout_enabled"):
                timed_out_lbl = ctk.CTkLabel(
                    stat_row, text="0",
                    font=ctk.CTkFont(size=11, weight="bold"), text_color="#a78bfa")
                timed_out_lbl.pack(side="left", padx=(0, 2))
                ctk.CTkLabel(stat_row, text="signed out",
                             font=ctk.CTkFont(size=9), text_color=C_MUTED).pack(
                    side="left", padx=(0, 8))

            self._pill_widgets[pid] = {
                "frame":      pill,
                "active_dot": active_dot,
                "name_row":   name_row,
                "scanned":    scanned_lbl,
                "late":       late_lbl,
                "timed_out":  timed_out_lbl,
            }

        # ── Summary pill (rightmost) ─────────────────────────────────────────
        n_total = self.active_session.get("count", 0)
        est     = self.active_session.get("estimated_attendees")

        summary = ctk.CTkFrame(
            self._pills_frame,
            fg_color="#1a1d27", corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        summary.pack(side="left", padx=(6, 0), anchor="n")

        count_text = f"{n_total} / {est}" if est else str(n_total)
        count_lbl = ctk.CTkLabel(
            summary, text=count_text,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEXT)
        count_lbl.pack(padx=12, pady=(8, 0))
        ctk.CTkLabel(summary, text="total scans",
                     font=ctk.CTkFont(size=9), text_color=C_MUTED).pack(
            padx=12, pady=(0, 4))

        pct_lbl = bar_fill = None
        if est and est > 0:
            pct = min(round(n_total / est * 100), 100)
            pct_lbl = ctk.CTkLabel(
                summary, text=f"{pct}%",
                font=ctk.CTkFont(size=10), text_color=C_ACCENT)
            pct_lbl.pack(padx=12, pady=(0, 2))

            fill_w = max(2, round(80 * n_total / est))
            bar_bg = ctk.CTkFrame(summary, fg_color=C_BORDER,
                                  corner_radius=2, height=4, width=80)
            bar_bg.pack(padx=12, pady=(0, 8))
            bar_bg.pack_propagate(False)
            bar_fill = ctk.CTkFrame(bar_bg, fg_color=C_ACCENT,
                                    corner_radius=2, height=4, width=fill_w)
            bar_fill.place(x=0, y=0)

        self._summary_widgets = {
            "frame":     summary,
            "count_lbl": count_lbl,
            "pct_lbl":   pct_lbl,
            "bar_fill":  bar_fill,
            "est":       est,
        }

    def _update_pills(self):
        """Update only stat labels and active-highlight in existing pill widgets.
        Never destroys or creates widgets — zero flicker."""
        if not self.active_session:
            return

        now = datetime.now().time()

        for i, p in enumerate(self.active_session.get("periods", [])):
            pid     = p["id"]
            widgets = self._pill_widgets.get(pid)
            if not widgets:
                continue

            stats     = self.active_session.get("period_stats", {}).get(pid, {})
            scanned   = stats.get("scanned",   0)
            late      = stats.get("late",      0)
            timed_out = stats.get("timed_out", 0)

            widgets["scanned"].configure(text=str(scanned))
            if widgets["late"]:
                widgets["late"].configure(text=str(late))
            if widgets["timed_out"]:
                widgets["timed_out"].configure(text=str(timed_out))

            # Active period highlight
            t_in_s = p.get("time_in_start")
            t_in_e = p.get("time_in_end")
            active = t_in_s and t_in_e and t_in_s <= now <= t_in_e
            color  = _PERIOD_COLORS[i % len(_PERIOD_COLORS)]

            widgets["frame"].configure(
                fg_color="#0d1f18" if active else "#1a1d27",
                border_color=color if active else C_BORDER,
            )

            # Show/hide the live dot without rebuilding
            dot = widgets["active_dot"]
            if active:
                if not dot.winfo_ismapped():
                    dot.pack(side="left", padx=(0, 5), before=dot.master.winfo_children()[-1])
            else:
                dot.pack_forget()

        self._update_summary_pill()

    def _update_summary_pill(self):
        """Update the summary pill count/pct/bar in-place."""
        sw = self._summary_widgets
        if not sw or not self.active_session:
            return

        n_total = self.active_session.get("count", 0)
        est     = sw.get("est")

        count_text = f"{n_total} / {est}" if est else str(n_total)
        sw["count_lbl"].configure(text=count_text)

        if est and est > 0 and sw.get("pct_lbl") and sw.get("bar_fill"):
            pct    = min(round(n_total / est * 100), 100)
            fill_w = max(2, round(80 * n_total / est))
            sw["pct_lbl"].configure(text=f"{pct}%")
            sw["bar_fill"].configure(width=fill_w)

    # def _update_session_summary(self):
    #     """Update the bottom-bar count label."""
    #     if not self.active_session:
    #         return
    #     n_total = self.active_session.get("count", 0)
    #     est     = self.active_session.get("estimated_attendees")
    #     if est:
    #         pct = min(round(n_total / est * 100), 100)
    #         self._count_lbl.configure(text=f"{n_total}/{est} expected scans ({pct}%)")
    #     else:
    #         self._count_lbl.configure(text=f"Total scans this session: {n_total}")

    # ------------------------------------------------------------------
    # Tick — poll DB every 5 s, update UI only when state changed
    # ------------------------------------------------------------------

    def _tick(self):
        if not self.winfo_exists():
            return

        if self._selected_session_id is None:
            self._safe_after(5000, self._tick)
            return
        db_session = get_session_by_id(self._selected_session_id)
        current_id = self._last_session_id
        new_id     = db_session["id"] if db_session else None

        # ── Case 1: Same session ─────────────────────────────────────────────
        if current_id == new_id:
            if db_session:
                new_state = self._get_render_state(db_session)
                if new_state != self._last_render_state:
                        self.active_session     = db_session
                        self._last_render_state = new_state
                        self._build_pills()   # was _update_pills()
                        self._update_pills()

        # ── Case 2: New session started ──────────────────────────────────────
        elif current_id is None and new_id is not None:
            self.active_session   = db_session
            self._last_session_id = new_id

            self._dot.configure(text_color=C_SUCCESS)
            self._session_lbl.configure(text=db_session["name"], text_color=C_ACCENT)
            self._start_btn.grid_remove()
            self._end_btn.grid()
            self._info_strip.grid()

            self._build_pills()
            self._update_pills()
            self._last_render_state = self._get_render_state(db_session)

        # ── Case 3: Session ended ────────────────────────────────────────────
        elif current_id is not None and new_id is None:
            self.active_session   = None
            self._last_session_id = None

            self._dot.configure(text_color=C_MUTED)
            self._session_lbl.configure(text="No active session", text_color=C_MUTED)
            self._end_btn.grid_remove()
            self._start_btn.grid()
            self._count_lbl.configure(text="Start a Session")
            self._info_strip.grid_remove()

            for w in self._pills_frame.winfo_children():
                w.destroy()
            self._pill_widgets.clear()
            self._summary_widgets.clear()
            self._last_render_state = None
            self._set_mode("in")

        # ── Case 4: Different session (rare) ─────────────────────────────────
        elif current_id != new_id:
            self.active_session   = db_session
            self._last_session_id = new_id

            self._dot.configure(text_color=C_SUCCESS)
            self._session_lbl.configure(text=db_session["name"], text_color=C_ACCENT)
            self._info_strip.grid()
            self._start_btn.grid_remove()
            self._end_btn.grid()

            self._build_pills()
            self._update_pills()
            self._last_render_state = self._get_render_state(db_session)

        self._safe_after(5000, self._tick)

    # ------------------------------------------------------------------
    # RFID
    # ------------------------------------------------------------------

    def _start_rfid(self):
        def safe_after(fn, *args):
            try:
                if self.winfo_exists():
                    self.after(0, fn, *args)
            except Exception:
                pass

        self._listener = RFIDListener(
            on_card=lambda c: safe_after(self._on_card, c),
            on_error=lambda m: safe_after(self._on_error, m),
            on_connected=lambda: safe_after(self._on_connected),
            on_disconnected=lambda: safe_after(self._on_disconnected),
        )
        self._listener.start()

    def stop_rfid(self):
        if self._listener:
            self._listener.stop()
        for aid in getattr(self, "_after_ids", []):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    # def _start_session(self):
    #     dlg = NewSessionDialog(self)
    #     self.wait_window(dlg)

    #     if not dlg.result or not dlg.result.get("started"):
    #         return

    #     # Force immediate refresh instead of waiting 5 s
    #     self._last_session_id = None
    #     self._tick()

    # def _end_session(self):
    #     if not messagebox.askyesno(
    #             "End Session",
    #             f"End session '{self.active_session['name']}'?"):
    #         return
    #     db = SessionLocal()
    #     try:
    #         db.query(EventSession).filter(
    #             EventSession.is_active == 1
    #         ).update({"is_active": 0, "active_flag": None})
    #         db.commit()
    #     finally:
    #         db.close()

    #     self._dot.configure(text_color=C_MUTED)
    #     self._session_lbl.configure(text="No active session", text_color=C_MUTED)
    #     self._cutoff_lbl.configure(text="")
    #     self._end_btn.grid_remove()
    #     self._start_btn.grid()
    #     self._count_lbl.configure(text="Start a Session")
    #     self._set_mode("in")
    #     # _tick will handle hiding the strip and clearing pills on next poll

    def _choose_session(self):
        dlg = ChooseSessionDialog(self)
        self.wait_window(dlg)

        if not dlg.result:
            return

        self._selected_session_id = dlg.result["id"]
        self._last_session_id = None  # force _tick to treat this as a new session
        self._tick()

    def _leave_session(self):
        if not messagebox.askyesno(
                "Leave Session",
                f"Leave session '{self.active_session['name']}'?"):
            return

        self._selected_session_id = None
        self.active_session       = None
        self._last_session_id     = None

        self._dot.configure(text_color=C_MUTED)
        self._session_lbl.configure(text="No active session", text_color=C_MUTED)
        self._cutoff_lbl.configure(text="")
        self._end_btn.grid_remove()
        self._start_btn.grid()
        self._info_strip.grid_remove()
        for w in self._pills_frame.winfo_children():
            w.destroy()
        self._pill_widgets.clear()
        self._summary_widgets.clear()
        self._last_render_state = None
        self._set_mode("in")

    def _set_mode(self, mode: str):
        self._scan_mode = mode
        if mode == "in":
            self._in_btn.configure(fg_color=C_SUCCESS, text_color="#ffffff")
            self._out_btn.configure(fg_color="transparent", text_color=C_MUTED)
        else:
            self._in_btn.configure(fg_color="transparent", text_color=C_MUTED)
            self._out_btn.configure(fg_color="#7c3aed", text_color="#ffffff")
        self._scan_area.set_mode(mode)

    def _increment_breakdown(self, status: str):
        if self.active_session and "breakdown" in self.active_session:
            bd = self.active_session["breakdown"]
            if status in bd:
                bd[status] += 1

    # ------------------------------------------------------------------
    # Card handlers
    # ------------------------------------------------------------------

    def _on_card(self, card: CardData):
        if self.active_session is None:
            self._scan_area.show_no_session()
            return
        self._process_with_db(card)

    def _get_active_period(self, mode: str | None = None) -> dict | None:
        now  = datetime.now().time()
        mode = mode or self._scan_mode

        for p in self.active_session.get("periods", []):
            if mode == "out":
                t_out_s = p.get("timeout_start")
                t_out_e = p.get("timeout_end")
                if p.get("timeout_enabled") and t_out_s and t_out_e and t_out_s <= now <= t_out_e:
                    return p
            else:
                t_in_s = p.get("time_in_start")
                t_in_e = p.get("time_in_end")
                if t_in_s and t_in_e and t_in_s <= now <= t_in_e:
                    return p
        return None

    def _process_with_db(self, card: CardData):
        db = SessionLocal()
        try:
            student = db.query(Student).filter(
                Student.student_id == card.student_id).first()

            if not student:
                self._scan_area.show_error(f"Student ID {card.student_id} not found")
                self._add_log("Unknown card", card.student_id, "error",
                              datetime.now().strftime("%I:%M:%S %p"))
                return

            name = f"{student.first_name} {student.last_name}"
            now  = datetime.now()

            period = self._get_active_period(self._scan_mode)
            if period is None:
                if self._scan_mode == "out":
                    self._scan_area.show_error("No active scan-out window right now")
                else:
                    self._scan_area.show_error(
                        "No active period right now — check session windows")
                return

            existing = db.query(Attendance).filter(
                Attendance.student_id == card.student_id,
                Attendance.session_id == self.active_session["id"],
                Attendance.period_id  == period["id"],
            ).first()

            # ── SCAN OUT ─────────────────────────────────────────────────────
            if self._scan_mode == "out":
                if not period["timeout_enabled"]:
                    self._scan_area.show_error(
                        f"Time-out tracking is off for '{period['name']}'")
                    return

                if period["timeout_start"] and period["timeout_end"]:
                    now_t = now.time()
                    if not (period["timeout_start"] <= now_t <= period["timeout_end"]):
                        ts = period["timeout_start"].strftime("%I:%M %p").lstrip("0")
                        te = period["timeout_end"].strftime("%I:%M %p").lstrip("0")
                        self._scan_area.show_error(f"Scan-out window is {ts} – {te}")
                        return

                if not existing:
                    self._scan_area.show_not_checked_in(name)
                    return
                if existing.time_out:
                    self._scan_area.show_already_out(
                        name, existing.time_out.strftime("%I:%M %p"))
                    return

                existing.time_out     = now
                existing.terminal_id  = terminal_id
                db.commit()

                ps  = self.active_session.setdefault("period_stats", {})
                pid = period["id"]
                ps.setdefault(pid, {"scanned": 0, "late": 0, "timed_out": 0})
                ps[pid]["timed_out"] += 1

                time_in_str = (existing.time_in.strftime("%I:%M %p")
                               if existing.time_in else "—")
                self._scan_area.show_timeout(name, student.student_id, time_in_str)
                self._add_log(name, student.student_id, "timeout",
                              now.strftime("%I:%M:%S %p"))
                self.active_session["count"] += 1
                self._update_pills()
                return

            # ── SCAN IN ──────────────────────────────────────────────────────
            if existing:
                self._scan_area.show_warning(
                    f"{student.first_name} already marked for "
                    f"'{period['name']}' at "
                    f"{existing.time_in.strftime('%I:%M %p')}")
                return

            from datetime import timedelta
            if period["late_enabled"] and period["late_start"]:
                cutoff_dt = now.replace(
                    hour=period["late_start"].hour,
                    minute=period["late_start"].minute, second=0)
                cutoff_dt += timedelta(minutes=period["grace_minutes"])
                status = "late" if now > cutoff_dt else "present"
            else:
                status = "present"

            ps  = self.active_session.setdefault("period_stats", {})
            pid = period["id"]
            ps.setdefault(pid, {"scanned": 0, "late": 0, "timed_out": 0})
            ps[pid]["scanned"] += 1
            if status == "late":
                ps[pid]["late"] += 1

            db.add(Attendance(
                student_id=student.student_id,
                session_id=self.active_session["id"],
                period_id=period["id"],
                status=status,
                time_in=now,
                terminal_id=terminal_id,
            ))
            db.commit()

            self._increment_breakdown(status)
            self._scan_area.show_success(
                name, student.student_id,
                f"{student.program.code if student.program else '—'}  ·  {period['name']}",
                status)
            self._add_log(name, student.student_id, status,
                          now.strftime("%I:%M:%S %p"))
            self.active_session["count"] += 1
            self._update_pills()
        finally:
            db.close()

    def _on_error(self, _):
        self._scan_area.show_error("Card read error")

    def _on_connected(self):
        self._reader_lbl.configure(text="● Reader Connected", text_color=C_SUCCESS)

    def _on_disconnected(self):
        self._reader_lbl.configure(text="● Reader disconnected", text_color=C_ERROR)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _add_log(self, name, student_id, status, time_str):
        entry = LogEntry(self._log_frame, name, student_id, status, time_str)
        entry.pack(fill="x", padx=20, pady=3)
        self._log_entries.append(entry)
        if len(self._log_entries) > 20:
            self._log_entries.pop(0).destroy()
        self._safe_after(
            50,
            lambda: self._log_frame._parent_canvas.yview_moveto(1.0),
        )