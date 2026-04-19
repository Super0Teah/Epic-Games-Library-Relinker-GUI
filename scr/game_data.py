from dataclasses import dataclass
from file_management import FileDirectory, FileManagement
from menu_cli import MenuCLI
import os
import sys
import json
import shutil


@dataclass
class GameData:
    game_folder: FileDirectory
    manifest_folder: FileDirectory
    manifest_file_list: list[FileDirectory]

    def __str__(self) -> str:
        return self.game_folder.name

class GameDataManager:

    DEFAULT_MANIFESTS_PATH: str = "C:\\ProgramData\\Epic\\EpicGamesLauncher\\Data\\Manifests"
    MANIFEST_BACKUP_FOLDER_NAME: str = "_MANIFEST_BACKUPS"
    GAME_MANIFEST_FOLDER_NAME: str = ".egstore"
    GAME_MANIFEST_FILE_TYPE: str = ".manifest"
    LAUNCHER_MANIFEST_FILE_TYPE: str = ".item"
    STAGING_FOLDER_NAME: str = "bps"
    SUPPORTED_LAUNCHER_MANIFEST_VERSIONS: list[int] = [0,]

    def __init__(self, launcher_manifest_folder, games_folder) -> None:
        
        self._launcher_manifest_folder = launcher_manifest_folder
        self._games_folder = games_folder
        self._manifest_backup_folder = os.path.join(games_folder, self.MANIFEST_BACKUP_FOLDER_NAME)

        self._game_data_list: list[GameData] = self.get_game_data_list(games_folder)

    def get_game_count(self) -> int:
        return len(self._game_data_list)

    def is_valid_game_folder(self, entry: os.DirEntry) -> bool:
        return (
            entry.is_dir() 
            and os.path.exists(os.path.join(entry.path, self.GAME_MANIFEST_FOLDER_NAME))
        )
    
    def is_valid_launcher_manifest_file(self, entry: os.DirEntry) -> bool:
        return (
            entry.is_file() 
            and self.LAUNCHER_MANIFEST_FILE_TYPE in entry.name
        )
    
    def is_valid_game_manifest_file(self, entry: os.DirEntry) -> bool:
        return (
            entry.is_file() 
            and self.GAME_MANIFEST_FILE_TYPE in entry.name
        )

    def get_launcher_manifest_files(self, launcher_manifest_folder: str) -> list[FileDirectory]:
    
        launcher_manifest_file_list: list[FileDirectory] = []

        for manifest_entry in os.scandir(launcher_manifest_folder):
            if self.is_valid_launcher_manifest_file(manifest_entry):
                launcher_manifest_file_list.append(FileDirectory(manifest_entry.name, manifest_entry.path))
        
        return launcher_manifest_file_list
    
    def get_game_data_list(self, games_folder):
    
        game_data_list: list[GameData] = []

        for dirpath, dirnames, _ in os.walk(games_folder):

            # Prevent descending into the backup folder at any depth.
            dirnames[:] = [d for d in dirnames if d != self.MANIFEST_BACKUP_FOLDER_NAME]

            for dirname in dirnames:

                game_folder: FileDirectory = None
                manifest_folder: FileDirectory = None
                manifest_file_list: list[FileDirectory] = []

                entry_path = os.path.join(dirpath, dirname)
                game_manifest_folder_path = os.path.join(entry_path, self.GAME_MANIFEST_FOLDER_NAME)

                if not os.path.exists(game_manifest_folder_path):
                    continue  # Not a game folder, keep walking subfolders.

                for manifest_entry in os.scandir(game_manifest_folder_path):
                    if self.is_valid_game_manifest_file(manifest_entry):
                        manifest_file_list.append(FileDirectory(manifest_entry.name, manifest_entry.path))

                game_folder = FileDirectory(dirname, entry_path)
                manifest_folder = FileDirectory(self.GAME_MANIFEST_FOLDER_NAME, game_manifest_folder_path)

                print(f"INFO: Adding \"{dirname}\"")
                game_data_list.append(GameData(game_folder, manifest_folder, manifest_file_list))

        return game_data_list
    
    def get_matching_launcher_manifest(
        self,
        game_manifest: FileDirectory,
        launcher_manifest_file_list: list[FileDirectory]
    ) -> FileDirectory:
        
        # Find launcher manifest that matches the name of the game manifest.
        # Search result is None if match does not exist.
        # Assumes there is only one or zero matching launcher manifests.
        matching_launcher_manifest: FileDirectory = next(
            (launcher_manifest for launcher_manifest in launcher_manifest_file_list if game_manifest.get_name_raw() == launcher_manifest.get_name_raw()),
            None # Default
        )

        return matching_launcher_manifest
    
    def assert_manifest_is_supported(self, format_version: int):

        if format_version not in self.SUPPORTED_LAUNCHER_MANIFEST_VERSIONS:

            output: str = "ERROR!: Launcher manifest format version is incompatible.\n"
            output += "Check if the new launcher \".item\" manifest format is compatible with this program.\n"
            output += "Then add format version to SUPPORTED_LAUNCHER_MANIFEST_VERSIONS." 

            print(output)
            sys.exit(1)
    
    def update_manifest_location_references(self, launcher_manifest: FileDirectory, updated_game_folder: str) -> None:
        
        # Open file as read/write
        with open(launcher_manifest.path, 'r+', encoding='utf-8') as file:
            data = json.load(file)

            # Check version
            self.assert_manifest_is_supported(data["FormatVersion"])

            manifest_location = os.path.join(updated_game_folder, self.GAME_MANIFEST_FOLDER_NAME)
            staging_location = os.path.join(manifest_location, self.STAGING_FOLDER_NAME)

            # Update location references using forward slashes for Epic compatibility
            data["InstallLocation"] = updated_game_folder.replace('\\', '/')
            data["ManifestLocation"] = manifest_location.replace('\\', '/')
            data["StagingLocation"] = staging_location.replace('\\', '/')
            
            # Force Epic to see the game as fully installed
            data["bIsIncompleteInstall"] = False

            file.seek(0) # Reset file pointer to beginning.
            json.dump(data, file, indent=4) #
            file.truncate() # Remove any remaining data after the written data.

        # Force sync UUID of the game manifest files (DLC-Aware)
        sync_count = 0
        try:
            import shutil
            new_basename = os.path.splitext(os.path.basename(launcher_manifest.path))[0]
            pending_dir = os.path.join(manifest_location, "Pending")
            
            # Phase 1: Pull out generated captures safely
            if os.path.exists(pending_dir):
                for ext in [".manifest", ".manc", ".chunkdb", ".bms"]:
                    try:
                        for e in os.scandir(pending_dir):
                            if e.is_file() and e.name.endswith(ext):
                                new_path = os.path.join(manifest_location, e.name)
                                if e.path != new_path:
                                    shutil.move(e.path, new_path)
                                    sync_count += 1
                    except Exception: pass
            
            # Phase 2: Rename root files only if safe (no DLCs)
            try:
                for ext in [".manifest", ".manc", ".chunkdb", ".bms"]:
                    existing_files = [e for e in os.scandir(manifest_location) if e.is_file() and e.name.endswith(ext)]
                    if len(existing_files) == 1:
                        e = existing_files[0]
                        new_path = os.path.join(manifest_location, new_basename + ext)
                        if e.path != new_path:
                            shutil.move(e.path, new_path)
                            sync_count += 1
            except Exception: pass
            
            # Phase 3: Copy .item safely
            try:
                dest_item = os.path.join(manifest_location, os.path.basename(launcher_manifest.path))
                shutil.copy2(launcher_manifest.path, dest_item)
                sync_count += 1
            except Exception: pass
            
            if sync_count > 0:
                print(f"INFO: Successfully synced {sync_count} tracking files safely for {updated_game_folder}")
        except Exception as e:
            print(f"WARNING: Exception while syncing game manifests for {updated_game_folder}: {e}")

    def backup_manifests(self) -> None:

        if MenuCLI.yes_no_prompt(f"Launcher manifests will backup to \"{self._manifest_backup_folder}\". Continue?") == False:
            print("INFO: Aborting...")
            sys.exit(0)

        FileManagement.try_create_dir(self._manifest_backup_folder)

        launcher_manifest_file_list: list[FileDirectory] = self.get_launcher_manifest_files(self._launcher_manifest_folder)

        MenuCLI.print_line_separator()

        for game_data in self._game_data_list:
            for game_manifest in game_data.manifest_file_list:
                
                matching_launcher_manifest: FileDirectory = self.get_matching_launcher_manifest(game_manifest, launcher_manifest_file_list)

                if matching_launcher_manifest is not None:
                    print(f"INFO: Backing up \"{matching_launcher_manifest.name}\".")
                    shutil.copy2(matching_launcher_manifest.path, self._manifest_backup_folder)    
                else:
                    print(f"WARNING: Unable to backup launcher manifest for \"{game_data.game_folder.name}\". (Launcher manifest does not exist).")
            # END for
        # END for

        MenuCLI.print_line_separator()

    def restore_manifests(self) -> None:

        FileManagement.assert_path_exists(self._manifest_backup_folder, hint="You may need to backup manifests first.")

        if MenuCLI.yes_no_prompt(f"Launcher manifests will restore to \"{self._launcher_manifest_folder}\". Continue?") == False:
            print("INFO: Aborting...")
            sys.exit(0)

        MenuCLI.print_line_separator()

        for manifest_entry in os.scandir(self._manifest_backup_folder):
            if self.is_valid_launcher_manifest_file(manifest_entry):
                print(f"INFO: Restoring launcher manifest: {manifest_entry.name}")
                shutil.copy2(manifest_entry.path, self._launcher_manifest_folder)
        
        MenuCLI.print_line_separator()

    def move_game_installation(self) -> None:
        
        FileManagement.assert_path_exists(self._manifest_backup_folder, hint="You may need to backup manifests first.")

        MenuCLI.print_line_separator()

        selected_games_list: list[GameData] = MenuCLI.list_prompt(
            header="Movable Games Menu:",
            prompt="Select games to move",
            option_list=self._game_data_list
        )

        MenuCLI.print_line_separator()

        if len(selected_games_list) == 0:
            print("INFO: No games selected. Exiting...")
            sys.exit(0)

        # Print out what user selected
        print("Your selection:")
        for game in selected_games_list:
            print(f"- \"{game.game_folder.name}\"")

        destination_path: str = input("\nInput a destination path: ")

        if destination_path == self._games_folder:
            print("ERROR: Source and destination paths are equal!")
            sys.exit(1)

        FileManagement.assert_path_exists(destination_path)
        
        MenuCLI.print_line_separator()

        prompt = f"Selected game installations will be moved to \"{destination_path}\".\n"
        prompt += "Manifest backup folder will be created.\n"
        prompt += "Associated manifest files will be moved.\n"
        prompt += "Manifest file location references will be updated.\nContinue?"

        if MenuCLI.yes_no_prompt(prompt) == False:
            print("INFO: Aborting...")
            sys.exit(0)

        MenuCLI.print_line_separator()

        # Create manifest backups folder in destination folder.
        destination_backup_folder = os.path.join(destination_path, self.MANIFEST_BACKUP_FOLDER_NAME)
        FileManagement.try_create_dir(destination_backup_folder)

        selected_game_count: int = len(selected_games_list)

        for index, selected_game in enumerate(selected_games_list):

            # Check if a folder matching game name already exists in destination
            if (os.path.exists(os.path.join(destination_path, selected_game.game_folder.get_name_raw()))):
                print(f"WARNING!: Skipping \"{selected_game.game_folder.name}\"", end='') 
                print(f" as the game folder already exists within {destination_path}")
                continue

            found_all_manifests = True

            backed_up_launcher_manifest_list: list[FileDirectory] = self.get_launcher_manifest_files(self._manifest_backup_folder)

            # Find matching launcher manifests within the backups folder.
            for game_manifest in selected_game.manifest_file_list:
                matching_launcher_manifest = self.get_matching_launcher_manifest(game_manifest, backed_up_launcher_manifest_list)

                if matching_launcher_manifest is None:
                    found_all_manifests = False
                    break

                # Update launcher manifest with new destination
                new_game_folder_path: str = os.path.join(destination_path, selected_game.game_folder.name)
                self.update_manifest_location_references(matching_launcher_manifest, new_game_folder_path)

                # Move launcher manifest to destination
                shutil.move(matching_launcher_manifest.path, destination_backup_folder)

            if found_all_manifests == True:
                # Move game installation
                print(f"INFO: Moving games ({int(100 * index / selected_game_count)}%): \"{selected_game.game_folder.name}\"")
                shutil.move(selected_game.game_folder.path, destination_path)
            else:
                print(f"WARNING!: Skipping \"{selected_game.game_folder.name}\"", end='') 
                print(f" as it is missing a manifest file within {self.MANIFEST_BACKUP_FOLDER_NAME}")

        print(f"INFO: Moving games (100%): DONE")

        MenuCLI.print_line_separator()

        print("INFO: You should now run the \"Restore Manifests\" function!")

    def relink_manifests(self) -> None:

        prompt: str = f"Launcher manifests within \"{self._manifest_backup_folder}\""
        prompt += " will be relinked to their associated games.\nContinue?"
        
        if MenuCLI.yes_no_prompt(prompt) == False:
            print("INFO: Aborting...")
            sys.exit(0)

        MenuCLI.print_line_separator()

        backed_up_launcher_manifest_list: list[FileDirectory] = self.get_launcher_manifest_files(self._manifest_backup_folder)

        for game_data in self._game_data_list:
            for game_manifest in game_data.manifest_file_list:

                matching_launcher_manifest: FileDirectory = self.get_matching_launcher_manifest(game_manifest, backed_up_launcher_manifest_list)

                if matching_launcher_manifest is None:
                    print(f"WARNING!: Launcher manifest for \"{game_data.game_folder.name}\" matching {game_manifest.name} does not exist.")
                    continue

                # Update launcher manifest to reference correct game path.
                print(f"INFO: Relinking \"{game_data.game_folder.name}\"")
                self.update_manifest_location_references(matching_launcher_manifest, game_data.game_folder.path)
            # END for
        # END for

        MenuCLI.print_line_separator()




    