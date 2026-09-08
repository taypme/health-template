# Health Kernel Template

Health Kernel is a GitHub-backed personal data kernel for ChatGPT conversations. It stores structured health-related rows as JSON files in a private GitHub repository, then uses `INSTRUCTIONS.md`, `kernel.json`, and `kernel-state.json` as the operating contract for reading, adding, updating, deleting, moving, and pushing kernel data.

This repository is the vanilla template. It contains the kernel system, commands, mutation processor, and GitHub Actions workflow, but no personal health data.

## Important distinction

`README.md` is onboarding for people. [`INSTRUCTIONS.md`](./INSTRUCTIONS.md)
is the authoritative operating contract for an AI client. If this README and
the contract ever differ, follow the contract and inspect the current
`kernel.json`.

## How It Works

- `INSTRUCTIONS.md` is the complete machine-readable operating contract for ChatGPT.
- `kernel.json` defines registered kernels, policies, and command semantics.
- `kernel-state.json` is the generated manifest of committed row counts and filenames.
- `kernels/<kernel>/data/` stores canonical per-row JSON files after data is added.
- `kernels/<kernel>/index.json` and `kernels/<kernel>/pack.json` are generated read artifacts.
- `mutations/` stores queued repository mutation files before the processor converts them into committed rows.
- `.github/workflows/process-mutations.yml` processes committed mutation files on GitHub-hosted runners.

## Create Your Data Repository

1. Create a new GitHub repository from this template.
2. Make the new repository private if it will store health or other sensitive data.
3. Keep the default branch as `main`.
4. Confirm GitHub Actions are enabled for the repository.
5. Use the new repository name in the ChatGPT hydration prompt below.

Do not put real data in this template repository. Create a separate private repository for your own records.

## Start A ChatGPT Conversation

Open a new ChatGPT conversation with GitHub access available, then send:

```text
Hydrate Health Kernel from "owner/repo_name_here" on "main". Read and follow "INSTRUCTIONS.md" completely.
```

Replace `owner/repo_name_here` with your repository, for example `octocat/my-health-kernel`.

After hydration, ChatGPT should report the latest commit SHA, instruction and registry blob SHAs, registered kernels, row counts, pending repository mutations, pending conversation-local mutations, stale indexes, hydration errors, and available capabilities. The report should end with:

```text
Health Kernel hydrated.
```

## Command Shape

Use `$kernel` followed by a global command or a kernel name:

```text
$kernel <global-command> <args...>
$kernel <kernel> <command-or-args...>
```

Examples:

```text
$kernel kernel
$kernel rx data
$kernel rx add sertraline 50mg daily
$kernel emotion anxious 6, hopeful 4
$kernel context add rx "medication rows should include dose and frequency"
$kernel queue move "^follow_up_.*$" experience
$kernel experience strip archived_
$kernel push
```

## Global Commands

- `$kernel kernel`: list every registered kernel and committed row count.
- `$kernel kernel create <name>`: add a new empty kernel to the repository configuration.
- `$kernel kernel delete <name>`: remove a registered kernel, its data, generated artifacts, commands, mutations, and context row.
- `$kernel pull`: refresh the conversation cache from the latest `main` commit.
- `$kernel behavior`: report active conversation state that would not survive a fresh hydration.
- `$kernel mutations`: report queued conversation-local mutation counts without invoking GitHub.
- `$kernel push`: atomically commit all queued conversation-local mutations to GitHub and let the workflow process them.

These generic commands are available for kernels that support the operation:

- `$kernel <kernel> add ...`: queue a row add mutation.
- `$kernel <kernel> update ...`: queue a row update mutation.
- `$kernel <kernel> delete ...`: queue a row remove mutation.
- `$kernel <kernel> move <selector-regex> <destination-kernel>`: queue one native move mutation selecting source rows by `name` regex and moving all matches to another registered kernel.
- `$kernel <kernel> strip <prefix>`: queue exact-name update mutations that remove a literal prefix from every matching committed row name.
- `$kernel <kernel> data`: read committed rows from the generated pack.
- `$kernel <kernel> names`: list committed row names from the cached manifest.
- `$kernel <kernel> view <name>`: render one committed row as Markdown.

## Native Mutation Schema

Mutation files contain exactly `action`, `selector`, and `json`.

`add`, `remove`, and `update` retain their existing behavior. Native `move` uses the same regex selector contract as `remove` and `update`:

```json
{
  "action": "move",
  "selector": {
    "field": "name",
    "regex": "^follow_up_.*$"
  },
  "json": {
    "kernel": "experience"
  }
}
```

A move is processed as one mutation: every matching source row is removed from the source kernel and appended unchanged to the destination kernel. The processor rejects an unregistered destination, moving to the same kernel, zero matches, and destination name collisions. Source and destination indexes, packs, row files, and `kernel-state.json` are regenerated in the same processor run.

`strip` is implemented as deterministic update mutations rather than direct row rewrites. This keeps prefix renaming inside the same mutation pipeline and preserves atomic push behavior.

## Registered Kernels

The template starts with these empty kernels:

```text
opinion
context
fact
diagnosis
element
experience
queue
si
doc
emotion
rx
regret
like
am
think
board
card
```

You can keep these, delete the ones you do not want, or create new kernels with `$kernel kernel create <name>`.

## Kernel-Specific Commands

- `$kernel context add <kernel> <context>`: add interpretive context for another registered kernel.
- `$kernel context delete <kernel>`: delete the context row for a registered kernel.
- `$kernel context data`: show committed context rows.
- `$kernel doc add <file>`: add a document pointer row.
- `$kernel emotion <name> <number>, ...`: add one or more emotion rows with numeric values and timestamps.
- `$kernel si add <color> <number>`: add an SI row; the processor can assign a deterministic name when needed.
- `$kernel rx add <medication details>`: add a medication row with brand/generic, dosage, frequency, and PRN handling.
- `$kernel rx data`: render medication rows as Brand, Generic, Dosage, Frequency, and PRN.
- `$kernel rx delete <brand-or-generic>`: remove medication rows by exact brand or generic match.
- `$kernel like add <name> <intensity>`: add a like row.
- `$kernel am add <name> <intensity>`: add an AM row.
- `$kernel think <text>`: add the provided text as a timestamped thought row.

## Trello Board And Card Integration

The template ships with empty `board` and `card` kernels. They are implemented through `kernel.json` and the normal kernel mutation system; they are not special-cased in `INSTRUCTIONS.md`.

These kernels can mirror and create Trello content when ChatGPT has access to the **Trello connector**. The connector is optional for the rest of Health Kernel, but it is required for commands that need to read from or write to Trello. Without a Trello connector, the board/card schemas still exist, but external board operations cannot be completed.

### Board schema

- `name`: kernel name for the board.
- `board_id`: stable Trello board identifier when available.

### Card schema

- `board`: board kernel row name.
- `board_id`: stable external board identifier.
- `list`: Trello list name.
- `list_id`: stable external list identifier.
- `name`: random UUID used as the kernel row name.
- `card`: card title.
- `card_id`: stable external card identifier and primary synchronization/deduplication key.
- `description`: card description.

### Commands

- `$kernel board <name>`: uses normal kernel add fallback semantics to queue a board row. When using Trello, resolve and store the stable Trello board ID.
- `$kernel board names`: show each committed board and its external lists in a compact `board` / `list` table.
- `$kernel board pull [board]`: fully synchronize the kernel-side card rows with the selected Trello board or boards. Current non-archived Trello cards are authoritative: missing active cards are added, matching cards are updated when metadata changes, and kernel card rows whose `card_id` is no longer present are removed. Archived Trello cards count as absent and are removed from the kernel. With no argument, synchronize every committed board row; when `board` is supplied, synchronize only that exact committed board. The command never creates, archives, unarchives, or deletes Trello cards.
- `$kernel card add <board> <list> <card> <description>`: create one Trello card exactly once, creating the list first only when needed, capture the returned board/list/card IDs, generate a random UUID for the kernel row name, then queue the complete card row. Stable IDs are checked before creation to prevent duplicates.
- `$kernel card data`: show committed cards in a compact table with `list`, `card`, and `description` columns.

The external IDs are important. `card_id` is the primary synchronization and deduplication key. During `board pull`, current non-archived Trello cards define the authoritative card set for the selected board, while the kernel must never invent Trello IDs or recreate a card merely because kernel persistence failed after Trello creation succeeded.

## Local Maintenance

The mutation processor can be run locally when validating template changes:

```bash
GITHUB_EVENT_NAME=workflow_dispatch python3 scripts/process_mutations.py
```

All committed kernel data should be regenerated through the processor or through the documented kernel commands. Treat `index.json`, `pack.json`, and `kernel-state.json` as generated artifacts.

## Before publishing a derived repository

Confirm that the new repository is private, contains no personal data in the
template, has Actions enabled, and uses `main`. Replace the placeholder owner
and repository in the hydration prompt before sharing it with ChatGPT.
