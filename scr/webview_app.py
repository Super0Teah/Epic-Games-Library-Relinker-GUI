import os
import sys
import json
import re
import difflib
import threading
import builtins
import webview
import traceback
import shutil
from time import sleep

sys.path.insert(0, os.path.dirname(__file__))
from file_management import FileManagement
from game_data import GameDataManager
from manifest_capture import ManifestCapture

class PyWebViewApi:
    def __init__(self):
        self._window = None
        self._worker = None
        
        # Async dialog triggers
        self._link_event = threading.Event()
        self._link_result = None
        
        self._fix_event = threading.Event()
        self._fix_result = None
        
        self._capture_event = threading.Event()
        self._capture_result = None

        self._move_event = threading.Event()
        self._move_result = None
        
        self._log_queue = []
        self._modal_queue = []
        
        # Intercept python prints globally
        self._real_print = builtins.print
        builtins.print = self._intercepted_print

    def _intercepted_print(self, *args, **kwargs):
        msg = " ".join(str(a) for a in args)
        self._real_print(*args, **kwargs)
        
        # Only capture prints from our specific worker thread!
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

    # ── POLLING ENDPOINTS (Safe Thread Context) ────────────────────────────────────────────────
    def get_logs(self):
        if not self._log_queue:
            return "[]"
        logs = self._log_queue.copy()
        self._log_queue.clear()
        return json.dumps(logs)

    def get_modal(self):
        if not self._modal_queue:
            return "[]"
        req = self._modal_queue.copy()
        self._modal_queue.clear()
        return json.dumps(req)
        
    def show_alert(self, msg):
        self._modal_queue.append({"type": "alert", "msg": msg})

    def show_credits(self):
        self.show_alert("Epic Games Relinker GUI\n\nDeveloped by Jeremi\n\nA modern tool to intelligently move and relink Epic Games installations.")

    # ── Initial State ──────────────────────────────────────────────────────────
    def get_initial_paths(self):
        return {
            "manifestPath": GameDataManager.DEFAULT_MANIFESTS_PATH,
            "gamesPath": "",
            "useDefault": True
        }

    def browse_directory(self, title):
        if self._window:
            try:
                # Use FileDialog.FOLDER in >v5, fallback to FOLDER_DIALOG in <v5
                dialog_type = getattr(webview, 'FileDialog', webview).FOLDER if hasattr(webview, 'FileDialog') else webview.FOLDER_DIALOG
                result = self._window.create_file_dialog(dialog_type, allow_multiple=False)
                if result and len(result) > 0:
                    return os.path.normpath(result[0])
            except AttributeError:
                result = self._window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
                if result and len(result) > 0:
                    return os.path.normpath(result[0])
            except Exception as e:
                self.warn_user(f"Failed to browse directory: {str(e)}")
        return ""

    # ── Action Dispatcher ──────────────────────────────────────────────────────
    def start_action(self, action, manifest_path, games_path, use_default, debug_mode=False):
        if self._worker and self._worker.is_alive():
            self.warn_user("An operation is already running. Please wait.")
            return

        manifest_path = manifest_path.strip()
        games_path = games_path.strip()
        
        if not manifest_path:
            self.warn_user("Manifests folder cannot be empty.")
            return
        
        # Games folder not required for capture/link/fix actions
        games_optional = action in ("capture", "link", "fix", "fix_dlc")
        if not games_path and not games_optional:
            self.warn_user("Games folder cannot be empty for this action.")
            return
            
        if not os.path.exists(manifest_path):
            os.makedirs(manifest_path, exist_ok=True)
            self._log(f"INFO: Created manifests folder {manifest_path}")

        self._worker = threading.Thread(
            target=self._run_dispatch,
            args=(action, manifest_path, games_path, debug_mode),
            daemon=True
        )
        self._worker.start()

    def _run_dispatch(self, action, m_path, g_path, debug_mode):
        fm = FileManagement()
        try:
            # Patch MenuCLI singleton methods for this thread so it doesn't hang on input()
            import menu_cli
            def auto_yes(*args, **kwargs): return True
            def auto_list(*args, **kwargs): return kwargs.get('option_list', []) if 'option_list' in kwargs else (args[2] if len(args) > 2 else [])
            menu_cli.MenuCLI.yes_no_prompt = staticmethod(auto_yes)
            menu_cli.MenuCLI.list_prompt = staticmethod(auto_list)
            menu_cli.MenuCLI.print_line_separator = staticmethod(lambda *a, **k: None)

            if debug_mode:
                self._log("INFO: [DEBUG MODE ON] — full tracebacks will be logged on error.", "INFO")
            
            gdm = GameDataManager(m_path, g_path) if g_path else None
            
            # Actions that require a games folder
            needs_games = action in ("relink", "move", "move_pc")
            if needs_games:
                if not gdm or gdm.get_game_count() == 0:
                    self._log("ERROR: No valid games found in the specified folder.")
                    return
            elif gdm is None:
                # For capture/link/fix, create a minimal gdm just for manifest reading
                gdm = type('FakeGDM', (), {'_game_data_list': [], '_manifest_backup_folder': '', '_launcher_manifest_folder': m_path})()  

            if action == "relink":
                self._log("STEP: Relinking all games in Games folder...")
                self._log("INFO: Step 1/3 — Backing up manifests...")
                gdm.backup_manifests()
                self._log("INFO: Step 2/3 — Relinking manifests...")
                gdm.relink_manifests()
                self._log("INFO: Step 3/3 — Restoring manifests...")
                gdm.restore_manifests()
                
                self._log(f"SUCCESS: Finished relinking operations.")

            elif action == "move":
                self._log("STEP: Fetching movable games...")
                games = gdm._game_data_list
                if not games:
                    self._log("INFO: No mapped games found to move.")
                    return
                
                games_json = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in games]
                self._move_result = None
                self._move_event.clear()
                
                self._modal_queue.append({
                    "type": "move",
                    "games_json": games_json
                })
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
                    if g.game_folder.path not in sel_paths: continue
                    
                    self._log(f"INFO: Processing {g.game_folder.name}...")
                    
                    if os.path.exists(os.path.join(dest, g.game_folder.name)):
                        self._log(f"WARNING: Skipping {g.game_folder.name} as folder already exists at destination...", "WARNING")
                        continue
                        
                    can_move = True
                    for gm in g.manifest_file_list:
                        match = gdm.get_matching_launcher_manifest(gm, backed_up_m)
                        if not match: 
                            can_move = False; break
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
                
            elif action == "move_pc":
                self._log("STEP: Beginning PC Move Sequence...")
                self._log("INFO: Step 1/2 — Backing up manifests...")
                gdm.backup_manifests()
                
                self._modal_queue.append({
                    "type": "capture_prompt",
                    "msg": "Backup complete.\n\nNow move your storage drive to the other PC.\n\nClick OK when you are ready to restore manifests."
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

            elif action == "capture":
                self._log("STEP: Capturing missing manifests...")
                cap = ManifestCapture(m_path, gdm._game_data_list)
                missing = cap.get_games_missing_manifests()
                if not missing:
                    self._log("SUCCESS: All games in the folder already have matching manifests.")
                    return
                
                self._log(f"INFO: Found {len(missing)} games without manifests.")
                for idx, game in enumerate(missing, 1):
                    game_name = game.game_folder.name
                    self._log(f"[{idx}/{len(missing)}] {game_name}", "STEP")
                    
                    snapshot = cap.take_snapshot()
                    self._capture_result = None
                    self._capture_event.clear()
                    
                    prompt = f"Open Epic Games Launcher, find '{game_name}', and start downloading it.\n\nAfter ~10 seconds CANCEL the download."
                    self._modal_queue.append({"type": "capture_prompt", "msg": prompt})
                    self._capture_event.wait()
                    
                    if self._capture_result == "abort" or self._capture_result == False:
                        self._log(f"WARNING: Capture aborted by user.", "WARNING")
                        break
                    
                    if self._capture_result == "skip" or not self._capture_result:
                        self._log(f"WARNING: Skipped '{game_name}'.", "WARNING")
                        continue
                        
                    self._log("INFO: Watching for new manifest file... (up to 5 minutes)", "INFO")
                    new_file = cap.wait_for_new_manifest(
                        snapshot,
                        progress_callback=lambda elapsed: self._log(f"INFO: Still watching... ({int(elapsed)}s)") if int(elapsed) % 5 == 0 and int(elapsed) > 0 else None,
                        cancel_flag=threading.Event()
                    )
                    
                    if new_file is None:
                        self._log(f"WARNING: No new manifest detected for '{game_name}'. Skipping.", "WARNING")
                        continue
                        
                    disp = ManifestCapture.read_display_name(new_file.path)
                    self._log(f"Captured manifest: {new_file.name}", "SUCCESS")
                    
                    ok, msg = ManifestCapture.cleanup_partial_download(new_file.path, game.game_folder.path)
                    if ok:
                        self._log(f"INFO: Cleanup — {msg}")
                        
                self._log("SUCCESS: Capture sequence complete.")

            elif action == "link":
                self._log("STEP: Checking for pending manifests...")
                cap = ManifestCapture(m_path, gdm._game_data_list)
                pending = cap.get_pending_manifests()
                if not pending:
                    self._log("INFO: No pending .item files found in Manifests directory.")
                    return
                
                all_games = gdm._game_data_list
                games_json = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in all_games]
                
                for idx, m in enumerate(pending, 1):
                    disp = ManifestCapture.read_display_name(m.path)
                    mj = [{"file_name": m.name, "file_path": m.path, "display_name": disp}]
                    self._link_result = None
                    self._link_event.clear()
                    
                    self._modal_queue.append({
                        "type": "link",
                        "manifests_json": mj,
                        "games_json": games_json
                    })
                    
                    self._link_event.wait()
                    
                    if not self._link_result:
                        self._log("INFO: Linking aborted by user.")
                        break
                        
                    sel_path = self._link_result
                    ok, msg = ManifestCapture.link_pending_manifest(m.path, sel_path, m_path)
                    if ok:
                        self._log(f"SUCCESS: {msg}")
                    else:
                        self._log(f"ERROR: {msg}")
                    
                self._log("SUCCESS: Link Pending Manifests complete.")

            elif action in ("fix", "fix_dlc"):
                modal_type = action  # "fix" or "fix_dlc"
                label = "Fix DLC Link" if action == "fix_dlc" else "Fix Manifest Link"
                self._log(f"STEP: Preparing {label} interface...")
                cap = ManifestCapture(m_path, gdm._game_data_list)
                manifests_files = cap.get_all_launcher_manifests()

                if not manifests_files:
                    self._log("INFO: No launcher manifests found in the Manifests folder.")
                    return

                all_games = gdm._game_data_list
                manifests = []
                for m_dict in manifests_files:
                    f = m_dict["file"]
                    disp = m_dict["display_name"]
                    manifests.append({
                        "file_path": f.path,
                        "file_name": f.name,
                        "display_name": disp,
                        "install_location": m_dict.get("install_location", "")
                    })

                games_json = [{"name": g.game_folder.name, "path": g.game_folder.path} for g in all_games]

                # Open the modal ONCE — then loop waiting for sequential fixes
                self._fix_result = None
                self._fix_event.clear()
                self._modal_queue.append({
                    "type": modal_type,
                    "manifests_json": manifests,
                    "games_json": games_json
                })

                fixed_pairs = set()  # Track (manifest_path, game_path) to prevent duplicates

                while True:
                    self._fix_event.wait()
                    self._fix_event.clear()

                    if not self._fix_result:
                        self._log(f"INFO: {label} session closed.")
                        break

                    mf_path, gf_path = self._fix_result
                    self._fix_result = None

                    pair = (mf_path, gf_path)
                    if pair in fixed_pairs:
                        self._log("WARNING: This manifest+folder combination was already fixed this session. Pick a different one.", "WARNING")
                        continue

                    ok, msg = ManifestCapture.fix_manifest_link(mf_path, gf_path, m_path)
                    if ok:
                        fixed_pairs.add(pair)
                        self._log(f"SUCCESS: {msg}")
                        # Signal JS to mark manifest as done
                        self._modal_queue.append({
                            "type": "fix_done",
                            "manifest_path": mf_path,
                            "game_path": gf_path
                        })
                    else:
                        self._log(f"ERROR: {msg}")

        except Exception as e:
            self._log(f"ERROR: Exception caught in action dispatch: {e}", "ERROR")
            if debug_mode:
                err_trace = traceback.format_exc()
                self._log("--- DEBUG TRACEBACK ---", "WARNING")
                self._log(err_trace, "WARNING")
                try:
                    with open("relinker_debug.log", "a", encoding="utf-8") as f:
                        f.write(err_trace + "\n")
                    self._log("INFO: Traceback dumped to relinker_debug.log", "INFO")
                except: pass

    # ── Frontend API Callbacks ─────────────────────────────────────────────────
    def abort_action(self):
        self._link_result = None
        self._link_event.set()
        self._fix_result = None
        self._fix_event.set()
        self._move_result = None
        self._move_event.set()

    def resume_link(self, path):
        self._link_result = path
        self._link_event.set()
        
    def resume_move(self, sel_paths, dest):
        self._move_result = (sel_paths, dest)
        self._move_event.set()
        
    def resume_fix(self, manifest_path, game_path):
        self._fix_result = (manifest_path, game_path)
        self._fix_event.set()
        
    def resume_capture(self, proceed: bool):
        self._capture_result = proceed
        self._capture_event.set()

    def get_predictions(self, manifest_json, game_list_json):
        games = json.loads(game_list_json)
        if not manifest_json or manifest_json == "null":
            return json.dumps({"best": -1, "closest": -1, "ratio": 0})
            
        m = json.loads(manifest_json)
        
        def _norm(txt): return re.sub(r'[^a-z0-9]', '', str(txt).lower())
        
        dl_n = _norm(m.get("display_name", ""))
        if_n = _norm(m.get("file_name", "").replace(".item", ""))
        
        best = -1
        closest = -1
        highest = 0.0
        
        for i, g in enumerate(games):
            fn_n = _norm(g["name"])
            
            if (dl_n and (dl_n in fn_n or fn_n in dl_n)) or \
               (if_n and len(if_n) >= 3 and (if_n in fn_n or fn_n in if_n)):
                best = i
                break
                
            r1 = difflib.SequenceMatcher(None, dl_n, fn_n).ratio() if dl_n else 0
            r2 = difflib.SequenceMatcher(None, if_n, fn_n).ratio() if if_n else 0
            m_ratio = max(r1, r2)
            if m_ratio > highest and m_ratio > 0.3:
                highest = m_ratio
                closest = i
                
        if best != -1:
            closest = -1
            
        return json.dumps({"best": best, "closest": closest, "ratio": highest})

def launch_gui():
    api = PyWebViewApi()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(current_dir, "web")
    html_file = os.path.join(web_dir, "index.html")
    
    window = webview.create_window("Epic Games Relinker GUI", html_file, js_api=api, width=1150, height=750, min_size=(900, 600))
    api._window = window
    webview.start(debug=False)
