import json, re, zipfile
from pathlib import Path, PurePosixPath
from app.config import cfg

def parse_obj(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", raw, flags=re.I)
    try: obj = json.loads(raw)
    except json.JSONDecodeError:
        a, b = raw.find("{"), raw.rfind("}")
        if a < 0 or b <= a: raise ValueError("Model did not return valid JSON")
        obj = json.loads(raw[a:b+1])
    if not isinstance(obj, dict): raise ValueError("Expected JSON object")
    return obj

def safe_path(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 240: raise ValueError("Invalid path")
    p = PurePosixPath(raw.replace("\\\\", "/"))
    if p.is_absolute() or any(x in ("", ".", "..") for x in p.parts): raise ValueError("Unsafe path")
    if ":" in p.parts[0] or p.parts[0].startswith("~"): raise ValueError("Absolute path rejected")
    if p.name.lower() in {".env", "id_rsa", "id_ed25519", "authorized_keys"}: raise ValueError("Sensitive filename rejected")
    if p.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}: raise ValueError("Private-key file rejected")
    if any(x.startswith(".git") for x in p.parts): raise ValueError("Git metadata rejected")
    return Path(*p.parts)

def write_files(root, obj):
    entries = obj.get("files")
    if not isinstance(entries, list) or not entries: raise ValueError("No files returned")
    if len(entries) > cfg.max_files: raise ValueError("Too many project files")
    total, seen, names = 0, set(), []
    for item in entries:
        rel = safe_path(item.get("path") if isinstance(item, dict) else None)
        content = item.get("content")
        if not isinstance(content, str): raise ValueError("File content must be text")
        data = content.encode()
        if len(data) > cfg.max_file_bytes: raise ValueError(f"File too large: {rel}")
        total += len(data)
        if total > cfg.max_total_bytes: raise ValueError("Project exceeds total size limit")
        if str(rel) in seen: raise ValueError(f"Duplicate file: {rel}")
        seen.add(str(rel))
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        names.append(str(rel))
    return names

def make_zip(root, job):
    out = root.parent / f"project_{job}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            if p.is_file(): z.write(p, p.relative_to(root))
    if out.stat().st_size > cfg.max_zip:
        out.unlink(missing_ok=True)
        raise ValueError("ZIP is too large to send")
    return out
