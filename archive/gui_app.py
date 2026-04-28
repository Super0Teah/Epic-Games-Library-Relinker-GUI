"""
Epic Games Relinker – GUI front-end (CustomTkinter 5.x)
[LEGACY VERSION] - Archived for reference.
Runs all backend operations in background threads and intercepts
print() / input() / MenuCLI so game_data.py needs no changes.
"""

import sys
import os
import builtins
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# ── project imports ──────────────────────────────────────────────────────────
import os
import sys

def get_logic_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'src')
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))

sys.path.insert(0, get_logic_path())
sys.path.insert(0, os.path.dirname(__file__) if not hasattr(sys, '_MEIPASS') else sys._MEIPASS)

from file_management import FileManagement
from game_data import GameDataManager
import menu_cli as menu_cli_module
from manifest_capture import ManifestCapture

# ── theme palette ────────────────────────────────────────────────────────────
import json

def get_base_path():
    """Returns the base path for assets, handling PyInstaller bundles."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

THEMES_FILE = os.path.join(get_base_path(), "themes.json")

_DEFAULT_THEMES = {
    "Hacker Green": {
        "mode": "dark", "bg": "#0a0a0a", "panel": "#0f1610", "card": "#141e15",
        "border": "#1c2e1f", "accent": "#22c55e", "accent2": "#16a34a",
        "success": "#3b82f6", "warn": "#f59e0b", "error": "#ef4444",
        "text": "#4ade80", "muted": "#166534"
    },
    "Dark Gray": {
        "mode": "dark", "bg": "#0f1117", "panel": "#181c27", "card": "#1f2435",
        "border": "#2a2f45", "accent": "#4f8ef7", "accent2": "#6c63ff",
        "success": "#22c55e", "warn": "#f59e0b", "error": "#ef4444",
        "text": "#e2e8f0", "muted": "#64748b"
    },
    "Amoled Black": {
        "mode": "dark", "bg": "#000000", "panel": "#040404", "card": "#080808",
        "border": "#1a1a1a", "accent": "#4f8ef7", "accent2": "#6c63ff",
        "success": "#22c55e", "warn": "#f59e0b", "error": "#ef4444",
        "text": "#ffffff", "muted": "#888888"
    },
    "Light White": {
        "mode": "light", "bg": "#f8fafc", "panel": "#f1f5f9", "card": "#e2e8f0",
        "border": "#cbd5e1", "accent": "#2563eb", "accent2": "#4f46e5",
        "success": "#16a34a", "warn": "#d97706", "error": "#dc2626",
        "text": "#0f172a", "muted": "#64748b"
    }
}

if not os.path.exists(THEMES_FILE):
    try:
        with open(THEMES_FILE, "w", encoding="utf-8") as _f:
            json.dump({"active_theme": "Hacker Green", "themes": _DEFAULT_THEMES}, _f, indent=4)
    except Exception:
        pass

try:
    with open(THEMES_FILE, "r", encoding="utf-8") as _f:
        _theme_data = json.load(_f)
        THEMES = _theme_data.get("themes", _DEFAULT_THEMES)
        _current_theme = _theme_data.get("active_theme", "Hacker Green")
        if _current_theme not in THEMES:
            _current_theme = list(THEMES.keys())[0] if THEMES else "Hacker Green"
except Exception:
    THEMES = _DEFAULT_THEMES
    _current_theme = "Hacker Green"

# Global placeholders
C_BG = C_PANEL = C_CARD = C_BORDER = C_ACCENT = C_ACCENT2 = ""
C_SUCCESS = C_WARN = C_ERROR = C_TEXT = C_MUTED = ""

def apply_theme_globals(name: str):
    global C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_ACCENT2
    global C_SUCCESS, C_WARN, C_ERROR, C_TEXT, C_MUTED
    t = THEMES[name]
    ctk.set_appearance_mode(t["mode"])
    C_BG, C_PANEL, C_CARD = t["bg"], t["panel"], t["card"]
    C_BORDER, C_ACCENT, C_ACCENT2 = t["border"], t["accent"], t["accent2"]
    C_SUCCESS, C_WARN, C_ERROR = t["success"], t["warn"], t["error"]
    C_TEXT, C_MUTED = t["text"], t["muted"]

apply_theme_globals(_current_theme)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: thread-safe GUI dialog that blocks the worker thread until answered
# ─────────────────────────────────────────────────────────────────────────────

class _BlockingDialog:
    """
    Posts a callable to the Tk main thread and waits for its return value.
    Used so background threads can show dialogs without touching Tk directly.
    """
    def __init__(self, app: "App"):
        self._app = app

    def ask(self, fn) -> any:
        result_holder = [None]
        event = threading.Event()

        def _run():
            result_holder[0] = fn()
            event.set()

        self._app.after(0, _run)
        event.wait()
        return result_holder[0]


# ─────────────────────────────────────────────────────────────────────────────
# GuiMenuCLI – replaces MenuCLI for background threads
# ─────────────────────────────────────────────────────────────────────────────

class GuiMenuCLI:
    """Drop-in replacement for MenuCLI that shows GUI dialogs instead of CLI prompts."""

    def __init__(self, app: "App"):
        self._dlg = _BlockingDialog(app)
        self._app = app

    def yes_no_prompt(self, prompt: str) -> bool:
        return self._dlg.ask(lambda: messagebox.askyesno("Confirm", prompt, parent=self._app))

    def print_line_separator(self, char: str = "—", length: int = 40) -> None:
        self._app.log(char * length, tag="sep")

    def numbered_prompt(self, header: str = "Menu:", prompt: str = "Enter an option:",
                        option_list=None) -> int:
        # Not used in the GUI workflow — operations are triggered directly.
        raise NotImplementedError("numbered_prompt should not be called in GUI mode.")

    def list_prompt(self, header: str = "Menu:", prompt: str = "Select from list",
                    option_list=None) -> list:
        """Shows a multi-select checklist dialog."""
        if not option_list:
            return []
        return self._dlg.ask(lambda: _ListDialog(self._app, header, option_list).result)


# ─────────────────────────────────────────────────────────────────────────────
# List-select dialog (used for "Move Game Installation")
# ─────────────────────────────────────────────────────────────────────────────

class _ListDialog:
    def __init__(self, parent, header: str, option_list: list):
        self.result = []
        dlg = tk.Toplevel(parent)
        dlg.title(header)
        dlg.configure(bg=C_PANEL)
        dlg.grab_set()
        dlg.resizable(False, False)

        fg = C_TEXT
        font_h = ("Inter", 13, "bold")
        font_n = ("Inter", 11)

        tk.Label(dlg, text=header, bg=C_PANEL, fg=fg, font=font_h).pack(padx=20, pady=(16, 8))
        tk.Label(dlg, text="Select games to move:", bg=C_PANEL, fg=C_MUTED, font=font_n).pack(padx=20)

        frame = tk.Frame(dlg, bg=C_CARD, bd=1, relief="flat")
        frame.pack(padx=20, pady=10, fill="both", expand=True)

        vars_ = []
        for item in option_list:
            v = tk.BooleanVar(value=False)
            vars_.append(v)
            cb = tk.Checkbutton(
                frame, text=str(item), variable=v,
                bg=C_CARD, fg=fg, selectcolor=C_CARD,
                activebackground=C_CARD, activeforeground=C_ACCENT,
                font=font_n, anchor="w"
            )
            cb.pack(fill="x", padx=12, pady=3)

        btn_row = tk.Frame(dlg, bg=C_PANEL)
        btn_row.pack(pady=(0, 16))

        def _all():
            for v in vars_: v.set(True)
        def _none():
            for v in vars_: v.set(False)
        def _ok():
            self.result = [opt for opt, v in zip(option_list, vars_) if v.get()]
            dlg.destroy()
        def _cancel():
            self.result = []
            dlg.destroy()

        for label, cmd in [("All", _all), ("None", _none), ("OK", _ok), ("Cancel", _cancel)]:
            tk.Button(btn_row, text=label, command=cmd,
                      bg=C_ACCENT, fg="white", relief="flat",
                      padx=14, pady=6, font=font_n).pack(side="left", padx=4)

        parent.wait_window(dlg)


# ─────────────────────────────────────────────────────────────────────────────
# Per-game instruction dialog (OK / Skip / Abort)
# ─────────────────────────────────────────────────────────────────────────────

class _GameCaptureDialog:
    """
    Shown for each game that needs a manifest captured.
    result is one of: "ok" | "skip" | "abort"
    """
    def __init__(self, parent, game_name: str, index: int, total: int):
        self.result = "abort"          # safe default if window is force-closed
        dlg = tk.Toplevel(parent)
        dlg.title(f"Capture — {game_name}  [{index}/{total}]")
        dlg.configure(bg=C_PANEL)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.geometry("480x370")

        font_h = ("Inter", 13, "bold")
        font_n = ("Inter", 11)
        font_s = ("Inter", 10)

        # ── header ────────────────────────────────────────────────────────────
        tk.Label(
            dlg,
            text=f"[{index}/{total}]  {game_name}",
            bg=C_PANEL, fg=C_ACCENT, font=font_h
        ).pack(padx=20, pady=(18, 4))

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20, pady=(0, 10))

        # ── steps card ────────────────────────────────────────────────────────
        card = tk.Frame(dlg, bg=C_CARD)
        card.pack(fill="x", padx=20)

        steps = [
            "Open the Epic Games Launcher",
            f'Find  "{game_name}"  and click  Install / Resume',
            "Wait about 10 seconds  (do NOT let it finish)",
            "CANCEL or Pause the download",
            "Click  Done  below",
        ]
        for i, step in enumerate(steps, start=1):
            row = tk.Frame(card, bg=C_CARD)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(
                row, text=f"{i}.", width=3,
                bg=C_CARD, fg=C_ACCENT, font=font_n, anchor="e"
            ).pack(side="left")
            tk.Label(
                row, text=step,
                bg=C_CARD, fg=C_TEXT, font=font_s, anchor="w", justify="left"
            ).pack(side="left", padx=(6, 0), fill="x", expand=True)

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20, pady=(10, 0))

        # ── install-failed note ───────────────────────────────────────────────
        tk.Label(
            dlg,
            text='Note: "Install failed" messages in the Epic Games Launcher are normal — ignore them.',
            bg=C_PANEL, fg=C_WARN,
            font=("Inter", 9, "italic"),
            wraplength=440, justify="center"
        ).pack(padx=20, pady=(8, 0))

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(dlg, bg=C_PANEL)
        btn_row.pack(pady=12)

        def _ok():
            self.result = "ok"
            dlg.destroy()

        def _skip():
            self.result = "skip"
            dlg.destroy()

        def _abort():
            self.result = "abort"
            dlg.destroy()

        tk.Button(
            btn_row, text="Done", command=_ok,
            bg=C_SUCCESS, fg="white", relief="flat",
            padx=18, pady=8, font=font_n, cursor="hand2"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_row, text="Skip this game", command=_skip,
            bg=C_BORDER, fg=C_TEXT, relief="flat",
            padx=14, pady=8, font=font_s, cursor="hand2"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_row, text="Abort all", command=_abort,
            bg=C_ERROR, fg="white", relief="flat",
            padx=14, pady=8, font=font_s, cursor="hand2"
        ).pack(side="left", padx=5)

        parent.wait_window(dlg)



# ─────────────────────────────────────────────────────────────────────────────
# Match dialog — links a pending manifest to a real game folder
# ─────────────────────────────────────────────────────────────────────────────

class _LinkMatchDialog:
    """
    Shown for each .item file found in Pending.
    Lets the user select which real game folder the manifest belongs to.
    result: str path to the selected game folder, or None to skip.
    """
    def __init__(self, parent, display_name: str, item_file: str,
                 game_data_list: list, index: int, total: int):
        # result is a 2-tuple: ("link", path) | ("skip", None) | ("abort", None)
        self.result = ("abort", None)
        dlg = tk.Toplevel(parent)
        dlg.title(f"Link Manifest  [{index}/{total}]")
        dlg.configure(bg=C_PANEL)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.geometry("520x460")

        font_h = ("Inter", 13, "bold")
        font_n = ("Inter", 11)
        font_s = ("Inter", 10)

        # Header
        tk.Label(
            dlg,
            text=f"[{index}/{total}]  Link pending manifest",
            bg=C_PANEL, fg=C_ACCENT, font=font_h
        ).pack(padx=20, pady=(16, 4))

        # Info card
        info = tk.Frame(dlg, bg=C_CARD)
        info.pack(fill="x", padx=20, pady=(0, 8))

        for label, value in [
            ("Manifest file:", item_file),
            ("Game name:",     display_name or "(unknown)"),
        ]:
            row = tk.Frame(info, bg=C_CARD)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=C_CARD, fg=C_MUTED, font=font_s,
                     width=14, anchor="e").pack(side="left")
            tk.Label(row, text=value, bg=C_CARD, fg=C_TEXT, font=font_s,
                     anchor="w").pack(side="left", padx=(8, 0))

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20)

        # Warning note
        tk.Label(
            dlg,
            text=(
                "Important: Linking a manifest to the wrong game folder will corrupt"
                " the launcher entry. If you are unsure which folder belongs to this"
                " game, click Abort and verify before continuing."
            ),
            bg=C_PANEL, fg=C_WARN,
            font=("Inter", 9, "italic"),
            wraplength=480, justify="center"
        ).pack(padx=20, pady=(8, 4))

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20)

        # Game folder picker
        tk.Label(
            dlg,
            text="Select the installed game folder this manifest belongs to:",
            bg=C_PANEL, fg=C_TEXT, font=font_n
        ).pack(anchor="w", padx=20, pady=(10, 0))

        tk.Label(
            dlg,
            text="[ ★ ] indicates a predicted match  |  [ ? ] indicates a possible guess.",
            bg=C_PANEL, fg=C_MUTED, font=("Inter", 9, "italic")
        ).pack(anchor="w", padx=20, pady=(0, 4))

        list_frame = tk.Frame(dlg, bg=C_CARD)
        list_frame.pack(fill="both", expand=True, padx=20)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame,
            bg=C_CARD, fg=C_TEXT,
            selectbackground=C_ACCENT, selectforeground="white",
            font=font_s, relief="flat", bd=0,
            yscrollcommand=scrollbar.set,
            activestyle="none"
        )
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        import re
        import difflib
        def _norm(txt): return re.sub(r'[^a-z0-9]', '', str(txt).lower())

        # Predict best match by display name or file name (ignoring symbols)
        dl_n = _norm(display_name)
        if_n = _norm(item_file.replace(".item", ""))
        best_match_idx = -1
        
        closest_match_idx = -1
        highest_ratio = 0.0
        
        for i, game in enumerate(game_data_list):
            fn_n = _norm(game.game_folder.name)
            if (dl_n and (dl_n in fn_n or fn_n in dl_n)) or \
               (if_n and len(if_n) >= 3 and (if_n in fn_n or fn_n in if_n)):
                best_match_idx = i
                break
            
            r1 = difflib.SequenceMatcher(None, dl_n, fn_n).ratio() if dl_n else 0
            r2 = difflib.SequenceMatcher(None, if_n, fn_n).ratio() if if_n else 0
            m_ratio = max(r1, r2)
            if m_ratio > highest_ratio and m_ratio > 0.3:
                highest_ratio = m_ratio
                closest_match_idx = i

        if best_match_idx != -1:
            closest_match_idx = -1

        for i, game in enumerate(game_data_list):
            if i == best_match_idx:
                prefix = "[ ★ ]"
            elif i == closest_match_idx:
                prefix = "[ ? ]"
            else:
                prefix = "     "
            listbox.insert("end", f" {prefix}  {game.game_folder.name}  ({game.game_folder.path})")

        if best_match_idx >= 0:
            listbox.selection_set(best_match_idx)
            listbox.see(best_match_idx)
        elif closest_match_idx >= 0:
            listbox.see(closest_match_idx)

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20, pady=(8, 0))

        btn_row = tk.Frame(dlg, bg=C_PANEL)
        btn_row.pack(pady=10)

        def _link():
            sel = listbox.curselection()
            if not sel:
                tk.messagebox.showwarning("No selection",
                    "Please select a game folder before linking.", parent=dlg)
                return
            self.result = ("link", game_data_list[sel[0]].game_folder.path)
            dlg.destroy()

        def _skip():
            self.result = ("skip", None)
            dlg.destroy()

        def _abort():
            self.result = ("abort", None)
            dlg.destroy()

        tk.Button(
            btn_row, text="Link", command=_link,
            bg=C_SUCCESS, fg="white", relief="flat",
            padx=20, pady=8, font=font_n, cursor="hand2"
        ).pack(side="left", padx=5)
        tk.Button(
            btn_row, text="Skip this manifest", command=_skip,
            bg=C_BORDER, fg=C_TEXT, relief="flat",
            padx=14, pady=8, font=font_s, cursor="hand2"
        ).pack(side="left", padx=5)
        tk.Button(
            btn_row, text="Abort all", command=_abort,
            bg=C_ERROR, fg="white", relief="flat",
            padx=14, pady=8, font=font_s, cursor="hand2"
        ).pack(side="left", padx=5)

        parent.wait_window(dlg)


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight options dialog for Capture Missing Manifests
# ─────────────────────────────────────────────────────────────────────────────

class _CaptureOptionsDialog:
    """
    Shows before the capture loop starts.
    Returns {'delete_downloads': bool} on OK, or None on Cancel.
    """
    def __init__(self, parent, game_count: int):
        self.result = None
        dlg = tk.Toplevel(parent)
        dlg.title("Capture Options")
        dlg.configure(bg=C_PANEL)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.geometry("440x300")

        font_h = ("Inter", 13, "bold")
        font_n = ("Inter", 11)
        font_s = ("Inter", 10)

        # Header
        tk.Label(
            dlg,
            text=f"Capture {game_count} missing manifest{'s' if game_count != 1 else ''}",
            bg=C_PANEL, fg=C_TEXT, font=font_h
        ).pack(padx=20, pady=(18, 4))

        tk.Label(
            dlg,
            text=(
                "For each game you'll briefly trigger a download in\n"
                "the Epic Games Launcher so a manifest file is created."
            ),
            bg=C_PANEL, fg=C_MUTED, font=font_s, justify="center"
        ).pack(padx=20, pady=(0, 12))

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20)

        # Option card
        card = tk.Frame(dlg, bg=C_CARD)
        card.pack(fill="x", padx=20, pady=12)

        self._delete_var = tk.BooleanVar(value=True)

        row = tk.Frame(card, bg=C_CARD)
        row.pack(fill="x", padx=12, pady=10)

        tk.Checkbutton(
            row, variable=self._delete_var,
            bg=C_CARD, activebackground=C_CARD,
            selectcolor=C_CARD, cursor="hand2"
        ).pack(side="left", padx=(0, 8))

        col = tk.Frame(row, bg=C_CARD)
        col.pack(side="left", fill="x", expand=True)

        tk.Label(
            col, text="Auto-delete partial downloads after each capture",
            bg=C_CARD, fg=C_TEXT, font=font_n, anchor="w"
        ).pack(anchor="w")
        tk.Label(
            col,
            text="Removes game data Epic starts downloading — keeps only\nthe launcher manifest. Saves disk space (recommended).",
            bg=C_CARD, fg=C_MUTED, font=font_s, justify="left", anchor="w"
        ).pack(anchor="w")

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20)

        # Buttons
        btn_row = tk.Frame(dlg, bg=C_PANEL)
        btn_row.pack(pady=14)

        def _ok():
            self.result = {"delete_downloads": self._delete_var.get()}
            dlg.destroy()

        def _cancel():
            self.result = None
            dlg.destroy()

        tk.Button(
            btn_row, text="Start Capture", command=_ok,
            bg=C_ACCENT, fg="white", relief="flat",
            padx=18, pady=7, font=font_n, cursor="hand2"
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row, text="Cancel", command=_cancel,
            bg=C_BORDER, fg=C_TEXT, relief="flat",
            padx=18, pady=7, font=font_n, cursor="hand2"
        ).pack(side="left", padx=6)

        parent.wait_window(dlg)


# ─────────────────────────────────────────────────────────────────────────────
# Fix Manifest Link dialog — remap a wrongly-linked .item to the correct folder
# ─────────────────────────────────────────────────────────────────────────────

class _FixManifestDialog:
    """
    Two-pane dialog.  Left: all .item files in Manifests folder with their current
    InstallLocation.  Right: all detected game folders.  User picks one from
    each side and clicks Fix to rewrite the paths in place.
    result: (item_path: str, new_game_folder_path: str) or None.
    """
    def __init__(self, parent, manifests: list[dict], game_data_list: list):
        self.result = None
        dlg = tk.Toplevel(parent)
        dlg.title("Fix Manifest Link")
        dlg.configure(bg=C_PANEL)
        dlg.grab_set()
        dlg.resizable(True, True)
        dlg.geometry("780x540")

        font_h = ("Inter", 13, "bold")
        font_n = ("Inter", 11)
        font_s = ("Inter", 10)

        # Header
        tk.Label(dlg, text="Fix Manifest Link",
                 bg=C_PANEL, fg=C_WARN, font=font_h
                 ).pack(padx=20, pady=(16, 2))
        tk.Label(
            dlg,
            text="Select the incorrect manifest on the left, then select the correct game folder on the right.\n[ ★ ] exact match  |  [ ? ] likely guess",
            bg=C_PANEL, fg=C_MUTED, font=font_s, justify="center"
        ).pack(padx=20)

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20, pady=(10, 0))

        # Two-pane area
        panes = tk.Frame(dlg, bg=C_PANEL)
        panes.pack(fill="both", expand=True, padx=20, pady=10)
        panes.columnconfigure(0, weight=1)
        panes.columnconfigure(1, weight=1)
        panes.rowconfigure(1, weight=1)

        # ── Left: manifest list ───────────────────────────────────────────────
        tk.Label(panes, text="Launcher manifests (pick the wrong one):",
                 bg=C_PANEL, fg=C_TEXT, font=font_n, anchor="w"
                 ).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 4))

        lf = tk.Frame(panes, bg=C_CARD)
        lf.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        ls = tk.Scrollbar(lf); ls.pack(side="right", fill="y")
        self._mlb = tk.Listbox(
            lf, bg=C_CARD, fg=C_TEXT,
            selectbackground=C_WARN, selectforeground="white",
            font=font_s, relief="flat", bd=0,
            yscrollcommand=ls.set, activestyle="none",
            exportselection=False
        )
        self._mlb.pack(side="left", fill="both", expand=True)
        ls.config(command=self._mlb.yview)
        for m in manifests:
            label = m["display_name"] or m["file"].name
            self._mlb.insert("end", f"  {label}")

        # ── Right: game folder list ───────────────────────────────────────────
        tk.Label(panes, text="Correct game folder:",
                 bg=C_PANEL, fg=C_TEXT, font=font_n, anchor="w"
                 ).grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 4))

        rf = tk.Frame(panes, bg=C_CARD)
        rf.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        rs = tk.Scrollbar(rf); rs.pack(side="right", fill="y")
        self._flb = tk.Listbox(
            rf, bg=C_CARD, fg=C_TEXT,
            selectbackground=C_SUCCESS, selectforeground="white",
            font=font_s, relief="flat", bd=0,
            yscrollcommand=rs.set, activestyle="none",
            exportselection=False
        )
        self._flb.pack(side="left", fill="both", expand=True)
        rs.config(command=self._flb.yview)
        for game in game_data_list:
            self._flb.insert("end", f"    {game.game_folder.name}")

        # Status bar: shows current install location of selected manifest
        self._status = tk.StringVar(value="Select a manifest to see its current install location.")
        tk.Label(dlg, textvariable=self._status,
                 bg=C_PANEL, fg=C_MUTED, font=("Inter", 9, "italic"),
                 wraplength=740, justify="left",
                 anchor="w").pack(padx=24, pady=(0, 4), fill="x")

        def _on_manifest_select(_evt):
            sel = self._mlb.curselection()
            if not sel:
                return
            m = manifests[sel[0]]
            self._status.set(f"Current install location: {m['install_location']}")
            
            import re
            import difflib
            def _norm(txt): return re.sub(r'[^a-z0-9]', '', str(txt).lower())

            # Predict best matching game folder on the right (ignoring symbols)
            dl_n = _norm(m.get("display_name", ""))
            if_n = _norm(m["file"].name.replace(".item", ""))
            best_match_idx = -1
            
            closest_match_idx = -1
            highest_ratio = 0.0
            
            for i, game in enumerate(game_data_list):
                fn_n = _norm(game.game_folder.name)
                if (dl_n and (dl_n in fn_n or fn_n in dl_n)) or \
                   (if_n and len(if_n) >= 3 and (if_n in fn_n or fn_n in if_n)):
                    best_match_idx = i
                    break
                
                r1 = difflib.SequenceMatcher(None, dl_n, fn_n).ratio() if dl_n else 0
                r2 = difflib.SequenceMatcher(None, if_n, fn_n).ratio() if if_n else 0
                m_ratio = max(r1, r2)
                if m_ratio > highest_ratio and m_ratio > 0.3:
                    highest_ratio = m_ratio
                    closest_match_idx = i
                    
            if best_match_idx != -1:
                closest_match_idx = -1

            # Update the listbox text
            self._flb.delete(0, "end")
            self._flb.selection_clear(0, "end")
            for i, game in enumerate(game_data_list):
                if i == best_match_idx:
                    prefix = "[ ★ ]"
                elif i == closest_match_idx:
                    prefix = "[ ? ]"
                else:
                    prefix = "     "
                self._flb.insert("end", f" {prefix}  {game.game_folder.name}")

            if best_match_idx >= 0:
                self._flb.selection_set(best_match_idx)
                self._flb.see(best_match_idx)
            elif closest_match_idx >= 0:
                self._flb.see(closest_match_idx)

        self._mlb.bind("<<ListboxSelect>>", _on_manifest_select)

        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", padx=20)

        btn_row = tk.Frame(dlg, bg=C_PANEL)
        btn_row.pack(pady=12)

        def _fix():
            sm = self._mlb.curselection()
            sf = self._flb.curselection()
            if not sm:
                messagebox.showwarning("No manifest selected",
                    "Please select a manifest from the left list.", parent=dlg)
                return
            if not sf:
                messagebox.showwarning("No folder selected",
                    "Please select the correct game folder from the right list.", parent=dlg)
                return
            self.result = (
                manifests[sm[0]]["file"].path,
                game_data_list[sf[0]].game_folder.path,
            )
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        tk.Button(
            btn_row, text="Fix Link", command=_fix,
            bg=C_WARN, fg="white", relief="flat",
            padx=22, pady=8, font=font_n, cursor="hand2"
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row, text="Cancel", command=_cancel,
            bg=C_BORDER, fg=C_TEXT, relief="flat",
            padx=22, pady=8, font=font_s, cursor="hand2"
        ).pack(side="left", padx=6)

        parent.wait_window(dlg)


# ─────────────────────────────────────────────────────────────────────────────
# Main application window
# ─────────────────────────────────────────────────────────────────────────────

class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Epic Games Relinker GUI")
        self.geometry("1120x720")
        self.minsize(920, 580)
        self.configure(fg_color=C_BG)

        # Intercept print() globally so game_data.py logs appear in the panel
        self._real_print = builtins.print
        builtins.print = self._intercepted_print

        self._worker: threading.Thread | None = None
        self._gui_menu_cli = GuiMenuCLI(self)
        self._capture_cancel = threading.Event()

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── left column: config ───────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, width=360)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)

        self._build_branding(left)
        self._build_path_section(left)
        self._build_action_buttons(left)

        # ── right column: log panel ───────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=24, border_width=1, border_color=C_BORDER)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=16)

        self._build_log_panel(right)

    def _change_theme(self, new_theme: str):
        global _current_theme
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Busy", "Cannot change theme while an operation is running.", parent=self)
            self._theme_var.set(_current_theme)
            return

        _current_theme = new_theme
        apply_theme_globals(new_theme)
        
        try:
            import json
            with open(THEMES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["active_theme"] = new_theme
            with open(THEMES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

        # Save UI state before destroying
        old_m = getattr(self, "_manifest_var", None)
        old_m_val = old_m.get() if old_m else ""
        old_g = getattr(self, "_games_var", None)
        old_g_val = old_g.get() if old_g else ""
        old_d = getattr(self, "_use_default_var", None)
        old_d_val = old_d.get() if old_d else True
        
        log_text = ""
        if hasattr(self, '_log_box'):
            log_text = self._log_box.get("1.0", "end-1c")
            
        # Rebuild UI
        self.configure(fg_color=C_BG)
        for w in self.winfo_children():
            w.destroy()
            
        self._build_ui()
        
        # Restore UI state
        if hasattr(self, '_manifest_var'): self._manifest_var.set(old_m_val)
        if hasattr(self, '_games_var'): self._games_var.set(old_g_val)
        if hasattr(self, '_use_default_var'):
            self._use_default_var.set(old_d_val)
            self._toggle_default_path()
            
        if hasattr(self, '_log_box') and log_text.strip():
            self._log_box.delete("1.0", "end")
            self._log_box.insert("end", log_text)
            self._log_box.see("end")

    def _build_branding(self, parent):
        brand = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=24, border_width=1, border_color=C_BORDER)
        brand.pack(fill="x", padx=0, pady=(4, 8))

        ctk.CTkLabel(
            brand, text="Epic Games Relinker GUI",
            font=ctk.CTkFont("Inter", 20, "bold"),
            text_color=C_ACCENT
        ).pack(padx=16, pady=20)

    def _build_path_section(self, parent):
        section = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=24, border_width=1, border_color=C_BORDER)
        section.pack(fill="x", padx=0, pady=8)

        ctk.CTkLabel(
            section, text="CONFIGURATION",
            font=ctk.CTkFont("Inter", 10, "bold"),
            text_color=C_MUTED
        ).pack(anchor="w", padx=16, pady=(14, 4))

        # Manifests path row
        ctk.CTkLabel(section, text="Manifests Folder",
                     font=ctk.CTkFont("Inter", 12, "bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=16)

        mf_row = ctk.CTkFrame(section, fg_color="transparent")
        mf_row.pack(fill="x", padx=16, pady=(4, 0))

        self._manifest_var = tk.StringVar(value=GameDataManager.DEFAULT_MANIFESTS_PATH)
        mf_entry = ctk.CTkEntry(mf_row, textvariable=self._manifest_var,
                                font=ctk.CTkFont("Inter", 10),
                                fg_color=C_BG, border_color=C_BORDER, height=34)
        mf_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(mf_row, text="Browse", width=64, height=34, corner_radius=8,
                      font=ctk.CTkFont("Inter", 11, "bold"), text_color=C_TEXT,
                      fg_color=C_BORDER, hover_color=C_ACCENT,
                      command=self._browse_manifests).pack(side="left", padx=(6, 0))

        # Use-default checkbox
        self._use_default_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            section, text="Use default path",
            variable=self._use_default_var,
            font=ctk.CTkFont("Inter", 11),
            text_color=C_MUTED,
            checkbox_width=16, checkbox_height=16,
            command=self._toggle_default_path
        ).pack(anchor="w", padx=16, pady=(6, 0))

        # Games folder row
        ctk.CTkLabel(section, text="Games Folder",
                     font=ctk.CTkFont("Inter", 12, "bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=16, pady=(14, 0))

        gf_row = ctk.CTkFrame(section, fg_color="transparent")
        gf_row.pack(fill="x", padx=16, pady=(4, 14))

        self._games_var = tk.StringVar(value="")
        gf_entry = ctk.CTkEntry(gf_row, textvariable=self._games_var,
                                placeholder_text="Select your games folder...",
                                font=ctk.CTkFont("Inter", 10),
                                fg_color=C_BG, border_color=C_BORDER, height=34)
        gf_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(gf_row, text="Browse", width=64, height=34, corner_radius=8,
                      font=ctk.CTkFont("Inter", 11, "bold"), text_color=C_TEXT,
                      fg_color=C_BORDER, hover_color=C_ACCENT,
                      command=self._browse_games).pack(side="left", padx=(6, 0))

        self._toggle_default_path()

    def _build_action_buttons(self, parent):
        section = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=24, border_width=1, border_color=C_BORDER)
        section.pack(fill="x", padx=0, pady=8)

        ctk.CTkLabel(
            section, text="ACTIONS",
            font=ctk.CTkFont("Inter", 10, "bold"),
            text_color=C_MUTED
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self._action_buttons = []
        font_btn = ctk.CTkFont("Inter", 12, "bold")
        font_btn_s = ctk.CTkFont("Inter", 11, "bold")

        def _btn(parent_frame, label, color, cmd, **pack_kw):
            b = ctk.CTkButton(
                parent_frame, text=label,
                font=font_btn, height=40, corner_radius=8,
                fg_color=color, hover_color=self._darken(color),
                command=cmd
            )
            b.pack(**pack_kw)
            self._action_buttons.append(b)

        # Row 1: two-column  (Relink | Move)
        row1 = ctk.CTkFrame(section, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 4))
        row1.columnconfigure(0, weight=1)
        row1.columnconfigure(1, weight=1)
        b1 = ctk.CTkButton(row1, text="Relink Games",
                            font=font_btn, height=40, corner_radius=8,
                            fg_color=C_ACCENT, hover_color=self._darken(C_ACCENT),
                            command=self._run_relink)
        b1.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._action_buttons.append(b1)
        b2 = ctk.CTkButton(row1, text="Move Games",
                            font=font_btn, height=40, corner_radius=8,
                            fg_color=C_ACCENT2, hover_color=self._darken(C_ACCENT2),
                            command=self._run_move)
        b2.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self._action_buttons.append(b2)

        # Row 2: full-width  (Move Between PCs)
        _btn(section, "Move Between PCs", "#0ea5e9", self._run_move_pc,
             fill="x", padx=12, pady=4)

        # Row 3: two-column  (Capture | Link)
        row3 = ctk.CTkFrame(section, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(4, 14))
        row3.columnconfigure(0, weight=1)
        row3.columnconfigure(1, weight=1)
        b4 = ctk.CTkButton(row3, text="Capture",
                            font=font_btn_s, height=40, corner_radius=8,
                            fg_color="#16a34a", hover_color=self._darken("#16a34a"),
                            command=self._run_capture_manifests)
        b4.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._action_buttons.append(b4)
        b5 = ctk.CTkButton(row3, text="Link",
                            font=font_btn_s, height=40, corner_radius=8,
                            fg_color="#9333ea", hover_color=self._darken("#9333ea"),
                            command=self._run_link_manifests)
        b5.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self._action_buttons.append(b5)

        # Row 4: full-width  (Fix Manifest Link — amber)
        b6 = ctk.CTkButton(
            section, text="Fix Manifest Link",
            font=font_btn, height=38, corner_radius=8,
            fg_color=C_WARN, hover_color=self._darken(C_WARN),
            command=self._run_fix_manifest
        )
        b6.pack(fill="x", padx=12, pady=(0, 14))
        self._action_buttons.append(b6)

        # ── Theme Selector ────────────────────────────────────────────────────
        theme_frame = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=24, border_width=1, border_color=C_BORDER)
        theme_frame.pack(side="bottom", fill="x", padx=0, pady=(8, 4))
        
        ctk.CTkLabel(
            theme_frame, text="Theme:", text_color=C_MUTED, font=ctk.CTkFont("Inter", 11, "bold")
        ).pack(side="left", padx=(16, 0), pady=12)
        
        self._theme_var = tk.StringVar(value=_current_theme)
        theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=list(THEMES.keys()), variable=self._theme_var,
            command=self._change_theme, height=28,
            fg_color=C_CARD, button_color=C_BORDER, button_hover_color=C_ACCENT,
            text_color=C_TEXT, font=ctk.CTkFont("Inter", 11)
        )
        theme_menu.pack(side="right", fill="x", expand=True, padx=(10, 16), pady=12)

    def _build_log_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Log",
            font=ctk.CTkFont("Inter", 14, "bold"),
            text_color=C_TEXT
        ).pack(side="left", padx=20, pady=12)

        ctk.CTkButton(
            header, text="Clear", width=64, height=28, corner_radius=6,
            font=ctk.CTkFont("Inter", 11, "bold"),
            fg_color=C_BORDER, hover_color=C_MUTED,
            command=self._clear_log
        ).pack(side="right", padx=(8, 16), pady=10)

        ctk.CTkButton(
            header, text="Credits", width=68, height=28, corner_radius=6,
            font=ctk.CTkFont("Inter", 11, "bold"),
            fg_color=C_BORDER, hover_color=C_ACCENT,
            command=self._show_credits
        ).pack(side="right", padx=(0, 0), pady=10)

        # Divider
        div = ctk.CTkFrame(parent, fg_color=C_BORDER, height=1)
        div.pack(fill="x", padx=24)

        # Text widget inside a frame
        log_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(8, 20))

        self._log_text = tk.Text(
            log_frame,
            bg=C_CARD, fg=C_TEXT,
            insertbackground=C_TEXT,
            font=("Consolas", 11),
            relief="flat", bd=0,
            wrap="word",
            state="disabled",
            padx=16, pady=12
        )
        self._log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ctk.CTkScrollbar(log_frame, command=self._log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=scrollbar.set)

        # Tags for coloured log lines
        self._log_text.tag_config("INFO",    foreground="#93c5fd")
        self._log_text.tag_config("WARNING", foreground=C_WARN)
        self._log_text.tag_config("ERROR",   foreground=C_ERROR)
        self._log_text.tag_config("SUCCESS", foreground=C_SUCCESS)
        self._log_text.tag_config("sep",     foreground=C_BORDER)
        self._log_text.tag_config("STEP",    foreground=C_ACCENT2)

        self.log("INFO: This version is old and probably not completely tested. You should use the newer version of the program. (Archived version for reference, preserving, and cleaning purposes).", tag="WARNING")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.75) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return "#{:02x}{:02x}{:02x}".format(int(r*factor), int(g*factor), int(b*factor))

    def _toggle_default_path(self):
        if self._use_default_var.get():
            self._manifest_var.set(GameDataManager.DEFAULT_MANIFESTS_PATH)

    def _browse_manifests(self):
        path = filedialog.askdirectory(title="Select Manifests Folder", parent=self)
        if path:
            self._manifest_var.set(os.path.normpath(path))
            self._use_default_var.set(False)

    def _browse_games(self):
        path = filedialog.askdirectory(title="Select Games Folder", parent=self)
        if path:
            self._games_var.set(os.path.normpath(path))

    # ── logging ───────────────────────────────────────────────────────────────

    def log(self, message: str, tag: str = ""):
        def _insert():
            self._log_text.configure(state="normal")

            # Auto-detect tag from message prefix if not given
            resolved_tag = tag
            if not resolved_tag:
                for prefix in ("ERROR", "WARNING", "INFO", "SUCCESS", "STEP"):
                    if prefix in message.upper():
                        resolved_tag = prefix
                        break

            self._log_text.insert("end", message + "\n", resolved_tag)
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

        self.after(0, _insert)

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _show_credits(self):
        messagebox.showinfo(
            "Credits",
            "Developed by Supernova1114 (Original Developer) &\n"
            "Super0Teah (GUI Dev)\n\n"
            "A modern tool to intelligently move and relink Epic Games installations.",
            parent=self
        )

    def _intercepted_print(self, *args, **kwargs):
        """Captures all print() calls from game_data.py and routes them to the log panel."""
        message = " ".join(str(a) for a in args)
        self.log(message)
        # Also write to real stdout for debugging
        self._real_print(*args, **kwargs)

    # ── path validation ───────────────────────────────────────────────────────

    def _validate_paths(self) -> tuple[str, str] | None:
        manifest_path = self._manifest_var.get().strip()
        games_path    = self._games_var.get().strip()

        if not manifest_path:
            messagebox.showerror("Error", "Please set the Manifests folder path.", parent=self)
            return None
        if not games_path:
            messagebox.showerror("Error", "Please set the Games folder path.", parent=self)
            return None
        if not os.path.exists(games_path):
            messagebox.showerror("Error", f"Games folder does not exist:\n{games_path}", parent=self)
            return None

        # Auto-create manifests folder if missing
        if not os.path.exists(manifest_path):
            self.log(f"INFO: Creating manifests folder: {manifest_path}")
            os.makedirs(manifest_path, exist_ok=True)

        return manifest_path, games_path

    # ── button lock/unlock ────────────────────────────────────────────────────

    def _set_buttons_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.after(0, lambda: [b.configure(state=state) for b in self._action_buttons])

    # ── worker runner ─────────────────────────────────────────────────────────

    def _run_worker(self, fn, label: str):
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Busy", "An operation is already running.", parent=self)
            return

        paths = self._validate_paths()
        if not paths:
            return

        manifest_path, games_path = paths
        self._set_buttons_state(False)
        self.log(f"\n{'─'*50}", tag="sep")
        self.log(f"▶  {label}", tag="STEP")
        self.log(f"{'─'*50}", tag="sep")

        def _thread():
            try:
                # Patch MenuCLI singleton methods for this thread
                gui_cli = GuiMenuCLI(self)
                menu_cli_module.MenuCLI.yes_no_prompt    = staticmethod(lambda prompt, _c=gui_cli: _c.yes_no_prompt(prompt))
                menu_cli_module.MenuCLI.print_line_separator = staticmethod(lambda char="—", length=40, _c=gui_cli: _c.print_line_separator(char, length))
                menu_cli_module.MenuCLI.list_prompt      = staticmethod(lambda header="Menu:", prompt="Select", option_list=None, _c=gui_cli: _c.list_prompt(header, prompt, option_list or []))

                mgr = GameDataManager(manifest_path, games_path)

                if mgr.get_game_count() == 0:
                    self.log("ERROR: No valid games found in the specified folder!", tag="ERROR")
                    return

                fn(mgr)
                self.log("\n✅  Operation completed successfully!", tag="SUCCESS")

            except SystemExit:
                self.log("ℹ️  Operation was cancelled or exited.", tag="WARNING")
            except Exception as e:
                self.log(f"ERROR: {e}", tag="ERROR")
            finally:
                self._set_buttons_state(True)

        self._worker = threading.Thread(target=_thread, daemon=True)
        self._worker.start()

    # ── workflow handlers ─────────────────────────────────────────────────────

    def _run_relink(self):
        def _workflow(mgr: GameDataManager):
            self.log("INFO: Step 1/3 — Backing up manifests...")
            mgr.backup_manifests()
            self.log("INFO: Step 2/3 — Relinking manifests...")
            mgr.relink_manifests()
            self.log("INFO: Step 3/3 — Restoring manifests...")
            mgr.restore_manifests()

        self._run_worker(_workflow, "Relink Games  (Backup → Relink → Restore)")

    def _run_move(self):
        def _workflow(mgr: GameDataManager):
            self.log("INFO: Step 1/3 — Backing up manifests...")
            mgr.backup_manifests()
            self.log("INFO: Step 2/3 — Moving game installation...")
            mgr.move_game_installation()
            self.log("INFO: Step 3/3 — Restoring manifests...")
            mgr.restore_manifests()

        self._run_worker(_workflow, "Move Games  (Backup → Move → Restore)")

    def _run_move_pc(self):
        def _workflow(mgr: GameDataManager):
            self.log("INFO: Step 1/2 — Backing up manifests...")
            mgr.backup_manifests()
            self.log("INFO: Move your games folder to the other PC, then click OK.", tag="WARNING")

            ready = self._blocking_dialog_ask(
                lambda: messagebox.askokcancel(
                    "Move Between PCs",
                    "Backup complete.\n\nNow move your storage drive / games folder to the other PC.\n\nClick OK when ready to restore manifests, or Cancel to abort.",
                    parent=self
                )
            )
            if not ready:
                self.log("INFO: Operation cancelled by user.")
                return

            self.log("INFO: Step 2/2 — Restoring manifests...")
            mgr.restore_manifests()

        self._run_worker(_workflow, "Move Games Between PCs  (Backup → Restore)")

    def _blocking_dialog_ask(self, fn):
        dlg = _BlockingDialog(self)
        return dlg.ask(fn)

    # ── capture missing manifests ─────────────────────────────────────────────

    def _run_capture_manifests(self):
        """Guides the user to acquire new launcher .item manifests for games
        that are installed but not yet known to the Epic Launcher."""

        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Busy", "An operation is already running.", parent=self)
            return

        paths = self._validate_paths()
        if not paths:
            return

        manifest_path, games_path = paths
        self._set_buttons_state(False)
        self._capture_cancel.clear()
        self.log(f"\n{'─'*50}", tag="sep")
        self.log("▶  Capture Missing Manifests", tag="STEP")
        self.log(f"{'─'*50}", tag="sep")

        def _thread():
            try:
                # Patch MenuCLI for this thread
                gui_cli = GuiMenuCLI(self)
                menu_cli_module.MenuCLI.yes_no_prompt        = staticmethod(lambda p, _c=gui_cli: _c.yes_no_prompt(p))
                menu_cli_module.MenuCLI.print_line_separator = staticmethod(lambda char="—", length=40, _c=gui_cli: _c.print_line_separator(char, length))
                menu_cli_module.MenuCLI.list_prompt          = staticmethod(lambda header="Menu:", prompt="Select", option_list=None, _c=gui_cli: _c.list_prompt(header, prompt, option_list or []))

                from game_data import GameDataManager
                mgr = GameDataManager(manifest_path, games_path)

                if mgr.get_game_count() == 0:
                    self.log("ERROR: No valid games found in the specified folder!", tag="ERROR")
                    return

                capturer = ManifestCapture(manifest_path, mgr._game_data_list)
                missing  = capturer.get_games_missing_manifests()

                if not missing:
                    self.log("All games already have launcher manifests. Nothing to do!", tag="SUCCESS")
                    return

                self.log(f"INFO: Found {len(missing)} game(s) missing launcher manifests:", tag="INFO")
                for g in missing:
                    self.log(f"  -  {g.game_folder.name}", tag="INFO")

                confirmed = self._blocking_dialog_ask(
                    lambda: messagebox.askyesno(
                        "Capture Missing Manifests",
                        f"{len(missing)} game(s) need new launcher manifests.\n\n"
                        "For each game you will be told what to do in the Epic Games Launcher.\n\n"
                        "Make sure the Epic Games Launcher is open before continuing.\n\nProceed?",
                        parent=self
                    )
                )
                if not confirmed:
                    self.log("INFO: Capture cancelled by user.", tag="WARNING")
                    return

                # ── pre-flight options dialog ──────────────────────────────────
                options = self._blocking_dialog_ask(
                    lambda: _CaptureOptionsDialog(self, len(missing)).result
                )
                if options is None:
                    self.log("INFO: Capture cancelled by user.", tag="WARNING")
                    return

                delete_downloads: bool = options.get("delete_downloads", False)
                self.log(
                    f"INFO: Auto-delete partial downloads: {'ON' if delete_downloads else 'OFF'}.",
                    tag="INFO"
                )

                captured = 0
                skipped  = 0

                for index, game in enumerate(missing, start=1):

                    if self._capture_cancel.is_set():
                        self.log("WARNING: Capture aborted by user.", tag="WARNING")
                        break

                    game_name = game.game_folder.name
                    self.log(f"[{index}/{len(missing)}]  {game_name}", tag="STEP")
                    self.log(
                        f"INFO: Open Epic Games Launcher, find '{game_name}',"
                        f" start downloading it. After ~10 seconds CANCEL the download, then click Done.",
                        tag="INFO"
                    )

                    # Snapshot BEFORE user triggers the download
                    snapshot = capturer.take_snapshot()

                    proceed = self._blocking_dialog_ask(
                        lambda gn=game_name, idx=index, tot=len(missing): _GameCaptureDialog(
                            self, gn, idx, tot
                        ).result
                    )

                    if proceed == "abort":
                        self._capture_cancel.set()
                        self.log("WARNING: Capture aborted by user.", tag="WARNING")
                        break
                    if proceed == "skip":
                        self.log(f"WARNING: Skipped '{game_name}'.", tag="WARNING")
                        skipped += 1
                        continue

                    self.log("INFO: Watching for new manifest file... (up to 5 minutes)", tag="INFO")

                    last_dot = [0.0]
                    def _progress(elapsed, _ld=last_dot):
                        if elapsed - _ld[0] >= 5:
                            self.log(f"INFO: Still watching... ({int(elapsed)}s elapsed)", tag="INFO")
                            _ld[0] = elapsed

                    new_file = capturer.wait_for_new_manifest(
                        snapshot,
                        progress_callback=_progress,
                        cancel_flag=self._capture_cancel
                    )

                    if new_file is None:
                        self.log(f"WARNING: No new manifest detected for '{game_name}'. Skipping.", tag="WARNING")
                        skipped += 1
                        continue

                    display = ManifestCapture.read_display_name(new_file.path)
                    label   = display if display else new_file.name
                    self.log(f"Captured manifest: {new_file.name}", tag="SUCCESS")
                    self.log(f"    Launcher reports game as: '{label}'", tag="SUCCESS")
                    captured += 1

                    # ── optional cleanup ──────────────────────────────────────
                    if delete_downloads:
                        ok, msg = ManifestCapture.cleanup_partial_download(
                            new_file.path, game.game_folder.path
                        )
                        self.log(
                            f"INFO: Cleanup — {msg}",
                            tag="INFO" if ok else "WARNING"
                        )

                # ── summary ───────────────────────────────────────────────────
                self.log(f"\n{'─'*50}", tag="sep")
                self.log(
                    f"Capture complete -- {captured} captured, {skipped} skipped.",
                    tag="SUCCESS"
                )
                if captured > 0:
                    self.log(
                        "INFO: Run 'Relink Games' now so the launcher recognises the newly captured manifests.",
                        tag="INFO"
                    )

            except SystemExit:
                self.log("INFO: Operation was cancelled.", tag="WARNING")
            except Exception as e:
                self.log(f"ERROR: {e}", tag="ERROR")
            finally:
                self._set_buttons_state(True)

        self._worker = threading.Thread(target=_thread, daemon=True)
        self._worker.start()

    # ── fix manifest link ──────────────────────────────────────────────────────

    def _run_fix_manifest(self):
        """Lists all launcher manifests and lets the user remap any one
        to the correct game folder, overwriting the wrong install path in place."""
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Busy", "An operation is already running.", parent=self)
            return

        paths = self._validate_paths()
        if not paths:
            return

        manifest_path, games_path = paths
        self._set_buttons_state(False)
        self.log(f"\n{'─'*50}", tag="sep")
        self.log("Fix Manifest Link", tag="STEP")
        self.log(f"{'─'*50}", tag="sep")

        def _thread():
            try:
                from game_data import GameDataManager
                mgr = GameDataManager(manifest_path, games_path)

                capturer = ManifestCapture(manifest_path, mgr._game_data_list)
                manifests = capturer.get_all_launcher_manifests()

                if not manifests:
                    self.log("INFO: No launcher manifests found in the Manifests folder.",
                             tag="INFO")
                    return

                self.log(f"INFO: Found {len(manifests)} launcher manifest(s).", tag="INFO")

                result = self._blocking_dialog_ask(
                    lambda: _FixManifestDialog(self, manifests, mgr._game_data_list).result
                )

                if result is None:
                    self.log("INFO: Fix cancelled.", tag="WARNING")
                    return

                item_path, new_folder = result
                display = ManifestCapture.read_display_name(item_path)
                ok, msg = ManifestCapture.fix_manifest_link(item_path, new_folder)

                if ok:
                    self.log(f"INFO: Fixed '{display or os.path.basename(item_path)}'.",
                             tag="INFO")
                    self.log(f"      New location: {new_folder}", tag="SUCCESS")
                    self.log(f"      {msg}", tag="SUCCESS")
                    self.log(
                        "INFO: Restart the Epic Games Launcher to apply the change.",
                        tag="INFO"
                    )
                else:
                    self.log(f"ERROR: {msg}", tag="ERROR")

            except Exception as e:
                self.log(f"ERROR: {e}", tag="ERROR")
            finally:
                self._set_buttons_state(True)

        self._worker = threading.Thread(target=_thread, daemon=True)
        self._worker.start()

    # ── link missing manifests ────────────────────────────────────────────────

    def _run_link_manifests(self):
        """
        Finds .item files stuck in Manifests\\Pending\\, lets the user confirm
        which game folder each one belongs to, then rewrites the install paths
        and moves each file into Manifests\\ so Epic Launcher detects the game.
        """
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Busy", "An operation is already running.",
                                   parent=self)
            return

        paths = self._validate_paths()
        if not paths:
            return

        manifest_path, games_path = paths
        self._set_buttons_state(False)
        self.log(f"\n{'─'*50}", tag="sep")
        self.log("Link Missing Manifests", tag="STEP")
        self.log(f"{'─'*50}", tag="sep")

        def _thread():
            try:
                from game_data import GameDataManager
                mgr = GameDataManager(manifest_path, games_path)

                capturer = ManifestCapture(manifest_path, mgr._game_data_list)
                pending  = capturer.get_pending_manifests()

                if not pending:
                    self.log(
                        "INFO: No pending manifests found. "
                        "Run 'Capture Missing Manifests' first.",
                        tag="INFO"
                    )
                    return

                self.log(
                    f"INFO: Found {len(pending)} pending manifest(s) to link:",
                    tag="INFO"
                )
                for p in pending:
                    self.log(f"  -  {p.name}", tag="INFO")

                linked  = 0
                skipped = 0

                for index, item in enumerate(pending, start=1):
                    display = ManifestCapture.read_display_name(item.path)
                    self.log(
                        f"\n[{index}/{len(pending)}]  {display or item.name}",
                        tag="STEP"
                    )

                    action, game_folder_path = self._blocking_dialog_ask(
                        lambda d=display, fn=item.name, idx=index, tot=len(pending): _LinkMatchDialog(
                            self, d, fn, mgr._game_data_list, idx, tot
                        ).result
                    )

                    if action == "abort":
                        self.log("WARNING: Linking aborted by user.", tag="WARNING")
                        break

                    if action == "skip":
                        self.log(f"INFO: Skipped '{display or item.name}'.",
                                 tag="WARNING")
                        skipped += 1
                        continue

                    # action == "link"
                    ok, msg = ManifestCapture.link_pending_manifest(
                        item.path, game_folder_path, manifest_path
                    )
                    if ok:
                        self.log(f"INFO: Linked '{display or item.name}' ->",
                                 tag="INFO")
                        self.log(f"      {game_folder_path}", tag="INFO")
                        self.log(f"      {msg}", tag="SUCCESS")
                        linked += 1
                    else:
                        self.log(f"ERROR: {msg}", tag="ERROR")
                        skipped += 1

                self.log(f"\n{'─'*50}", tag="sep")
                self.log(
                    f"Link complete -- {linked} linked, {skipped} skipped.",
                    tag="SUCCESS" if linked > 0 else "WARNING"
                )
                if linked > 0:
                    self.log(
                        "INFO: Restart the Epic Games Launcher -- "
                        "it should now detect your linked games.",
                        tag="INFO"
                    )

            except Exception as e:
                self.log(f"ERROR: {e}", tag="ERROR")
            finally:
                self._set_buttons_state(True)

        self._worker = threading.Thread(target=_thread, daemon=True)
        self._worker.start()

    # ── exit ──────────────────────────────────────────────────────────────────

    def _on_exit(self):
        builtins.print = self._real_print
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    run()
