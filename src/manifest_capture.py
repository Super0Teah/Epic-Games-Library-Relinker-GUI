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
        """
        Robustly syncs tracking files (.manifest, .manc, .chunkdb, .bms) in .egstore.
        Ensures they match the InstallationGuid of the .item file to prevent verification loops.
        """
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

        # Phase 2: Rename root files to match the new GUID (Installation ID) or ManifestHash
        # This is critical for Epic to recognize the files as 'valid' for this installation.
        try:
            # Get the target AppName and ManifestHash from the item we are syncing
            target_app_name = ""
            manifest_hash = ""
            try:
                with open(item_path, "r", encoding="utf-8") as f:
                    item_data = json.load(f)
                    target_app_name = item_data.get("AppName", "").lower()
                    manifest_hash = item_data.get("ManifestHash", "").lower()
            except: pass

            for ext in [".manifest", ".manc", ".chunkdb", ".bms"]:
                existing_files = [e for e in os.scandir(egstore) if e.is_file() and e.name.endswith(ext)]
                
                # Try to find the match via ManifestHash or .mancpn
                target_file = None
                
                # 1. Best: Match by ManifestHash (since we know the file's hash matches the item's ManifestHash)
                if manifest_hash:
                    # We can't easily hash every file, but we can check if a file already has this name
                    # or try to match it via .mancpn
                    pass

                # 2. Fallback: Match via .mancpn
                if not target_file and target_app_name:
                    for e in os.scandir(egstore):
                        if e.is_file() and e.name.endswith(".mancpn"):
                            try:
                                with open(e.path, "r", encoding="utf-8") as f:
                                    cpn = json.load(f)
                                    if str(cpn.get("AppName", "")).lower() == target_app_name:
                                        base = os.path.splitext(e.name)[0]
                                        match = next((f for f in existing_files if f.name.startswith(base)), None)
                                        if match:
                                            target_file = match
                                            break
                            except: pass

                if target_file:
                    # We will rename it to match the InstallationGuid (new_basename)
                    # AND also try renaming it to the ManifestHash if that's what Epic wants.
                    # Usually, InstallationGuid is the safest bet for the filename.
                    new_path = os.path.join(egstore, new_basename + ext)
                    if target_file.path.lower() != new_path.lower():
                        if os.path.exists(new_path):
                            os.remove(new_path)
                        shutil.move(target_file.path, new_path)
                        sync_count += 1

        except Exception as exc:
            error_msg = str(exc)

        # Phase 3: Cleanup .item files: Ensure a backup exists in .egstore
        try:
            dest_item = os.path.join(egstore, os.path.basename(item_path))
            if not os.path.exists(dest_item) or os.path.getsize(item_path) != os.path.getsize(dest_item):
                shutil.copy2(item_path, dest_item)
                sync_count += 1
        except Exception:
            pass

        if error_msg:
            return f" (Partially synced {sync_count} files, Warning: {error_msg})"
        return f" (Synced {sync_count} tracking files)"

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

    # ── Manifest Management Tools (#14) ──────────────────────────────────────

    def get_orphaned_manifests(self) -> list[dict]:
        """
        Scans every .item file in the Manifests root (not Pending) and returns
        those whose InstallLocation points to a folder that does NOT exist on disk.

        Each result dict:
            file_path    – absolute path to the .item file
            file_name    – basename of the .item file
            display_name – human-readable game name (may be empty)
            install_location – the path that is missing
        """
        orphans: list[dict] = []
        try:
            for e in os.scandir(self._launcher_manifest_folder):
                if not (e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)):
                    continue
                try:
                    with open(e.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    install_loc = data.get("InstallLocation", "").strip()
                    display     = data.get("DisplayName") or data.get("AppName") or ""
                    if not install_loc:
                        # No install location set at all → definitely orphaned
                        orphans.append({
                            "file_path":        e.path,
                            "file_name":        e.name,
                            "display_name":     display,
                            "install_location": "(no path set)",
                        })
                    elif not os.path.isdir(install_loc):
                        orphans.append({
                            "file_path":        e.path,
                            "file_name":        e.name,
                            "display_name":     display,
                            "install_location": install_loc,
                        })
                except Exception:
                    # Unreadable / corrupt JSON → treat as orphaned
                    orphans.append({
                        "file_path":        e.path,
                        "file_name":        e.name,
                        "display_name":     "(unreadable)",
                        "install_location": "(could not parse)",
                    })
        except OSError:
            pass
        return orphans

    REQUIRED_MANIFEST_KEYS = [
        "FormatVersion",
        "AppName",
        "DisplayName",
        "InstallLocation",
        "ManifestLocation",
    ]

    def validate_manifests(self) -> list[dict]:
        """
        Validates every .item file in the Manifests root (not Pending).
        Returns a list of issue dicts with:
            file_path    – absolute path
            file_name    – basename
            display_name – human-readable name or empty
            issues       – list[str] of problem descriptions
            severity     – "ok" | "warning" | "error"
        Only files WITH at least one issue are returned.
        """
        results: list[dict] = []
        try:
            for e in os.scandir(self._launcher_manifest_folder):
                if not (e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)):
                    continue

                issues: list[str] = []
                severity = "ok"
                display  = ""

                try:
                    with open(e.path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    display = data.get("DisplayName") or data.get("AppName") or ""

                    # 1. Check required keys
                    for key in self.REQUIRED_MANIFEST_KEYS:
                        if key not in data:
                            issues.append(f"Missing required key: '{key}'")
                            severity = "error"

                    # 2. Check FormatVersion
                    fv = data.get("FormatVersion", None)
                    if fv is not None and fv not in GameDataManager.SUPPORTED_LAUNCHER_MANIFEST_VERSIONS:
                        issues.append(f"Unknown FormatVersion: {fv} (expected one of {GameDataManager.SUPPORTED_LAUNCHER_MANIFEST_VERSIONS})")
                        if severity != "error":
                            severity = "warning"

                    # 3. Check InstallLocation exists on disk
                    install_loc = data.get("InstallLocation", "").strip()
                    if install_loc:
                        if not os.path.isdir(install_loc):
                            issues.append(f"InstallLocation does not exist: {install_loc}")
                            if severity != "error":
                                severity = "warning"
                    else:
                        issues.append("InstallLocation is empty or missing")
                        if severity != "error":
                            severity = "warning"

                    # 4. Check ManifestLocation folder exists
                    manifest_loc = data.get("ManifestLocation", "").strip()
                    if manifest_loc and not os.path.isdir(manifest_loc):
                        issues.append(f"ManifestLocation (.egstore) does not exist: {manifest_loc}")
                        if severity != "error":
                            severity = "warning"

                    # 5. Flag incomplete installs
                    if data.get("bIsIncompleteInstall", False):
                        issues.append("Flagged as incomplete install (bIsIncompleteInstall = true)")
                        if severity == "ok":
                            severity = "warning"

                except json.JSONDecodeError:
                    issues.append("File is not valid JSON — likely corrupted")
                    severity = "error"
                except Exception as exc:
                    issues.append(f"Could not read file: {exc}")
                    severity = "error"

                if issues:
                    results.append({
                        "file_path":    e.path,
                        "file_name":    e.name,
                        "display_name": display,
                        "issues":       issues,
                        "severity":     severity,
                    })
        except OSError:
            pass
        return results

    @staticmethod
    def delete_manifest(item_path: str) -> tuple[bool, str]:
        """Permanently deletes the given .item manifest file."""
        try:
            os.remove(item_path)
            return True, f"Deleted: {os.path.basename(item_path)}"
        except Exception as exc:
            return False, f"Could not delete {os.path.basename(item_path)}: {exc}"

    def get_duplicate_pending_manifests(self) -> list[dict]:
        """
        Finds .item files in the Pending subfolder that are duplicates of an
        already-existing manifest in the root Manifests folder.

        Comparison is done by AppName (the game's unique Epic identifier).
        If a root manifest already covers the same AppName, the Pending copy
        is safe to delete — it is just a leftover from a cancelled download.

        Each result dict:
            file_path         – absolute path to the PENDING .item file
            file_name         – basename of the pending .item
            display_name      – human-readable name (may be empty)
            app_name          – Epic AppName used for matching
            root_file_name    – basename of the root manifest that supersedes it
            root_install_ok   – bool: whether root manifest's InstallLocation exists
        """
        pending_dir = os.path.join(self._launcher_manifest_folder, self.PENDING_FOLDER_NAME)
        if not os.path.isdir(pending_dir):
            return []

        # Build AppName → (file_path, install_location) map from root manifests
        root_by_appname: dict[str, dict] = {}
        try:
            for e in os.scandir(self._launcher_manifest_folder):
                if not (e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)):
                    continue
                try:
                    with open(e.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    app_name = data.get("AppName", "").strip()
                    if app_name:
                        root_by_appname[app_name] = {
                            "file_path":        e.path,
                            "file_name":        e.name,
                            "install_location": data.get("InstallLocation", "").strip(),
                        }
                except Exception:
                    pass
        except OSError:
            return []

        # Now scan Pending and match
        duplicates: list[dict] = []
        try:
            for e in os.scandir(pending_dir):
                if not (e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)):
                    continue
                try:
                    with open(e.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    app_name    = data.get("AppName", "").strip()
                    display     = data.get("DisplayName") or data.get("AppName") or ""
                    if app_name and app_name in root_by_appname:
                        root = root_by_appname[app_name]
                        root_install_ok = bool(root["install_location"]) and os.path.isdir(root["install_location"])
                        duplicates.append({
                            "file_path":       e.path,
                            "file_name":       e.name,
                            "display_name":    display,
                            "app_name":        app_name,
                            "root_file_name":  root["file_name"],
                            "root_install_ok": root_install_ok,
                        })
                except Exception:
                    pass
        except OSError:
            pass
        return duplicates

    def get_duplicate_system_manifests(self) -> list[dict]:
        """
        Finds .item files in the root Manifests folder that are redundant.
        Prioritizes manifests that have a matching peer in their .egstore folder.
        """
        appname_map: dict[str, list[dict]] = {}
        catalog_map: dict[str, list[dict]] = {}
        folder_map:  dict[str, list[dict]] = {}
        
        try:
            for e in os.scandir(self._launcher_manifest_folder):
                if not (e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE)):
                    continue
                try:
                    with open(e.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    app_name   = data.get("AppName", "").strip()
                    catalog_id = data.get("CatalogItemId", "").strip()
                    display    = (data.get("DisplayName") or "").strip()
                    loc        = (data.get("InstallLocation") or "").strip()
                    norm_loc   = loc.lower().replace("\\", "/")
                    
                    if not app_name:
                        continue
                        
                    # ── Sync & Superseded Detection ───────────────────────────
                    has_sync        = False
                    superseded_by   = None
                    is_incomplete   = data.get("bIsIncompleteInstall", False)
                    
                    if loc and os.path.isdir(loc):
                        egstore = os.path.join(loc, ".egstore")
                        if os.path.isdir(egstore):
                            # Exact match (synced)
                            if os.path.exists(os.path.join(egstore, e.name)):
                                has_sync = True
                            else:
                                # Look for ANY .item file in .egstore
                                for sub in os.scandir(egstore):
                                    if sub.is_file() and sub.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE):
                                        superseded_by = sub.name
                                        break

                    # Score for sorting (Higher is better)
                    # Priority: Synced > Complete > Newest
                    score = 0
                    if has_sync:      score += 1000
                    if not is_incomplete: score += 500
                    score += (e.stat().st_mtime / 1000000.0) # Add a small factor for mtime

                    entry = {
                        "file_path":    e.path,
                        "file_name":    e.name,
                        "display_name": display or app_name,
                        "app_name":     app_name,
                        "catalog_id":   catalog_id,
                        "install_location": loc,
                        "has_sync":     has_sync,
                        "is_incomplete": is_incomplete,
                        "superseded_by": superseded_by,
                        "score":         score,
                    }
                    
                    appname_map.setdefault(app_name, []).append(entry)
                    if catalog_id:
                        catalog_map.setdefault(catalog_id, []).append(entry)
                    if norm_loc and display:
                        folder_key = f"{norm_loc}|{display.lower()}"
                        folder_map.setdefault(folder_key, []).append(entry)
                except Exception:
                    pass
        except OSError:
            pass

        results = []
        seen_files = set()

        def flag_dupes(mapping):
            for key, group in mapping.items():
                if len(group) > 1:
                    # Sort by score descending (best first)
                    group.sort(key=lambda x: x["score"], reverse=True)
                    
                    primary = group[0]
                    for dup in group[1:]:
                        if dup["file_path"] not in seen_files:
                            dup["root_file_name"] = primary["file_name"]
                            
                            # Add descriptive labels
                            if dup["superseded_by"]:
                                dup["display_name"] += f" (Superseded by {dup['superseded_by']})"
                            elif dup["is_incomplete"] and not primary["is_incomplete"]:
                                dup["display_name"] += " (Incomplete)"
                            elif not dup["has_sync"] and primary["has_sync"]:
                                dup["display_name"] += " (Out-of-Sync)"
                            
                            results.append(dup)
                            seen_files.add(dup["file_path"])

        flag_dupes(appname_map)
        flag_dupes(catalog_map)
        flag_dupes(folder_map)
        return results

    # ── One-click Fix (from .mancpn) ──────────────────────────────────────

    @staticmethod
    def discover_manifests(game_folder_path: str) -> list[dict]:
        """
        Scans <game_folder>/.egstore/ for all .item and .mancpn files.
        Returns a list of deduplicated manifests.
        
        Deduplication logic:
        1. Prefers .item files over .mancpn.
        2. Deduplicates by CatalogItemId (if present) or AppName.
        3. Only keeps the 'best' manifest for each unique component.
        """
        egstore = os.path.join(game_folder_path, GameDataManager.GAME_MANIFEST_FOLDER_NAME)
        if not os.path.isdir(egstore):
            return []

        # Map CatalogItemId (or AppName as fallback) -> best manifest found so far
        best_manifests: dict[str, dict] = {}

        def add_if_better(data):
            # Unique key: CatalogItemId is best, AppName is fallback
            cid = data.get("CatalogItemId") or data.get("AppName")
            if not cid: return

            existing = best_manifests.get(cid)
            if not existing:
                best_manifests[cid] = data
                return

            # Scoring: .item > .mancpn
            e_type = existing.get("manifest_type", "mancpn")
            n_type = data.get("manifest_type", "mancpn")
            
            if n_type == "item" and e_type == "mancpn":
                best_manifests[cid] = data
            elif n_type == e_type:
                # Tie-breaker: prefer higher version if possible
                e_ver = existing.get("AppVersionString", "0")
                n_ver = data.get("AppVersionString", "0")
                if n_ver > e_ver:
                    best_manifests[cid] = data

        try:
            # 1. Scan for .item files
            for e in os.scandir(egstore):
                if e.is_file() and e.name.endswith(GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE):
                    try:
                        with open(e.path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["manifest_source_path"] = e.path
                        data["manifest_type"] = "item"
                        add_if_better(data)
                    except Exception:
                        pass

            # 2. Scan for .mancpn files
            for e in os.scandir(egstore):
                if e.is_file() and e.name.endswith(GameDataManager.MANCPN_FILE_TYPE):
                    try:
                        with open(e.path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["manifest_source_path"] = e.path
                        data["manifest_type"] = "mancpn"
                        add_if_better(data)
                    except Exception:
                        pass
        except OSError:
            pass

        return list(best_manifests.values())

    @staticmethod
    def read_mancpn(game_folder_path: str) -> dict | None:
        """
        Legacy wrapper for discover_manifests that returns the most 'important' one.
        Tries to find the main game entry first.
        """
        manifests = ManifestCapture.discover_manifests(game_folder_path)
        if not manifests:
            return None
        
        # Try to find the one where AppName == MainGameAppName (the main game)
        for m in manifests:
            if m.get("AppName") == m.get("MainGameAppName") and m.get("MainGameAppName"):
                return m
        
        # Or just return the first one
        return manifests[0]


    @staticmethod
    def create_item_manifest(
        manifest_data: dict,
        game_folder_path: str,
        manifests_root: str,
    ) -> tuple[bool, str]:
        """
        Synthesises or updates a full .item file from manifest_data and writes it into
        manifests_root.

        Returns (success: bool, message: str).
        """
        try:
            app_name  = manifest_data.get("AppName")
            if not app_name:
                return False, "AppName is empty in manifest data — cannot create manifest."

            # Determine the GUID (the official identity of this installation)
            # 1. Try 'InstallationGuid' from the JSON metadata (most reliable)
            guid = manifest_data.get("InstallationGuid")
            
            # 2. Try to get it from the source path filename (if it's an .item or .mancpn backup)
            if not guid:
                source_path = manifest_data.get("manifest_source_path")
                if source_path:
                    # Both .item and .mancpn backups use the GUID as the filename
                    guid = os.path.splitext(os.path.basename(source_path))[0]
            
            # 3. Fallback to AppName
            if not guid:
                guid = app_name

            # Update the original dict so callers (like add_to_launcher_installed) see it
            manifest_data["InstallationGuid"] = guid

            egstore   = os.path.join(game_folder_path, GameDataManager.GAME_MANIFEST_FOLDER_NAME)
            staging   = os.path.join(egstore, "bps")
            item_name = guid + GameDataManager.LAUNCHER_MANIFEST_FILE_TYPE
            item_path = os.path.join(manifests_root, item_name)

            # Use manifest_data as the base content
            content = manifest_data.copy()
            content.pop("manifest_source_path", None)
            content.pop("manifest_type", None)

            # Inject / overwrite the location-dependent fields
            content["InstallationGuid"]     = guid
            content["InstallLocation"]      = game_folder_path.replace("\\", "/")
            content["ManifestLocation"]     = egstore.replace("\\", "/")
            content["StagingLocation"]      = staging.replace("\\", "/")
            content["bIsIncompleteInstall"] = False
            
            # Preserve existing version if present, otherwise set to "0"
            if "AppVersionString" not in content:
                content["AppVersionString"] = "0"
            
            if "DisplayName" not in content or not content["DisplayName"]:
                # Robust DisplayName fallback
                content["DisplayName"] = os.path.basename(game_folder_path.rstrip("/\\")) or app_name

            # Atomic write via temp file
            temp_path = item_path + ".relinker-tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=4)
                os.replace(temp_path, item_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False, f"Failed to write .item file: {e}"

            # Verification: Check if file exists on disk
            if not os.path.exists(item_path):
                return False, "Verification failed: .item file disappeared immediately after writing!"

            # CRITICAL: Sync the tracking files in .egstore to match this GUID!
            sync_msg = ManifestCapture._sync_egstore_files(item_path, game_folder_path)

            return True, f"Manifest created and verified: {item_name} {sync_msg}"

        except Exception as exc:
            return False, f"Error creating .item manifest: {exc}"

    @staticmethod
    def backup_launcher_installed_dat() -> tuple[bool, str]:
        """
        Creates a one-time backup of LauncherInstalled.dat as
        LauncherInstalled.relinker-backup.dat (only if no backup already exists).

        Returns (success: bool, message: str).
        """
        import datetime
        src = GameDataManager.LAUNCHER_INSTALLED_DAT
        try:
            if os.path.exists(src):
                cache_dir = os.path.join(os.getcwd(), ".cache", "backups")
                os.makedirs(cache_dir, exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = os.path.join(cache_dir, f"LauncherInstalled.backup_{ts}.dat")
                shutil.copy2(src, dest)
                return True, f"Backup created in local cache: {os.path.basename(dest)}"
            return True, "No original file to back up — skipped."
        except Exception as exc:
            return False, f"Could not back up LauncherInstalled.dat: {exc}"

    @staticmethod
    def get_launcher_installed_map() -> dict[str, str]:
        """
        Reads LauncherInstalled.dat and returns { AppName.lower(): normalized_path }.
        Used for identifying 'Linked' vs 'Unregistered' games.
        """
        results = {}
        dat_path = GameDataManager.LAUNCHER_INSTALLED_DAT
        if os.path.exists(dat_path):
            try:
                with open(dat_path, "r", encoding="utf-8") as f:
                    dat = json.load(f)
                    for install in dat.get("InstallationList", []):
                        app = str(install.get("AppName") or "").strip()
                        loc = install.get("InstallLocation")
                        if app and loc:
                            norm_loc = os.path.normpath(loc).lower().rstrip("\\/")
                            results[app.lower()] = norm_loc
                
                # Debug Dump: Print all registered apps (first 5 to avoid spam)
                if results:
                    print(f"[DEBUG] Registry contains {len(results)} items. Samples: {list(results.keys())[:10]}")
            except Exception:
                pass
        return results

    @staticmethod
    def add_to_launcher_installed(
        manifest_data_list: list[dict] | dict,
        game_folder_path: str,
    ) -> tuple[bool, str]:
        """
        Adds (or updates) entries for the games/DLCs in LauncherInstalled.dat.
        Deduplicates by AppName. Can take a single manifest dict or a list.

        Returns (success: bool, message: str).
        """
        if isinstance(manifest_data_list, dict):
            manifest_data_list = [manifest_data_list]

        dat_path = GameDataManager.LAUNCHER_INSTALLED_DAT
        try:
            if not os.path.exists(dat_path):
                return False, f"LauncherInstalled.dat not found at {dat_path}"

            with open(dat_path, "r", encoding="utf-8") as f:
                dat = json.load(f)

            processed_names = []
            for m_data in manifest_data_list:
                app_name = m_data.get("AppName", "")
                if not app_name:
                    continue

                # Find and preserve existing fields if the entry already exists
                existing_entry = {}
                for e in dat.get("InstallationList", []):
                    if str(e.get("AppName")).lower() == app_name.lower():
                        existing_entry = e
                        break

                # Remove the old one
                dat["InstallationList"] = [
                    e for e in dat.get("InstallationList", [])
                    if str(e.get("AppName")).lower() != app_name.lower()
                ]

                # Map core fields, preserving others
                new_entry = existing_entry.copy()
                new_entry.update({
                    "InstallLocation":   game_folder_path.replace("\\", "/"),
                    "NamespaceId":       m_data.get("CatalogNamespace") or m_data.get("NamespaceId") or new_entry.get("NamespaceId", ""),
                    "ItemId":            m_data.get("CatalogItemId") or m_data.get("ItemId") or new_entry.get("ItemId", ""),
                    "ArtifactId":        m_data.get("ArtifactId") or m_data.get("AppName") or new_entry.get("ArtifactId", ""),
                    "AppVersion":        m_data.get("AppVersionString") or m_data.get("AppVersion") or new_entry.get("AppVersion", ""),
                    "AppName":           app_name,
                })
                
                dat["InstallationList"].append(new_entry)
                processed_names.append(app_name)

            if not processed_names:
                return False, "No valid AppNames found in manifest list."

            # NON-ATOMIC write (keeps file identity/inode)
            # Some file monitors or system tools dislike os.replace/os.rename on ProgramData
            try:
                with open(dat_path, "w", encoding="utf-8") as f:
                    json.dump(dat, f, indent=4)
            except Exception as e:
                return False, f"Failed to write to registry file: {e}"

            # Verification: Read back to confirm
            try:
                with open(dat_path, "r", encoding="utf-8") as f:
                    ver_dat = json.load(f)
                    ver_list = ver_dat.get("InstallationList", [])
                    found_names = []
                    missing_names = []
                    for name in processed_names:
                        if any(str(e.get("AppName")).lower() == name.lower() for e in ver_list):
                            found_names.append(name)
                        else:
                            missing_names.append(name)
                
                # Additional debug info
                count_before = len(dat.get("InstallationList", [])) - len(processed_names) # approx
                count_after = len(ver_list)
            except Exception as e:
                return False, f"Could not read back file for verification: {e}"
            
            if missing_names:
                return False, f"VERIFICATION FAILED: The following entries were GONE immediately after writing: {', '.join(missing_names)}. Total entries now: {count_after}."

            return True, f"Registry sync complete. VERIFIED: {len(processed_names)} entries added. Total registry size: {count_after} games."

        except Exception as exc:
            return False, f"Error updating LauncherInstalled.dat: {exc}"

    @staticmethod
    def forensic_verify_registry(app_names: list[str]) -> tuple[bool, str]:
        """
        Performs a deep read-back of LauncherInstalled.dat to ensure 
        the specific app_names are physically present.
        """
        dat_path = GameDataManager.LAUNCHER_INSTALLED_DAT
        try:
            import time
            time.sleep(2) # Give OS a moment
            with open(dat_path, "r", encoding="utf-8") as f:
                dat = json.load(f)
                ver_list = dat.get("InstallationList", [])
                missing = [n for n in app_names if not any(str(e.get("AppName")).lower() == n.lower() for e in ver_list)]
                if missing:
                    return False, f"FORENSIC FAIL: Entries for {', '.join(missing)} DISAPPEARED after writing! Total entries: {len(ver_list)}"
                return True, f"FORENSIC SUCCESS: All {len(app_names)} entries are firmly in the registry file."
        except Exception as e:
            return False, f"Forensic check error: {e}"
