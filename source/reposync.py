#!/usr/bin/env python3
"""RepoSync: manually mirror ANY local folder into a protected destination.

Python standard library only, no Git dependency, no cloud credentials.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

VERSION = "0.2.6"
META_DIR = ".reposync"
PROFILES_FILE = "profiles.json"
DEFAULT_EXCLUDE = [
    ".git", ".venv", "venv", "node_modules", ".pnpm-store", ".yarn", ".tox", ".nox",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis",
    ".cache", ".next", ".nuxt", ".vite", ".turbo", "tmp", "temp", ".tmp", ".temp",
    ".aws", ".ssh", ".azure", ".secrets", "secrets", ".credentials", "credentials",
    ".env", ".env.*", ".envrc", ".npmrc", ".pypirc", ".netrc", ".tmp.driveupload", ".tmp.drivedownload",
    "settings.local.json", "credentials.json", "token.json", "tokens.json", "auth.json",
    "client_secret*.json", "service-account*.json", "service_account*.json",
    "id_rsa*", "id_ed25519*", "*.pem", "*.p12", "*.pfx", "*.key", "*.kdbx",
    "*.sqlite", "*.sqlite3", "*.db", "*.log", "*.pyc", "*.pyo", "*.swp", "*.swo",
    "*.tmp", "*.temp", "*~", "Thumbs.db", ".DS_Store", 
]
CODE_EXCLUDE = [
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.bmp", "*.tiff",
    "*.mp4", "*.mov", "*.mkv", "*.avi", "*.mp3", "*.wav", "*.flac", "*.aac",
    "*.gguf", "*.safetensors", "*.pt", "*.pth", "*.onnx", "*.ckpt", "*.bin",
    "*.zip", "*.7z", "*.rar", "*.iso", "*.exe", "*.dll", "*.so", "*.dylib",
]

# Google Drive Desktop may create upload/download scratch directories while
# managing the destination mirror. They are not project files and must never be
# deleted or traversed by RepoSync. Keep these exceptions narrowly scoped to
# exact names; do not ignore unrelated temporary or user-owned directories.
DESTINATION_MANAGED_NAMES = frozenset({".tmp.driveupload", ".tmp.drivedownload"})


def is_destination_managed_path(rel):
    return rel.rsplit("/", 1)[-1].casefold() in DESTINATION_MANAGED_NAMES


class RepoSyncError(Exception):
    pass


def clock():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def base_dir():
    if os.getenv("REPOSYNC_HOME"):
        return Path(os.environ["REPOSYNC_HOME"]).expanduser().resolve()
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "RepoSync"
    return Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config") / "reposync"


def load_profiles():
    path = base_dir() / PROFILES_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("profiles"), dict):
            raise ValueError("wrong profile schema")
        return data["profiles"]
    except (OSError, ValueError) as exc:
        raise RepoSyncError(f"Cannot load profiles: {exc}") from exc


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def save_profiles(profiles):
    atomic_json(base_dir() / PROFILES_FILE, {"schema": 1, "profiles": profiles})


def get_profile(name):
    profiles = load_profiles()
    if name not in profiles:
        raise RepoSyncError(f"Profile '{name}' not found. Use: reposync list")
    return profiles[name]


def is_link(p):
    try:
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            return True
        a = p.lstat().st_file_attributes if os.name == "nt" else 0
        return bool(a & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except FileNotFoundError:
        return False


def validate_paths(source, destination):
    s, d = Path(source).expanduser().resolve(), Path(destination).expanduser().resolve()
    if not s.is_dir():
        raise RepoSyncError(f"Source is not an accessible folder: {s}")
    if s == d or s in d.parents or d in s.parents:
        raise RepoSyncError("Source and destination must be separate, non-nested folders")
    if d == Path(d.anchor) or d == Path.home().resolve():
        raise RepoSyncError("Refusing to mirror into a drive root or home directory")
    if is_link(Path(destination).expanduser()):
        raise RepoSyncError("Destination root is a symlink/junction; choose a normal folder")
    if is_link(Path(source).expanduser()):
        raise RepoSyncError("Source root is a symlink/junction; choose a normal folder")
    # Avoid writing through a junction/symlink parent where an unexpected directory might be modified.
    p = Path(destination).expanduser().absolute()
    for parent in (p, *p.parents):
        if parent.exists() and is_link(parent):
            raise RepoSyncError(f"Destination path contains a link/junction: {parent}")
    return s, d


def matches(path, pattern):
    """File-name globs match any path component; slash-globs match paths.
    Prefix paths ('docs/' or 'docs/**') select all descendants.
    """
    path = path.replace("\\", "/")
    pattern = pattern.replace("\\", "/").strip()
    if not pattern:
        return False
    if pattern.endswith("/"):
        root = pattern.rstrip("/")
        return path == root or path.startswith(root + "/")
    if pattern.endswith("/**"):
        root = pattern[:-3].rstrip("/")
        return path == root or path.startswith(root + "/")
    if "/" in pattern:
        return fnmatch.fnmatchcase(path.casefold(), pattern.casefold())
    return any(fnmatch.fnmatchcase(part.casefold(), pattern.casefold()) for part in path.split("/"))


def should_exclude(rel, patterns):
    return any(matches(rel, pattern) for pattern in patterns)


def should_include(rel, include_patterns):
    return not include_patterns or any(matches(rel, pattern) for pattern in include_patterns)


def scan_tree(root, *, exclude=(), include=(), source=True):
    """Return files and directories, refusing to traverse links or special objects.
    Paths are slash-normalized and relative to root. Never follows directory links.
    """
    files, dirs, excluded, warnings = {}, set(), 0, []
    if not root.exists():
        return files, dirs, excluded, warnings
    if not root.is_dir():
        raise RepoSyncError(f"Not a directory: {root}")
    def fail_walk(error):
        raise RepoSyncError(f"Folder unreadable: {error}")
    for folder, child_dirs, filenames in os.walk(root, topdown=True, followlinks=False, onerror=fail_walk):
        here = Path(folder)
        rel_folder = here.relative_to(root).as_posix()
        if rel_folder != ".":
            dirs.add(rel_folder)
        for dirname in list(child_dirs):
            child = here / dirname
            rel = child.relative_to(root).as_posix()
            if (rel == META_DIR) or (source and should_exclude(rel, exclude)) or (not source and is_destination_managed_path(rel)):
                child_dirs.remove(dirname)
                excluded += 1
            elif is_link(child):
                if source:
                    child_dirs.remove(dirname)
                    warnings.append(f"Skipped source link/junction: {rel}")
                else:
                    raise RepoSyncError(f"Destination has an unsafe link/junction: {rel}")
        for filename in filenames:
            child = here / filename
            rel = child.relative_to(root).as_posix()
            if rel.startswith(META_DIR + "/") or rel == META_DIR:
                continue
            if not source and is_destination_managed_path(rel):
                # Drive Desktop owns its own transient upload objects. Their
                # concurrent creation/deletion must not race our exact mirror.
                continue
            if source and (should_exclude(rel, exclude) or not should_include(rel, include)):
                excluded += 1
                continue
            if is_link(child):
                if source:
                    warnings.append(f"Skipped source link: {rel}")
                    continue
                raise RepoSyncError(f"Destination has an unsafe link: {rel}")
            try:
                st = child.stat()
            except OSError as exc:
                raise RepoSyncError(f"Cannot stat file {child}: {exc}") from exc
            if not stat.S_ISREG(st.st_mode):
                if source:
                    warnings.append(f"Skipped non-regular source object: {rel}")
                    continue
                raise RepoSyncError(f"Destination contains non-regular object: {rel}")
            files[rel] = (st.st_size, st.st_mtime_ns)
    return files, dirs, excluded, warnings


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def git_info(source):
    if not (source / ".git").exists():
        return None
    try:
        def run(*args):
            return subprocess.run(["git", "-C", str(source), *args], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, timeout=5, check=True).stdout.strip()
        return {"branch": run("branch", "--show-current"), "commit": run("rev-parse", "HEAD"),
                "dirty": bool(run("status", "--porcelain", "--untracked-files=normal"))}
    except (OSError, subprocess.SubprocessError):
        return None  # Non-Git folders and incomplete .git directories are allowed.


def marker_path(destination):
    return destination / META_DIR / "owner.json"


def marker_state(profile):
    source, destination = validate_paths(profile["source"], profile["destination"])
    marker = marker_path(destination)
    if is_link(destination / META_DIR) or is_link(marker) or is_link(destination / META_DIR / "last-sync.json"):
        raise RepoSyncError("Destination metadata contains a link/junction; refusing unsafe access")
    if marker.exists():
        try:
            obj = json.loads(marker.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise RepoSyncError(f"Invalid destination owner marker: {exc}") from exc
        if obj.get("schema") != 1 or obj.get("source") != str(source) or obj.get("profile") != profile["name"] or obj.get("destination") != str(destination):
            raise RepoSyncError("Destination owner marker belongs to a different profile or source")
        return "owned"
    if (destination / META_DIR).exists():
        raise RepoSyncError("Destination has an unrecognized .reposync metadata folder; refusing to modify it")
    if destination.exists() and any(destination.iterdir()):
        return "unmanaged-populated"
    return "new"


def plan(profile):
    source, destination = validate_paths(profile["source"], profile["destination"])
    owner = marker_state(profile)
    exclusions = list(DEFAULT_EXCLUDE) + (CODE_EXCLUDE if profile["preset"] == "code" else []) + list(profile.get("exclude", []))
    include = list(profile.get("include", []))
    sf, sd, excluded, warnings = scan_tree(source, exclude=exclusions, include=include, source=True)
    df, dd, _, _ = scan_tree(destination, source=False)
    # Restrict source directories in include-only mode to ancestors of included files,
    # plus explicitly matched directories. Empty directories are preserved in default mode.
    if include:
        needed = set()
        for rel in sf:
            parts = rel.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                needed.add("/".join(parts[:i]))
        needed.update(d for d in sd if should_include(d, include))
        sd = needed
    file_paths, dir_paths = set(sf), set(sd)
    # A file may replace a directory or vice versa; the preview explicitly identifies both.
    conflicts = sorted((file_paths & dd) | (dir_paths & set(df)))
    to_copy = []
    for rel in sorted(sf):
        if rel not in df:
            to_copy.append(rel)
        elif sf[rel][0] != df[rel][0] or hash_file(source / rel) != hash_file(destination / rel):
            # Content determines transfers; differing timestamp precision on Drive
            # must not cause a complete re-upload on every manual sync.
            to_copy.append(rel)
    delete_files = sorted(set(df) - file_paths)
    delete_dirs = sorted(dd - dir_paths, key=lambda x: (x.count("/"), x), reverse=True)
    create_dirs = sorted(dir_paths - dd, key=lambda x: (x.count("/"), x))
    return {
        "profile": profile["name"], "source": str(source), "destination": str(destination),
        "owner": owner, "source_files": len(sf), "source_directories": len(sd),
        "destination_managed_exceptions": sorted(DESTINATION_MANAGED_NAMES),
        "excluded_count": excluded, "warnings": warnings, "git": git_info(source),
        "copy": to_copy, "delete_files": delete_files, "delete_dirs": delete_dirs,
        "create_dirs": create_dirs, "type_conflicts": conflicts,
        "copy_bytes": sum(sf[k][0] for k in to_copy),
        "unchanged_files": len(sf) - len(to_copy),
        "all_source_files": sorted(sf), "all_source_dirs": sorted(sd),
        "all_source_file_stats": {k:list(sf[k]) for k in sf},
    }


def slim_plan(data):
    return {k: v for k, v in data.items() if k not in ("all_source_files", "all_source_dirs", "all_source_file_stats")}


def verify(profile):
    source, dest = validate_paths(profile["source"], profile["destination"])
    state = marker_state(profile)
    if state != "owned":
        raise RepoSyncError(f"Destination isn't owned by this profile (state: {state})")
    x = plan(profile)
    # Plan can use mtime/size; full verify checks bytes even when metadata differs.
    src_file_set = set(x["all_source_files"])
    dest_files, dest_dirs, _, _ = scan_tree(dest, source=False)
    missing = sorted(src_file_set - set(dest_files))
    extra = sorted(set(dest_files) - src_file_set)
    different = []
    for rel in sorted(src_file_set & set(dest_files)):
        if hash_file(source / rel) != hash_file(dest / rel):
            different.append(rel)
    source_dirs = set(x["all_source_dirs"])
    missing_dirs = sorted(source_dirs - dest_dirs)
    extra_dirs = sorted(dest_dirs - source_dirs)
    ok = not (missing or extra or different or missing_dirs or extra_dirs)
    return {"ok": ok, "profile": profile["name"], "source_files": len(src_file_set),
            "destination_files": len(dest_files), "missing": missing, "extra": extra,
            "different": different, "missing_dirs": missing_dirs, "extra_dirs": extra_dirs,
            "source_links_skipped": x["warnings"], "file_content_verification": "SHA-256",
            "scope": "local destination only; Google Drive cloud upload is independent",
            "destination_managed_exceptions": sorted(DESTINATION_MANAGED_NAMES)}


@contextlib.contextmanager
def sync_lock(name):
    home = base_dir()
    home.mkdir(parents=True, exist_ok=True)
    path = home / ("sync-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:20] + ".lock")
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RepoSyncError("Sync already running or a stale lock exists. Check for running copies first.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()} at={clock()}\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def sync(profile, *, yes=False, adopt=False):
    with sync_lock(profile["name"]):
        p = plan(profile)
        source, destination = Path(p["source"]), Path(p["destination"])
        if p["owner"] == "unmanaged-populated" and not adopt:
            raise RepoSyncError("Destination already has unrelated content. Preview, then pass --adopt --yes to take ownership.")
        deletions = len(p["delete_files"]) + len(p["delete_dirs"])
        if not yes:
            if not sys.stdin.isatty():
                raise RepoSyncError("Noninteractive sync requires explicit --yes (and --adopt if needed)")
            print(f"Sync {profile['name']}: {len(p['copy'])} copy/update, {deletions} deletions.", file=sys.stderr)
            answer = input("Type SYNC to proceed: ")
            if answer != "SYNC":
                raise RepoSyncError("Sync canceled")
        # Recompute plan *after* prompting to detect source changes during user confirmation.
        p2 = plan(profile)
        keys = ("copy", "delete_files", "delete_dirs", "create_dirs", "all_source_file_stats", "type_conflicts")
        if any(p[k] != p2[k] for k in keys):
            raise RepoSyncError("Source or destination changed while confirming. Preview again before syncing.")
        p = p2
        destination.mkdir(parents=True, exist_ok=True)
        meta = destination / META_DIR
        meta.mkdir(exist_ok=True)
        # Metadata marker belongs to this profile; set before transfers to permit retry.
        atomic_json(marker_path(destination), {"schema": 1, "source": str(source),
            "destination": str(destination), "profile": profile["name"], "created_utc": clock()})

        # Safest common case: copy first, delete obsolete entries after successful copies.
        # Resolve file/dir shape collisions explicitly before creating new paths.
        for rel in p["type_conflicts"]:
            target = destination / rel
            if is_link(target):
                raise RepoSyncError(f"Unsafe destination link: {rel}")
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for rel in p["all_source_dirs"]:
            target = destination / rel
            if target.exists() and not target.is_dir():
                raise RepoSyncError(f"Unexpected type while creating source directory: {rel}")
            target.mkdir(parents=True, exist_ok=True)
        for rel in p["copy"]:
            source_file, target = source / rel, destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(".reposync-transfer-" + uuid.uuid4().hex + ".tmp")
            try:
                shutil.copy2(source_file, tmp)
                if hash_file(source_file) != hash_file(tmp):
                    raise RepoSyncError(f"Source file changed during copy or checksum mismatch: {rel}")
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)
        # Reject a changing source BEFORE the normal delete phase.
        fresh = plan(profile)
        if fresh["all_source_file_stats"] != p["all_source_file_stats"] or fresh["all_source_dirs"] != p["all_source_dirs"]:
            raise RepoSyncError("Source changed during copy. Aborted before stale-file deletion; rerun when idle.")
        # New plan still sees unneeded destination contents. These are the only deletion targets.
        for rel in fresh["delete_files"]:
            target = destination / rel
            if is_link(target):
                raise RepoSyncError(f"Unsafe destination link: {rel}")
            if target.is_file():
                target.unlink()
        for rel in fresh["delete_dirs"]:
            target = destination / rel
            if is_link(target):
                raise RepoSyncError(f"Unsafe destination link: {rel}")
            if target.is_dir():
                # Child dirs can contain obsolete files; safe because all were indexed.
                try:
                    target.rmdir()
                except OSError as exc:
                    raise RepoSyncError(f"Could not remove obsolete destination directory {rel}: {exc}. "
                                        "A concurrent process may have created content or retained an open handle; "
                                        "mirror is not fully verified. Stop and preview before retrying.") from exc
        result = verify(profile)
        if not result["ok"]:
            raise RepoSyncError("Local mirror verification FAILED; destination may be incomplete. Details: " + json.dumps(result))
        state = {"schema": 1, "profile": profile["name"], "completed_utc": clock(),
                 "source": str(source), "destination": str(destination),
                 "source_files": p["source_files"], "copied": len(p["copy"]),
                 "deleted_files": len(p["delete_files"]), "deleted_dirs": len(p["delete_dirs"]),
                 "git": p["git"], "warnings": p["warnings"],
                 "verification": "local SHA-256 verified; Drive Desktop uploads asynchronously"}
        atomic_json(meta / "last-sync.json", state)
        return {"ok": True, **state}


def format_out(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if data.get("command") == "list":
        if not data["profiles"]:
            print("No profiles. Use reposync add NAME --source ... --destination ...")
        for n, v in data["profiles"].items():
            print(f"{n}: {v['source']}  ->  {v['destination']}  [{v['preset']}]")
    elif data.get("command") == "preview":
        print(f"{data['profile']}  {data['source']}  ->  {data['destination']}")
        print(f"Ownership: {data['owner']} | source files: {data['source_files']} | excluded: {data['excluded_count']}")
        print(f"Copy/update: {len(data['copy'])} ({data['copy_bytes']:,} B) | delete files: {len(data['delete_files'])} | delete folders: {len(data['delete_dirs'])}")
        for label, key in (("COPY", "copy"),("DELETE FILE", "delete_files"),("DELETE DIR", "delete_dirs")):
            for p in data[key][:100]:
                print(f"  {label}: {p}")
            if len(data[key]) > 100:
                print(f"  ... and {len(data[key]) - 100} more")
        for w in data["warnings"]:
            print(f"  WARNING: {w}")
        if data["owner"] == "unmanaged-populated":
            print("  WARNING: Destination has unowned files. Sync requires --adopt --yes.")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="reposync", description="Manually mirror ANY local folder. Never uploads directly to Google Drive.")
    parser.add_argument("--version", action="version", version=VERSION)
    subs = parser.add_subparsers(dest="command", required=True)
    def sub(name, description):
        p = subs.add_parser(name, help=description)
        p.add_argument("--json", action="store_true", help="Machine-readable output")
        return p
    ap = sub("add", "Save a folder-to-folder sync profile (no copying)")
    ap.add_argument("name")
    ap.add_argument("--source", required=True)
    ap.add_argument("--destination", required=True)
    ap.add_argument("--preset", choices=["review", "code"], default="review")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    ap.add_argument("--include", action="append", default=[], metavar="GLOB")
    ep = sub("update", "Update an existing profile (filters are replaced when supplied)")
    ep.add_argument("name")
    ep.add_argument("--source")
    ep.add_argument("--destination")
    ep.add_argument("--preset", choices=["review", "code"])
    ep.add_argument("--exclude", action="append", default=None, metavar="GLOB")
    ep.add_argument("--include", action="append", default=None, metavar="GLOB")
    sub("list", "List saved profiles")
    for name in ("preview", "sync", "verify", "status", "remove"):
        p = sub(name, {"preview":"Preview exact additions, updates and deletions", "sync":"Apply mirror manually",
                       "verify":"SHA-256 compare local source and mirror", "status":"Read last successful local-sync state",
                       "remove":"Remove profile (never deletes destination)"}[name])
        p.add_argument("name")
        if name == "sync":
            p.add_argument("--yes", action="store_true", help="Explicit noninteractive authorization")
            p.add_argument("--adopt", action="store_true", help="Explicitly accept a populated unmanaged destination")
    sub("gui", "Open the optional graphical frontend")
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            from reposync_gui import run_gui
            run_gui()
            return 0
        if args.command == "add":
            source, destination = validate_paths(args.source, args.destination)
            profs = load_profiles()
            if args.name in profs:
                raise RepoSyncError(f"Profile already exists: {args.name}. Remove first to change settings.")
            if not args.name.strip() or args.name.startswith(".") or any(c in args.name for c in "/\\\r\n"):
                raise RepoSyncError("Profile name must be nonempty and cannot contain slashes or newlines")
            p = {"name": args.name, "source": str(source), "destination": str(destination),
                 "preset": args.preset, "exclude": args.exclude, "include": args.include}
            marker_state(p)  # fail if destination has conflicting ownership
            profs[args.name] = p
            save_profiles(profs)
            result = {"ok": True, "command": "add", "profile": p}
        elif args.command == "update":
            profs = load_profiles()
            if args.name not in profs:
                raise RepoSyncError(f"Profile '{args.name}' not found")
            p = dict(profs[args.name])
            for attr in ("source", "destination", "preset", "exclude", "include"):
                val = getattr(args, attr)
                if val is not None:
                    p[attr] = val
            s, d = validate_paths(p["source"], p["destination"])
            p["source"], p["destination"] = str(s), str(d)
            marker_state(p)
            profs[args.name] = p
            save_profiles(profs)
            result = {"ok": True, "command": "update", "profile": p}
        elif args.command == "list":
            result = {"ok": True, "command": "list", "profiles": load_profiles()}
        elif args.command == "remove":
            profs = load_profiles()
            if args.name not in profs:
                raise RepoSyncError("No such profile: " + args.name)
            del profs[args.name]
            save_profiles(profs)
            result = {"ok": True, "command": "remove", "removed": args.name,
                      "note": "Destination files and metadata were NOT deleted"}
        elif args.command == "preview":
            result = {"ok": True, "command": "preview", **slim_plan(plan(get_profile(args.name)))}
        elif args.command == "sync":
            result = {"command": "sync", **sync(get_profile(args.name), yes=args.yes, adopt=args.adopt)}
        elif args.command == "verify":
            result = {"command": "verify", **verify(get_profile(args.name))}
            format_out(result, args.json)
            return 0 if result["ok"] else 3
        elif args.command == "status":
            profile = get_profile(args.name)
            _, d = validate_paths(profile["source"], profile["destination"])
            path = d / META_DIR / "last-sync.json"
            result = {"ok": True, "command": "status", "profile": args.name,
                      "last_sync": json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None,
                      "note": "This reflects LOCAL mirroring only, not cloud upload completion"}
        else:
            raise RepoSyncError("Unsupported command")
        format_out(result, args.json)
        return 0
    except (RepoSyncError, OSError, ValueError, ImportError) as exc:
        error = {"ok": False, "error": {"type": exc.__class__.__name__, "message": str(exc)}}
        if getattr(args, "json", False):
            print(json.dumps(error, ensure_ascii=False))
        else:
            print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
