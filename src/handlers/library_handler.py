"""
LibraryHandler
--------------
Provides the Library Hub data: game/DLC/pending lists, game launch,
and launcher restart.
"""

import os
import re
import json
import difflib

from game_data     import GameDataManager
from manifest_capture import ManifestCapture


class LibraryHandler:
    """Mixin — depends on PollingHandler (_log, warn_user)."""

    # ── Entry builder ─────────────────────────────────────────────────────────

    def _create_entry(self, m: dict, loc: str, status: str) -> dict:
        """
        Converts a raw manifest dict (from get_all_launcher_manifests) into
        the flat structure consumed by the frontend game-card renderer.
        """
        app_name = ""
        try:
            with open(m["file"].path, "r", encoding="utf-8") as f:
                d = json.load(f)
            app_name = d.get("AppName", "")
        except Exception:
            pass

        return {
            "name":         m["display_name"] or m["file"].name,
            "path":         m.get("install_location", "(unknown)"),
            "status":       status,
            "app_name":     app_name,
            "display_name": m["display_name"],
        }

    # ── Main library scan ─────────────────────────────────────────────────────

    def get_library_data(self, manifest_path: str, games_path: str) -> str:
        """
        Scans the Manifests folder (and optionally the Games folder) and
        returns a JSON payload with three lists:

            games   — main game entries (Linked / Path Broken / Missing Manifest)
            dlcs    — secondary manifests sharing the same install folder
            pending — .item files found inside the Pending subfolder
        """
        manifest_path = manifest_path.strip()
        games_path    = games_path.strip()

        if not manifest_path or not os.path.exists(manifest_path):
            return json.dumps({"error": "Invalid manifests folder."})

        try:
            cap       = ManifestCapture(manifest_path, [])
            manifests = cap.get_all_launcher_manifests()

            results_games   = []
            results_dlcs    = []
            results_pending = []
            linked_paths    = set()

            # ── Separate root manifests from Pending folder manifests ─────────
            groups            = {}
            pending_manifests = []

            for m in manifests:
                if "pending" in os.path.basename(
                    os.path.dirname(m["file"].path)
                ).lower():
                    pending_manifests.append(m)
                    continue

                loc      = m.get("install_location", "")
                norm_loc = os.path.normpath(loc).lower() if loc else ""
                groups.setdefault(norm_loc, []).append(m)

            def _norm(txt: str) -> str:
                return re.sub(r"[^a-z0-9]", "", str(txt).lower())

            # ── Build root AppName set (used to classify pending entries) ─────
            root_app_names: set[str] = set()
            for m_list in groups.values():
                for m in m_list:
                    try:
                        with open(m["file"].path, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        an = d.get("AppName", "").strip()
                        if an:
                            root_app_names.add(an)
                    except Exception:
                        pass

            # ── Classify root manifests ───────────────────────────────────────
            for norm_loc, group in groups.items():
                if not norm_loc:
                    for m in group:
                        results_games.append(
                            self._create_entry(m, "Path Broken", "Path Broken")
                        )
                    continue

                status = "Linked" if os.path.isdir(norm_loc) else "Path Broken"
                if status == "Linked":
                    linked_paths.add(norm_loc)

                folder_name = os.path.basename(norm_loc)
                fn_n        = _norm(folder_name)

                best_m    = None
                best_score = -1.0

                for m in group:
                    dl_n  = _norm(m.get("display_name", ""))
                    if_n  = _norm(m["file"].name.replace(".item", ""))
                    r1    = difflib.SequenceMatcher(None, dl_n, fn_n).ratio() if dl_n else 0
                    r2    = difflib.SequenceMatcher(None, if_n, fn_n).ratio() if if_n else 0
                    score = max(r1, r2)
                    if fn_n and (fn_n == dl_n or fn_n == if_n):
                        score += 1.0  # exact-match bonus
                    if score > best_score:
                        best_score = score
                        best_m     = m

                for m in group:
                    target = results_games if (m == best_m or len(group) == 1) else results_dlcs
                    target.append(self._create_entry(m, norm_loc, status))

            # ── Classify pending manifests ────────────────────────────────────
            for m in pending_manifests:
                try:
                    with open(m["file"].path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    app_name    = d.get("AppName", "").strip()
                    display     = d.get("DisplayName") or d.get("AppName") or m["file"].name
                    install_loc = d.get("InstallLocation", "").strip()

                    # Duplicate: a root manifest already covers this game
                    status = (
                        "Pending Manifest"
                        if (app_name and app_name in root_app_names)
                        else "Pending Install"
                    )

                    results_pending.append({
                        "name":         display,
                        "path":         install_loc or "(no path set)",
                        "status":       status,
                        "app_name":     "",   # pending games cannot be launched
                        "display_name": display,
                    })
                except Exception:
                    results_pending.append({
                        "name":         m["file"].name,
                        "path":         "(could not read)",
                        "status":       "Pending Manifest",
                        "app_name":     "",
                        "display_name": "",
                    })

            # ── Missing-manifest entries from the Games folder ────────────────
            if games_path and os.path.exists(games_path):
                gdm = GameDataManager(manifest_path, games_path)
                for game in gdm._game_data_list:
                    game_loc = os.path.normpath(game.game_folder.path).lower()
                    if game_loc not in linked_paths:
                        results_games.append({
                            "name":         game.game_folder.name,
                            "path":         game.game_folder.path,
                            "status":       "Missing Manifest",
                            "app_name":     "",
                            "display_name": "",
                        })

            return json.dumps({
                "games":   results_games,
                "dlcs":    results_dlcs,
                "pending": results_pending,
            })

        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ── Game launch & launcher control ────────────────────────────────────────

    def launch_game(self, app_name: str):
        """Launches a game through the Epic Games protocol URL."""
        if not app_name:
            return
        try:
            os.system(
                f"start com.epicgames.launcher://apps/{app_name}?action=launch^&silent=true"
            )
        except Exception as exc:
            self.warn_user(f"Failed to launch game: {exc}")

    def restart_launcher(self):
        """Kills and restarts the Epic Games Launcher process."""
        try:
            os.system("taskkill /F /IM EpicGamesLauncher.exe")
            from time import sleep
            sleep(2)
            
            paths = [
                r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
                r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
                r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"
            ]
            
            launched = False
            for p in paths:
                if os.path.exists(p):
                    os.system(f'start "" "{p}"')
                    launched = True
                    break
            
            if not launched:
                # Fallback to URL protocol
                os.system("start com.epicgames.launcher://")
                
        except Exception as exc:
            self.warn_user(f"Failed to restart launcher: {exc}")
