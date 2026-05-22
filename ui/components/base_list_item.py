import customtkinter as ctk
from ui.theme import C_SURFACE, C_BORDER, C_ACCENT, C_TEXT, C_MUTED


class BaseListItem(ctk.CTkFrame):
    """
    Base class for selectable list items.
    Subclasses must implement:
        _build_top(top: CTkFrame)   — left side of the top row
        _build_bottom(bot: CTkFrame) — contents of the bottom row
        _update_contents(data: dict) — update labels when data changes
        _get_id(data: dict) -> any  — return the unique ID from data
    """

    def __init__(self, parent, data: dict, on_select, selected=False, **kwargs):
        super().__init__(
            parent,
            fg_color="#1e2130" if selected else C_SURFACE,
            corner_radius=10, border_width=1,
            border_color=C_ACCENT if selected else C_BORDER,
            **kwargs)

        self._data      = data
        self._on_select = on_select
        self._selected  = selected

        self.bind("<Button-1>", self._clicked)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))

        self._name_lbl = ctk.CTkLabel(
            top, text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_ACCENT if selected else C_TEXT,
            anchor="w")
        self._name_lbl.pack(side="left")

        self._build_top(top)

        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=14, pady=(0, 10))

        self._build_bottom(bot)

        for f in [top, bot]:
            f.bind("<Button-1>", self._clicked)
            for child in f.winfo_children():
                child.bind("<Button-1>", self._clicked)

        self._update_contents(data)

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def _build_top(self, top: ctk.CTkFrame):
        """Add extra widgets to the top row (after the name label)."""
        pass

    def _build_bottom(self, bot: ctk.CTkFrame):
        """Build the bottom row widgets."""
        raise NotImplementedError

    def _update_contents(self, data: dict):
        """Update all labels when data changes."""
        raise NotImplementedError

    def _get_id(self, data: dict):
        """Return the unique identifier from data."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared logic
    # ------------------------------------------------------------------

    def _clicked(self, _event=None):
        self._on_select(self._data)

    def update_data(self, data: dict, selected: bool = False):
        self._data     = data
        self._selected = selected
        self._name_lbl.configure(
            text_color=C_ACCENT if selected else C_TEXT)
        self.configure(
            fg_color="#1e2130" if selected else C_SURFACE,
            border_color=C_ACCENT if selected else C_BORDER)
        self._update_contents(data)

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