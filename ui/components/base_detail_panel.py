import customtkinter as ctk
from ui.theme import C_BG, C_SURFACE, C_MUTED, C_TEXT, C_SUCCESS, C_WARNING
from ui.components.stats_pills import StatsPills
from ui.components.history_table import HistoryTable


class BaseDetailPanel(ctk.CTkFrame):
    """
    Base class for entity detail panels.
    Subclasses must implement:
        _empty_text() -> str          — placeholder when nothing selected
        _build_info_row(info)         — populate the info strip
        _stats_pills() -> list        — list of (key, label, color) tuples
        _fetch_fn()                   — callable for HistoryTable
        _page_size() -> int           — records per page
        _load_header(data)            — update name/id labels from data
        _load_info(data)              — update info row labels from data
        _load_stats(data)             — call self._stats.set() for each pill
        _get_entity_id(data)          — return the ID to pass to HistoryTable
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        self._name_lbl = ctk.CTkLabel(
            hdr, text=self._empty_text(),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_MUTED)
        self._name_lbl.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        self._id_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=12), text_color=C_MUTED)
        self._id_lbl.grid(row=0, column=1, padx=(0, 20))

        # ── Info row ──────────────────────────────────────────────────
        info = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        info.grid(row=1, column=0, sticky="ew")
        info.grid_propagate(False)
        self._build_info_row(info)

        # ── Stats pills ───────────────────────────────────────────────
        self._stats = StatsPills(self, pills=self._stats_pills())
        self._stats.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))

        # ── History table ─────────────────────────────────────────────
        self._history = HistoryTable(
            self, fetch_fn=self._fetch_fn(), page_size=self._page_size())
        self._history.grid(row=3, column=0, sticky="nsew", padx=16, pady=(12, 0))

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def _empty_text(self) -> str:
        raise NotImplementedError

    def _build_info_row(self, info: ctk.CTkFrame):
        raise NotImplementedError

    def _stats_pills(self) -> list:
        raise NotImplementedError

    def _fetch_fn(self):
        raise NotImplementedError

    def _page_size(self) -> int:
        raise NotImplementedError

    def _load_header(self, data: dict):
        raise NotImplementedError

    def _load_info(self, data: dict):
        raise NotImplementedError

    def _load_stats(self, data: dict):
        raise NotImplementedError

    def _get_entity_id(self, data: dict):
        raise NotImplementedError

    def _clear_info(self):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared logic
    # ------------------------------------------------------------------

    def load(self, data: dict):
        self._load_header(data)
        self._load_info(data)
        self._load_stats(data)
        self._history.load(self._get_entity_id(data))

    def clear(self):
        self._name_lbl.configure(text=self._empty_text(), text_color=C_MUTED)
        self._id_lbl.configure(text="")
        self._clear_info()
        self._stats.reset()
        self._history.clear()