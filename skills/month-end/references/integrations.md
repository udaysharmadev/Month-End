# Project installation and optional lifecycle hooks

The installer changes only the explicitly selected project. It creates a managed
skill copy and a hash receipt, never global settings or credentials.

```bash
python3 scripts/integrations.py install --host codex --project /path/to/project
python3 scripts/integrations.py status --host codex --project /path/to/project
python3 scripts/integrations.py uninstall --host codex --project /path/to/project
```

Use `claude` or `antigravity` for the other supported layouts. Installation is
idempotent. A different or modified copy is preserved, and uninstall refuses to
remove user additions or modified files. Source-tree symlinks and paths escaping
the project are rejected. Global configuration is never touched.

## Optional checkpoint hook

Codex and Claude document a `SessionStart` command hook with
`hookSpecificOutput.additionalContext`. This adapter reads only the explicitly
selected task note after resume/compaction, capped at 2048 bytes; larger notes
are refused whole. It never reads the transcript path or changes a command,
permission, approval or model setting. Checkpoint text is framed as untrusted
task data and must be verified against current files.

```bash
python3 scripts/integrations.py hook-config --host codex \
  --project /path/to/project --checkpoint task-note.md
```

The default prints a configuration for review and activates nothing. With
`--output /path/to/project/new-hooks.json`, it creates a new file and refuses to
overwrite existing settings. Merge the reviewed entry into project
`.codex/hooks.json` for Codex or `.claude/settings.json` for Claude, preserving
other settings. Remove that entry to disable it. In Codex, review and trust the
exact hook through native `/hooks`; this package never bypasses hook trust.
The copied skill must be installed before activating its hook command.

Antigravity uses the portable skill and manual checkpoint template here; this
adapter does not invent an undocumented host lifecycle contract. Hook errors
produce an empty, nonblocking result with diagnostics on stderr.

Primary contracts checked 28 October 2026:
[Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude hooks](https://code.claude.com/docs/en/hooks).
