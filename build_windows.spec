# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Novel Mill (Windows release build).
#
# Produces in dist/:
#   NovelMill.exe   (GUI, windowed, single file)
#
# Build:  pyinstaller --noconfirm build_windows.spec
#
# The launcher loads its tab modules by filename (wn-*.py) at runtime,
# so they ship as data files inside the bundle and wn-local-mill.py
# resolves them through sys._MEIPASS when frozen.

from pathlib import Path

ROOT = Path(SPECPATH).resolve()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

# Sibling modules + shipped data. "." = the bundle root (sys._MEIPASS).
DATAS = [
    (str(ROOT / "wn_series.py"), "."),
    (str(ROOT / "wn-epub-extract.py"), "."),
    (str(ROOT / "wn-ocr.py"), "."),
    (str(ROOT / "wn-raw-split.py"), "."),
    (str(ROOT / "wn-scene-mill.py"), "."),
    (str(ROOT / "wn-raw-split.rules.json"), "."),
    (str(ROOT / "VERSION"), "."),
]

a = Analysis(
    [str(ROOT / "wn-local-mill.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    # The sibling wn-*.py files ship as data, so their imports are invisible
    # to analysis — list every stdlib module they pull in.
    hiddenimports=[
        "html",
        "html.parser",
        "zipfile",
        "posixpath",
        "xml.etree.ElementTree",
        "shutil",
        "subprocess",
        "tempfile",
        "queue",
        "threading",
        "dataclasses",
        "urllib.request",
        "urllib.error",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NovelMill",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "novel-mill.ico"),
)
