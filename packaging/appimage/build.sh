#!/bin/sh
# Build the Linux AppImage. Run INSIDE a manylinux_2_28 x86_64 container
# with the repository mounted at /src (the oldest glibc base we support):
#
#   docker run --rm -v "$PWD:/src" quay.io/pypa/manylinux_2_28_x86_64 \
#       /src/packaging/appimage/build.sh
#
set -e
# The /opt/python manylinux builds are static (no libpython.so), which
# PyInstaller cannot embed. The OS python is a shared build and already
# has tkinter; it only needs pip.
PY=/usr/bin/python3.12
$PY -m pip --version >/dev/null 2>&1 || dnf install -y -q python3.12-pip
$PY -m pip install --quiet pyinstaller

cd /src
$PY -m PyInstaller --noconfirm build_linux.spec

APPDIR=/tmp/NovelMill.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r dist/NovelMill/. "$APPDIR/usr/bin/"
cp packaging/appimage/NovelMill.desktop "$APPDIR/NovelMill.desktop"
cp assets/novel-mill-256.png "$APPDIR/NovelMill.png"
cp packaging/appimage/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"

# appimagetool itself is an AppImage; containers have no FUSE, so run it
# via its self-extracting mode.
curl -fsSL -o /tmp/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x /tmp/appimagetool
mkdir -p /src/dist
cd /tmp
ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run "$APPDIR" \
    /src/dist/NovelMill-x86_64.AppImage
ls -la /src/dist/
