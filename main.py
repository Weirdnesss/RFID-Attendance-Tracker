"""
main.py
-------
Entry point for the RFID Attendance Tracker.
Owns the root window, shared sidebar, and all screen frames.

Run:
    python main.py

Screens:
    Scan        — live RFID scanning (scan_screen.py)
    Students    — view/search students (students_screen.py)
    Sessions    — view past sessions  (sessions_screen.py)

Requirements:
    pip install customtkinter pyscard SQLAlchemy PyMySQL openpyxl reportlab
    MySQL must be running.
"""

import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import customtkinter as ctk

from ui.scan_screen import ScanScreen
from ui.theme import (C_BG, C_SURFACE, C_BORDER, C_TEXT, C_MUTED, C_SUCCESS, C_ERROR)
from ui.sessions_screen import SessionsScreen
from ui.students_screen import StudentsScreen
from ui.components.nav_button import NavButton
from ui.admin_screen import AdminScreen
from database       import test_connection, create_tables
from ui.login_screen import LoginScreen
from db.auth_db import seed_superadmin

ctk.set_appearance_mode("dark")


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    SCREENS = ["Scan", "Students", "Sessions", "Admin"]

    def __init__(self):
        super().__init__()
        self.title("Attendance Tracker")
        self.geometry("1020x680")
        self.minsize(900, 600)
        self.configure(fg_color=C_BG)

        self._mode = None
        self._user = None
        self._nav_buttons   = {}
        self._screens       = {}
        self._active_screen = ""

        self._show_login()

    def _show_login(self):
        self._login_screen = LoginScreen(self, on_success=self._on_login)
        self._login_screen.pack(fill="both", expand=True)

    def _on_login(self, mode: str, user: dict):
        self._mode = mode
        self._user = user
        self._login_screen.destroy()

        if mode == "scan_only":
            self._build_scan_only()
        else:
            self._build_layout()
            self._build_sidebar()
            self._build_screens()
            self._navigate("Scan")
            self._tick_clock()
    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_scan_only(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        scan = ScanScreen(self, on_exit=self._logout)
        scan.grid(row=0, column=0, sticky="nsew")
        self._screens["Scan"] = scan

        # ── Bottom status bar ────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=0, height=36)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self._db_lbl = ctk.CTkLabel(
            bar, text="● Connecting...",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._db_lbl.grid(row=0, column=0, padx=20, pady=8)

        self._clock_lbl = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._clock_lbl.grid(row=0, column=2, padx=20, pady=8)

        self.after(200, self._check_db)
        self._tick_clock()

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=180)  # was just weight=1 on col 1
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self):
        self._sb = ctk.CTkFrame(self, fg_color=C_SURFACE,
                                 corner_radius=0, width=180)
        self._sb.grid(row=0, column=0, sticky="nsew")
        self._sb.grid_propagate(False)
        self._sb.grid_rowconfigure(10, weight=1)  # pushes clock to bottom

        # Logo
        ctk.CTkLabel(self._sb, text="ATTEND",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=14, pady=(26, 0))
        ctk.CTkLabel(self._sb, text="RFID TRACKER",
                     font=ctk.CTkFont(size=10),
                     text_color=C_MUTED).grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 16))

        ctk.CTkFrame(self._sb, height=1,
                     fg_color=C_BORDER).grid(
            row=2, column=0, sticky="ew")

        # Nav buttons
        icons = {"Scan": "  ⬡  Scan",
                 "Students": "  ◈  Students",
                 "Sessions": "  ◇  Sessions",
                 "Admin": "  ⬢  Admin"}

        for i, name in enumerate(self.SCREENS):
            btn = NavButton(
                self._sb,
                text=icons[name],
                command=lambda n=name: self._navigate(n),
            )
            btn.grid(row=3 + i, column=0, sticky="ew")
            self._nav_buttons[name] = btn
        
        ctk.CTkButton(
            self._sb, text="  ⬡  Logout",
            fg_color="transparent", hover_color=C_SURFACE,
            text_color=C_MUTED, anchor="w",
            font=ctk.CTkFont(size=13),
            command=self._logout,
        ).grid(row=8, column=0, sticky="ew")

        # Divider before bottom
        ctk.CTkFrame(self._sb, height=1,
                     fg_color=C_BORDER).grid(
            row=10, column=0, sticky="ew", pady=(0, 0))

        # DB status indicator
        self._db_lbl = ctk.CTkLabel(
            self._sb, text="● Connecting...",
            font=ctk.CTkFont(size=11), text_color=C_MUTED)
        self._db_lbl.grid(row=11, column=0, sticky="w", padx=14, pady=(10, 0))

        # Clock
        self._clock_lbl = ctk.CTkLabel(
            self._sb, text="",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED, justify="left")
        self._clock_lbl.grid(
            row=12, column=0, sticky="w", padx=14, pady=(6, 20))

        # Check DB after UI loads
        self.after(200, self._check_db)

    def _build_screens(self):
        container = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self._container = container

        # Scan
        self._screens["Scan"] = ScanScreen(container)

        # Students
        self._screens["Students"] = StudentsScreen(container)

        # Sessions
        self._screens["Sessions"] = SessionsScreen(container)

        # Admin
        self._screens["Admin"] = AdminScreen(container)

        # Place all screens in the same cell — only one visible at a time
        for screen in self._screens.values():
            screen.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    
    def _logout(self):
        # Stop RFID and clock first
        if "Scan" in self._screens:
            self._screens["Scan"].stop_rfid()
        
        if hasattr(self, "_clock_after_id"):
            try:
                self.after_cancel(self._clock_after_id)
            except Exception:
                pass

        # Tear down everything
        for widget in self.winfo_children():
            widget.destroy()

        self.grid_columnconfigure(0, weight=1, minsize=0)
        self.grid_columnconfigure(1, weight=0, minsize=0)

        self._screens       = {}
        self._nav_buttons   = {}
        self._active_screen = ""
        self._mode          = None
        self._user          = None

        # Back to login
        self._show_login()

    def _navigate(self, name: str):
        if name == self._active_screen:
            return

        # Update nav buttons
        if self._active_screen:
            self._nav_buttons[self._active_screen].set_active(False)
        self._nav_buttons[name].set_active(True)

        # Raise the selected screen
        self._screens[name].tkraise()
        self._active_screen = name

        # Refresh data when navigating to live screens
        screen = self._screens[name]

        if hasattr(screen, "refresh"):
            screen.refresh()

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _tick_clock(self):
        if not self.winfo_exists():
            return

        self._clock_lbl.configure(
            text=datetime.now().strftime("%I:%M %p\n%a %d %b %Y"))
        
        self._clock_after_id = self.after(1000, self._tick_clock)
    # ------------------------------------------------------------------
    # DB check
    # ------------------------------------------------------------------

    def _check_db(self):
        ok = test_connection()
        if ok:
            create_tables()
            self._db_lbl.configure(
                text="● DB connected", text_color=C_SUCCESS)
        else:
            self._db_lbl.configure(
                text="● DB offline", text_color=C_ERROR)
            # messagebox.showerror(
            #     "Database offline",
            #     "Could not connect to MySQL.\n\n"
            #     "The app will now close.")
            # self.after(0, self.on_close)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def on_close(self):
        # Stop clock loop
        if hasattr(self, "_clock_after_id"):
            try:
                self.after_cancel(self._clock_after_id)
            except Exception:
                pass

        # Stop RFID safely
        if "Scan" in self._screens:
            self._screens["Scan"].stop_rfid()

        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    seed_superadmin()  # ensure superadmin exists

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()