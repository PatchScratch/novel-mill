# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Novel Mill (Linux AppImage build).
#
# Produces in dist/NovelMill/  (onedir — the AppDir wraps this tree, so
# the AppImage does not double-extract on every launch).
#
# Build:  pyinstaller --noconfirm build_linux.spec
#
# Same data layout as the Windows spec; see the comment there.

from pathlib import Path

ROOT = Path(SPECPATH).resolve()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

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
    [],
    exclude_binaries=True,
    name="NovelMill",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NovelMill",
)
