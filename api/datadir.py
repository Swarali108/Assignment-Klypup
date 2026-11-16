"""Keep the app's writable files on a mounted volume (DATA_DIR), seeded from the files shipped in the image.

Unset DATA_DIR (local demo, tests): nothing happens; everything stays in the checkout as before.

Set (e.g. DATA_DIR=/data on Railway, where a volume is mounted): before the server starts,
  1. each folder in LINKED (outputs, events, cache, api/state) gets a twin under DATA_DIR;
  2. files shipped in the image are copied into it (the seed), see sync_tree for the rule;
  3. the folder in the app is replaced by a symlink to DATA_DIR/<folder>, so every module that
     writes ROOT/outputs/... (pipeline, discovery, API) writes onto the volume without a code change;
  4. cost_log.csv is seeded the same way and the app's copy becomes a symlink to DATA_DIR/cost_log.csv;
     COST_LOG_PATH (read by tools/costs.py) is set to it as well.

Seed rule, per file, using DATA_DIR/.seed-manifest.json (path -> sha256 of the shipped copy last seeded):
  - missing on the volume                  -> copy it (first boot, or a new event shipped in a later deploy);
  - on the volume, unchanged since seeded,
    and the shipped copy is different      -> copy it (a later deploy shipped a newer committed version);
  - changed on the volume since seeded     -> keep the volume copy (work done in production wins).
Nothing on the volume is ever deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKED = ("outputs", "events", "cache", "api/state")
COST_LOG = "cost_log.csv"
MANIFEST = ".seed-manifest.json"


def _sha(path: Path) -> str:
    """sha256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sync_file(source: Path, target: Path, key: str, manifest: dict[str, str]) -> bool:
    """Apply the seed rule to one shipped file; True when it was copied."""
    shipped = _sha(source)
    if target.exists():
        seeded = manifest.get(key)
        if seeded is None or seeded == shipped or _sha(target) != seeded:
            if seeded is None and _sha(target) == shipped:
                manifest[key] = shipped  # same bytes, first time we see it: adopt it
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    manifest[key] = shipped
    return True


def sync_tree(source: Path, target: Path, prefix: str, manifest: dict[str, str]) -> int:
    """sync_file for every file under source; returns how many were copied."""
    copied = 0
    if not source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return 0
    for path in sorted(source.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(source).as_posix()
            copied += sync_file(path, target / rel, f"{prefix}/{rel}", manifest)
    target.mkdir(parents=True, exist_ok=True)
    return copied


def _link(app_path: Path, volume_path: Path) -> None:
    """Replace the app's folder with a symlink to the volume's folder (idempotent)."""
    if app_path.is_symlink():
        if Path(os.readlink(app_path)) == volume_path:
            return
        app_path.unlink()
    elif app_path.is_dir():
        shutil.rmtree(app_path)
    elif app_path.exists():
        app_path.unlink()
    app_path.parent.mkdir(parents=True, exist_ok=True)
    app_path.symlink_to(volume_path, target_is_directory=True)


def _check_writable(data_dir: Path) -> None:
    """Fail loudly (exit 1) when DATA_DIR cannot be written, with the usual fix."""
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        sys.stderr.write(f"DATA_DIR={data_dir} is not writable ({type(exc).__name__}). On Railway, set the service "
                         "variable RAILWAY_RUN_UID=0 so the app can write to the mounted volume.\n")
        raise SystemExit(1)


def prepare(root: Path = ROOT, data_dir: str | None = None) -> dict | None:
    """Seed and link DATA_DIR (env DATA_DIR when not given); None when it is unset. Returns copy counts."""
    value = (data_dir if data_dir is not None else os.environ.get("DATA_DIR") or "").strip()
    if not value:
        return None
    volume = Path(value)
    _check_writable(volume)
    manifest_path = volume / MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    counts: dict[str, int] = {}
    for name in LINKED:
        app_path, volume_path = root / name, volume / name
        if not app_path.is_symlink():  # the image's own copy is the seed; once linked, it was already used
            counts[name] = sync_tree(app_path, volume_path, name, manifest)
        volume_path.mkdir(parents=True, exist_ok=True)
        _link(app_path, volume_path)
    shipped_log, volume_log = root / COST_LOG, volume / COST_LOG
    if shipped_log.is_file() and not shipped_log.is_symlink():
        counts[COST_LOG] = int(sync_file(shipped_log, volume_log, COST_LOG, manifest))
    volume_log.touch(exist_ok=True)
    # A file symlink too, so a pipeline started from a shell (no COST_LOG_PATH) also appends onto the volume.
    if not (shipped_log.is_symlink() and Path(os.readlink(shipped_log)) == volume_log):
        if shipped_log.is_symlink() or shipped_log.exists():
            shipped_log.unlink()
        shipped_log.symlink_to(volume_log)
    os.environ.setdefault("COST_LOG_PATH", str(volume_log))
    manifest_path.write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")
    print(f"DATA_DIR {volume}: seeded {counts}", flush=True)
    return counts


if __name__ == "__main__":
    prepare()
