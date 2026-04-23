"""
edit_session.py
---------------
Dialog for editing an active session's period settings.
"""

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

from database import SessionLocal, SessionPeriod
from ui.components.period_row import PeriodRow
from ui.theme import C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED, C_ACCENT, C_ERROR

def _fmt_time(t) -> str:
    if isinstance(t, str):
        return t
    return t.strftime("%I:%M %p").lstrip("0")

class EditSessionDialog(ctk.CTkToplevel):
    def __init__(self, parent, session: dict):
        super().__init__(parent)
        self.title(f"Edit Session — {session['name']}")
        self.geometry("660x600")
        self.minsize(580, 400)
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self._session    = session
        self._period_rows: list[PeriodRow] = []
        self.result      = None

        self._build_ui()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="Edit Session",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", padx=24, pady=(14, 2))
        ctk.CTkLabel(
            hdr, text=f"Editing periods for: {self._session['name']}",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(anchor="w", padx=24)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # Period label
        pl = ctk.CTkFrame(self, fg_color="transparent")
        pl.pack(fill="x", padx=24, pady=(12, 4))
        ctk.CTkLabel(
            pl, text="PERIODS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C_MUTED,
        ).pack(side="left")
        ctk.CTkLabel(
            pl, text="Adding or removing periods is not available on active sessions.",
            font=ctk.CTkFont(size=10),
            text_color=C_MUTED,
        ).pack(side="left", padx=(12, 0))

        # Scrollable period list
        self._period_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._period_scroll.pack(fill="both", expand=True, padx=24)
        self._period_scroll.grid_columnconfigure(0, weight=1)

        self._load_periods()

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x")

        # Footer
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
            foot, text="Save Changes",
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._accept,
        ).pack(side="right")

    def _load_periods(self):
        db = SessionLocal()
        try:
            periods = (
                db.query(SessionPeriod)
                .filter(SessionPeriod.session_id == self._session["id"])
                .order_by(SessionPeriod.sort_order)
                .all()
            )
            # Build defaults dicts while session is open
            period_data = []
            for p in periods:
                period_data.append({
                    "id":              p.id,
                    "name":            p.name,
                    "time_in_start":   p.time_in_start.strftime("%H:%M") if p.time_in_start else "07:00",
                    "time_in_end":     p.time_in_end.strftime("%H:%M")   if p.time_in_end   else "09:00",
                    "late_enabled":    p.late_enabled,
                    "late_start":      p.late_start.strftime("%H:%M")    if p.late_start    else "07:30",
                    "grace_minutes":   str(p.grace_minutes),
                    "timeout_enabled": p.timeout_enabled,
                    "timeout_start":   p.timeout_start.strftime("%H:%M") if p.timeout_start else "11:00",
                    "timeout_end":     p.timeout_end.strftime("%H:%M")   if p.timeout_end   else "12:00",
                })
        finally:
            db.close()

        for i, data in enumerate(period_data):
            row = PeriodRow(
                self._period_scroll,
                index=i,
                on_delete=self._block_delete,
                defaults=data,
            )
            row.pack(fill="x", pady=(0, 8))
            row._period_id = data["id"]  # stash DB id for saving
            self._period_rows.append(row)

    def _block_delete(self, row):
        messagebox.showwarning(
            "Not allowed",
            "Periods cannot be removed from an active session.",
        )

    def _accept(self):
        # Validate first
        period_data = []
        for row in self._period_rows:
            try:
                data = row.get_data()
                data["id"] = row._period_id
                period_data.append(data)
            except ValueError as e:
                messagebox.showerror("Invalid time", str(e))
                return

        # Confirm
        dlg = ConfirmEditDialog(self, self._session["name"], period_data)
        self.wait_window(dlg)
        if not dlg.result:
            return

        # Save to DB
        db = SessionLocal()
        try:
            for data in period_data:
                db.query(SessionPeriod).filter(
                    SessionPeriod.id == data["id"]
                ).update({
                    "name":            data["name"],
                    "time_in_start":   data["time_in_start"],
                    "time_in_end":     data["time_in_end"],
                    "grace_minutes":   data["grace_minutes"],
                    "late_enabled":    data["late_enabled"],
                    "late_start":      data["late_start"],
                    "timeout_enabled": data["timeout_enabled"],
                    "timeout_start":   data["timeout_start"],
                    "timeout_end":     data["timeout_end"],
                })
            db.commit()
        except Exception as e:
            db.rollback()
            messagebox.showerror("Save failed", str(e))
            return
        finally:
            db.close()

        self.result = True
        self.destroy()

class ConfirmEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, session_name: str, periods: list[dict]):
        super().__init__(parent)
        self.title("Confirm Changes")
        self.geometry("560x480")
        self.configure(fg_color=C_SURFACE)
        self.grab_set()

        self.result   = False
        self._name    = session_name
        self._periods = periods

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Confirm Changes",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", padx=20, pady=(16, 2))
        ctk.CTkLabel(
            self, text=f"Saving updated periods for: {self._name}",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(fill="x", padx=20, pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20)

        for i, p in enumerate(self._periods, 1):
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
            foot, text="Save Changes",
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
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
                fg_color=bg, text_color=fg,
                corner_radius=6, padx=8, pady=2,
            ).pack(side="left", padx=(0, 6))

    def _confirm(self):
        self.result = True
        self.destroy()