#!/bin/sh
# The PyInstaller folder (dist/umcub-gui) as an AppImage: packaging/appimage.sh <folder> <output.AppImage>
# appimagetool from $APPIMAGETOOL (default: appimagetool in PATH); without FUSE set APPIMAGE_EXTRACT_AND_RUN=1.
set -eu
folder=$1
out=$2
here=$(dirname "$0")
appdir=$(mktemp -d)/umcub-gui.AppDir
mkdir -p "$appdir/usr/lib"
cp -a "$folder" "$appdir/usr/lib/umcub-gui"
cp "$here/umcub-gui.desktop" "$here/umcub-gui.svg" "$appdir/"
cat > "$appdir/AppRun" <<'RUN'
#!/bin/sh
exec "$(dirname "$(readlink -f "$0")")/usr/lib/umcub-gui/umcub-gui" "$@"
RUN
chmod +x "$appdir/AppRun"
ARCH=x86_64 "${APPIMAGETOOL:-appimagetool}" --no-appstream "$appdir" "$out"
