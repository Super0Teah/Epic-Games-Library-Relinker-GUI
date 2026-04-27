"""
PollingHandler
--------------
Provides the low-level log/modal queue, the print interceptor,
and the warn_user helper.

All other handlers depend on the three primitives defined here:
    _log(message, tag)
    warn_user(message)
    _log_queue / _modal_queue
"""

import json
import threading
import traceback
import os
import subprocess
import datetime


class PollingHandler:
    """Mixin — initialised by PyWebViewApi.__init__."""

    # ── Init (called by the concrete class) ──────────────────────────────────

    def _init_polling(self):
        self._log_queue   = []
        self._modal_queue = []

        # Intercept print() calls that come from the worker thread so they
        # automatically appear in the terminal log.
        import builtins
        self._real_print = builtins.print
        builtins.print   = self._intercepted_print

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _intercepted_print(self, *args, **kwargs):
        """Forwards prints from the background worker thread to the log queue."""
        msg = " ".join(str(a) for a in args)
        self._real_print(*args, **kwargs)
        if threading.current_thread() != self._worker:
            return
        self._log(msg)

    def _log(self, message: str, tag: str = None):
        """
        Appends a structured log entry to _log_queue.

        Auto-detects tag from common prefixes (ERROR, WARNING, INFO, SUCCESS, STEP)
        when no explicit tag is supplied.
        """
        if not tag:
            tag = "INFO"
            for prefix in ("ERROR", "WARNING", "INFO", "SUCCESS", "STEP"):
                if prefix in message.upper():
                    tag = prefix
                    break
        self._log_queue.append({"text": message, "tag": tag})

    def warn_user(self, msg: str):
        """Logs a WARNING-tagged message."""
        self._log(f"WARNING: {msg}", "WARNING")

    def _log_exception(self, context: str, exc: Exception, debug_mode: bool = False):
        """
        Logs a caught exception.  When debug_mode is True, also logs the full
        traceback and writes it to relinker_debug.log.
        """
        self._log(f"ERROR: {context}: {exc}", "ERROR")
        if debug_mode:
            err_trace = traceback.format_exc()
            self._log("--- DEBUG TRACEBACK ---", "WARNING")
            self._log(err_trace, "WARNING")
            try:
                with open("relinker_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"# {context}\n{err_trace}\n")
                self._log("INFO: Traceback written to relinker_debug.log", "INFO")
            except Exception:
                pass

    # ── Polling endpoints (called from JS via pywebview) ─────────────────────

    def get_logs(self) -> str:
        """Returns and clears the pending log queue as a JSON array."""
        if not self._log_queue:
            return "[]"
        logs = self._log_queue.copy()
        self._log_queue.clear()
        return json.dumps(logs)

    def get_modal(self) -> str:
        """Returns and clears the pending modal queue as a JSON array."""
        if not self._modal_queue:
            return "[]"
        req = self._modal_queue.copy()
        self._modal_queue.clear()
        return json.dumps(req)

    def show_alert(self, msg: str):
        """Queues a generic alert modal."""
        self._modal_queue.append({"type": "alert", "msg": msg})

    # ── Log Export & Folders ──────────────────────────────────────────────────

    def export_log(self, log_text: str) -> bool:
        """Saves the provided text to logs/relinker.log and returns success."""
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "relinker.log")
            
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"Epic Games Relinker GUI Log Export\n")
                f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("-" * 50 + "\n\n")
                f.write(log_text)
            
            self._log(f"SUCCESS: Log saved to {log_path}", "SUCCESS")
            return True
        except Exception as exc:
            self.warn_user(f"Failed to export log: {exc}")
            return False

    def open_log_folder(self):
        """Opens the logs directory in Explorer."""
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            os.startfile(log_dir)
        except Exception as exc:
            self.warn_user(f"Failed to open log folder: {exc}")

    def get_readme(self) -> str:
        """Returns the contents of README.md for the Home screen."""
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "README.md")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "README.md not found."

