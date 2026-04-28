import os
import sys
import webview

sys.path.insert(0, os.path.dirname(__file__))

from handlers.polling_handler        import PollingHandler
from handlers.settings_handler       import SettingsHandler
from handlers.library_handler        import LibraryHandler
from handlers.action_handler         import ActionHandler
from handlers.manifest_tools_handler import ManifestToolsHandler

class PyWebViewApi(
    PollingHandler,
    SettingsHandler,
    LibraryHandler,
    ActionHandler,
    ManifestToolsHandler,
):
    def __init__(self):
        self._window = None
        self._init_polling()
        self._init_action_handler()

    def show_credits(self):
        self.show_alert(
            "Epic Games Relinker GUI v2.0.0\n\n"
            "(Original Developer)\nSupernova1114\n\n"
            "Super0Teah — GUI Dev & Fix, Link, Capture, and Auto Fix Features Dev\n\n"
            "A modern tool to intelligently move and fix Epic Games installations."
        )

    def open_dev_tools(self):
        if not self._window: return
        try:
            self._window.gui.browser.CoreWebView2.OpenDevToolsWindow()
        except:
            self.show_alert("Developer Console: Press F12 or Right-click anywhere and select 'Inspect'.")

def get_base_path():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_executable_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def launch_gui():
    import shutil
    base_path = get_base_path()
    local_appdata = os.getenv('LOCALAPPDATA', '')
    user_profile = os.getenv('USERPROFILE', '')
    folders_to_clear = [
        os.path.join(os.path.dirname(base_path), "gui"),
        os.path.join(local_appdata, "pywebview"),
    ]
    packages_path = os.path.join(user_profile, "AppData", "Local", "Packages")
    if os.path.exists(packages_path):
        import glob
        python_pkgs = glob.glob(os.path.join(packages_path, "PythonSoftwareFoundation.Python.*"))
        for pkg in python_pkgs:
            folders_to_clear.append(os.path.join(pkg, "LocalCache", "Local", "pywebview"))
    for folder in folders_to_clear:
        if folder and os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

    api = PyWebViewApi()
    web_dir   = os.path.join(base_path, "web")
    html_file = os.path.join(web_dir, "index.html")
    WIN_W, WIN_H = 1150, 750
    try:
        import ctypes
        user32  = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        start_x  = max(0, (screen_w - WIN_W) // 2)
        start_y  = max(0, (screen_h - WIN_H) // 2)
    except Exception:
        start_x, start_y = None, None
    create_kwargs = dict(
        title="Epic Games Relinker GUI",
        url=html_file,
        js_api=api,
        width=WIN_W,
        height=WIN_H,
        min_size=(900, 600),
    )
    if start_x is not None:
        create_kwargs["x"] = start_x
        create_kwargs["y"] = start_y
    window = webview.create_window(**create_kwargs)
    api._window = window
    cache_dir = os.path.join(get_executable_path(), ".cache")
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.start(
        debug=True, 
        private_mode=False, 
        storage_path=cache_dir
    )
