"""
webview_app.py
--------------
Thin composition root for the Epic Games Relinker GUI.

PyWebViewApi is assembled from four domain-specific handler mixins so
that each area of responsibility lives in its own module:

    handlers/polling_handler.py       — log queue, modal queue, print hook
    handlers/settings_handler.py      — path persistence, directory browser
    handlers/library_handler.py       — Library Hub data, game launch
    handlers/action_handler.py        — background game operations (relink / move / fix …)
    handlers/manifest_tools_handler.py — Manifest Cleanup, Validator, predictions

The public surface of PyWebViewApi is unchanged — all method names and
signatures are identical to the previous monolithic class, so no JS or
HTML changes are required.
"""

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
    """
    The single object registered with pywebview as `js_api`.

    Every public method is inherited from one of the handler mixins above.
    This class is intentionally kept minimal — its only job is to wire the
    mixins together and hold the pywebview window reference.
    """

    def __init__(self):
        # Give the window reference a default so mixins can access it safely
        # before webview.start() fires.
        self._window = None

        # Initialise mixin state that can't live at the class level
        self._init_polling()        # from PollingHandler
        self._init_action_handler() # from ActionHandler

    def show_credits(self):
        """Displays the credits alert (kept on the root class for visibility)."""
        self.show_alert(
            "Epic Games Relinker GUI\n\n"
            "(Original Developer)\nSupernova1114\n\n"
            "Super0Teah — GUI Dev & Fix, Link and Capture Features Dev\n\n"
            "A modern tool to intelligently move and relink Epic Games installations."
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def launch_gui():
    api = PyWebViewApi()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir     = os.path.join(current_dir, "web")
    html_file   = os.path.join(web_dir, "index.html")

    window = webview.create_window(
        "Epic Games Relinker GUI",
        html_file,
        js_api=api,
        width=1150,
        height=750,
        min_size=(900, 600),
    )
    api._window = window
    webview.start(debug=False, private_mode=False)
