from main import MainApp
import msgpack
import os
import winreg
import shutil
from fnmatch import fnmatch


# Create class for modding instance ##################################
class ModInstance:
    """
    General class for mod manager instances.
    """

    def __init__(self, app: MainApp, instance: dict):
        self.app = app
        self.instance = instance
        self.name = instance.get('name', "")
        self.mods = instance.get('mods', [])
        self.paths = instance.get('paths', {})
        self.loadorder = []
        self.size = 0
    
    def __repr__(self):
        return "ModInstance"
    
    def get_loadorder(self, psignal=None):
        """
        Returns loadorder.
        """

        return self.mods
    
    def create_instance(self):
        """
        Create instance. Steps depend on mod manager.
        """

        return
    
    def get_size(self):
        """
        Calculates total size in bytes of instance files.
        """

        return self.size
    
    def import_mod(self, folder: str):
        return


# Create class for Vortex stagefiles #################################
class StageFile:
    def __init__(self, path: str):
        self.path = path
        self.dir = os.path.dirname(path)
        self.data = {}
        self.loadorder = [] # list of all mod names in loadorder
        self.modfiles = {} # mod: files

        self.parse_file()
        self.get_modlist()
    
    def parse_file(self):
        with open(self.path, 'rb') as file:
            data = msgpack.load(file)
        
        self.data = data
    
    def get_modlist(self):
        loadorder = []
        modfiles = {}
        for file in self.data['files']:
            mod = file['source']
            if mod not in loadorder:
                loadorder.append(mod)
            if mod not in modfiles.keys():
                modfiles[mod] = [file['relPath'].lower()]
            else:
                modfiles[mod].append(file['relPath'].lower())
        
        self.loadorder = loadorder
        self.modfiles = modfiles

    def get_mod_by_filename(self, filename: str):
        """
        Returns modname as string or None if nothing is found.
        Parameters:
            filename: relative path to file
        """

        for mod, files in self.modfiles.items():
            for file in files:
                if filename.lower() == file.lower():
                    return mod
        else:
            print(f"File '{filename}' not found!")
        
            return None
    

# Create class for Vortex instance ###################################
class VortexInstance(ModInstance):
    """
    Class for Vortex ModInstance. Inherited from ModInstance class.
    """

    def __init__(self, app: MainApp, instance: dict):
        super().__init__(app, instance)
        
        self.stagefile = StageFile(self.paths['stagefile'])
        self.mods = self.stagefile.loadorder
        self.loadorder = self.stagefile.loadorder

    def __repr__(self):
        return "VortexInstance"
    
    @staticmethod
    def sort_loadorder(app: MainApp, stagefile: StageFile, psignal=None):
        """
        Creates loadorder from Vortex stagefile.
        """

        app.log.info(f"Creating loadorder with {len(stagefile.loadorder)} mod(s)...")

        app.log.debug("Scanning mods...")
        new_loadorder = stagefile.loadorder.copy()
        overwrites = ""
        for c, mod in enumerate(stagefile.loadorder):
            app.log.debug(f"Scanning mod '{mod}'... ({c}/{len(stagefile.loadorder)})")
            overwriting_mods = []
            
            modfiles = create_folder_list(os.path.join(stagefile.dir, mod))

            for file in modfiles:
                overwriting_mod = stagefile.get_mod_by_filename(file)
                if (overwriting_mod is not None) and (overwriting_mod != mod) and (overwriting_mod not in overwriting_mods):
                    overwriting_mods.append(overwriting_mod)
            
            if overwriting_mods:
                _overwriting_mods = '\n    '.join(overwriting_mods)
                overwrites += f"\nMod: {mod}\nOverwritten by:\n    {_overwriting_mods}\n{'-'*100}"

                app.log.debug(f"Sorting mod '{mod}'...")

                old_index = index = new_loadorder.index(mod)

                # get smallest index of all overwriting mods
                index = min([new_loadorder.index(overwriting_mod) for overwriting_mod in overwriting_mods])
                app.log.debug(f"Current index: {old_index} | Minimal index of overwriting mods: {index}")

                # Move mod to index if index is smaller than before
                if old_index > index:
                    new_loadorder.insert(index, new_loadorder.pop(old_index))
                    app.log.debug(f"Moved mod '{mod}' from index {old_index} to {index}.")
        
        #with open("overwrites.txt", "w") as _file:
        #    _file.write(overwrites)
        

        # Sort until deployed files and loadorder match
        stagefile_files = {}
        for file in stagefile.data['files']:
            stagefile_files[file['relPath'].lower()] = file['source']
        while different_files := VortexInstance.check_loadorder(stagefile, new_loadorder):
            loadorder_files = {}
            for c, mod in enumerate(new_loadorder):
                files = create_folder_list(os.path.join(stagefile.dir, mod))
                for file in files:
                    loadorder_files[file.lower()] = mod
            for file in different_files:
                mod = loadorder_files[file]
                old_index = new_loadorder.index(mod)
                new_index = new_loadorder.index(stagefile_files[file])
                if old_index > new_index:
                    new_loadorder.insert(new_index, new_loadorder.pop(old_index))
                    app.log.debug(f"Moved mod '{mod}' from index {old_index} to {new_index}.")
        
        new_loadorder.reverse()

        app.log.info("Created loadorder from Vortex deployment file.")
        
        # Write loadorder to text file for debbuging
        with open('sorted_loadorder.txt', 'w') as file:
            mods = ""
            for mod in new_loadorder:
                mods += "\n+" + os.path.basename(mod)
            mods = mods.strip()
            file.write(f"# This file was automatically generated by Mod Organizer.\n{mods}")

        return new_loadorder
    
    def get_loadorder(self, psignal=None):
        """
        Returns loadorder. Creates it from stagefile if not already done.
        """

        self.loadorder = VortexInstance.sort_loadorder(self.app, self.stagefile, psignal)
        self.loadorder.reverse()

        # Check if loadorder matches stagefile
        # If log level is 'debug'
        if self.app.log_level == 10:
            #loadorder = self.loadorder.copy()
            #loadorder.reverse()
            VortexInstance.check_loadorder(self.stagefile, self.loadorder, reverse=False)

        return super().get_loadorder()
    
    @staticmethod
    def check_loadorder(stagefile: StageFile, loadorder: list, reverse=False):
        """
        Checks if files in stagefile and loadorder match.
        
        It returns different files as a list.
        
        For debugging purposes!
        """

        if reverse:
            loadorder = loadorder.copy()
            loadorder.reverse()

        print("Checking loadorder...")
        stagefile_files = {}
        _files = ""
        for file in stagefile.data['files']:
            stagefile_files[file['relPath'].lower()] = file['source']
            _files += f"\n{file['relPath'].lower()} ---FROM--- {file['source']}"
        
        #with open("stagefiles.txt", "w", encoding='utf8') as f:
        #    f.write(_files)
        
        loadorder_files = {}
        _files = ""
        for c, mod in enumerate(loadorder):
            files = create_folder_list(os.path.join(stagefile.dir, mod))
            for file in files:
                loadorder_files[file.lower()] = mod
                _files += f"\n{file.lower()} ---FROM--- {mod}"
        
        #with open("modfiles.txt", "w", encoding='utf8') as f:
        #    f.write(_files)
        
        #print("Comparing...")
        different_files = []
        for file, mod in loadorder_files.items():
            if file not in stagefile_files:
                print(f"File: {file}")
                print(f"Loadorder mod: {mod} ({loadorder.index(mod)})")
                print(f"Stagefile mod: NOT FOUND!")
                print("-"*50)
                different_files.append(file)
            elif mod != stagefile_files[file]:
                #print(f"File '{file}' comes from '{mod}' but should come from '{stagefile_files[file]}'!")
                print(f"File: {file}")
                print(f"Loadorder mod: {mod} ({loadorder.index(mod)})")
                print(f"Stagefile mod: {stagefile_files[file]} ({loadorder.index(stagefile_files[file])})")
                print("-"*50)
                different_files.append(file)

        print(f"Found {len(different_files)} difference(s).")

        return different_files

    def get_size(self):
        self.app.log.debug(f"Calculating size of Vortex instance...")
        
        # Calculate size of staging folder
        #size = get_folder_size(self.paths['staging_folder'])
        size = 0
        for file in self.stagefile.data['files']:
            size += os.path.getsize(os.path.join(self.paths['staging_folder'], file['source'], file['relPath']))

        # Add size of download folder if one is given
        if self.paths['download_path']:
            size += get_folder_size(self.paths['download_path'])

        self.size = size
        self.app.log.debug(f"Calculation complete. Instance size: {get_size(self.size)}")
        return super().get_size()


# Create class for MO2 instance ######################################
class MO2Instance(ModInstance):
    """
    Class for ModOrganizer ModInstance. Inherited from ModInstance class.
    """

    def __repr__(self):
        return "MO2Instance"

    def create_instance(self):
        self.app.log.info(f"Creating MO2 instance '{self.name}' in '{self.paths['instance_path']}'...")

        # Create directories
        self.app.log.debug(f"Creating directories...")
        appdata_path = os.path.join(os.getenv('LOCALAPPDATA'), 'ModOrganizer', self.name)
        os.makedirs(appdata_path) # raise exception if instance does already exist
        os.makedirs(self.paths['instance_path'], exist_ok=True)
        os.makedirs(self.paths['download_path'], exist_ok=True)
        os.makedirs(self.paths['mods_path'], exist_ok=True)
        os.makedirs(self.paths['profiles_path'], exist_ok=True)
        os.makedirs(os.path.join(self.paths['profiles_path'], 'Default'), exist_ok=True)
        os.makedirs(self.paths['overwrite_path'], exist_ok=True)
        self.app.log.debug(f"Created instance folders.")

        # Create ini file with instance paths
        instance_path = self.paths['instance_path'].replace('\\', '/')
        download_path = self.paths['download_path'].replace('\\', '/')
        skyrim_path = os.path.join(get_steam_path(), 'steamapps', 'common', 'Skyrim Special Edition').replace('\\', '/')
        with open(os.path.join(appdata_path, 'ModOrganizer.ini'), 'w') as inifile:
            ini = f"""
[General]
gameName=Skyrim Special Edition
selected_profile=@ByteArray(Default)
gamePath={skyrim_path}
version=2.4.4
first_start=true

[Settings]
base_directory={instance_path}
download_directory={download_path}
style=Paper Dark.qss

[PluginPersistance]
Python%20Proxy\\tryInit=false

[recentDirectories]
size=0
""".strip()
            inifile.write(ini)
        self.app.log.debug(f"Created 'ModOrganizer.ini'.")

        # Create profile files
        prof_path = os.path.join(self.paths['profiles_path'], 'Default')
        # Create initweaks.ini
        with open(os.path.join(prof_path, 'initweaks.ini'), 'w') as inifile:
            inifile.write("""[Archive]\nbInvalidateOlderFiles=1""".strip())
        self.app.log.debug("Created 'initweaks.ini'.")

        # Create modlist.txt
        with open(os.path.join(prof_path, 'modlist.txt'), 'w') as file:
            mods = ""
            for mod in self.loadorder:
                mods += "\n+" + os.path.basename(mod)
            mods = mods.strip()
            file.write(f"# This file was automatically generated by Mod Organizer.\n{mods}")
        self.app.log.debug("Created 'modlist.txt'.")

        # Copy ini files from User\Documents\My Games\Skyrim Special Edition
        ini_path = self.app.doc_path
        shutil.copy(os.path.join(ini_path, 'Skyrim.ini'), os.path.join(prof_path, 'skyrim.ini'))
        shutil.copy(os.path.join(ini_path, 'SkyrimCustom.ini'), os.path.join(prof_path, 'skyrimcustom.ini'))
        shutil.copy(os.path.join(ini_path, 'SkyrimPrefs.ini'), os.path.join(prof_path, 'skyrimprefs.ini'))
        self.app.log.debug("Copied ini files from Skyrim folder.")

        self.app.log.info(f"Created MO2 instance.")
    
    def import_mod(self, folder: str):
        modname = os.path.basename(folder)
        shutil.copytree(folder, os.path.join(self.paths['mods_path'], modname))
    
    def get_size(self):
        self.app.log.debug(f"Calculating size of MO2 instance...")

        # WORK IN PROGRESS!!
        # Calculate size for each instance subfolder
        # because they can be at different locations

        self.app.log.debug(f"Calculation complete. Instance size: {self.size}")

        return super().get_size()

    @staticmethod
    def get_instances(app: MainApp):
        """
        Create a list with all ModOrganizer instances at %LOCALAPPDATA%\\ModOrganizer
        """
        instances_path = os.path.join(os.getenv('LOCALAPPDATA'), 'ModOrganizer')
        instances = []
        # Check if path exists
        if os.path.isdir(instances_path):
            # Filter for folders and ignore files
            instances = [obj for obj in os.listdir(instances_path) if os.path.isdir(os.path.join(instances_path, obj))]
            app.log.info(f"Found {len(instances)} instance(s).")
        # Show error message otherwise
        else:
            app.log.error("Failed to load instances from ModOrganizer: Found no instances.")
        
        # Return list with found instances
        return instances


# Read folder and save files with relative paths to list #############
def create_folder_list(folder, lower=True):
    """
    Creates a list with all files with relative paths to <folder> and returns it.

    Lowers filenames if <lower> is True.
    """
    files = []

    for root, dirs, _files in os.walk(folder):
        for f in _files:
            if f not in ['.gitignore', 'meta.ini']: # check if in blacklist
                path = os.path.join(root, f)
                path = path.removeprefix(f"{folder}\\")
                files.append(path.lower())

    return files

# Define function to round bytes #####################################
def get_size(bytes: int | float, suffix="B"):
    """
    Scale bytes to their proper format; for e.g:
    1253656 => '1.20MB'
    1253656678 => '1.17GB'
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P", "H"]:
        if bytes < factor:
            if f"{bytes:.2f}".split(".")[1] == "00":
                return f"{int(bytes)}{unit}{suffix}"
            else:
                return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor
    else:
        return str(bytes)

# Define function to calculate folder size
def get_folder_size(start_path: str):
    total_size = 0
    i = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except Exception as ex:
                    pass
                i += 1
                #print(f"{f'''Calculating size of '{start_path}'... ({get_size(total_size)})''':100}", end='\r')
    return total_size

# Define function get Steam installation path from registry ##########
def get_steam_path():
    steam_path = ""

    # Get Steam key in registry
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Valve\\Steam") as hkey:
        # Get installation path from key
        steam_path = os.path.normpath(winreg.QueryValueEx(hkey, "installPath")[0])
    
    return steam_path

