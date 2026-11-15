# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Explicit file list (NOT the whole config/ dir): the machine-local
        # config/local.yaml and any *.bak.* backups must never ship inside
        # the bundle. Keep this list in sync when adding shared config files.
        ('config/database.yaml', 'config'),
        ('config/dcc.yaml', 'config'),
        ('config/projects.yaml', 'config'),
        ('config/local.yaml.example', 'config'),
        ('launcher/ui/imgs', 'launcher/ui/imgs'),
    ],
    hiddenimports=['launcher.core', 'launcher.dcc', 'launcher.ui', 'launcher.database', 'launcher.utils', 'launcher.ui.widgets', 'yaml', 'sqlalchemy', 'psycopg2', 'PySide6'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pipeline Hatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['launcher/ui/imgs/pipeline_hatch.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Pipeline Hatch',
)
app = BUNDLE(
    coll,
    name='Pipeline Hatch.app',
    icon='launcher/ui/imgs/pipeline_hatch.icns',
    bundle_identifier='com.pipeline.hatch',
)
