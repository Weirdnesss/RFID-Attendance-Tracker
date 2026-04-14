import customtkinter as ctk
from ui.theme import (C_ACCENT, C_MUTED)

class NavButton(ctk.CTkButton):
    def __init__(self, parent, text, command, active=False):
        super().__init__(
            parent,
            text=text,
            anchor="w",
            fg_color="#1e2130" if active else "transparent",
            hover_color="#1e2130",
            text_color=C_ACCENT if active else C_MUTED,
            font=ctk.CTkFont(size=13),
            corner_radius=0,
            height=44,
            command=command,
        )
        self._active = active

    def set_active(self, active: bool):
        self._active = active
        self.configure(
            fg_color="#1e2130" if active else "transparent",
            text_color=C_ACCENT if active else C_MUTED,
        )