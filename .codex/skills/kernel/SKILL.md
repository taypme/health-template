---
name: kernel
description: Dispatch Health Kernel commands in a confirmed Health Kernel repository using `$kernel <kernel> <command-or-args...>` or `$kernel <global-command>`, including kernel row reads, names/data/view commands, and mutation-oriented add/update/delete workflows.
---

# Kernel

Use this skill in a confirmed Health Kernel checkout.

## Command Shape

`$kernel` is a dispatcher. Parse the user text after `$kernel` as:

```text
$kernel <kernel> <command-or-args...>
$kernel <global-command> <args...>
```

The first token controls routing:

- If it is a registered kernel name from `kernel.json`, treat the remaining text as that kernel's command or add arguments.
- If it is a global command from `kernel.json.global_commands`, run that global command.
- Otherwise report an unknown kernel or command.

Examples:

```text
$kernel rx data
$kernel rx names
$kernel rx view example_rx_row
$kernel emotion sad 7, happy 9
$kernel context add doc "interpret doc rows as external document pointers"
$kernel mutations
```

`$kernel emotion sad 7, happy 9` means the same Health Kernel operation as `emotion sad 7, happy 9` in a hydrated Health Kernel conversation: route to the `emotion` kernel and use that kernel's add behavior from `kernel.json`.

## Required Reads

Before changing repository state, read:

- `README.md` for the current Health Kernel contract.
- `kernel.json` for registered kernels and command semantics.
- `kernel-state.json` for committed row counts and filename arrays.

For read-only commands, read the smallest sufficient set: usually `kernel.json` and `kernel-state.json`, plus a row file or `pack.json` only when the command needs row contents.

## Dispatcher Helper

Use `scripts/kernel_command.py` when useful to validate routing:

```bash
python3 .codex/skills/kernel/scripts/kernel_command.py rx data
python3 .codex/skills/kernel/scripts/kernel_command.py emotion sad 7, happy 9
```

The helper only parses and classifies the command. It does not edit files.

## Command Rules

Use command definitions from `kernel.json`; do not hardcode kernel behavior unless `kernel.json` delegates that behavior to normal repository conventions.

Default kernel command:

- If `<command-or-args...>` starts with a command listed for that kernel, use that command.
- If it does not start with a listed command, treat the remaining text as an `add` request for that kernel when an `add` command exists.
- If no suitable command exists, report the missing command.

Global commands:

- `kernel`, `pull`, `behavior`, `push`, and `mutations` are global.
- For `$kernel list`, use the global `kernel` command behavior.

Read commands:

- `<kernel> names`: use the cached filename array in `kernel-state.json`; strip `.json`; do not fetch row files.
- `<kernel> view <name>`: confirm `<name>.json` exists in `kernel-state.json`, then read `kernels/<kernel>/data/<name>.json`; render fields as Markdown, not raw JSON.
- `<kernel> data`: read `kernels/<kernel>/pack.json` once and render according to the kernel's command semantics.

Mutation commands:

- Prefer queued mutation files under `mutations/<kernel>/<uuid>.json` unless the user explicitly asks for direct local maintenance edits.
- Mutation files contain exactly `action`, `selector`, and `json`.
- For `add`, `selector` is `null` and `json` is the complete row.
- For `update` and `remove`, escape user text in regex selectors and anchor exact-name matches when matching a row by name.
- After creating mutation files locally, run `python3 scripts/process_mutations.py` when validation/regeneration is appropriate for the task.

## Safety

- Do not silently reorder the command grammar. `$kernel rx data` is correct; `$kernel data rx` is not the kernel-command shape.
- Do not rewrite unrelated rows or generated artifacts by hand.
- Treat `index.json`, `pack.json`, and `kernel-state.json` as generated artifacts.
- Preserve the atomic mutation-batch behavior described in `kernel.json` for GitHub pushes.
