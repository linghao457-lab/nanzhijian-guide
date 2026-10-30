#!/usr/bin/env python3
"""Build a frozen public tutorial snapshot, without any app/customer data."""
import concurrent.futures
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "mirror-manifest.json").read_text(encoding="utf-8"))
OUT = ROOT / "site"
if OUT.exists() and any(OUT.iterdir()):
    raise SystemExit("Refusing to overwrite populated output")
OUT.mkdir(exist_ok=True)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def materialize(entry):
    rel = PurePosixPath(entry["path"])
    if rel.is_absolute() or ".." in rel.parts or "\\" in entry["path"]:
        raise ValueError("Unsafe output path")
    if "content" in entry:
        data = entry["content"].encode("utf-8")
    else:
        url = entry["url"]
        if not any(url.startswith(host + "/") for host in manifest["allowed_source_origins"]):
            raise ValueError("Unexpected source origin")
        failure = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=40) as response:
                    if response.status != 200:
                        raise ValueError("Non-200 source response")
                    data = response.read(10 * 1024 * 1024 + 1)
                if len(data) > 10 * 1024 * 1024 or digest(data) != entry["source_sha256"]:
                    raise ValueError("Source hash mismatch: " + str(rel))
                failure = None
                break
            except Exception as exc:
                failure = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        if failure:
            raise failure
        if entry.get("replace"):
            text = data.decode("utf-8")
            for old, new in entry["replace"]:
                if old not in text:
                    raise ValueError("Expected link missing: " + str(rel))
                text = text.replace(old, new)
            data = text.encode("utf-8")
    if digest(data) != entry["sha256"] or len(data) != entry["bytes"]:
        raise ValueError("Final hash/size mismatch: " + str(rel))
    target = OUT.joinpath(*rel.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return len(data)

entries = manifest["files"]
if len(entries) != len({entry["path"] for entry in entries}):
    raise SystemExit("Duplicate manifest path")
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    sizes = list(pool.map(materialize, entries))
print("Verified %d public static files (%d bytes)." % (len(sizes), sum(sizes)))
