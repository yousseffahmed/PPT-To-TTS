# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


block_cipher = None
root = Path.cwd()
app_name = "PPT Script to Video Bot"


def safe_collect_data(package):
    try:
        return collect_data_files(package)
    except Exception:
        return []


def safe_collect_submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


def safe_collect_binaries(package):
    try:
        return collect_dynamic_libs(package)
    except Exception:
        return []


datas = [
    ("app/assets", "app/assets"),
    ("app/config", "app/config"),
]

hiddenimports = [
    "edge_tts",
    "TTS",
    "torch",
    "torchcodec",
    "torchaudio",
    "transformers",
    "soundfile",
    "librosa",
    "fitz",
    "docx",
    "pptx",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
]

packages_to_collect = [
    "TTS",
    "trainer",
    "coqpit",
    "encodec",
    "torch",
    "torchaudio",
    "transformers",
    "tokenizers",
    "spacy",
    "docx",
    "lxml",
]

for package in packages_to_collect:
    datas += safe_collect_data(package)
    hiddenimports += safe_collect_submodules(package)

binaries = []
for package in ["torch", "torchaudio"]:
    binaries += safe_collect_binaries(package)


a = Analysis(
    ["app/desktop_app.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == "win32":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        exclude_binaries=False,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon="app/assets/icon.ico",
        version="packaging/windows_version_info.txt",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
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
        upx=False,
        upx_exclude=[],
        name=app_name,
    )

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{app_name}.app",
        icon="app/assets/icon.icns",
        bundle_identifier="com.presenter.pptscriptotovideobot",
        info_plist={
            "CFBundleDisplayName": app_name,
            "CFBundleName": app_name,
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
