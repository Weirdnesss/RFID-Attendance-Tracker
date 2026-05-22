import customtkinter as ctk
from ui.theme import C_SURFACE, C_BORDER, C_BG, C_MUTED, C_TEXT


class PaginationBar(ctk.CTkFrame):
    def __init__(self, parent, on_prev, on_next, height=38, **kwargs):
        super().__init__(parent, fg_color=C_SURFACE,
                         corner_radius=0, height=height, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            self, text="← Prev", width=70, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            command=on_prev)
        self._prev_btn.grid(row=0, column=0, padx=(8, 4), pady=5)

        self._page_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._page_lbl.grid(row=0, column=1)

        self._next_btn = ctk.CTkButton(
            self, text="Next →", width=70, height=28,
            fg_color="transparent", border_color=C_BORDER,
            border_width=1, text_color=C_MUTED,
            hover_color=C_BG, corner_radius=6,
            command=on_next)
        self._next_btn.grid(row=0, column=2, padx=(4, 8), pady=5)

    def update(self, page: int, total_pages: int, total_count: int = None):
        self._page_lbl.configure(text=f"{page + 1} / {total_pages}")
        self._prev_btn.configure(
            state="normal" if page > 0 else "disabled",
            text_color=C_TEXT if page > 0 else C_MUTED)
        self._next_btn.configure(
            state="normal" if page < total_pages - 1 else "disabled",
            text_color=C_TEXT if page < total_pages - 1 else C_MUTED)