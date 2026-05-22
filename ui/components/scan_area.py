import customtkinter as ctk
from ui.theme import (
    C_BORDER, C_ERROR, C_ERROR_BG, C_MUTED,
    C_SUCCESS, C_SUCCESS_BG, C_SURFACE, C_TEXT,
    C_WARNING, C_WARNING_BG,
)
from datetime import datetime

_PURPLE    = "#a78bfa"
_PURPLE_BG = "#100e1f"


class ScanArea(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C_SURFACE,
                         corner_radius=16, border_width=2,
                         border_color=C_BORDER)
        self._reset_job = None
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0)

        self._icon = ctk.CTkLabel(
            inner, text="⬡",
            font=ctk.CTkFont(size=64),
            text_color=C_BORDER)
        self._icon.pack(pady=(0, 8))

        self._status = ctk.CTkLabel(
            inner, text="READY TO SCAN",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=C_MUTED)
        self._status.pack()

        self._name = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=C_TEXT)
        self._name.pack(pady=(10, 0))

        self._detail = ctk.CTkLabel(
            inner, text="Tap a card on the reader",
            font=ctk.CTkFont(size=14),
            text_color=C_MUTED)
        self._detail.pack(pady=(6, 0))

        self._meta = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED)
        self._meta.pack(pady=(4, 0))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schedule_reset(self, ms):
        if not self.winfo_exists():
            return
        if self._reset_job:
            try:
                self.after_cancel(self._reset_job)
            except Exception:
                pass
        self._reset_job = self.after(ms, self._reset)

    def _apply(self, bg, border, icon_text, icon_color,
               status_text, status_color,
               name="", detail="", meta="",
               reset_ms=3000):
        self.configure(fg_color=bg, border_color=border)
        self._icon.configure(text=icon_text, text_color=icon_color)
        self._status.configure(text=status_text, text_color=status_color)
        self._name.configure(text=name)
        self._detail.configure(text=detail, text_color=C_MUTED)
        self._meta.configure(text=meta, text_color=C_MUTED)
        self._schedule_reset(reset_ms)

    def _ts(self):
        return datetime.now().strftime("%I:%M:%S %p")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_success(self, name, entity_id, tag, status="present"):
        if status == "late":
            self._apply(
                bg=C_WARNING_BG, border=C_WARNING,
                icon_text="◈", icon_color=C_WARNING,
                status_text="LATE", status_color=C_WARNING,
                name=name,
                detail=f"ID: {entity_id}  ·  {self._ts()}",
                meta=tag,
                reset_ms=3000)
        else:
            self._apply(
                bg=C_SUCCESS_BG, border=C_SUCCESS,
                icon_text="✦", icon_color=C_SUCCESS,
                status_text="PRESENT", status_color=C_SUCCESS,
                name=name,
                detail=f"ID: {entity_id}  ·  {self._ts()}",
                meta=tag,
                reset_ms=3000)

    def show_timeout(self, name, entity_id, time_in_str):
        self._apply(
            bg=_PURPLE_BG, border=_PURPLE,
            icon_text="◁", icon_color=_PURPLE,
            status_text="SIGNED OUT", status_color=_PURPLE,
            name=name,
            detail=f"ID: {entity_id}  ·  {self._ts()}",
            meta=f"Checked in at {time_in_str}",
            reset_ms=3000)

    def show_warning(self, message):
        self._apply(
            bg=C_WARNING_BG, border=C_WARNING,
            icon_text="◇", icon_color=C_WARNING,
            status_text="ALREADY MARKED", status_color=C_WARNING,
            detail=message,
            reset_ms=2500)

    def show_not_checked_in(self, name):
        self._apply(
            bg=C_WARNING_BG, border=C_WARNING,
            icon_text="◇", icon_color=C_WARNING,
            status_text="NOT CHECKED IN", status_color=C_WARNING,
            detail=f"{name} has no check-in record this session",
            reset_ms=2500)

    def show_already_out(self, name, time_out_str):
        self._apply(
            bg=C_WARNING_BG, border=C_WARNING,
            icon_text="◇", icon_color=C_WARNING,
            status_text="ALREADY LEFT", status_color=C_WARNING,
            detail=f"{name} signed out at {time_out_str}",
            reset_ms=2500)

    def show_no_session(self):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="○", icon_color=C_ERROR,
            status_text="NO SESSION", status_color=C_ERROR,
            detail="Start a session before scanning",
            reset_ms=2500)

    def show_unknown_card(self, entity_id):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="UNKNOWN CARD", status_color=C_ERROR,
            detail=f"ID {entity_id} is not registered in the system",
            reset_ms=2500)

    def show_no_period(self):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="NO ACTIVE PERIOD", status_color=C_ERROR,
            detail="No sign-in window is open right now",
            reset_ms=2500)

    def show_no_timeout_period(self):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="NO SCAN-OUT WINDOW", status_color=C_ERROR,
            detail="No sign-out window is open right now",
            reset_ms=2500)

    def show_timeout_disabled(self, period_name):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="SCAN OUT DISABLED", status_color=C_ERROR,
            detail=f"Time-out tracking is off for '{period_name}'",
            reset_ms=2500)

    def show_wrong_type(self, expected: str):
        # expected: "students" or "staff"
        who   = "students" if expected == "students" else "staff"
        other = "staff" if expected == "students" else "student"
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="ACCESS DENIED", status_color=C_ERROR,
            detail=f"This session is for {who} only — {other} cards are not accepted",
            reset_ms=2500)

    def show_scan_window_closed(self, start, end):
        self._apply(
            bg=C_ERROR_BG, border=C_ERROR,
            icon_text="✕", icon_color=C_ERROR,
            status_text="OUTSIDE WINDOW", status_color=C_ERROR,
            detail=f"Scan window is {start} – {end}",
            reset_ms=2500)

    def set_mode(self, mode: str):
        if mode == "out":
            self._icon.configure(text_color=_PURPLE)
            self._detail.configure(text="Tap a card to sign out")
        else:
            self._icon.configure(text_color=C_BORDER)
            self._detail.configure(text="Tap a card on the reader")

    def _reset(self):
        self._reset_job = None
        self.configure(fg_color=C_SURFACE, border_color=C_BORDER)
        self._icon.configure(text="⬡", text_color=C_BORDER)
        self._status.configure(text="READY TO SCAN", text_color=C_MUTED)
        self._name.configure(text="")
        self._detail.configure(
            text="Tap a card on the reader", text_color=C_MUTED)
        self._meta.configure(text="")