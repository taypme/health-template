#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
REGISTRY_PATH = ROOT / "kernel.json"


def load_registry() -> dict:
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"kernel.json not found at {REGISTRY_PATH}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid kernel.json: {exc}")


def command_names(rows: list[dict]) -> set[str]:
    names = set()
    for row in rows:
        machine = row.get("machine")
        if isinstance(machine, str):
            names.add(machine)
    return names


def main(argv: list[str]) -> int:
    if not argv:
        print(
            json.dumps(
                {
                    "type": "error",
                    "error": "usage: kernel_command.py <kernel|global-command> [args...]",
                },
                indent=2,
            )
        )
        return 2

    registry = load_registry()
    kernels = {
        row["name"]
        for row in registry.get("kernels", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    global_commands = command_names(registry.get("global_commands", []))
    kernel_commands = registry.get("kernel_commands", {})

    head, rest = argv[0], argv[1:]

    if head == "list":
        result = {
            "type": "global",
            "command": "kernel",
            "arguments": rest,
            "canonical": "kernel" + ((" " + " ".join(rest)) if rest else ""),
        }
    elif head in global_commands:
        result = {
            "type": "global",
            "command": head,
            "arguments": rest,
            "canonical": " ".join(argv),
        }
    elif head in kernels:
        commands = command_names(kernel_commands.get(head, []))
        if rest and rest[0] in commands:
            command = rest[0]
            arguments = rest[1:]
        elif "add" in commands:
            command = "add"
            arguments = rest
        else:
            command = None
            arguments = rest

        result = {
            "type": "kernel",
            "kernel": head,
            "command": command,
            "arguments": arguments,
            "raw_arguments": " ".join(rest),
            "known_kernel_commands": sorted(commands),
            "canonical": " ".join(argv),
        }
        if command is None:
            result["warning"] = f"Kernel {head} has no explicit command and no add command"
    else:
        result = {
            "type": "error",
            "error": f"Unknown kernel or global command: {head}",
            "known_kernels": sorted(kernels),
            "known_global_commands": sorted(global_commands | {"list"}),
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["type"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
