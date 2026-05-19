---
name: codex
description: "Delegate coding to Codex CLI — OpenAI's autonomous coding agent. Codex is the primary coding agent for App1 (18th invariant), with Kiro CLI as fallback."
version: 1.2.0
author: Money Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Codex, OpenAI, Code-Review, Refactoring, Primary]
    related_skills: [kiro-cli, claude-code, hermes-agent]
---

# Codex CLI — App1 Primary Coding Agent (18th Invariant)

> **Codex CLI is the primary coding agent** per the 18th invariant.
> Kiro CLI is the secondary fallback (for when Codex quota is exhausted).
> DeepSeek Flash → only dialog, search, research, ≤50-line one-shot scripts.

Delegate coding tasks to [Codex](https://github.com/openai/codex) via the Hermes terminal. Codex is OpenAI's autonomous coding agent CLI.

## When to Use

- **>50 line / multi-file / architecture-level code** — this is MANDATORY per the 18th invariant
- Feature implementation
- Refactoring
- PR reviews
- Batch issue fixing

## Prerequisites

- Codex installed (v0.130.0 at time of writing)
- OpenAI auth configured via login (see below)
- **Must run inside a git repository** — Codex refuses to run outside one
- Use `pty=true` in terminal calls — Codex is an interactive terminal app

## Auth Setup

### Check Auth Status

```bash
codex login status
# → "Not logged in" or "Logged in as ..."
```

### Method 1: API Key (Fastest, for automation)

```bash
echo "sk-proj-xxxxxxxx" | codex login --with-api-key
# → "Reading API key from stdin..."
# → "Successfully logged in"
```

**Important**: ChatGPT subscription ($20/mo) does NOT include OpenAI API credits.
Codex CLI consumes API credits from [platform.openai.com](https://platform.openai.com/account/billing).
If you get "Quota exceeded. Check your plan and billing details.", you need to
add credits to your OpenAI API account — they are billed separately from ChatGPT.

### Method 2: Device Auth (Browser-based, for interactive use)

```bash
codex login --device-auth
# Output:
#   1. Open this link in your browser: https://auth.openai.com/codex/device
#   2. Enter this one-time code: 2CQ3-TTOKL (expires in 15 minutes)
```

When run in a Hermes background process, the output may be delayed or not appear
due to PTY buffering. If using background mode, use `pty=true` and check `process(action="log")`
after a few seconds to capture the device code.

### Method 3: OAuth (via Hermes)

For Hermes managed auth:
```bash
hermes auth add openai-codex
```
Credentials stored in `~/.hermes/auth.json`.

## CLI Usage

### Non-Interactive Mode (for automation)

```bash
# Via argument
codex exec --sandbox danger-full-access -C /project "Refactor the auth module"

# Via stdin (preferred for long prompts)
echo "Refactor the auth module" | codex exec --sandbox danger-full-access -C /project
```

### Key Flags for `codex exec`

| Flag | Effect |
|------|--------|
| `"prompt"` | Prompt as argument, or pipe via stdin |
| `--sandbox danger-full-access` | Allow file writes (required for most tasks) |
| `--sandbox read-only` | Read-only mode (safe for reviews) |
| `--sandbox workspace-write` | Write only within workspace |
| `--dangerously-bypass-approvals-and-sandbox` | Full bypass (fastest, most dangerous) |
| `-C, --cd <DIR>` | Working directory |
| `--json` | Output events as JSONL (useful for monitoring) |
| `-m, --model <MODEL>` | Model selection (e.g., o3, o4-mini) |
| `--ephemeral` | Don't persist session to disk |
| `-i, --image <FILE>` | Attach image(s) to initial prompt |
| `-o, --output-last-message <FILE>` | Save last response to file |
| `--enable <FEATURE>` | Enable feature flags (repeatable) |

### Interactive Mode

```bash
# Direct prompt
codex "Refactor this file to use async/await"

# Start interactive session
codex
```

## One-Shot Tasks

```bash
terminal(
    command="codex exec --sandbox danger-full-access -C /project 'Add dark mode toggle to settings'",
    workdir="~/project",
    pty=true,
    timeout=300,
)
```

For scratch work (Codex needs a git repo):
```bash
terminal(
    command="cd $(mktemp -d) && git init && codex exec 'Build a snake game in Python'",
    pty=true,
    timeout=120,
)
```

## Background Mode (Long Tasks)

```bash
# Start in background
terminal(
    command="cd /project && codex exec --sandbox danger-full-access -C /project 'Refactor the auth module'",
    background=true,
    pty=true,
    timeout=600,
)
# Returns session_id

# Monitor progress
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")

# Check if files were modified
terminal(command="ls -la --time-style=full /project/lib/module.py")

# Kill if stuck
process(action="kill", session_id="<id>")
```

## Error Handling

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` / `Missing bearer or basic authentication` | Not logged in | Run `codex login --with-api-key` or `--device-auth` |
| `Quota exceeded. Check your plan and billing details.` | OpenAI API credits exhausted | Add credits at platform.openai.com/account/billing |
| `unexpected argument '--trust-all-tools' found` | Wrong flag for exec | Use `--sandbox danger-full-access` instead |
| `error: Input must be provided...` | `--print` needs stdin | Pipe prompt via stdin, don't use in `codex exec` |
| `tcsetattr: Inappropriate ioctl for device` | PTY device issue | Use `pty=true` in terminal calls; background processes may have issues |

### Fallback Chain (when Codex is unavailable)

1. **Kiro CLI** — `HOME=/home/zhangwei_pmf kiro-cli chat --no-interactive -a "task"`
2. **Claude Code CLI** — `echo "task" | claude -p --permission-mode bypassPermissions`
3. **Manual refactoring** — via Hermes write_file/patch tools

## Known Models

Codex CLI uses OpenAI models. Check available models:
```bash
codex --list-models  # Not directly supported; uses OpenAI defaults
```

The API key determines which models are accessible. Pro/Enterprise API users get more.

## Auth Persistence

- API key login persists until you `codex logout`
- Device auth persists via refresh tokens (may expire)
- Login status: `codex login status`
- Config: `~/.codex/config.toml`
- Auth: stored in credential chain (varies by platform)

## Pitfalls & Gotchas

1. **ChatGPT sub ≠ API credits** — If "Quota exceeded," the $20 ChatGPT sub doesn't cover API usage. Get API credits separately at platform.openai.com.
2. **`--sandbox danger-full-access` is required** for most refactoring tasks that need file writes. Without it, Codex may silently fail.
3. **Git repo required** — Codex refuses to run outside a git directory. Use `mktemp -d && git init` for scratch work.
4. **PTY essential** — Always use `pty=true`. Without it, Codex hangs or produces no output.
5. **Background output buffering** — Codex running in background may show empty `process(action="log")` while still running. Check exit code and file modification times instead.
6. **Don't retry 401s or quota errors** — They won't resolve without action. Switch to fallback immediately.
7. **Long tasks need patience** — Complex refactoring can take 120-600s. Set generous timeouts.
8. **`--json` for monitoring** — Using `--json` gives real-time JSONL events you can parse.
