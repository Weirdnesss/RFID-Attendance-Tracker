import customtkinter as ctk
from ui.theme import (
    C_BORDER, C_ERROR, C_ERROR_BG, C_MUTED,
    C_SUCCESS, C_SUCCESS_BG, C_SURFACE, C_TEXT,
    C_WARNING, C_WARNING_BG,
)
from datetime import datetime

class ScanArea(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C_SURFACE,
                         corner_radius=16, border_width=1,
                         border_color=C_BORDER)
        self._icon = ctk.CTkLabel(self, text="⬡",
                                   font=ctk.CTkFont(size=48),
                                   text_color=C_BORDER)
        self._icon.pack(pady=(28, 4))

        self._status = ctk.CTkLabel(self, text="READY TO SCAN",
                                     font=ctk.CTkFont(size=26, weight="bold"),
                                     text_color=C_MUTED)
        self._status.pack()

        self._detail = ctk.CTkLabel(self, text="Tap a card on the reader",
                                     font=ctk.CTkFont(size=14),
                                     text_color=C_MUTED)
        self._detail.pack(pady=(4, 0))

        self._name = ctk.CTkLabel(self, text="",
                                   font=ctk.CTkFont(size=20, weight="bold"),
                                   text_color=C_TEXT)
        self._name.pack(pady=(6, 0))

        self._meta = ctk.CTkLabel(self, text="",
                                   font=ctk.CTkFont(size=12),
                                   text_color=C_MUTED)
        self._meta.pack(pady=(2, 24))
        self._reset_job = None

    def _schedule_reset(self, ms):
        if not self.winfo_exists():
            return

        if self._reset_job:
            try:
                self.after_cancel(self._reset_job)
            except Exception:
                pass

        self._reset_job = self.after(ms, self._reset)

    def show_success(self, name, student_id, program, status="present"):
        color = C_WARNING if status == "late" else C_SUCCESS
        bg    = C_WARNING_BG if status == "late" else C_SUCCESS_BG
        self.configure(fg_color=bg, border_color=color)
        self._icon.configure(
            text="◈" if status == "late" else "✦", text_color=color)
        self._status.configure(
            text="LATE" if status == "late" else "PRESENT", text_color=color)
        self._detail.configure(
            text=f"ID: {student_id}  ·  {datetime.now().strftime('%I:%M:%S %p')}",
            text_color=C_MUTED)
        self._name.configure(text=name, text_color=C_TEXT)
        self._meta.configure(text=program, text_color=C_MUTED)
        self._schedule_reset(3000)

    def show_warning(self, message):
        self.configure(fg_color=C_WARNING_BG, border_color=C_WARNING)
        self._icon.configure(text="◇", text_color=C_WARNING)
        self._status.configure(text="ALREADY MARKED", text_color=C_WARNING)
        self._detail.configure(text=message, text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
        self._schedule_reset(2500)

    def show_error(self, message):
        self.configure(fg_color=C_ERROR_BG, border_color=C_ERROR)
        self._icon.configure(text="✕", text_color=C_ERROR)
        self._status.configure(text="NOT FOUND", text_color=C_ERROR)
        self._detail.configure(text=message, text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
        self._schedule_reset(2500)

    def show_no_session(self):
        self.configure(fg_color=C_ERROR_BG, border_color=C_ERROR)
        self._icon.configure(text="○", text_color=C_ERROR)
        self._status.configure(text="NO SESSION", text_color=C_ERROR)
        self._detail.configure(
            text="Start a session before scanning", text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
        self._schedule_reset(2500)

    def show_timeout(self, name, student_id, time_in_str):
        """Show successful time-out scan."""
        self.configure(fg_color="#100e1f", border_color="#a78bfa")
        self._icon.configure(text="◁", text_color="#a78bfa")
        self._status.configure(text="SIGNED OUT", text_color="#a78bfa")
        self._detail.configure(
            text=f"ID: {student_id}  ·  {datetime.now().strftime('%I:%M:%S %p')}",
            text_color=C_MUTED)
        self._name.configure(text=name, text_color=C_TEXT)
        self._meta.configure(text=f"Checked in at {time_in_str}", text_color=C_MUTED)
        self._schedule_reset(3000)

    def show_not_checked_in(self, name):
        """Student tapped in SCAN OUT mode but has no time_in."""
        self.configure(fg_color=C_WARNING_BG, border_color=C_WARNING)
        self._icon.configure(text="◇", text_color=C_WARNING)
        self._status.configure(text="NOT CHECKED IN", text_color=C_WARNING)
        self._detail.configure(
            text=f"{name} has no check-in record this session",
            text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
        self._schedule_reset(2500)

    def show_already_out(self, name, time_out_str):
        """Student already has a time_out recorded."""
        self.configure(fg_color=C_WARNING_BG, border_color=C_WARNING)
        self._icon.configure(text="◇", text_color=C_WARNING)
        self._status.configure(text="ALREADY LEFT", text_color=C_WARNING)
        self._detail.configure(
            text=f"{name} signed out at {time_out_str}",
            text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
        self._schedule_reset(2500)

    def set_mode(self, mode: str):
        """Update idle state to reflect current mode."""
        if mode == "out":
            self._icon.configure(text_color="#a78bfa")
            self._detail.configure(text="Tap a card to sign out")
        else:
            self._icon.configure(text_color=C_BORDER)
            self._detail.configure(text="Tap a card on the reader")

    def _reset(self):
        self._reset_job = None
        self.configure(fg_color=C_SURFACE, border_color=C_BORDER)
        self._icon.configure(text="⬡", text_color=C_BORDER)
        self._status.configure(text="READY TO SCAN", text_color=C_MUTED)
        self._detail.configure(
            text="Tap a card on the reader", text_color=C_MUTED)
        self._name.configure(text="")
        self._meta.configure(text="")
