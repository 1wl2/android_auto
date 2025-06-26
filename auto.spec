# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['auto.py'],
    pathex=[],
    binaries=[],
    datas=[('top_Performance.sh', '.'), ('cleanup.sh', '.'), ('platform-tools\\adb.exe', 'platform-tools'), ('platform-tools\\AdbWinApi.dll', 'platform-tools'), ('platform-tools\\AdbWinUsbApi.dll', 'platform-tools')],
    hiddenimports=['PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtNetwork'],
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
    a.binaries,
    a.datas,
    [],
    name='auto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
