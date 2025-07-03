# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DMS Dashboard Windows executable.
"""

import sys
from pathlib import Path

block_cipher = None

# Set recursion limit to handle complex imports
sys.setrecursionlimit(5000)

# Define paths
project_root = Path.cwd()
src_path = project_root / "src"
package_path = src_path / "pydms"

# Data files to include
data = []

# Include package data (views and assets are now part of the package)
if package_path.exists():
    # Include views
    views_path = package_path / "views"
    if views_path.exists():
        data.append((str(views_path), "pydms/views"))
    
    # Include assets
    assets_path = package_path / "assets"
    if assets_path.exists():
        data.append((str(assets_path), "pydms/assets"))
    
    # Include other package modules
    for subdir in ["checks", "connectors", "processing", "utils"]:
        subdir_path = package_path / subdir
        if subdir_path.exists():
            data.append((str(subdir_path), f"pydms/{subdir}"))

# Include Streamlit configuration
streamlit_config_path = project_root / ".streamlit"
if streamlit_config_path.exists():
    data.append((str(streamlit_config_path), ".streamlit"))

# Include streamlit static files
import streamlit
streamlit_path = Path(streamlit.__file__).parent
data.append((str(streamlit_path / "static"), "streamlit/static"))
data.append((str(streamlit_path / "runtime"), "streamlit/runtime"))

# Include streamlit web files
data.append((str(streamlit_path / "web"), "streamlit/web"))

# Hidden imports for streamlit and dependencies
hiddenimports = [
    # pyDMS package modules
    'pydms',
    'pydms.app',
    'pydms.cli',
    'pydms.checks',
    'pydms.connectors',
    'pydms.processing',
    'pydms.utils',
    # Streamlit
    'streamlit',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner.script_runner',
    'streamlit.runtime.state',
    'streamlit.runtime.uploaded_file_manager',
    'streamlit.components.v1',
    'streamlit.web.server',
    'streamlit.web.server.server',
    'streamlit.runtime.caching',
    'streamlit.runtime.metrics_util',
    'streamlit_extras',
    # Data analysis
    'plotly',
    'plotly.graph_objects',
    'plotly.express',
    'pandas',
    'numpy',
    'openpyxl',
    'seaborn',
    'sklearn',
    'geopy',
    'pysurveycto',
    'requests',
    'millify',
    'pyarrow',
    'cv2',
    'matplotlib',
    'polars',
    'duckdb',
    'altair',
    'PIL',
    # System
    'tornado',
    'validators',
    'watchdog',
    'click',
    'toml',
    'tzlocal',
    'packaging',
    'importlib_metadata',
    'pytz',
    'dateutil',
    'six',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    # Additional critical imports
    'blinker',
    'cachetools',
    'gitpython',
    'pydeck',
    'pympler',
    'rich',
    'tenacity',
    'typing_extensions',
    'watchdog.observers',
    'watchdog.events',
]

a = Analysis(
    [str(package_path / "cli.py")],
    pathex=[str(project_root), str(src_path)],
    binaries=[],
    datas=data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pydms',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pydms'
)