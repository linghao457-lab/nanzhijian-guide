#!/usr/bin/env python3
"""Deploy only the frozen, public static tutorial archive; no app/customer access."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "mirror-manifest.json").read_text(encoding="utf-8"))
package = manifest["archive"]
if not package["url"].startswith("https://github.com/linghao457-lab/nanzhijian-guide/releases/download/"):
    raise SystemExit("Unexpected archive origin")
with urllib.request.urlopen(package["url"], timeout=120) as response:
    if response.status != 200:
        raise SystemExit("Archive unavailable")
    raw = response.read(60 * 1024 * 1024 + 1)
if len(raw) != package["bytes"] or hashlib.sha256(raw).hexdigest() != package["sha256"]:
    raise SystemExit("Archive hash or size mismatch")
entries = manifest["files"]
expected = {entry["path"]: entry for entry in entries}
if len(entries) != len(expected):
    raise SystemExit("Duplicate manifest path")
out = ROOT / "site"
if out.exists() and any(out.iterdir()):
    raise SystemExit("Refusing to overwrite populated output")
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names = archive.namelist()
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise SystemExit("Archive contents differ from manifest")
    total = 0
    for name in names:
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name:
            raise SystemExit("Unsafe path")
        info = archive.getinfo(name)
        if info.is_dir() or info.file_size > 10 * 1024 * 1024:
            raise SystemExit("Unexpected entry")
        data = archive.read(name)
        entry = expected[name]
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit("Static file hash/size mismatch: " + name)
        target = out.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        total += len(data)
print("Verified %d public static files (%d bytes)." % (len(entries), total))
