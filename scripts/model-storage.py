#!/usr/bin/env python3
"""Keep *all* Hugging Face model/download caches on selected verified storage.

Only stdout of `prepare` is machine-readable shell exports; diagnostics go to stderr.
Designed to ship as STORAGE_HELPER_B64 with the RunPod bootstrap.
"""
import json
import math
import os
from pathlib import Path
import shlex
import sys

DRAFT_REPOS = {
    "dflash2": "incoai/Qwen3.8-27B-DFlash2",
    "dspark": "RadixArk/Qwen3.8-27B-DSpark",
}
EXPORT_NAMES = ("HF_HOME", "HF_HUB_CACHE", "HF_XET_CACHE", "HF_ASSETS_CACHE",
                "HF_DATASETS_CACHE", "XDG_CACHE_HOME", "TORCH_HOME", "TMPDIR",
                "HF_XET_HIGH_PERFORMANCE")
GIB = 1024 ** 3


class StorageError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise StorageError(message)


def mount_info(path, mountinfo="/proc/self/mountinfo"):
    """Return nearest covering mount (point, fstype) in this mount namespace."""
    target = os.path.realpath(path)
    winner = None
    try:
        with open(mountinfo, encoding="utf-8") as handle:
            for line in handle:
                lhs, rhs = line.rstrip("\n").split(" - ", 1)
                parts, rest = lhs.split(), rhs.split()
                point = parts[4]
                # mountinfo encodes space/tab/newline/backslash as octal sequences.
                for escaped, value in (("\\040", " "), ("\\011", "\t"),
                                       ("\\012", "\n"), ("\\134", "\\")):
                    point = point.replace(escaped, value)
                point = os.path.normpath(point)
                if os.path.commonpath((target, point)) == point:
                    if winner is None or len(point) > len(winner[0]):
                        winner = (point, rest[0])
    except (OSError, ValueError, IndexError) as exc:
        raise StorageError(f"cannot inspect /proc/self/mountinfo: {exc}") from exc
    require(winner is not None, f"no mount found for {target}")
    return winner


def existing_ancestor(path):
    path = Path(path)
    while not path.exists():
        require(path.parent != path, f"no existing parent for {path}")
        path = path.parent
    return path


def selected_storage():
    mode = os.environ.get("MODEL_STORAGE", "ram")
    require(mode in ("ram", "ssd"), "MODEL_STORAGE must be exactly 'ram' or 'ssd'")
    chosen = os.environ.get("MODEL_RAM_DIR", "/dev/shm/qwen38-hf") if mode == "ram" \
        else os.environ.get("MODEL_SSD_DIR", "/workspace/hf")
    require(chosen.startswith("/"), "MODEL_RAM_DIR/MODEL_SSD_DIR must be absolute")
    root = Path(os.path.realpath(chosen))
    require(root != Path("/"), "model storage root cannot be /")
    ancestor = existing_ancestor(root)
    require(ancestor.is_dir(), f"model root parent is not a directory: {ancestor}")
    mount, fs_type = mount_info(str(ancestor))
    if mode == "ram":
        require(fs_type == "tmpfs", f"RAM mode requires tmpfs, got {fs_type} at {mount} for {root}")
        require(str(root) != mount, "MODEL_RAM_DIR must be a subdirectory of tmpfs, not its mount root")
    return mode, root, mount, fs_type


def storage_env(root):
    return {
        "HF_HOME": str(root),
        "HF_HUB_CACHE": str(root / "hub"),
        "HF_XET_CACHE": str(root / "xet"),
        "HF_ASSETS_CACHE": str(root / "assets"),
        "HF_DATASETS_CACHE": str(root / "datasets"),
        "XDG_CACHE_HOME": str(root / "xdg"),
        "TORCH_HOME": str(root / "torch"),
        "TMPDIR": str(root / "tmp"),
        "HF_XET_HIGH_PERFORMANCE": "1",
    }


def draft_repo():
    spec = os.environ.get("SPEC", "dflash2")
    require(spec in ("none", "mtp", "dflash2", "dspark"),
            f"unsupported speculative decoding mode: {spec}")
    return DRAFT_REPOS.get(spec)


def model_repos():
    main = os.environ.get("MODEL_ID", "")
    require(main and main.count("/") == 1, "MODEL_ID must be a Hugging Face owner/repo")
    draft = draft_repo()
    return [main] + ([draft] if draft else [])


def _cgroup_mounts(mountinfo="/proc/self/mountinfo"):
    """Yield cgroup mount (root, mountpoint, version) from the current namespace."""
    try:
        with open(mountinfo, encoding="utf-8") as handle:
            for line in handle:
                lhs, rhs = line.rstrip("\n").split(" - ", 1)
                fields, fs = lhs.split(), rhs.split()
                if len(fields) < 5 or len(fs) < 3:
                    continue
                if fs[0] == "cgroup2":
                    yield fields[3], fields[4], "v2"
                elif fs[0] == "cgroup" and "memory" in fs[2].split(","):
                    yield fields[3], fields[4], "v1"
    except (OSError, ValueError, IndexError) as exc:
        raise StorageError(f"cannot inspect cgroup mountinfo: {exc}") from exc


def _cgroup_paths(proc_cgroup="/proc/self/cgroup"):
    """Cgroup namespace paths; choose only the memory hierarchy or unified v2."""
    try:
        with open(proc_cgroup, encoding="utf-8") as handle:
            for line in handle:
                hierarchy, controllers, path = line.strip().split(":", 2)
                if hierarchy == "0" and not controllers:
                    yield "v2", path
                elif "memory" in controllers.split(","):
                    yield "v1", path
    except (OSError, ValueError) as exc:
        raise StorageError(f"cannot inspect /proc/self/cgroup: {exc}") from exc


def _resolve_cgroup_mount(mount_root, mountpoint, member):
    """Mountinfo root may already be a delegated container sub-tree."""
    root = os.path.normpath(mount_root)
    group = os.path.normpath(member)
    target = os.path.normpath(mountpoint)
    require(os.path.isabs(root) and os.path.isabs(group) and os.path.isabs(target),
            "invalid cgroup mount namespace path")
    if group == root:
        relative = "."
    elif os.path.commonpath((root, group)) == root:
        relative = os.path.relpath(group, root)
    else:
        raise StorageError("cgroup membership outside visible memory controller mount")
    resolved = os.path.normpath(os.path.join(target, relative))
    require(os.path.commonpath((target, resolved)) == target, "cgroup path escapes mount")
    return Path(resolved)


def _finite_cgroup_budget(directory, version):
    """Never interpret absent or unlimited cgroup controller as enough RAM."""
    try:
        if version == "v2":
            raw = (directory / "memory.max").read_text().strip()
            used_raw = (directory / "memory.current").read_text().strip()
        else:
            raw = (directory / "memory.limit_in_bytes").read_text().strip()
            used_raw = (directory / "memory.usage_in_bytes").read_text().strip()
        require(raw.isdecimal() and used_raw.isdecimal(),
                f"{version} memory controller missing a finite numeric budget")
        limit, current = int(raw), int(used_raw)
        # Linux v1 'unlimited' sentinel is typically ~2**63; do not trust it.
        require(0 < limit < 1 << 60 and 0 <= current <= limit,
                f"{version} memory controller is unlimited, invalid or already over limit")
        return limit - current
    except OSError as exc:
        raise StorageError(f"cannot read {version} memory controller at {directory}: {exc}") from exc


def cgroup_available(root="/sys/fs/cgroup", mountinfo="/proc/self/mountinfo",
                     proc_cgroup="/proc/self/cgroup"):
    """Prove a *finite* RAM budget from active v2 or v1 controller, else fail."""
    root = Path(root)
    # Retain deterministic tests and explicit standalone cgroup-v2 root probes.
    if (root / "memory.max").is_file():
        available = _finite_cgroup_budget(root, "v2")
        events_path = root / "memory.events"
        if events_path.is_file():
            events = dict(line.split() for line in events_path.read_text().splitlines())
            if int(events.get("oom", "0")):
                print(f"NOTE: cgroup reports {events['oom']} previous OOM event(s)",
                      file=sys.stderr)
        return available

    groups = list(_cgroup_paths(proc_cgroup))
    mounts = list(_cgroup_mounts(mountinfo))
    # Only accept a mounted, explicitly joined memory controller.
    for version, group in groups:
        for mount_root, mountpoint, mount_version in mounts:
            if version != mount_version:
                continue
            directory = _resolve_cgroup_mount(mount_root, mountpoint, group)
            return _finite_cgroup_budget(directory, version)
    raise StorageError("cannot establish finite cgroup v1/v2 memory budget; "
                       "inspect /proc/self/cgroup and mountinfo before RAM download")


def host_available():
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError) as exc:
        raise StorageError(f"cannot read MemAvailable: {exc}") from exc
    raise StorageError("MemAvailable is missing in /proc/meminfo")


def state_dir():
    return Path(os.environ.get("QWEN38_STATE_DIR", "/workspace"))


def repo_bytes(repo_ids):
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ.get("HF_TOKEN") or None)
        total = 0
        for repo in repo_ids:
            info = api.model_info(repo_id=repo, files_metadata=True)
            siblings = info.siblings or []
            require(siblings, f"Hugging Face returned no file inventory for {repo}")
            unknown = [item.rfilename for item in siblings if item.size is None]
            require(not unknown, f"cannot size {repo}: missing file sizes for {unknown[:3]}")
            size = sum(item.size for item in siblings)
            require(size > 0, f"Hugging Face returned empty model {repo}")
            print(f"Model inventory: {repo} = {size / GIB:.2f} GiB ({len(siblings)} files)",
                  file=sys.stderr)
            total += size
        return total
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"could not size all model/draft files before download: {exc}") from exc


def positive_setting(name, default, minimum):
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise StorageError(f"{name} must be a finite number") from exc
    require(math.isfinite(value) and value >= minimum,
            f"{name} must be >= {minimum} and finite")
    return value


def preflight(root, mount):
    """Conservative admission: size model+draft * multiplier + operational room."""
    size = repo_bytes(model_repos())
    multiplier = positive_setting("MODEL_RAM_PEAK_FACTOR", 2.5, 1.5)
    headroom = positive_setting("MODEL_RAM_HEADROOM_GIB", 8, 2) * GIB
    process = positive_setting("MODEL_RAM_PROCESS_HEADROOM_GIB", 8, 2) * GIB
    # hf_xet may hold partial data, staging buffers and duplicate checkpoint data.
    # The extra process reserve covers non-model host RSS during SGLang init.
    required_shm = math.ceil(size * multiplier + headroom)
    required_cgroup = math.ceil(required_shm + process)
    existing = existing_ancestor(root)
    stat = os.statvfs(existing)
    shm_free = stat.f_bavail * stat.f_frsize
    # Log the real tmpfs free space and required model+draft estimate even if
    # the cgroup controller is not visible. No SSD fallback or download here.
    print(f"RAM admission diagnostic: checkpoint+draft={size / GIB:.2f} GiB "
          f"shm_required={required_shm / GIB:.2f} GiB "
          f"shm_available={shm_free / GIB:.2f} GiB "
          f"cgroup_required={required_cgroup / GIB:.2f} GiB "
          f"mount={mount}", file=sys.stderr)
    require(shm_free >= required_shm,
            f"RAM preflight FAILED: tmpfs needs {required_shm / GIB:.2f} GiB "
            f"but has {shm_free / GIB:.2f} GiB free. Resize /dev/shm or select MODEL_STORAGE=ssd")
    cg_free = cgroup_available()
    host_free = host_available()  # Additional guard, never a substitute for cgroup accounting.
    print(f"RAM preflight: checkpoint+draft={size / GIB:.2f} GiB "
          f"peak_factor={multiplier:.2f}, shm_required={required_shm / GIB:.2f} GiB "
          f"shm_available={shm_free / GIB:.2f} GiB, "
          f"cgroup_required={required_cgroup / GIB:.2f} GiB "
          f"cgroup_available={cg_free / GIB:.2f} GiB, "
          f"host_available={host_free / GIB:.2f} GiB, mount={mount}", file=sys.stderr)
    require(shm_free >= required_shm,
            f"RAM preflight FAILED: tmpfs needs {required_shm / GIB:.2f} GiB "
            f"but has {shm_free / GIB:.2f} GiB free. Resize /dev/shm or select MODEL_STORAGE=ssd")
    require(host_free >= required_cgroup,
            f"RAM preflight FAILED: host MemAvailable is only {host_free / GIB:.2f} GiB "
            f"but {required_cgroup / GIB:.2f} GiB is required")
    require(cg_free >= required_cgroup,
            f"RAM preflight FAILED: cgroup needs {required_cgroup / GIB:.2f} GiB "
            f"but has {cg_free / GIB:.2f} GiB available. Pick a larger RAM pod or SSD mode")


def make_dirs(root):
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        for name, value in storage_env(root).items():
            if name == "HF_XET_HIGH_PERFORMANCE":
                continue
            p = Path(value)
            p.mkdir(parents=True, exist_ok=True, mode=0o700)
            require(p.is_dir() and os.access(p, os.W_OK | os.X_OK),
                    f"cache path is not writable: {p}")
            # Even a preexisting cache subdirectory symlink must not escape.
            actual = p.resolve(strict=True)
            require(os.path.commonpath((str(actual), str(root))) == str(root),
                    f"cache path escapes selected storage: {p} -> {actual}")
            require(mount_info(str(actual))[0] == mount_info(str(root))[0],
                    f"cache path has a different filesystem mount: {p}")
    except OSError as exc:
        raise StorageError(f"cannot create writable model/cache/temp paths: {exc}") from exc


def configure_env(root):
    os.environ.update(storage_env(root))
    if os.environ.get("HF_TOKEN"):
        os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]


def verify_snapshot(path, root, mount):
    """Prevent cache symlinks (including snapshot->blob links) escaping storage."""
    path = Path(path)
    require(path.is_dir(), f"snapshot path missing: {path}")
    root = root.resolve(strict=True)
    require(os.path.commonpath((path.resolve(strict=True), root)) == str(root),
            f"snapshot escaped selected storage: {path}")
    require(mount_info(str(path))[0] == mount,
            f"snapshot not on selected storage mount: {path}")
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            entry = Path(parent, name)
            try:
                target = entry.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise StorageError(f"invalid cache link/file {entry}: {exc}") from exc
            require(os.path.commonpath((str(target), str(root))) == str(root),
                    f"cache symlink points outside selected storage: {entry} -> {target}")
            require(mount_info(str(target))[0] == mount,
                    f"cache element is on a different mount: {entry} -> {target}")


def prepare():
    mode, root, mount, _fs = selected_storage()
    model_repos()  # Validate inputs before creating any files.
    configure_env(root)  # Set ALL HF caches before HfApi imports in RAM preflight.
    if mode == "ram":
        preflight(root, mount)
    make_dirs(root)
    require(selected_storage()[2] == mount, "storage mount changed while creating cache directories")
    for key, value in storage_env(root).items():
        print(f"export {key}={shlex.quote(value)}")
    print(f"Storage mode: {mode}, root={root}, mount={mount}", file=sys.stderr)


def download():
    mode, root, mount, _fs = selected_storage()
    require(root.is_dir(), "storage root missing: run prepare before download")
    configure_env(root)  # Must precede importing huggingface_hub.
    from huggingface_hub import snapshot_download
    paths = (state_dir() / "model_path", state_dir() / "draft_path")
    for path in paths:
        path.unlink(missing_ok=True)  # Never re-use stale checkpoint paths after failures.
    models = model_repos()
    resolved = []
    for repo in models:
        path = snapshot_download(repo, max_workers=16,
                                 token=os.environ.get("HF_TOKEN") or None)
        verify_snapshot(path, root, mount)
        resolved.append(str(Path(path).resolve(strict=True)))
        print(f"Downloaded and verified {repo}: {path}", flush=True)
    # Write metadata only after BOTH snapshots were fetched and verified.
    for index, value in enumerate(resolved):
        paths[index].write_text(value)
    if mode == "ram":
        print("RAM mode verified: main and draft paths remain on tmpfs", flush=True)


def audit():
    mode, root, mount, fs_type = selected_storage()
    output = {"mode": mode, "root": str(root), "mount": mount, "filesystem": fs_type,
              "cgroup_available_bytes": None, "snapshots": {}}
    if mode == "ram":
        output["cgroup_available_bytes"] = cgroup_available()
    # Audit Xet, hub and temporary cache links, not just snapshot links.
    if root.is_dir():
        for entry in root.rglob("*"):
            if entry.is_symlink():
                resolved = entry.resolve(strict=True)
                require(os.path.commonpath((str(resolved), str(root))) == str(root),
                        f"cache link escaped storage: {entry} -> {resolved}")
                require(mount_info(str(resolved))[0] == mount,
                        f"cache link crosses mount: {entry} -> {resolved}")
    for name in ("model", "draft"):
        file = state_dir() / (name + "_path")
        if file.is_file():
            path = file.read_text().strip()
            verify_snapshot(path, root, mount)
            output["snapshots"][name] = path
    print(json.dumps(output, indent=2))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "download", "audit"):
        raise StorageError("usage: model-storage.py prepare|download|audit")
    {"prepare": prepare, "download": download, "audit": audit}[sys.argv[1]]()


if __name__ == "__main__":
    try:
        main()
    except (StorageError, OSError) as error:
        print(f"MODEL STORAGE ERROR: {error}", file=sys.stderr)
        sys.exit(64)
