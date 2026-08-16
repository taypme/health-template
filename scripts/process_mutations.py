#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "kernel.json"
STATE_PATH = ROOT / "kernel-state.json"
KERNELS_ROOT = ROOT / "kernels"
MUTATIONS_ROOT = ROOT / "mutations"
EXPECTED_KEYS = {"action", "selector", "json"}
ALLOWED_ACTIONS = {"add", "remove", "update"}
MAX_FILENAME_BYTES = 240


def encode_storage_name(name: str) -> str:
    return name.replace("%", "%25").replace("/", "%2F").replace("\\", "%5C")


def is_safe_row_name(name: str) -> bool:
    return (
        name not in {"", ".", ".."}
        and "\x00" not in name
        and len(encode_storage_name(name).encode("utf-8")) <= MAX_FILENAME_BYTES
    )


class MutationError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        # Repair historical rows accidentally stored as a JSON string containing JSON.
        if isinstance(value, str):
            value = json.loads(value)
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise MutationError(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc


def relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_registry() -> dict[str, dict[str, Path]]:
    registry = load_json(REGISTRY_PATH)
    kernels = registry.get("kernels")
    if not isinstance(kernels, list):
        raise MutationError("kernel.json must contain a kernels list")

    result: dict[str, dict[str, Path]] = {}
    for row in kernels:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise MutationError("Every kernel registry row needs a string name")
        name = row["name"]
        data_dir = row.get("data_dir", f"kernels/{name}/data")
        index_path = row.get("index_path", f"kernels/{name}/index.json")
        pack_path = row.get("pack_path", f"kernels/{name}/pack.json")
        if not all(isinstance(value, str) for value in (data_dir, index_path, pack_path)):
            raise MutationError(f"Invalid paths for kernel {name}")
        result[name] = {
            "data_dir": ROOT / data_dir,
            "index_path": ROOT / index_path,
            "pack_path": ROOT / pack_path,
        }
    return result


def load_rows(data_dir: Path) -> list[dict[str, Any]]:
    if not data_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*.json")):
        row = load_json(path)
        if not isinstance(row, dict):
            raise MutationError(f"Expected an object in {path.relative_to(ROOT)}")
        rows.append(row)
    return rows


def load_index(path: Path) -> list[str]:
    value = load_json(path)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MutationError(f"Expected a filename array in {path.relative_to(ROOT)}")
    return value


def generated_name(kernel: str, row: dict[str, Any], ordinal: int) -> str:
    timestamp = str(row.get("timestamp", "")).lower()
    timestamp = re.sub(r"[^a-z0-9]+", "_", timestamp).strip("_")
    if timestamp:
        base = f"{kernel}_{timestamp}"
    else:
        digest = hashlib.sha256(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12]
        base = f"{kernel}_{digest}"
    return base if ordinal == 0 else f"{base}_{ordinal + 1}"


def normalize_names(kernel: str, rows: list[dict[str, Any]]) -> None:
    used: set[str] = set()
    for position, row in enumerate(rows):
        raw = row.get("name")
        name = str(raw).strip() if raw is not None else ""
        if not is_safe_row_name(name):
            name = generated_name(kernel, row, position)
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        row["name"] = candidate
        used.add(candidate)


def validate_selector(value: Any, path: Path) -> tuple[str, re.Pattern[str]]:
    if not isinstance(value, dict) or set(value) != {"field", "regex"}:
        raise MutationError(
            f"{path.relative_to(ROOT)} selector must contain exactly field and regex"
        )
    field, regex = value.get("field"), value.get("regex")
    if not isinstance(field, str) or not field or not isinstance(regex, str):
        raise MutationError(f"Invalid selector in {path.relative_to(ROOT)}")
    try:
        return field, re.compile(regex)
    except re.error as exc:
        raise MutationError(f"Invalid regex in {path.relative_to(ROOT)}: {exc}") from exc


def validate_mutation(path: Path) -> dict[str, Any]:
    mutation = load_json(path)
    if not isinstance(mutation, dict) or set(mutation) != EXPECTED_KEYS:
        raise MutationError(
            f"{path.relative_to(ROOT)} must contain exactly action, selector, and json"
        )
    action = mutation.get("action")
    if action not in ALLOWED_ACTIONS:
        raise MutationError(
            f"{path.relative_to(ROOT)} action must be add, remove, or update"
        )
    selector, payload = mutation.get("selector"), mutation.get("json")
    if action == "add":
        if selector is not None or not isinstance(payload, dict):
            raise MutationError(f"Invalid add mutation in {path.relative_to(ROOT)}")
    elif action == "remove":
        validate_selector(selector, path)
        if payload is not None:
            raise MutationError(
                f"Remove json must be null in {path.relative_to(ROOT)}"
            )
    else:
        validate_selector(selector, path)
        if not isinstance(payload, dict) or not payload:
            raise MutationError(
                f"Update json must be a non-empty object in {path.relative_to(ROOT)}"
            )
    return mutation


def selector_candidates(field: str, value: Any) -> list[str]:
    if isinstance(value, (dict, list)):
        candidate = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    elif value is None:
        candidate = "null"
    elif isinstance(value, bool):
        candidate = "true" if value else "false"
    else:
        candidate = str(value)

    candidates = [candidate]
    if field == "name":
        storage_candidate = encode_storage_name(candidate)
        if storage_candidate != candidate:
            candidates.append(storage_candidate)
    return candidates


def matches(row: dict[str, Any], field: str, pattern: re.Pattern[str]) -> bool:
    if field not in row:
        return False
    return any(pattern.search(candidate) is not None for candidate in selector_candidates(field, row[field]))


def apply_mutation(
    rows: list[dict[str, Any]],
    mutation: dict[str, Any],
    path: Path,
) -> list[dict[str, Any]]:
    action, payload = mutation["action"], mutation["json"]
    if action == "add":
        rows.append(dict(payload))
        return rows

    field, pattern = validate_selector(mutation["selector"], path)
    matched = 0
    if action == "remove":
        kept = []
        for row in rows:
            if matches(row, field, pattern):
                matched += 1
            else:
                kept.append(row)
        rows = kept
    else:
        for row in rows:
            if matches(row, field, pattern):
                row.update(payload)
                matched += 1

    if matched == 0:
        raise MutationError(
            f"{path.relative_to(ROOT)} matched zero rows using {field} /{pattern.pattern}/"
        )
    return rows


def write_kernel(
    kernel: str,
    paths: dict[str, Path],
    rows: list[dict[str, Any]],
) -> None:
    normalize_names(kernel, rows)
    ordered_rows = sorted(rows, key=lambda item: item["name"])
    data_dir = paths["data_dir"]
    index_path = paths["index_path"]
    pack_path = paths["pack_path"]
    temporary = data_dir.with_name(data_dir.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=True)

    filenames = []
    for row in ordered_rows:
        filename = f"{encode_storage_name(str(row['name']))}.json"
        filenames.append(filename)
        (temporary / filename).write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if data_dir.exists():
        shutil.rmtree(data_dir)
    temporary.replace(data_dir)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(filenames, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(ordered_rows, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def write_state(registry: dict[str, dict[str, Path]]) -> None:
    kernels: dict[str, dict[str, Any]] = {}
    total_rows = 0
    for kernel, paths in registry.items():
        filenames = load_index(paths["index_path"])
        total_rows += len(filenames)
        kernels[kernel] = {
            "data_dir": relative_path(paths["data_dir"]),
            "index_path": relative_path(paths["index_path"]),
            "pack_path": relative_path(paths["pack_path"]),
            "count": len(filenames),
            "filenames": filenames,
        }

    state = {
        "version": 1,
        "registry_blob_sha": hashlib.sha1(
            f"blob {len(REGISTRY_PATH.read_bytes())}\0".encode("ascii")
            + REGISTRY_PATH.read_bytes()
        ).hexdigest(),
        "total_rows": total_rows,
        "kernels": kernels,
    }
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def mutation_files() -> list[Path]:
    if not MUTATIONS_ROOT.exists():
        return []
    return sorted(
        path
        for path in MUTATIONS_ROOT.glob("*/*.json")
        if path.is_file()
    )


def purge_processed(files: list[Path]) -> None:
    for path in files:
        path.unlink()
    if MUTATIONS_ROOT.exists():
        for child in MUTATIONS_ROOT.iterdir():
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()


def prune_unregistered_kernel_storage(
    registry: dict[str, dict[str, Path]],
) -> None:
    registered = set(registry)

    if KERNELS_ROOT.exists():
        for child in sorted(KERNELS_ROOT.iterdir()):
            if not child.is_dir() or child.name in registered:
                continue
            has_kernel_storage = any(
                (
                    (child / "data").exists(),
                    (child / "index.json").exists(),
                    (child / "pack.json").exists(),
                )
            )
            if not has_kernel_storage:
                continue
            shutil.rmtree(child)
            print(f"Removed storage for unregistered kernel {child.name}.")

    if MUTATIONS_ROOT.exists():
        for child in sorted(MUTATIONS_ROOT.iterdir()):
            if child.is_dir() and child.name not in registered:
                shutil.rmtree(child)
                print(
                    f"Removed pending mutation storage for unregistered kernel {child.name}."
                )


def event_changed_paths() -> set[str]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return set()
    path = Path(event_path)
    if not path.is_file():
        return set()
    try:
        event = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    changed: set[str] = set()
    for commit in event.get("commits", []):
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            values = commit.get(key, [])
            if isinstance(values, list):
                changed.update(value for value in values if isinstance(value, str))
    return changed


def affected_kernels(
    registry: dict[str, dict[str, Path]],
    grouped: dict[str, list[Path]],
) -> tuple[set[str], bool]:
    affected = set(grouped)
    changed = event_changed_paths()
    force_all = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    if "kernel.json" in changed or "scripts/process_mutations.py" in changed:
        force_all = True

    for path in changed:
        match = re.fullmatch(r"kernels/([^/]+)/data/(?:.+\.json|data\.jsonl)", path)
        if match and match.group(1) in registry:
            affected.add(match.group(1))

    for kernel, paths in registry.items():
        if not paths["index_path"].is_file() or not paths["pack_path"].is_file():
            affected.add(kernel)

    if force_all:
        return set(registry), True
    return affected, False


def main() -> int:
    registry = load_registry()
    prune_unregistered_kernel_storage(registry)
    files = mutation_files()
    grouped: dict[str, list[Path]] = {}
    validated: dict[Path, dict[str, Any]] = {}

    for path in files:
        kernel = path.parent.name
        if kernel not in registry:
            raise MutationError(
                f"Unknown kernel folder {path.parent.relative_to(ROOT)}"
            )
        validated[path] = validate_mutation(path)
        grouped.setdefault(kernel, []).append(path)

    affected, force_all = affected_kernels(registry, grouped)

    for kernel, paths in registry.items():
        if kernel not in affected:
            continue

        rows = load_rows(paths["data_dir"])
        for path in sorted(grouped.get(kernel, [])):
            rows = apply_mutation(rows, validated[path], path)

        write_kernel(kernel, paths, rows)
        print(
            f"Indexed and packed {len(rows)} row(s) for {kernel}; "
            f"processed {len(grouped.get(kernel, []))} mutation(s)."
        )

    write_state(registry)
    purge_processed(files)

    if not affected:
        print("No kernel row scans were required; refreshed kernel-state.json only.")
    elif not force_all:
        skipped = len(registry) - len(affected)
        print(f"Reused {skipped} unaffected kernel(s) without scanning row files.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MutationError as exc:
        print(f"Mutation processing failed: {exc}")
        raise SystemExit(1)
