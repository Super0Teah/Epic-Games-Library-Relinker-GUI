import os
import shutil
import subprocess
import sys

def build_main():
    clean()
    print("\n--- Building Main Version (PyWebView) v2.0.1 ---")
    
    # Path setup
    entry_point = os.path.join("src", "main.py")
    icon_path = "" # Add path to .ico if you have one
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "EpicGamesRelinker_v2.0.1",
        # Include the web folder (HTML/CSS/JS) and README
        f"--add-data=src/web{os.pathsep}web",
        f"--add-data=README.md{os.pathsep}.",
        # Hidden imports for PyWebView on Windows (WinForms + EdgeChromium)
        "--hidden-import=webview.platforms.winforms",
        "--hidden-import=webview.platforms.edgechromium",
        "--collect-all", "webview",
        entry_point
    ]
    
    if icon_path and os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])
        
    subprocess.run(cmd)

def build_archive():
    print("\n--- Building Archived Version (CustomTkinter) ---")
    
    # Path setup
    entry_point = os.path.join("archive", "gui_app.py")
    
    # Try to find customtkinter path for bundling
    ctk_data = ""
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        ctk_data = f"{ctk_path}{os.pathsep}customtkinter"
    except ImportError:
        print("Warning: customtkinter not found, build might fail or UI might look broken.")

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "EpicGamesRelinker_Legacy",
        # Include the themes.json
        "--add-data", f"archive/themes.json{os.pathsep}.",
        # Add src to the path so PyInstaller can find file_management, game_data, etc.
        "--paths", "src",
        entry_point
    ]
    
    if ctk_data:
        # Insert before entry_point
        cmd.insert(-1, "--add-data")
        cmd.insert(-1, ctk_data)
        
    subprocess.run(cmd)

def clean():
    print("Cleaning up temporary build artifacts...")
    # Only clean the build folder, keep the dist folder where EXEs are stored
    for folder in ["build"]:
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
