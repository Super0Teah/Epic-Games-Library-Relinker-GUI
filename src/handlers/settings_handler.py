"""
SettingsHandler
---------------
Manages application settings: loading from disk, saving to disk,
directory browsing, and the Reset / Restore actions exposed to the
frontend.
"""

import os
import json
import webview

from game_data import GameDataManager


class SettingsHandler:
    """Mixin — depends on PollingHandler (_log, warn_user)."""

    CONFIG_FILE: str = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "relinker_config.json"
    )

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_initial_paths(self) -> dict:
        """
        Returns the saved settings config as a plain dict (pywebview
        serialises it to JSON automatically for the JS caller).

        Falls back to sane defaults when no config file exists.
        """
        config = {
            "manifestPath": GameDataManager.DEFAULT_MANIFESTS_PATH,
            "gamesPath":    "",
            "useDefault":   True,
        }
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                config.update(saved)
            except Exception as exc:
                self.warn_user(f"Could not read saved settings: {exc}")
        return config

    # ── Write ────────────────────────────────────────────────────────────────

    def save_settings(self, manifest_path: str, games_path: str, use_default: bool):
        """Persists the three path settings to the JSON config file."""
        config = {
            "manifestPath": manifest_path,
            "gamesPath":    games_path,
            "useDefault":   use_default,
        }
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
        except Exception as exc:
            self.warn_user(f"Failed to save settings: {exc}")

    # ── Browse ───────────────────────────────────────────────────────────────

    def browse_directory(self, title: str) -> str:
        """
        Opens a native folder-picker dialog.
        Returns the selected path string, or "" on cancel / error.
        """
        if not self._window:
            return ""
        try:
            dialog_type = (
                getattr(webview, "FileDialog", webview).FOLDER
                if hasattr(webview, "FileDialog")
                else webview.FOLDER_DIALOG
            )
            result = self._window.create_file_dialog(dialog_type, allow_multiple=False)
            if result and len(result) > 0:
                return os.path.normpath(result[0])
        except AttributeError:
            try:
                result = self._window.create_file_dialog(
                    webview.FOLDER_DIALOG, allow_multiple=False
                )
                if result and len(result) > 0:
                    return os.path.normpath(result[0])
            except Exception as exc:
                self.warn_user(f"Failed to browse directory: {exc}")
        except Exception as exc:
            self.warn_user(f"Failed to browse directory: {exc}")
        return ""
