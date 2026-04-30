"""
login_screen.py
---------------
Login frame shown on app startup inside the main window.
Two paths:
    - Admin login  → full app with sidebar
    - Scan Only    → scan screen only, no sidebar
"""

import tkinter as tk
import customtkinter as ctk
from db.auth_db import authenticate
from ui.theme import (
    C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED,
    C_ACCENT, C_ERROR, C_SUCCESS
)


class LoginScreen(ctk.CTkFrame):
    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color=C_BG)
        self._on_success = on_success  # callback(mode, user)
        self._build_ui()

    def _build_ui(self):
        # ── Logo ─────────────────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        logo_frame.pack(pady=(48, 0))

        ctk.CTkLabel(
            logo_frame, text="ATTEND",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=C_TEXT,
        ).pack()
        ctk.CTkLabel(
            logo_frame, text="RFID TRACKER",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
        ).pack()

        ctk.CTkFrame(self, fg_color=C_BORDER, height=1).pack(
            fill="x", padx=40, pady=(32, 0))

        # ── Login form ────────────────────────────────────────────────────
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=40, pady=(24, 0))

        ctk.CTkLabel(
            form, text="USERNAME",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C_MUTED, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._username_var = tk.StringVar()
        self._username_entry = ctk.CTkEntry(
            form, textvariable=self._username_var,
            placeholder_text="Enter username",
            fg_color=C_SURFACE, border_color=C_BORDER,
            text_color=C_TEXT, height=38,
            font=ctk.CTkFont(size=13),
        )
        self._username_entry.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            form, text="PASSWORD",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=C_MUTED, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._password_var = tk.StringVar()
        self._password_entry = ctk.CTkEntry(
            form, textvariable=self._password_var,
            placeholder_text="Enter password",
            fg_color=C_SURFACE, border_color=C_BORDER,
            text_color=C_TEXT, height=38,
            font=ctk.CTkFont(size=13),
            show="●",
        )
        self._password_entry.pack(fill="x")
        self._password_entry.bind("<Return>", lambda e: self._login())

        # ── Error label ───────────────────────────────────────────────────
        self._error_lbl = ctk.CTkLabel(
            form, text="",
            font=ctk.CTkFont(size=11),
            text_color=C_ERROR,
        )
        self._error_lbl.pack(fill="x", pady=(8, 0))

        # ── Login button ──────────────────────────────────────────────────
        ctk.CTkButton(
            form, text="Login",
            fg_color=C_ACCENT, hover_color="#8aabff",
            text_color="#ffffff", height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._login,
        ).pack(fill="x", pady=(16, 0))

        # ── Divider ───────────────────────────────────────────────────────
        div_frame = ctk.CTkFrame(self, fg_color="transparent")
        div_frame.pack(fill="x", padx=40, pady=(24, 0))
        div_frame.grid_columnconfigure(0, weight=1)
        div_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkFrame(div_frame, fg_color=C_BORDER, height=1).grid(
            row=0, column=0, sticky="ew", pady=8)
        ctk.CTkLabel(
            div_frame, text="or",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
        ).grid(row=0, column=1, padx=12)
        ctk.CTkFrame(div_frame, fg_color=C_BORDER, height=1).grid(
            row=0, column=2, sticky="ew", pady=8)

        # ── Scan Only button ──────────────────────────────────────────────
        ctk.CTkButton(
            self, text="Scan Only",
            fg_color="transparent",
            border_color=C_BORDER, border_width=1,
            text_color=C_MUTED, hover_color=C_SURFACE,
            height=40, font=ctk.CTkFont(size=13),
            command=self._scan_only,
        ).pack(fill="x", padx=40, pady=(16, 0))

        ctk.CTkLabel(
            self, text="No login required — scan attendance only",
            font=ctk.CTkFont(size=10),
            text_color=C_MUTED,
        ).pack(pady=(6, 0))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _login(self):
        username = self._username_var.get().strip()
        password = self._password_var.get().strip()

        if not username or not password:
            self._show_error("Please enter your username and password.")
            return

        self._error_lbl.configure(text="")
        user = authenticate(username, password)

        if not user:
            self._show_error("Invalid username or password.")
            self._password_entry.configure(border_color=C_ERROR)
            self._username_entry.configure(border_color=C_ERROR)
            return

        # Fire the callback — App handles the rest
        self._on_success(mode="admin", user=user)

    def _scan_only(self):
        self._on_success(mode="scan_only", user=None)

    def _show_error(self, message: str):
        self._error_lbl.configure(text=message)
        self._username_entry.configure(border_color=C_ERROR)
        self._password_entry.configure(border_color=C_ERROR)