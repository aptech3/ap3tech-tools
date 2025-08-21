# main_app.spec
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from PyInstaller.building.build_main import Analysis, PYZ, EXE

# Hidden imports that PyInstaller may miss
hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
hiddenimports += collect_submodules("tkinterdnd2")

# Data files (include tkdnd assets and logo if present)
datas = []
datas += collect_data_files("tkinterdnd2")  # needed for drag & drop
if os.path.exists("logo.png"):
    datas.append(("logo.png", "."))  # app will look for it in CWD

a = Analysis(
    ["main_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="RSG-Recovery-Tools",
    console=False,     # GUI app
    # icon="app.ico",  # uncomment if you have one
)
