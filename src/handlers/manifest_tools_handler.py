import re
import json
import difflib
from manifest_capture import ManifestCapture
class ManifestToolsHandler:
    def get_manifest_cleanup_data(self, manifest_path: str) -> str:
        manifest_path = manifest_path.strip()
        if not manifest_path or not __import__("os").path.exists(manifest_path):
            return json.dumps({"error": "Invalid manifests folder."})
        try:
            cap           = ManifestCapture(manifest_path, [])
            orphans       = cap.get_orphaned_manifests()
            pending_dupes = cap.get_duplicate_pending_manifests()
            return json.dumps({"orphans": orphans, "pending_dupes": pending_dupes})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    def get_manifest_validate_data(self, manifest_path: str) -> str:
        manifest_path = manifest_path.strip()
        if not manifest_path or not __import__("os").path.exists(manifest_path):
            return json.dumps({"error": "Invalid manifests folder."})
        try:
            cap    = ManifestCapture(manifest_path, [])
            issues = cap.validate_manifests()
            return json.dumps({"issues": issues})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    def delete_manifest_file(self, item_path: str) -> str:
        try:
            ok, msg = ManifestCapture.delete_manifest(item_path)
            tag     = "SUCCESS" if ok else "ERROR"
            self._log(f"{tag}: {msg}", tag)
            return json.dumps({"ok": ok, "msg": msg})
        except Exception as exc:
            self._log(f"ERROR: delete_manifest_file: {exc}", "ERROR")
            return json.dumps({"ok": False, "msg": str(exc)})
    def get_predictions(self, manifest_json: str, game_list_json: str) -> str:
        games = json.loads(game_list_json)
        if not manifest_json or manifest_json == "null":
            return json.dumps({"best": -1, "closest": -1, "ratio": 0})
        m = json.loads(manifest_json)
        def _norm(txt: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(txt).lower())
        dl_n = _norm(m.get("display_name", ""))
        if_n = _norm(m.get("file_name", "").replace(".item", ""))
        best    = -1
        closest = -1
        highest = 0.0
        for i, g in enumerate(games):
            fn_n = _norm(g["name"])
            if (dl_n and (dl_n in fn_n or fn_n in dl_n)) or \
               (if_n and len(if_n) >= 3 and (if_n in fn_n or fn_n in if_n)):
                best = i
                break
            r1      = difflib.SequenceMatcher(None, dl_n, fn_n).ratio() if dl_n else 0
            r2      = difflib.SequenceMatcher(None, if_n, fn_n).ratio() if if_n else 0
            m_ratio = max(r1, r2)
            if m_ratio > highest and m_ratio > 0.3:
                highest = m_ratio
                closest = i
        if best != -1:
            closest = -1   
        return json.dumps({"best": best, "closest": closest, "ratio": highest})