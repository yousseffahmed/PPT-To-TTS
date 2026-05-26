# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


block_cipher = None
root = Path.cwd()


a = Analysis(
    ["app/desktop_app.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[
        ("app/config/settings.json", "app/config"),
        ("app/config/voices.json", "app/config"),
        ("app/assets/icon.ico", "app/assets"),
        ("app/assets/voices/default_narrator.wav", "app/assets/voices"),
        ("app/assets/icons/chevron-down.svg", "app/assets/icons"),
        ("app/assets/icons/check-white.svg", "app/assets/icons"),
    ],
    hiddenimports=[
        "edge_tts",
        "TTS",
        "torch",
        "torchcodec",
        "transformers",
        "fitz",
        "docx",
        "pptx",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
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
    name="PPTScriptToVideo",
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
    icon="app/assets/icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PPTScriptToVideo",
)
