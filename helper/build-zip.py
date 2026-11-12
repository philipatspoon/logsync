#!/usr/bin/env python3
"""Packar helper/Logsync.app och LÄS MIG.txt till Logsync-app.zip i repots rot.
Kör efter varje ändring i helper/:   python3 helper/build-zip.py
Zip-filen blir identisk varje gång (fasta tider), så git visar bara verkliga ändringar."""
import pathlib, sys, zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "Logsync-app.zip"


def entries():
    files = sorted(p for p in (HERE / "Logsync.app").rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store")
    return [(p.relative_to(HERE).as_posix(), p) for p in files] + [("LÄS MIG.txt", HERE / "LÄS MIG.txt")]


def build(out=OUT):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in entries():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            exe = path.parent.name == "MacOS"                      # startfilen måste vara körbar
            info.external_attr = (0o100755 if exe else 0o100644) << 16
            z.writestr(info, path.read_bytes())
    return out


def in_sync(out=OUT):
    """True om zip-filen innehåller exakt det som ligger i helper/."""
    if not out.exists():
        return False
    with zipfile.ZipFile(out) as z:
        have = {i.filename: z.read(i.filename) for i in z.infolist()}
    want = {name: path.read_bytes() for name, path in entries()}
    return have == want


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if in_sync() else "Logsync-app.zip stämmer inte med helper/. Kör: python3 helper/build-zip.py")
    print("Skrev", build().name, "med", len(entries()), "filer")
