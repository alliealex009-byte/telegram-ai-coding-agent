import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
import zipfile

BLOCKED_NAMES = {".env", "id_rsa", "id_ed25519", ".git"}


def safe_path(rel_path: str) -> PurePosixPath:
    if not rel_path or rel_path.startswith("/") or "\\" in rel_path:
        raise ValueError(f"Invalid relative path: {rel_path!r}")

    p = PurePosixPath(rel_path)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"Unsafe path traversal: {rel_path!r}")

    if any(part in BLOCKED_NAMES or part.endswith(".pem") or part.endswith(".key") for part in p.parts):
        raise ValueError(f"Blocked sensitive filename in path: {rel_path!r}")

    return p


def parse_obj(raw_text: str) -> dict:
    obj = json.loads(raw_text)
    if not isinstance(obj, dict):
        raise ValueError("Model output JSON must be an object")
    return obj


def prepare_workspace(root: Path, user_id: int, job_id: str) -> Path:
    ws = (root / f"user_{user_id}" / job_id).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def write_project_files(
    workspace: Path,
    files: list[dict],
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> list[str]:
    if not isinstance(files, list) or not files:
        raise ValueError("No project files generated")
    if len(files) > max_files:
        raise ValueError(f"Too many files ({len(files)} > {max_files})")

    written: list[str] = []
    total_bytes = 0
    ws_resolved = workspace.resolve()

    for item in files:
        if not isinstance(item, dict):
            continue
        rel = safe_path(str(item.get("path", "")).strip())
        content = item.get("content", "")
        if not isinstance(content, str):
            raise ValueError(f"File content for {rel} must be a string")

        encoded = content.encode("utf-8")
        if len(encoded) > max_file_bytes:
            raise ValueError(f"File {rel} exceeds max size ({len(encoded)} > {max_file_bytes})")

        total_bytes += len(encoded)
        if total_bytes > max_total_bytes:
            raise ValueError(f"Total project size exceeds limit ({total_bytes} > {max_total_bytes})")

        target = (ws_resolved / Path(*rel.parts)).resolve()
        if ws_resolved not in target.parents and target != ws_resolved:
            raise ValueError(f"Resolved path escapes workspace: {rel}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        written.append(str(rel))

    if not written:
        raise ValueError("No valid files could be written")

    return written


def read_project_snapshot(workspace: Path, max_file_bytes: int) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    ws_resolved = workspace.resolve()
    for root_dir, dirnames, filenames in os.walk(ws_resolved):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".pytest_cache"}]
        for fname in sorted(filenames):
            fpath = Path(root_dir) / fname
            rel = fpath.relative_to(ws_resolved).as_posix()
            data = fpath.read_bytes()
            if len(data) <= max_file_bytes:
                snapshot[rel] = data.decode("utf-8", errors="replace")
    return snapshot


def create_project_zip(workspace: Path, zip_path: Path, max_zip_bytes: int) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    ws_resolved = workspace.resolve()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirnames, filenames in os.walk(ws_resolved):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".pytest_cache"}]
            for fname in sorted(filenames):
                fpath = Path(root_dir) / fname
                arcname = Path(workspace.name) / fpath.relative_to(ws_resolved)
                zf.write(fpath, arcname.as_posix())

    size = zip_path.stat().st_size
    if size > max_zip_bytes:
        zip_path.unlink(missing_ok=True)
        raise ValueError(f"Generated ZIP size ({size} bytes) exceeds limit ({max_zip_bytes} bytes)")

    return zip_path


def cleanup_stale_workspaces(root: Path, ttl_hours: int) -> None:
    if not root.exists():
        return
    cutoff = time.time() - (ttl_hours * 3600)
    for child in root.iterdir():
        try:
            if child.stat().st_mtime < cutoff:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        except OSError:
            pass
