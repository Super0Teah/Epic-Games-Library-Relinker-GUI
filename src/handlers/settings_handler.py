import os
import json
import webview
from game_data import GameDataManager
class SettingsHandler:
    import sys
    _EXE_PATH = os.path.dirname(sys.executable) if hasattr(sys, '_MEIPASS') else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_FILE: str = os.path.join(_EXE_PATH, "relinker_config.json")
    def get_initial_paths(self) -> dict:
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
    def save_settings(self, manifest_path: str, games_path: str, use_default: bool):
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
    def browse_directory(self, title: str) -> str:
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