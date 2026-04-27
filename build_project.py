import os
import shutil
import subprocess
import sys

def build_main():
    print("--- Building Main Version (PyWebView) ---")
    
    # Path setup
    entry_point = os.path.join("src", "main.py")
    icon_path = "" # Add path to .ico if you have one
    
    # PyInstaller command (run as module for better compatibility on Windows)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "EpicGamesRelinker",
        # Include the web folder (HTML/CSS/JS)
        f"--add-data=src/web{os.pathsep}web",
        # Hidden imports for PyWebView on Windows
        "--hidden-import=webview.platforms.winforms",
        entry_point
    ]
    
    if icon_path and os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])
        
    subprocess.run(cmd)

def build_archive():
    print("\n--- Building Archived Version (CustomTkinter) ---")
    
    # Path setup
    entry_point = os.path.join("archive", "gui_app.py")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "EpicGamesRelinker_Legacy",
        # Include the themes.json
        "--add-data", f"archive/themes.json{os.pathsep}.",
        # We need to include the customtkinter directory for its assets
        # This usually requires finding where the site-package is
        entry_point
    ]
    
    subprocess.run(cmd)

def clean():
    print("Cleaning up build folders...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    
    # Clean spec files
    for file in os.listdir("."):
        if file.endswith(".spec"):
            os.remove(file)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "main":
            build_main()
        elif sys.argv[1] == "archive":
            build_archive()
        elif sys.argv[1] == "clean":
            clean()
        else:
            print("Usage: python build_project.py [main|archive|clean]")
    else:
        # Default to building main
        build_main()
