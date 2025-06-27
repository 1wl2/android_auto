# auto.spec

block_cipher = None

a = Analysis(
    ['auto.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('platform-tools/*', 'platform-tools')  # 把整个平台工具打包进去
    ],
    hiddenimports=[
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtCore'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='STBAutoTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 改为 True 可调试打开控制台
    icon=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='STBAutoTool'
)
