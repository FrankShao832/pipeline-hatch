"""
Build script for py2app — creates a standalone macOS .app bundle.

Usage:
    python setup.py py2app   # Build the .app
    open dist/               # Reveal in Finder
"""

from setuptools import setup

APP = ["launcher/main.py"]

# Include the config directory (YAML files) and images in the app bundle
DATA_FILES = ["config", "launcher/ui/imgs"]

OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "launcher",
        "PySide6",
        "sqlalchemy",
        "yaml",
        "psycopg2",
    ],
    "includes": [
        "launcher.core",
        "launcher.dcc",
        "launcher.ui",
        "launcher.database",
        "launcher.utils",
        "launcher.ui.widgets",
    ],
    "site_packages": True,
    "frameworks": [
        "/usr/local/Caskroom/miniconda/base/lib/libffi.8.dylib",
    ],
    "plist": {
        "CFBundleName": "Pipeline Hatch",
        "CFBundleDisplayName": "Pipeline Hatch",
        "CFBundleIdentifier": "com.pipeline.hatch",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
)
