"""
admin_screen.py
---------------
Admin screen for managing sessions.
Allows creating new sessions and ending active ones.
"""

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from database import SessionLocal, Session as EventSession
from ui.dialogs.edit_session import EditSessionDialog
from ui.theme import (
    C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
    C_ACCENT, C_SUCCESS, C_ERROR
)


class AdminScreen(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._session_rows: dict[int, ctk.CTkFrame] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ──────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=60)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr, text="Admin",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(10, 0))
        ctk.CTkLabel(
            hdr, text="Manage active sessions",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=24)

        ctk.CTkButton(
            hdr, text="+ Create New Session", width=160,
            fg_color=C_ACCENT, hover_color="#8aabff", text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._create_session,
        ).grid(row=0, column=1, rowspan=2, padx=24, pady=10)

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).grid(
            row=0, column=0, sticky="sew")

        # ── Session list ─────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="ACTIVE SESSIONS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C_MUTED,
        ).grid(row=1, column=0, sticky="nw", padx=24, pady=(16, 4))

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0)
        self._list_frame.grid(
            row=1, column=0, sticky="nsew", padx=16, pady=(40, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Session rows
    # ------------------------------------------------------------------

    def _load_sessions(self):
        # Clear existing rows
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._session_rows.clear()

        db = SessionLocal()
        try:
            sessions = (
                db.query(EventSession)
                .filter(EventSession.is_active == 1)
                .order_by(EventSession.date.desc(), EventSession.created_at.desc())
                .all()
            )
            # Eagerly load what we need
            data = [
                {
                    "id":                  s.id,
                    "name":                s.name,
                    "date":                s.date,
                    "created_at":          s.created_at,
                    "estimated_attendees": s.estimated_attendees,
                    "period_count":        len(s.periods),
                }
                for s in sessions
            ]
        finally:
            db.close()

        if not data:
            ctk.CTkLabel(
                self._list_frame,
                text="No active sessions.",
                font=ctk.CTkFont(size=13),
                text_color=C_MUTED,
            ).pack(pady=40)
            return

        for s in data:
            self._build_row(s)

    def _build_row(self, s: dict):
        row = ctk.CTkFrame(
            self._list_frame,
            fg_color=C_SURFACE, corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)

        # Left — session info
        ctk.CTkLabel(
            row, text=s["name"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 2))

        period_count = s["period_count"]
        created      = s["created_at"].strftime("%I:%M %p") if s["created_at"] else "—"
        meta = (f"{s['date']}  ·  "
                f"Started {created}  ·  "
                f"{s['estimated_attendees'] or '—'} expected  ·  "
                f"{period_count} period{'s' if period_count != 1 else ''}")
        ctk.CTkLabel(
            row, text=meta,
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=1, rowspan=2, padx=16, pady=10)

        ctk.CTkButton(
            btn_frame, text="Edit", width=80,
            fg_color="transparent",
            border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, hover_color=C_SURFACE,
            font=ctk.CTkFont(size=12),
            command=lambda sid=s["id"], sname=s["name"]: self._edit_session(sid, sname),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="End Session", width=110,
            fg_color="transparent",
            border_color=C_ERROR, border_width=1,
            text_color=C_ERROR, hover_color="#2a1a1a",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda sid=s["id"], sname=s["name"]: self._end_session(sid, sname),
        ).pack(side="left")

        self._session_rows[s["id"]] = row

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _create_session(self):
        from ui.dialogs.new_session import NewSessionDialog
        dlg = NewSessionDialog(self)
        self.wait_window(dlg)
        if dlg.result and dlg.result.get("started"):
            self._load_sessions()

    def _edit_session(self, session_id: int, session_name: str):
        dlg = EditSessionDialog(self, {"id": session_id, "name": session_name})
        self.wait_window(dlg)
        if dlg.result:
            self._load_sessions()

    def _end_session(self, session_id: int, session_name: str):
        if not messagebox.askyesno(
                "End Session",
                f"End session '{session_name}'?\n\nThis cannot be undone."):
            return

        db = SessionLocal()
        try:
            db.query(EventSession).filter(
                EventSession.id == session_id
            ).update({
                "is_active":  0,
                "active_flag": None,
                "ended_at":   datetime.now(),
            })
            db.commit()
        finally:
            db.close()

        # Remove the row without reloading everything
        if session_id in self._session_rows:
            self._session_rows.pop(session_id).destroy()

        # Show empty state if no sessions left
        if not self._session_rows:
            ctk.CTkLabel(
                self._list_frame,
                text="No active sessions.",
                font=ctk.CTkFont(size=13),
                text_color=C_MUTED,
            ).pack(pady=40)

    # ------------------------------------------------------------------
    # Refresh (called by main.py on navigate)
    # ------------------------------------------------------------------

    def refresh(self):
        self._load_sessions()