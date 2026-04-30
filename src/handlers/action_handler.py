import os
import re
import json
import shutil
import threading
import traceback
from file_management  import FileManagement
from game_data        import GameDataManager
from manifest_capture import ManifestCapture
class ActionHandler:
    def _init_action_handler(self):
        self._worker = None
        self._link_event  = threading.Event()
        self._link_result = None
        self._fix_event   = threading.Event()
        self._fix_result  = None
        self._capture_event  = threading.Event()
        self._capture_result = None
        self._move_event  = threading.Event()
        self._move_result = None
    def start_action(
        self,
        action: str,
        manifest_path: str,
        games_path: str,
        use_default: bool,
        debug_mode: bool = False,
    ):
        if self._worker and self._worker.is_alive():
            self.warn_user("An operation is already running. Please wait.")
            return
        manifest_path = manifest_path.strip()
        games_path    = games_path.strip()
        if not manifest_path:
            self.warn_user("Manifests folder cannot be empty.")
            return
        games_optional = action in ("capture", "link", "fix", "fix_dlc")
        if not games_path and not games_optional:
            self.warn_user("Games folder cannot be empty for this action.")
            return
        if not os.path.exists(manifest_path):
            os.makedirs(manifest_path, exist_ok=True)
            self._log(f"INFO: Created manifests folder: {manifest_path}")
        self._worker = threading.Thread(
            target=self._run_dispatch,
            args=(action, manifest_path, games_path, debug_mode),
            daemon=True,
        )
        self._worker.start()
    def abort_action(self):
        self._link_result    = None
        self._link_event.set()
        self._fix_result     = None
        self._fix_event.set()
        self._move_result    = None
        self._move_event.set()
    def resume_link(self, path: str):
        self._link_result = path
        self._link_event.set()
    def resume_move(self, sel_paths: list, dest: str):
        self._move_result = (sel_paths, dest)
        self._move_event.set()
    def resume_fix(self, manifest_path: str, game_path: str):
        self._fix_result = (manifest_path, game_path)
        self._fix_event.set()
    def resume_capture(self, proceed: bool):
        self._capture_result = proceed
        self._capture_event.set()
    def _run_dispatch(
        self,
        action: str,
        m_path: str,
        g_path: str,
        debug_mode: bool,
    ):
        self._debug_mode = debug_mode
        try:
            if debug_mode:
                self._log("INFO: [DEBUG MODE ON] — full tracebacks will be logged on error.", "INFO")
            gdm = GameDataManager(m_path, g_path) if g_path else None
            needs_games = action in ("relink", "move", "move_pc")
            if needs_games:
                if not gdm or gdm.get_game_count() == 0:
                    self._log("ERROR: No valid games found in the specified folder.", "ERROR")
                    return
            elif gdm is None:
                gdm = type(
                    "MinimalGDM", (),
                    {
                        "_game_data_list":           [],
                        "_manifest_backup_folder":   "",
                        "_launcher_manifest_folder": m_path,
                    },
                )()
            dispatch = {
                "relink":  self._action_relink,
                "move":    self._action_move,
                "move_pc": self._action_move_pc,
                "capture": self._action_capture,
                "link":    self._action_link,
                "fix":      self._action_fix,
                "fix_dlc":  self._action_fix,
                "auto_fix": self._action_auto_fix,
            }
            handler = dispatch.get(action)
            if handler:
                handler(action, m_path, g_path, gdm)
            else:
                self._log(f"ERROR: Unknown action '{action}'.", "ERROR")
        except Exception as exc:
            self._log_exception("action dispatch", exc, debug_mode)
    def _action_relink(self, action, m_path, g_path, gdm):
        self._log("STEP: Relinking all games in Games folder...")
        self._log("INFO: Step 1/3 — Backing up manifests...")
        gdm.backup_manifests()
        self._log("INFO: Step 2/3 — Relinking manifests...")
        gdm.relink_manifests()
        self._log("INFO: Step 3/3 — Restoring manifests...")
        gdm.restore_manifests()
        self._log("SUCCESS: Finished relinking operations.")
        self._modal_queue.append({
            "type": "restart_prompt",
            "msg":  "Relinking complete!\n\nDo you want to restart the Epic Games Launcher now to apply changes?",
        })
    def _action_move(self, action, m_path, g_path, gdm):
        self._log("STEP: Fetching movable games...")
        games = gdm._game_data_list
        if not games:
            self._log("INFO: No mapped games found to move.")
            return
        games_json        = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in games]
        self._move_result = None
        self._move_event.clear()
        self._modal_queue.append({"type": "move", "games_json": games_json})
        self._move_event.wait()
        if not self._move_result:
            self._log("INFO: Move operation cancelled.")
            return
        sel_paths, dest = self._move_result
        if dest == g_path:
            self._log("ERROR: Destination path cannot be the same as source path.", "ERROR")
            return
        FileManagement.try_create_dir(dest)
        dest_backup = os.path.join(dest, gdm.MANIFEST_BACKUP_FOLDER_NAME)
        FileManagement.try_create_dir(dest_backup)
        self._log("INFO: Step 1/3 — Backing up manifests...")
        gdm.backup_manifests()
        self._log("INFO: Step 2/3 — Moving game installation(s)...")
        backed_up_m = gdm.get_launcher_manifest_files(gdm._manifest_backup_folder)
        for g in games:
            if g.game_folder.path not in sel_paths:
                continue
            if os.path.exists(os.path.join(dest, g.game_folder.name)):
                self._log(f"WARNING: Skipping {g.game_folder.name} — folder already exists at destination.", "WARNING")
                continue
            can_move = True
            for gm in g.manifest_file_list:
                match = gdm.get_matching_launcher_manifest(gm, backed_up_m)
                if not match:
                    can_move = False
                    break
                new_path = os.path.join(dest, g.game_folder.name)
                gdm.update_manifest_location_references(match, new_path)
                shutil.move(match.path, dest_backup)
            if can_move:
                self._log(f"INFO: Moving {g.game_folder.name}...")
                shutil.move(g.game_folder.path, dest)
            else:
                self.warn_user(f"Missing manifest file for {g.game_folder.name}, skipped moving.")
        self._log("INFO: Step 3/3 — Restoring manifests...")
        gdm.restore_manifests()
        self._log("SUCCESS: Move complete. Run 'Restore Manifests' or 'Relink' and restart your launcher.")
        self._modal_queue.append({
            "type": "restart_prompt",
            "msg":  "Move complete!\n\nDo you want to restart the Epic Games Launcher now to apply changes?",
        })
    def _action_move_pc(self, action, m_path, g_path, gdm):
        self._log("STEP: Beginning PC Move Sequence...")
        self._log("INFO: Step 1/2 — Backing up manifests...")
        gdm.backup_manifests()
        self._modal_queue.append({
            "type": "capture_prompt",
            "msg":  "Backup complete.\n\nNow move your storage drive to the other PC.\n\nClick OK when you are ready to restore manifests.",
        })
        self._capture_result = None
        self._capture_event.clear()
        self._capture_event.wait()
        if self._capture_result in (False, "abort", None):
            self._log("INFO: Setup Cancelled.")
            return
        self._log("INFO: Step 2/2 — Restoring manifests...")
        gdm.restore_manifests()
        self._log("SUCCESS: Setup complete.")
    def _action_capture(self, action, m_path, g_path, gdm):
        self._log("STEP: Capturing missing manifests...")
        cap     = ManifestCapture(m_path, gdm._game_data_list)
        missing = cap.get_games_missing_manifests()
        if not missing:
            self._log("SUCCESS: All games in the folder already have matching manifests.")
            return
        self._log(f"INFO: Found {len(missing)} games without manifests.")
        for idx, game in enumerate(missing, 1):
            game_name = game.game_folder.name
            self._log(f"[{idx}/{len(missing)}] {game_name}", "STEP")
            snapshot             = cap.take_snapshot()
            self._capture_result = None
            self._capture_event.clear()
            prompt = (
                f"Open Epic Games Launcher, find '{game_name}', and start downloading it.\n\n"
                "After ~10 seconds CANCEL the download."
            )
            self._modal_queue.append({"type": "capture_prompt", "msg": prompt})
            self._capture_event.wait()
            if self._capture_result in (False, "abort"):
                self._log("WARNING: Capture aborted by user.", "WARNING")
                break
            if self._capture_result in ("skip", None, True):
                if self._capture_result in ("skip", None):
                    self._log(f"WARNING: Skipped '{game_name}'.", "WARNING")
                    continue
            self._log("INFO: Watching for new manifest file... (up to 5 minutes)", "INFO")
            new_file = cap.wait_for_new_manifest(
                snapshot,
                progress_callback=lambda elapsed: (
                    self._log(f"INFO: Still watching... ({int(elapsed)}s)")
                    if int(elapsed) % 5 == 0 and int(elapsed) > 0
                    else None
                ),
                cancel_flag=threading.Event(),
            )
            if new_file is None:
                self._log(f"WARNING: No new manifest detected for '{game_name}'. Skipping.", "WARNING")
                continue
            self._log(f"Captured manifest: {new_file.name}", "SUCCESS")
            ok, msg = ManifestCapture.cleanup_partial_download(new_file.path, game.game_folder.path)
            if ok:
                self._log(f"INFO: Cleanup — {msg}")
        self._log("SUCCESS: Capture sequence complete.")
    def _action_link(self, action, m_path, g_path, gdm):
        self._log("STEP: Checking for pending manifests...")
        cap     = ManifestCapture(m_path, gdm._game_data_list)
        pending = cap.get_pending_manifests()
        if not pending:
            self._log("INFO: No pending .item files found in Manifests directory.")
            return
        all_games  = gdm._game_data_list
        games_json = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in all_games]
        for idx, m in enumerate(pending, 1):
            disp             = ManifestCapture.read_display_name(m.path)
            mj               = [{"file_name": m.name, "file_path": m.path, "display_name": disp}]
            self._link_result = None
            self._link_event.clear()
            self._modal_queue.append({
                "type":           "link",
                "manifests_json": mj,
                "games_json":     games_json,
            })
            self._link_event.wait()
            if not self._link_result:
                self._log("INFO: Linking aborted by user.")
                break
            ok, msg = ManifestCapture.link_pending_manifest(m.path, self._link_result, m_path)
            tag     = "SUCCESS" if ok else "ERROR"
            self._log(f"{tag}: {msg}", tag)
        self._log("SUCCESS: Link Pending Manifests complete.")
        self._modal_queue.append({
            "type": "restart_prompt",
            "msg":  "Link operations complete!\n\nDo you want to restart the Epic Games Launcher now to apply changes?",
        })
    def _action_fix(self, action, m_path, g_path, gdm):
        label      = "Fix DLC Link" if action == "fix_dlc" else "Fix Manifest Link"
        modal_type = action
        self._log(f"STEP: Preparing {label} interface...")
        cap             = ManifestCapture(m_path, gdm._game_data_list)
        manifests_files = cap.get_all_launcher_manifests()
        if not manifests_files:
            self._log("INFO: No launcher manifests found in the Manifests folder.")
            return
        manifests  = [
            {
                "file_path":        f_dict["file"].path,
                "file_name":        f_dict["file"].name,
                "display_name":     f_dict["display_name"],
                "install_location": f_dict.get("install_location", ""),
            }
            for f_dict in manifests_files
        ]
        games_json = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in gdm._game_data_list]
        self._fix_result = None
        self._fix_event.clear()
        self._modal_queue.append({
            "type":           modal_type,
            "manifests_json": manifests,
            "games_json":     games_json,
        })
        fixed_pairs: set = set()
        while True:
            self._fix_event.wait()
            self._fix_event.clear()
            if not self._fix_result:
                self._log(f"INFO: {label} session closed.")
                if fixed_pairs:
                    self._modal_queue.append({
                        "type": "restart_prompt",
                        "msg":  f"{label} operations complete!\n\nDo you want to restart the Epic Games Launcher now to apply changes?",
                    })
                break
            mf_path, gf_path = self._fix_result
            self._fix_result  = None
            pair              = (mf_path, gf_path)
            if pair in fixed_pairs:
                self._log(
                    "WARNING: This manifest + folder combination was already fixed this session. Pick a different one.",
                    "WARNING",
                )
                continue
            ok, msg = ManifestCapture.fix_manifest_link(mf_path, gf_path, m_path)
            if ok:
                fixed_pairs.add(pair)
                self._log(f"SUCCESS: {msg}", "SUCCESS")
                self._modal_queue.append({
                    "type":          "fix_done",
                    "manifest_path": mf_path,
                    "game_path":     gf_path,
                })
            else:
                self._log(f"ERROR: {msg}", "ERROR")
    def _action_auto_fix(self, action, m_path, g_path, gdm):
        game_folder = g_path.strip()
        if not game_folder or not os.path.isdir(game_folder):
            self._log("ERROR: Fix requires a valid game folder path.", "ERROR")
            return
            
        self._log(f"STEP: Discovering manifests in: {game_folder}")
        manifests = ManifestCapture.discover_manifests(game_folder)
        
        if not manifests:
            self._log(
                "ERROR: No .item or .mancpn files found inside the game's .egstore folder. "
                "Cannot auto-fix — use Fix Manifest Link instead.",
                "ERROR",
            )
            return
            
        self._log(f"INFO: Found {len(manifests)} manifest(s) to fix.")
        
        # Admin Check
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            self._log("WARNING: App is NOT running as Administrator. Taskkill and Registry updates may fail.", "WARNING")

        try:
            # Force kill Epic processes to unlock LauncherInstalled.dat
            import subprocess
            import time
            target_procs = [
                "EpicGamesLauncher.exe", 
                "EpicWebHelper.exe", 
                "EpicOnlineServices.exe", 
                "EpicOnlineServicesUserHelper.exe",
                "SocialOverlayUI.exe"
            ]
            self._log("INFO: Terminating Epic Games Launcher processes to unlock registry...")
            found_procs = False
            for p in target_procs:
                res = subprocess.run(['taskkill', '/F', '/IM', p, '/T'], capture_output=True, creationflags=0x08000000)
                if res.returncode == 0:
                    found_procs = True
            
            if found_procs:
                self._log("SUCCESS: Epic processes found and terminated.", "SUCCESS")
                # Wait times removed as requested
            else:
                self._log("INFO: No active Epic Games processes found.")

        except Exception as e:
            self._log(f"WARNING: Exception during taskkill: {e}", "WARNING")

        dat_path = GameDataManager.LAUNCHER_INSTALLED_DAT
        # Verify access to LauncherInstalled.dat
        if os.path.exists(dat_path):
            try:
                # Try to open for append to check lock
                with open(dat_path, "a"): pass
            except OSError:
                self._log("WARNING: LauncherInstalled.dat is still locked. Attempting to proceed anyway...", "WARNING")
                time.sleep(2)

        ok_bak, msg_bak = ManifestCapture.backup_launcher_installed_dat()
        if ok_bak:
            self._log(f"INFO: {msg_bak}")
        else:
            self._log(f"WARNING: {msg_bak}", "WARNING")

        success_count = 0
        success_manifests = []
        for m_data in manifests:
            app_name = m_data.get("AppName", "Unknown")
            m_type   = m_data.get("manifest_type", "unknown")
            display  = m_data.get("DisplayName") or app_name
            
            self._log(f"INFO: Processing {display} ({app_name}) via {m_type}...")
            
            ok_item, msg_item = ManifestCapture.create_item_manifest(m_data, game_folder, m_path)
            if not ok_item:
                self._log(f"ERROR: Failed to create manifest for {app_name}: {msg_item}", "ERROR")
                continue
                
            success_manifests.append(m_data)
            success_count += 1
            self._log(f"SUCCESS: Created manifest for {app_name}", "SUCCESS")

        if success_count > 0:
            self._log("INFO: Finalising registry updates...")
            ok_dat, msg_dat = ManifestCapture.add_to_launcher_installed(success_manifests, game_folder)
            
            if not ok_dat:
                self._log(f"ERROR: {msg_dat}", "ERROR")
                return # Stop here if registry failed

            self._log(f"SUCCESS: {msg_dat}", "SUCCESS")
            
            # Final Forensic Pass (Only if Debug Mode is ON)
            if getattr(self, "_debug_mode", False):
                self._log("INFO: Performing debug forensic verification...")
                names = [m.get("AppName","") for m in success_manifests if m.get("AppName")]
                ok_f, msg_f = ManifestCapture.forensic_verify_registry(names)
                if ok_f:
                    self._log(f"SUCCESS: {msg_f}", "SUCCESS")
                else:
                    self._log(f"WARNING: {msg_f}", "WARNING")
                
            self._log(f"SUCCESS: Import complete! {success_count} entries are now registered and verified.", "SUCCESS")
            
            self._modal_queue.append({
                "type": "restart_prompt",
                "msg":  f"Import complete!\n\n{success_count} manifests were successfully linked and verified in the registry.\n\nDo you want to restart the Epic Games Launcher now?",
            })
        else:
            self._log("ERROR: No manifests were successfully imported.", "ERROR")