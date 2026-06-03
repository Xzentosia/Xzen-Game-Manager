# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


def source_datas():
    excluded_parts = {
        '__pycache__',
        'backups',
        'user_settings',
    }
    datas = []
    for path in Path('source').rglob('*'):
        if not path.is_file():
            continue
        if any(part.lower() in excluded_parts for part in path.parts):
            continue
        datas.append((str(path), str(path.parent)))
    return datas


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=source_datas(),
    hiddenimports=[],
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
    name='Xzen Game Manager',
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
    icon=['source\\assets\\xzen.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Xzen Game Manager',
)
