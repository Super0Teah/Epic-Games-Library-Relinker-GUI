"""
manifest_capture.py
-------------------
Backend logic for the "Capture Missing Manifests" feature.

Workflow (per game):
  1. User triggers a fresh download of the game in Epic Launcher.
  2. Epic writes a new .item file to the Manifests folder within ~10 seconds.
  3. We detect that new file by diffing directory snapshots.
  4. We read DisplayName / AppName from the JSON to confirm which game it is.
"""

import os
import json
import time
import shutil

from file_management import FileDirectory
from game_data import GameData, GameDataManager


# ─────────────────────────────────────────────────────────────────────────────

class ManifestCapture:
    """Identifies games missing launcher manifests and watches for new ones."""

    POLL_INTERVAL: float  = 0.5    # seconds between directory polls
    WATCH_TIMEOUT: float  = 300.0  # seconds to wait before giving up (5 min)
    PENDING_FOLDER_NAME: str = "Pending"  # Epic stages new .item files here first

    def __init__(
        self,
        launcher_manifest_folder: str,
        game_data_list: list[GameData],
    ) -> None:
        self._launcher_manifest_folder = launcher_manifest_folder
        self._game_data_list = game_data_list

    # ── Finding missing games ────────────────────────────────────────────────

    def get_games_missing_manifests(self) -> list[GameData]:
        """
        Returns GameData entries whose .egstore manifest has no matching
        .item file in the launcher manifests folder.
        """
        existing = self._get_launcher_manifest_names()
        missing: list[GameData] = []

        for game_data in self._game_data_list:
            has_match = any(
                gm.get_name_raw() in existing
                for gm in game_data.manifest_file_list
            )
            if not has_match:
                missing.append(game_data)

        return missing

    def _get_launcher_manifest_names(self) -> set[str]:
        """Base-names (no extension) of all .item files currently in the folder."""
        try:
            return {
                os.path.splitext(e.name)[0]
                for e in os.scandir(self._launcher_manifest_folder)
                if e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)
            }
        except OSError:
            return set()

    # ── Directory snapshot + polling ─────────────────────────────────────────

    def _scan_all_item_files(self) -> dict[str, str]:
        """
        Scans BOTH the main Manifests folder and the Pending subfolder for
        .item files.  Returns a dict of  {unique_key: absolute_path}  where
        unique_key = "<subfolder_or_root>/<filename>" to avoid key collisions.
        """
        result: dict[str, str] = {}
        folders_to_scan = [self._launcher_manifest_folder]

        pending = os.path.join(self._launcher_manifest_folder, self.PENDING_FOLDER_NAME)
        if os.path.isdir(pending):
            folders_to_scan.append(pending)

        for folder in folders_to_scan:
            rel = os.path.relpath(folder, self._launcher_manifest_folder)  # "." or "Pending"
            try:
                for e in os.scandir(folder):
                    if e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE):
                        key = f"{rel}/{e.name}"
                        result[key] = e.path
            except OSError:
                pass

        return result

    def take_snapshot(self) -> set[str]:
        """
        Returns the current set of unique keys for all .item files found in
        the Manifests folder AND the Pending subfolder.
        Call this BEFORE the user starts a download.
        """
        return set(self._scan_all_item_files().keys())

    def wait_for_new_manifest(
        self,
        snapshot: set[str],
        progress_callback=None,   # called every poll tick with elapsed seconds
        cancel_flag=None,         # threading.Event – set it to abort early
    ) -> FileDirectory | None:
        """
        Polls BOTH the Manifests folder and Manifests\\Pending\\ until a new
        .item file appears that was not in `snapshot`.
        Returns its FileDirectory, or None on timeout/cancel.
        """
        elapsed = 0.0

        while elapsed < self.WATCH_TIMEOUT:

            if cancel_flag and cancel_flag.is_set():
                return None

            time.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL

            if progress_callback:
                progress_callback(elapsed)

            current = self._scan_all_item_files()  # {key: path}
            new_keys = set(current.keys()) - snapshot

            if new_keys:
                key  = next(iter(new_keys))
                path = current[key]
                name = os.path.basename(path)
                return FileDirectory(name, path)

        return None  # timed out

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def read_display_name(item_path: str) -> str:
        """
        Reads the human-readable game name from a launcher .item JSON file.
        Returns an empty string if the file can't be parsed.
        """
        try:
            with open(item_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Epic uses DisplayName; fall back to AppName
            return data.get("DisplayName") or data.get("AppName") or ""
        except Exception:
            return ""

    @staticmethod
    def cleanup_partial_download(item_path: str, known_game_path: str) -> tuple[bool, str]:
        """
        After capturing a manifest, removes the partial game data Epic downloaded.

        Reads InstallLocation from the .item file:
          - If different from known_game_path → deletes the entire partial folder.
          - If same (unusual edge case) → only removes the staging (bps) subfolder.

        Returns (success: bool, message: str).
        """
        try:
            with open(item_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            install_loc = data.get("InstallLocation", "").strip()
            staging_loc = data.get("StagingLocation", "").strip()

            if not install_loc:
                return False, "Could not read InstallLocation from manifest."

            install_norm = os.path.normpath(install_loc)
            known_norm   = os.path.normpath(known_game_path)

            if install_norm.lower() != known_norm.lower():
                # Epic downloaded to a brand-new location — safe to delete entirely
                if os.path.exists(install_norm):
                    shutil.rmtree(install_norm, ignore_errors=True)
                    return True, f"Deleted partial download folder: {install_norm}"
                return True, "Partial download folder did not exist (nothing to delete)."
            else:
                # Same as the known game folder — only remove staging area
                if staging_loc and os.path.exists(staging_loc):
                    shutil.rmtree(staging_loc, ignore_errors=True)
                    return True, f"Deleted staging folder: {staging_loc}"
                return True, "No staging folder found (nothing to delete)."

        except Exception as exc:
            return False, f"Cleanup error: {exc}"

    # ── Linking pending manifests ─────────────────────────────────────────────

    def get_pending_manifests(self) -> list[FileDirectory]:
        """
        Returns all .item files currently sitting in Manifests\\Pending\\.
        These are manifests Epic created but never moved to the root because
        the download was cancelled before it finished.
        """
        pending = os.path.join(
            self._launcher_manifest_folder, self.PENDING_FOLDER_NAME
        )
        result: list[FileDirectory] = []
        if os.path.isdir(pending):
            for e in os.scandir(pending):
                if e.is_file() and e.name.endswith(
                    GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE
                ):
                    result.append(FileDirectory(e.name, e.path))
        return result

    @staticmethod
    def link_pending_manifest(
        item_path: str,
        game_folder_path: str,
        manifests_root: str,
    ) -> tuple[bool, str]:
        """
        Rewrites InstallLocation / ManifestLocation / StagingLocation inside
        the .item file to point at game_folder_path, then moves the file from
        Pending\\ into manifests_root so Epic Launcher can detect the game.

        Returns (success: bool, message: str).
        """
        try:
            egstore = os.path.join(game_folder_path, GameDataManager.GAME_MANIFEST_FOLDER_NAME)
            staging = os.path.join(egstore, GameDataManager.STAGING_FOLDER_NAME)

            with open(item_path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["InstallLocation"]  = game_folder_path.replace('\\', '/')
                data["ManifestLocation"] = egstore.replace('\\', '/')
                data["StagingLocation"]  = staging.replace('\\', '/')
                data["bIsIncompleteInstall"] = False
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()

            dest = os.path.join(manifests_root, os.path.basename(item_path))
            
            # Sync the UUID inside .egstore
            sync_res = ManifestCapture._sync_egstore_files(item_path, game_folder_path)
            
            shutil.move(item_path, dest)
            return True, f"Moved to: {dest}" + sync_res

        except Exception as exc:
            return False, f"Error: {exc}"

    def get_all_launcher_manifests(self) -> list[dict]:
        """
        Returns details about every .item file in the Manifests root folder
        AND Pending folder. Each entry is a dict with keys:
            file           – FileDirectory(name, path)
            display_name   – str from DisplayName / AppName, or ""
            install_location – str from InstallLocation, or "(unknown)"
        """
        result: list[dict] = []
        folders_to_scan = [self._launcher_manifest_folder]
        pending = os.path.join(self._launcher_manifest_folder, self.PENDING_FOLDER_NAME)
        if os.path.isdir(pending):
            folders_to_scan.append(pending)
            
        for folder in folders_to_scan:
            try:
                for e in os.scandir(folder):
                    if not (e.is_file() and e.name.endswith(
                        GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE
                    )):
                        continue
                    display = self.read_display_name(e.path)
                    try:
                        with open(e.path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        install_loc = data.get("InstallLocation", "(unknown)")
                    except Exception:
                        install_loc = "(could not read)"
                    
                    # Prefix Pending items so users can see
                    prefix = "[PENDING] " if os.path.basename(folder).lower() == "pending" else ""
                    
                    result.append({
                        "file":             FileDirectory(e.name, e.path),
                        "display_name":     prefix + display,
                        "install_location": install_loc,
                    })
            except OSError:
                pass
        return result

    @staticmethod
    def _sync_egstore_files(item_path: str, game_folder_path: str) -> str:
        """Smarter Sync so DLC manifests aren't destroyed."""
        egstore = os.path.join(game_folder_path, GameDataManager.GAME_MANIFEST_FOLDER_NAME)
        if not os.path.exists(egstore):
            return " (No .egstore found to sync)"
            
        new_basename = os.path.splitext(os.path.basename(item_path))[0]
        pending_dir = os.path.join(egstore, "Pending")
        sync_count = 0
        error_msg = ""
        
        # Phase 1: Safely pull newly generated manifests out of Pending 
        if os.path.exists(pending_dir):
            for ext in [".manifest", ".manc", ".chunkdb", ".bms"]:
                try:
                    for e in os.scandir(pending_dir):
                        if e.is_file() and e.name.endswith(ext):
                            new_path = os.path.join(egstore, e.name)
                            if e.path != new_path:
                                shutil.move(e.path, new_path)
                                sync_count += 1
                except Exception as exc:
                    error_msg = str(exc)

        # Phase 2: If we still need to forcefully rename old root manifests, ONLY do it if it's safe (e.g., no DLCs)
        try:
            for ext in [".manifest", ".manc", ".chunkdb", ".bms"]:
                existing_files = [e for e in os.scandir(egstore) if e.is_file() and e.name.endswith(ext)]
                # If there's multiple (meaning DLCs exist), DO NOT blindly rename them all!
                # If there's exactly one, and it's not the new UUID, it's safe to rename to the new UUID.
                if len(existing_files) == 1:
                    e = existing_files[0]
                    new_path = os.path.join(egstore, new_basename + ext)
                    if e.path != new_path:
                        shutil.move(e.path, new_path)
                        sync_count += 1
        except Exception as exc:
            pass

        # Cleanup .item files: Only delete the exact old one if we know it, or avoid wiping all
        try:
            dest_item = os.path.join(egstore, os.path.basename(item_path))
            shutil.copy2(item_path, dest_item)
            sync_count += 1
        except Exception:
            pass

        if error_msg:
            return f" (Synced {sync_count} tracking files, Warning: {error_msg})"
        return f" (Synced {sync_count} tracking files safely)"

    @staticmethod
    def fix_manifest_link(
        item_path: str,
        new_game_folder_path: str,
        manifest_root_path: str
    ) -> tuple[bool, str]:
        """
        Rewrites InstallLocation / ManifestLocation / StagingLocation inside
        an existing .item file (already in Manifests root) to point to a
        different game folder. If the item is in Pending, moves it to root.
        
        It also syncs the UUID of the game manifest files!

        Returns (success: bool, message: str).
        """
        try:
            egstore = os.path.join(
                new_game_folder_path, GameDataManager.GAME_MANIFEST_FOLDER_NAME
            )
            staging = os.path.join(egstore, GameDataManager.STAGING_FOLDER_NAME)

            with open(item_path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["InstallLocation"]  = new_game_folder_path.replace('\\', '/')
                data["ManifestLocation"] = egstore.replace('\\', '/')
                data["StagingLocation"]  = staging.replace('\\', '/')
                data["bIsIncompleteInstall"] = False
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
            
            # Sync the UUID inside .egstore
            sync_res = ManifestCapture._sync_egstore_files(item_path, new_game_folder_path)

            msg = f"Updated install location to: {new_game_folder_path}" + sync_res
            
            # If it's in pending, move it out so launcher detects it
            if os.path.basename(os.path.dirname(item_path)).lower() == "pending":
                dest = os.path.join(manifest_root_path, os.path.basename(item_path))
                shutil.move(item_path, dest)
                msg += f" \n(Moved from Pending to Root Manifests)"

            return True, msg

        except Exception as exc:
            return False, f"Error: {exc}"
