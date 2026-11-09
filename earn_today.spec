# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：将 earn_today 打包为 macOS .app（Apple Silicon / arm64）。

打包命令：
    pyinstaller earn_today.spec

产物：
    dist/EarnToday.app
"""

block_cipher = None


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    # 将整个 assets 目录打进包内，运行时通过 sys._MEIPASS 定位
    datas=[("assets", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EarnToday",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 窗口应用，不显示终端
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",  # 目标用户为 Apple Silicon
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EarnToday",
)

app = BUNDLE(
    coll,
    name="EarnToday.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="com.earntoday.app",
    info_plist={
        "CFBundleName": "EarnToday",
        "CFBundleDisplayName": "今天赚了多少",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        # 浮窗类应用不在 Dock 显示图标（LSUIElement=1 为纯后台/菜单栏样式）
        # 如需在 Dock 显示，删除下面一行
        "LSUIElement": True,
    },
)
