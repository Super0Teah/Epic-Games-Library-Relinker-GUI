import json
import threading
import traceback
import os
import subprocess
import datetime
class PollingHandler:
    def _init_polling(self):
        self._log_queue   = []
        self._modal_queue = []
        import builtins
        self._real_print = builtins.print
        builtins.print   = self._intercepted_print
    def _intercepted_print(self, *args, **kwargs):
        msg = " ".join(str(a) for a in args)
        self._real_print(*args, **kwargs)
        if threading.current_thread() != self._worker:
            return
        self._log(msg)
    def _log(self, message: str, tag: str = None):
        if not tag:
            tag = "INFO"
            for prefix in ("ERROR", "WARNING", "INFO", "SUCCESS", "STEP"):
                if prefix in message.upper():
                    tag = prefix
                    break
        self._log_queue.append({"text": message, "tag": tag})
    def warn_user(self, msg: str):
        self._log(f"WARNING: {msg}", "WARNING")
    def _log_exception(self, context: str, exc: Exception, debug_mode: bool = False):
        self._log(f"ERROR: {context}: {exc}", "ERROR")
        if debug_mode:
            err_trace = traceback.format_exc()
            self._log("--- DEBUG TRACEBACK ---", "WARNING")
            self._log(err_trace, "WARNING")
            try:
                with open("relinker_debug.log", "a", encoding="utf-8") as f:
                    f.write(err_trace + "\n")
                self._log("INFO: Traceback written to relinker_debug.log", "INFO")
            except Exception:
                pass
    def get_logs(self) -> str:
        if not self._log_queue:
            return "[]"
        logs = self._log_queue.copy()
        self._log_queue.clear()
        return json.dumps(logs)
    def get_modal(self) -> str:
        if not self._modal_queue:
            return "[]"
        req = self._modal_queue.copy()
        self._modal_queue.clear()
        return json.dumps(req)
    def show_alert(self, msg: str):
        self._modal_queue.append({"type": "alert", "msg": msg})
    def export_log(self, log_text: str) -> bool:
        try:
            import sys
            _EXE_PATH = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(_EXE_PATH, "logs")
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
        try:
            import sys
            _EXE_PATH = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(_EXE_PATH, "logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            os.startfile(log_dir)
        except Exception as exc:
            self.warn_user(f"Failed to open log folder: {exc}")
    def get_readme(self) -> str:
        try:
            import sys
            if hasattr(sys, '_MEIPASS'):
                path = os.path.join(sys._MEIPASS, "README.md")
            else:
                _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                path = os.path.join(_ROOT, "README.md")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "README.md not found."