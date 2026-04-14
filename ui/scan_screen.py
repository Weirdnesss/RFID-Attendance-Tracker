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

from ui.components.scan_area import ScanArea
from ui.components.log_entry import LogEntry
from ui.dialogs.new_session import NewSessionDialog, ConfirmSessionDialog, StudentGroupSelectorDialog
from db.scan_db import _fetch_group_counts

from sqlalchemy import func

from database import (SessionLocal, Student, Attendance,
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

# ---------------------------------------------------------------------------
# New Session Dialog
# ---------------------------------------------------------------------------

# Period colours cycling through for visual distinction
_PERIOD_COLORS = ["#3ecf8e", "#6c8fff", "#f0a843", "#e05c5c",
                  "#a78bfa", "#5DCAA5", "#F0997B"]

# ---------------------------------------------------------------------------
# Scan screen — now a CTkFrame, not a root window
# ---------------------------------------------------------------------------

class ScanScreen(ctk.CTkFrame):
    """
    Reusable frame embedded in main.py.
    The RFID listener is owned here and must be stopped on app close
    via stop_rfid().
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self.active_session = None
        self._log_entries   = []
        self._listener      = None
        self._scan_mode     = "in"   # "in" or "out"
        self._after_ids = []
        self._build_ui()
        # Delay start until mainloop is running — prevents
        # "main thread is not in main loop" on startup
        self._safe_after(500, self._start_rfid)

    def _safe_after(self, delay, callback):
        if not self.winfo_exists():
            return None
        aid = self.after(delay, callback)
        self._after_ids.append(aid)
        return aid

    def _build_ui(self):
        # rows: 0=sbar  1=info strip  2=scan area  3=log  4=rbar
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
    
        # ── Session bar ──────────────────────────────────────────────────────────
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
    
        # kept for compact — hidden behind the strip now
        self._cutoff_lbl = ctk.CTkLabel(
            sbar, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._cutoff_lbl.grid(row=0, column=2, padx=12)
    
        self._start_btn = ctk.CTkButton(
            sbar, text="+ Start Session", width=130,
            fg_color=C_ACCENT, hover_color="#8aabff", text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start_session)
        self._start_btn.grid(row=0, column=3, padx=(0, 8))
    
        self._end_btn = ctk.CTkButton(
            sbar, text="End Session", width=110,
            fg_color="transparent", border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._end_session)
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

        # ── DEV: manual scan input ───────────────────────────────────────────────────
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
            command=self._dev_scan
        ).grid(row=0, column=7, padx=(2, 16))
    
        # ── Info strip (hidden until session starts) ─────────────────────────────
        self._info_strip = ctk.CTkFrame(
            self, fg_color="#12141b", corner_radius=0)
        self._info_strip.grid(row=1, column=0, sticky="ew")
        self._info_strip.grid_remove()          # hidden at start
        self._build_info_strip()
    
        # ── Scan area ────────────────────────────────────────────────────────────
        self._scan_area = ScanArea(self)
        self._scan_area.grid(row=2, column=0, sticky="ew", padx=24, pady=(20, 0))
        self._scan_area.configure(height=220)
        self._scan_area.grid_propagate(False)
    
        # ── Log ──────────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="RECENT SCANS",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=C_MUTED).grid(
            row=3, column=0, sticky="nw", padx=28, pady=(14, 4))
    
        self._log_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._log_frame.grid(row=3, column=0, sticky="nsew", padx=0, pady=(36, 0))
        self._log_frame.grid_columnconfigure(0, weight=1)
    
        # ── Reader status bar ────────────────────────────────────────────────────
        rbar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        rbar.grid(row=4, column=0, sticky="ew")
        rbar.grid_propagate(False)
        rbar.grid_columnconfigure(1, weight=1)
    
        self._reader_lbl = ctk.CTkLabel(
            rbar, text="● Waiting for reader...",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._reader_lbl.grid(row=0, column=0, padx=20, pady=8)
    
        self._count_lbl = ctk.CTkLabel(
            rbar, text="Start a session",
            font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._count_lbl.grid(row=0, column=2, padx=20)

    def _dev_scan(self):
        sid = self._dev_id_var.get().strip()
        if not sid:
            return
        fake_card = CardData(
            raw="DEV_MODE",
            uid=f"DEV-{sid}",
            student_id=int(sid),
        )
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
        self._strip_stats  = None       

    def _refresh_info_strip(self):
        if not self.active_session:
            self._info_strip.grid_remove()
            return

        self._info_strip.grid()

        # ── Rebuild pills ────────────────────────────────────────────────────
        for w in self._pills_frame.winfo_children():
            w.destroy()

        now     = datetime.now().time()
        periods = self.active_session.get("periods", [])
        n_total = self.active_session.get("count", 0)
        est     = self.active_session.get("estimated_attendees")

        _PERIOD_COLORS = ["#3ecf8e", "#6c8fff", "#f0a843", "#e05c5c",
                        "#a78bfa", "#5DCAA5", "#F0997B"]

        for i, p in enumerate(periods):
            color  = _PERIOD_COLORS[i % len(_PERIOD_COLORS)]
            t_in_s = p.get("time_in_start")
            t_in_e = p.get("time_in_end")
            active = (t_in_s is not None and t_in_e is not None
                    and t_in_s <= now <= t_in_e)

            period_key = p.get("sort_order", i)
            pd_stats = self.active_session.get("period_stats", {}).get(period_key, {})
            scanned  = pd_stats.get("scanned", 0)
            late     = pd_stats.get("late", 0)
            # pd_list = self.active_session.get("period_stats", [])

            # if i < len(pd_list):
            #     pd_stats = pd_list[i]
            # else:
            #     pd_stats = {}

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
            if active:
                ctk.CTkFrame(name_row, width=5, height=5,
                            fg_color=C_SUCCESS, corner_radius=3).pack(
                    side="left", padx=(0, 5))
            ctk.CTkLabel(name_row,
                        text=p.get("name", f"Period {i+1}"),
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=C_TEXT).pack(side="left")

            # ── Time tags row ────────────────────────────────────────────────
            tags = []
            if p.get("time_in_start") and p.get("time_in_end"):
                ts = p["time_in_start"]
                te = p["time_in_end"]
                tags.append((f"In {ts.strftime('%I:%M %p').lstrip('0')}"
                            f"–{te.strftime('%I:%M %p').lstrip('0')}",
                            "#0b1220", "#38bdf8"))
            if p.get("late_enabled") and p.get("late_start"):
                ls    = p["late_start"]
                grace = p.get("grace_minutes", 0)
                tags.append((f"Late {ls.strftime('%I:%M %p').lstrip('0')}",
                            "#1f1708", "#f0a843"))
                if grace:
                    tags.append((f"+{grace}m", "#16181f", C_MUTED))
            if (p.get("timeout_enabled")
                    and p.get("timeout_start") and p.get("timeout_end")):
                ts = p["timeout_start"]
                te = p["timeout_end"]
                tags.append((f"Out {ts.strftime('%I:%M %p').lstrip('0')}"
                            f"–{te.strftime('%I:%M %p').lstrip('0')}",
                            "#100e1f", "#a78bfa"))

            if tags:
                tags_row = ctk.CTkFrame(pill, fg_color="transparent")
                tags_row.pack(anchor="w", padx=8, pady=(2, 0))
                for text, fg, tc in tags:
                    ctk.CTkLabel(tags_row, text=text,
                                font=ctk.CTkFont(size=9, weight="bold"),
                                fg_color=fg, text_color=tc,
                                corner_radius=3).pack(side="left", padx=(0, 3))

            # ── Stat row (inline, bottom of pill) ───────────────────────────
            stat_row = ctk.CTkFrame(pill, fg_color="transparent")
            stat_row.pack(anchor="w", padx=8, pady=(4, 6))

            stat_items = [("signed in", scanned, C_ACCENT)]

            if p.get("late_enabled"):
                stat_items.append(("late", late, C_WARNING))
            if p.get("timeout_enabled"):
                timed_out = pd_stats.get("timed_out", 0)
                stat_items.append(("signed out", timed_out, "#a78bfa"))

            for label, val, color_s in stat_items:
                ctk.CTkLabel(stat_row,
                            text=str(val),
                            font=ctk.CTkFont(size=11, weight="bold"),
                            text_color=color_s).pack(side="left", padx=(0, 2))
                ctk.CTkLabel(stat_row,
                            text=label,
                            font=ctk.CTkFont(size=9),
                            text_color=C_MUTED).pack(side="left", padx=(0, 8))              

        # ── Global summary pill (rightmost) ─────────────────────────────────
        summary = ctk.CTkFrame(
            self._pills_frame,
            fg_color="#1a1d27", corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        summary.pack(side="left", padx=(6, 0), anchor="n")

        count_text = f"{n_total} / {est}" if est else str(n_total)
        ctk.CTkLabel(summary,
                    text=count_text,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=C_TEXT).pack(padx=12, pady=(8, 0))
        ctk.CTkLabel(summary,
                    text="total scans",
                    font=ctk.CTkFont(size=9),
                    text_color=C_MUTED).pack(padx=12, pady=(0, 4))

        if est and est > 0:
            pct   = min(round(n_total / est * 100), 100)
            fill_w = max(2, round(80 * n_total / est))

            ctk.CTkLabel(summary,
                        text=f"{pct}%",
                        font=ctk.CTkFont(size=10),
                        text_color=C_ACCENT).pack(padx=12, pady=(0, 2))

            bar_bg = ctk.CTkFrame(summary, fg_color=C_BORDER,
                                corner_radius=2, height=4, width=80)
            bar_bg.pack(padx=12, pady=(0, 8))
            bar_bg.pack_propagate(False)
            ctk.CTkFrame(bar_bg, fg_color=C_ACCENT,
                        corner_radius=2, height=4, width=fill_w).place(x=0, y=0)
        
    def _tick(self):
        if not self.winfo_exists():
            return

        if not self.active_session:
            return
        
        self._refresh_info_strip()
        self._safe_after(30_000, self._tick)
    # ------------------------------------------------------------------
    # RFID
    # ------------------------------------------------------------------

    def _start_rfid(self):
        def safe_after(fn, *args):
            """Only dispatch to UI if the widget still exists."""
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
        # Stop RFID listener
        if self._listener:
            self._listener.stop()

        # Cancel ALL scheduled after() calls
        for aid in getattr(self, "_after_ids", []):
            try:
                self.after_cancel(aid)
            except Exception:
                pass

        self._after_ids.clear()

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def _start_session(self):
        dlg = NewSessionDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        data       = dlg.result
        session_id = None
        periods    = []

        db = SessionLocal()
        try:
            ev = EventSession(
                name=data["name"],
                date=data["date"],
                estimated_attendees=data.get("estimated_attendees"))
            db.add(ev)
            db.flush()  # get ev.id before commit

            for p in data["periods"]:
                period = SessionPeriod(
                    session_id      = ev.id,
                    name            = p["name"],
                    time_in_start   = p["time_in_start"],
                    time_in_end     = p["time_in_end"],
                    grace_minutes   = p["grace_minutes"],
                    late_enabled    = p["late_enabled"],
                    late_start      = p["late_start"],
                    timeout_enabled = p["timeout_enabled"],
                    timeout_start   = p["timeout_start"],
                    timeout_end     = p["timeout_end"],
                    sort_order      = p["sort_order"],
                )
                db.add(period)
                periods.append(period)

            db.commit()
            db.refresh(ev)
            for p in periods:
                db.refresh(p)
            session_id = ev.id
            # Detach objects so they can be used outside the session
            periods_data = [
                {
                    "id":              p.id,
                    "name":            p.name,
                    "sort_order":      p.sort_order,
                    "time_in_start":   p.time_in_start,
                    "time_in_end":     p.time_in_end,
                    "grace_minutes":   p.grace_minutes,
                    "late_enabled":    p.late_enabled,
                    "late_start":      p.late_start,
                    "timeout_enabled": p.timeout_enabled,
                    "timeout_start":   p.timeout_start,
                    "timeout_end":     p.timeout_end,
                }
                for p in periods
            ]
        finally:
            db.close()

        self.active_session = {
            "id":                  session_id,
            "name":                data["name"],
            "periods":             periods_data,
            "count":               0,
            "estimated_attendees": data.get("estimated_attendees"),
            "breakdown":           {"present": 0, "late": 0},
            "period_stats": {}
        }
 
        self._dot.configure(text_color=C_SUCCESS)
        self._session_lbl.configure(text=data["name"], text_color=C_ACCENT)
        self._cutoff_lbl.configure(text="")
        self._start_btn.grid_remove()
        self._end_btn.grid()
        self._refresh_info_strip()
        self._update_count()
        self._safe_after(30_000, self._tick)

    def _end_session(self):
        if not messagebox.askyesno(
                "End Session",
                f"End session '{self.active_session['name']}'?"):
            return
        self.active_session = None
        self._dot.configure(text_color=C_MUTED)
        self._session_lbl.configure(text="No active session", text_color=C_MUTED)
        self._cutoff_lbl.configure(text="")
        self._end_btn.grid_remove()
        self._start_btn.grid()
        self._count_lbl.configure(text="Start a Session")
        self._refresh_info_strip()   # hides the strip
        self._set_mode("in")

    def _set_mode(self, mode: str):
        """Switch between SCAN IN and SCAN OUT modes."""
        self._scan_mode = mode
        if mode == "in":
            self._in_btn.configure(
                fg_color=C_SUCCESS, text_color="#ffffff")
            self._out_btn.configure(
                fg_color="transparent", text_color=C_MUTED)
        else:
            self._in_btn.configure(
                fg_color="transparent", text_color=C_MUTED)
            self._out_btn.configure(
                fg_color="#7c3aed", text_color="#ffffff")
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
        """Return active period for scan-in or scan-out based on current time."""
        now = datetime.now().time()
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
                Student.student_id == card.student_id,
            ).first()

            if not student:
                self._scan_area.show_error(
                    f"Student ID {card.student_id} not found")
                self._add_log("Unknown card", card.student_id, "error",
                              datetime.now().strftime("%I:%M:%S %p"))
                return

            name = f"{student.first_name} {student.last_name}"
            now  = datetime.now()

            # Detect active period
            period = self._get_active_period(self._scan_mode)
            if period is None:
                if self._scan_mode == "out":
                    self._scan_area.show_error(
                        "No active scan-out window right now")
                else:
                    self._scan_area.show_error(
                        "No active period right now — check session windows")
                return

            # Find existing attendance for this student + period
            existing = db.query(Attendance).filter(
                Attendance.student_id == card.student_id,
                Attendance.session_id == self.active_session["id"],
                Attendance.period_id  == period["id"],
            ).first()

            # ── SCAN OUT mode ────────────────────────────────────────
            if self._scan_mode == "out":
                if not period["timeout_enabled"]:
                    self._scan_area.show_error(
                        f"Time-out tracking is off for '{period['name']}'")
                    return

                # Check if current time is within the timeout window
                if period["timeout_start"] and period["timeout_end"]:
                    now_time = now.time()
                    if not (period["timeout_start"] <= now_time <= period["timeout_end"]):
                        ts = period["timeout_start"].strftime("%I:%M %p").lstrip("0")
                        te = period["timeout_end"].strftime("%I:%M %p").lstrip("0")
                        self._scan_area.show_error(
                            f"Scan-out window is {ts} – {te}")
                        return

                if not existing:
                    self._scan_area.show_not_checked_in(name)
                    return
                if existing.time_out:
                    self._scan_area.show_already_out(
                        name, existing.time_out.strftime("%I:%M %p"))
                    return

                existing.time_out = now
                db.commit()
                ps = self.active_session.setdefault("period_stats", {})
                pid = period["sort_order"]

                if pid not in ps:
                    ps[pid] = {"scanned": 0, "late": 0, "timed_out": 0}

                ps[pid]["timed_out"] += 1
                time_in_str = (existing.time_in.strftime("%I:%M %p")
                            if existing.time_in else "—")
                self._scan_area.show_timeout(name, student.student_id, time_in_str)
                self._add_log(name, student.student_id, "timeout",
                            now.strftime("%I:%M:%S %p"))
                self.active_session["count"] += 1
                self._update_count()
                return

            # ── SCAN IN mode ─────────────────────────────────────────
            if existing:
                self._scan_area.show_warning(
                    f"{student.first_name} already marked for "
                    f"'{period['name']}' at "
                    f"{existing.time_in.strftime('%I:%M %p')}")
                return
            
            # Determine status using period's effective cutoff
            from datetime import timedelta
            if period["late_enabled"] and period["late_start"]:
                cutoff_dt = now.replace(
                    hour=period["late_start"].hour,
                    minute=period["late_start"].minute, second=0)
                cutoff_dt += timedelta(minutes=period["grace_minutes"])
                status = "late" if now > cutoff_dt else "present"
            else:
                status = "present"

            # ── Update period stats ─────────────────────────────
            ps = self.active_session.setdefault("period_stats", {})
            pid = period["sort_order"]   # or use index if consistent

            if pid not in ps:
                ps[pid] = {"scanned": 0, "late": 0, "timed_out": 0}

            ps[pid]["scanned"] += 1
            if status == "late":
                ps[pid]["late"] += 1

            db.add(Attendance(
                student_id=student.student_id,
                session_id=self.active_session["id"],
                period_id=period["id"],
                status=status,
                time_in=now))
            db.commit()

            self._increment_breakdown(status)

            # Show period name in the scan feedback
            self._scan_area.show_success(
                name, student.student_id,
                f"{student.program.code if student.program else '—'}  ·  {period['name']}",
                status)
            self._add_log(name, student.student_id, status,
                          now.strftime("%I:%M:%S %p"))
            self.active_session["count"] += 1
            self._update_count()
        finally:
            db.close()

    def _on_error(self, _):
        self._scan_area.show_error("Card read error")

    def _on_connected(self):
        self._reader_lbl.configure(
            text="● ACR1252U connected", text_color=C_SUCCESS)

    def _on_disconnected(self):
        self._reader_lbl.configure(
            text="● Reader disconnected", text_color=C_ERROR)

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
            lambda: self._log_frame._parent_canvas.yview_moveto(1.0)
        )

    def _update_count(self):
        n   = self.active_session["count"] if self.active_session else 0
        est = self.active_session.get("estimated_attendees") if self.active_session else None
        # if est:
        #     pct = min(round(n / est * 100), 100)
        #     self._count_lbl.configure(text=f"{n} / {est} scans  ({pct}%)")
        # else:
        self._count_lbl.configure(text=f"Total scans this session: {n}")
        self._refresh_info_strip()
