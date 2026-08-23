# Hermes Agent - Development Guide

Instructions for AI coding assistants and developers working on the hermes-agent codebase.

**Never give up on the right solution.**

## What Hermes Is

Hermes is a personal AI agent that runs the same agent core across a CLI, a
messaging gateway (Telegram, Discord, Slack, and ~20 other platforms), a TUI,
and an Electron desktop app. It learns across sessions (memory + skills),
delegates to subagents, runs scheduled jobs, and drives a real terminal and
browser. It is extended primarily through **plugins and skills**, not by
growing the core.

Two properties shape almost every design decision and are the lens for
reviewing any change:

- **Per-conversation prompt caching is sacred.** A long-lived conversation
  reuses a cached prefix every turn. Anything that mutates past context,
  swaps toolsets, or rebuilds the system prompt mid-conversation invalidates
  that cache and multiplies the user's cost. We do not do it (the one
  exception is context compression).
- **The core is a narrow waist; capability lives at the edges.** Every model
  tool we add is sent on every API call, so the bar for a new *core* tool is
  high. Most new capability should arrive as a CLI command + skill, a
  service-gated tool, or a plugin — not as core surface.

## Contribution Rubric — What We Want / What We Don't

This is the project's intent layer. Use it two ways:

1. **For humans and for your own work** — what gets merged and what gets
   rejected, so a contribution aims at the target.
2. **For automated review (the triage sweeper)** — guidance on when a PR is
   safe to close on the three allowed reasons (`implemented_on_main`,
   `cannot_reproduce`, `incoherent`) and, just as important, **when NOT to
   close** one. Taste-based "we don't want this / out of scope" closes are NOT
   an automated decision — those stay with a human maintainer. The sweeper's
   job here is to recognize design intent and *avoid wrongly closing a
   legitimate contribution*, not to make the won't-implement call itself.

Read the balance right: Hermes ships a **lot** — most merges are bug fixes to
real reported behavior, and the product surface (platforms, channels,
providers, models, desktop/TUI features) expands aggressively and on purpose.
The restraint below is aimed squarely at the **core agent + the model tool
schema**, the one place where every addition is paid for on every API call.
"Smallest footprint" governs *how a capability is wired into the core*, NOT
whether the product is allowed to grow. We are expansive at the edges and
conservative at the waist.

### What we want

- **Fix real bugs, well.** The bulk of what lands is `fix(...)` against an
  actual reported symptom. A good fix reproduces the symptom on current
  `main`, points to the exact line where it manifests, and fixes the whole bug
  class — sibling call paths included — not just the one site the reporter hit.
- **Expand reach at the edges.** New platform adapters, channels, providers,
  models, and desktop/TUI/dashboard features are welcome and land routinely,
  including large ones (a new messaging channel, a session-cap feature, a
  Windows PTY bridge). Breadth in the product is a goal, not a footprint
  concern — as long as it integrates with the existing setup/config UX
  (`hermes tools`, `hermes setup`, auto-install) rather than bolting on a raw
  env var.
- **Refactor god-files into clean modules.** Extracting a multi-thousand-line
  cluster out of `cli.py` / `run_agent.py` / `gateway/run.py` into a focused
  mixin or module is wanted work, even when the diff is huge and mechanical
  (large `+N/-N` refactors merge regularly). The "every line traces to the
  request" test applies to *feature* PRs; a declared refactor's request IS the
  extraction.
- **Keep the core narrow.** New *model tools* are the expensive exception —
  every tool ships on every API call. Prefer, in order: extend existing code →
  CLI command + skill → service-gated tool (`check_fn`) → plugin → MCP server
  in the catalog → new core tool (last resort). See "The Footprint Ladder."
- **Extend, don't duplicate.** Before adding a module/manager/hook, check
  whether existing infrastructure already covers the use case. When several PRs
  integrate the same *category*, design one shared interface instead of merging
  them one at a time (see the ABC + orchestrator note under the Footprint
  Ladder).
- **Behavior contracts over snapshots.** Tests should assert how two pieces of
  data must relate (invariants), not freeze a current value (model lists,
  config version literals, enumeration counts). See "Don't write
  change-detector tests."
- **E2E validation, not just green unit mocks.** For anything touching
  resolution chains, config propagation, security boundaries, remote
  backends, or file/network I/O, exercise the real path with real imports
  against a temp `HERMES_HOME`. Mocks hide integration bugs.
- **Cache-, alternation-, and invariant-safe.** Preserve prompt caching, strict
  message role alternation (never two same-role messages in a row; never a
  synthetic user message injected mid-loop), and a system prompt that is
  byte-stable for the life of a conversation.
- **Contributor credit preserved.** Salvage external work by cherry-picking
  (rebase-merge) so authorship survives in git history; don't reimplement from
  scratch when you can build on top.

### What we don't want (rejected even when well-built)

- **Speculative infrastructure.** Hooks, callbacks, or extension points with no
  concrete consumer. Adding a hook is easy; removing one after plugins depend
  on it is hard. A hook is NOT speculative if a contributor has a real, stated
  use case — even if the consumer ships separately.
- **New `HERMES_*` env vars for non-secret config.** `.env` is for secrets
  only (API keys, tokens, passwords). All behavioral settings — timeouts,
  thresholds, feature flags, display prefs — go in `config.yaml`. Bridge to an
  internal env var if the mechanism needs one, but user-facing docs point to
  `config.yaml`. Reject PRs that tell users to "set X in your .env" unless X
  is a credential.
- **A new core tool when terminal + file already do the job, or when a skill
  would.** If the only barrier is file visibility on a remote backend, fix the
  mount, not the toolset.
- **Lazy-reading escape hatches on instructional tools.** No `offset`/`limit`
  pagination on tools that load content the agent must read fully (skills,
  prompts, playbooks). Models will read page 1 and skip the rest.
- **"Fixes" that destroy the feature they secure.** A mitigation that kills the
  feature's purpose is the wrong mitigation. Read the original commit's intent
  (`git log -p -S`) before restricting behavior; find a fix that preserves the
  feature.
- **Outbound telemetry / usage attribution without opt-in gating.** No new
  analytics, third-party identifier tagging, or attribution tags until a
  generic user-facing opt-in (config gate + setup prompt + `hermes tools`
  toggle) exists. Park behind a label, do not merge.
- **Change-detector tests, cache-breaking mid-conversation, dead code wired in
  without E2E proof, and plugins that touch core files.** Plugins live in their
  own directory and work within the ABCs/hooks we provide; if a plugin needs
  more, widen the generic plugin surface, don't special-case it in core.
- **Third-party products / other people's projects integrated into the core
  tree.** Observability backends, vendor SaaS integrations, analytics dashboards,
  and similar "someone else's product" plugins do NOT land under `plugins/` in
  this repo. They place an ongoing maintenance burden on us to keep them working
  against a fast-moving core, for a backend we don't own. Ship them as a
  **standalone plugin repo** users install into `~/.hermes/plugins/` (or via a
  pip entry point), and promote them in the Nous Research Discord
  (`#plugins-skills-and-skins`). This is a coupling-and-maintenance decision, not
  a quality bar — the plugin can be excellent and still be a close. PRs that add
  such a directory to the tree are closed with a pointer to publish it as its own
  repo.

### Before you call it a bug — verify the premise (and when NOT to close)

The most common reason a well-written PR gets closed is not code quality — it
is that the change is built on a **wrong premise**, or it treats an
**intentional design as a gap**. These patterns cut both ways: they tell a
human reviewer what to scrutinize, and they tell the automated sweeper when a
PR is NOT safe to close as `implemented_on_main` / `cannot_reproduce` (when in
doubt, leave it open for a human). They are distilled from real closes.

- **"Intentional design, not a gap."** A limitation that looks like an
  oversight is often deliberate. Before "fixing" a missing link or a
  restriction, ask whether the isolation IS the design. Example: profiles are
  independent islands on purpose — a PR adding live config inheritance from the
  default profile was closed because coupling profiles together is exactly what
  the design prevents (the copy-at-creation `--clone` path already covers the
  legitimate "start from my default" case). Read the original commit's intent
  (`git log -p -S "<symbol>"`) before assuming something is unfinished.
- **"The premise doesn't hold against how X actually works."** A PR's
  justification frequently rests on a wrong mental model of an existing
  mechanism. Trace the real code/runtime before accepting the rationale. Two
  real closes: a rate-limit "re-probe during cooldown" PR (the breaker only
  trips on a *confirmed-empty* account bucket, so re-probing just hammers a
  bucket we've already proven empty); a usage-accumulation fix whose new branch
  **never executes at runtime** because an earlier guard already popped the
  state it depended on. If you can't point to the exact line where the bug
  manifests AND show the fix changes that line's behavior, you haven't verified
  the premise.
- **"This fix was wrong — the absence/omission was deliberate."** Adding the
  obvious-looking missing piece can break things the omission was protecting.
  Example: restoring "missing" `__init__.py` files made a test tree importable
  as a dotted package that shadowed the real plugin, deleting its `register()`
  at import time. The absence was load-bearing.
- **"Overreached / resurrected an approach we'd moved past."** Scope creep that
  supersedes an agreed-on base, or revives a direction the maintainers
  deliberately closed, gets rejected even when the code works. Keep the change
  to the narrow piece that was actually agreed; offer the rest as a focused
  follow-up.

The throughline: **verify the claim AND the intent against the codebase before
writing or merging a fix.** A confirmed reproduction on current `main` plus a
line-level account of where the fix acts beats a plausible-sounding rationale
every time. When in doubt about intent, it is cheaper to ask than to ship a
fix that fights the design.

### The Footprint Ladder (new capability decision)

Each rung adds more permanent surface than the one above. Choose the highest
(least-footprint) rung that correctly solves the problem:

1. **Extend existing code** — the capability is a variation of something that
   already exists. Zero new surface.
2. **CLI command + skill** — manages config/state/infra expressible as shell
   commands. The agent runs `hermes <subcommand>` guided by a skill. Zero
   model-tool footprint. Default choice for subscriptions, scheduled tasks,
   service setup. Examples: `hermes webhook`, `hermes cron`, `hermes tools`.
3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND
   only appears when a prerequisite is configured. Zero footprint otherwise.
   Examples: Home Assistant tools (gated on token), memory-provider tools.
4. **Plugin** — third-party/niche/user-specific capability that doesn't ship in
   core. Lives in `~/.hermes/plugins/` or a pip package, discovered at runtime.
5. **MCP server (in the catalog)** — if the capability genuinely needs to be a
   tool (structured I/O the agent invokes) but isn't core-fundamental, prefer
   building it as an MCP server and adding it to the MCP catalog over growing
   the core toolset. The agent connects to it through the built-in MCP client;
   zero permanent core-schema footprint, and it's reusable by any MCP host.
6. **New core tool** — only when the capability is fundamental, broadly useful
   to nearly every user, and unreachable via terminal + file (or an MCP server).
   Examples of correct core tools: terminal, read_file, web_search,
   browser_navigate.

When 3+ open PRs try to integrate the same *category* of thing (memory
backends, providers, notifiers), don't merge them one at a time — design an
ABC + orchestrator, wrap the existing built-in as the first provider, and turn
the competing PRs into plugins against that interface.

## Dependency Pinning Policy

All dependencies must have upper bounds to limit supply-chain attack surface.
This policy was established after the litellm compromise (PR #2796, #2810) and
reinforced after the Mini Shai-Hulud worm campaign (May 2026).

| Source type | Treatment | Example |
|---|---|---|
| PyPI package | `>=floor,<next_major` | `"httpx>=0.28.1,<1"` |
| Git URL | Commit SHA | `git+https://...@<40-char-sha>` |
| GitHub Actions | Commit SHA + comment | `uses: actions/checkout@<sha>  # v4` |
| CI-only pip | `==exact` | `pyyaml==6.0.2` |

**When adding a new dependency to `pyproject.toml`:**
1. Pin to `>=current_version,<next_major` for post-1.0 (e.g. `>=1.5.0,<2`).
2. For pre-1.0 packages, use `<0.(current_minor + 2)` (e.g. `>=0.29,<0.32`).
3. Never commit a bare `>=X.Y.Z` without a ceiling — CI and reviewers will reject it.
4. Run `uv lock` to regenerate `uv.lock` with hashes.

Reference: #2810 (bounds pass), #9801 (SHA pinning + audit CI).

---

## Adding Configuration

### config.yaml options:
1. Add to `DEFAULT_CONFIG` in `hermes_cli/config.py`
2. Bump `_config_version` (check the current value at the top of `DEFAULT_CONFIG`)
   ONLY if you need to actively migrate/transform existing user config
   (renaming keys, changing structure). Adding a new key to an existing
   section is handled automatically by the deep-merge and does NOT require
   a version bump.

### Top-level `config.yaml` sections (non-exhaustive):

`model`, `agent`, `terminal`, `compression`, `display`, `stt`, `tts`,
`memory`, `security`, `delegation`, `smart_model_routing`, `checkpoints`,
`auxiliary`, `curator`, `skills`, `gateway`, `logging`, `cron`, `profiles`,
`plugins`, `honcho`.

`auxiliary` holds per-task overrides for side-LLM work (curator, vision,
embedding, title generation, session_search, etc.) — each task can pin
its own provider/model/base_url/max_tokens/reasoning_effort. See
`agent/auxiliary_client.py::_resolve_auto` for resolution order.

`curator` holds the background skill-maintenance config —
`enabled`, `interval_hours`, `min_idle_hours`, `stale_after_days`,
`archive_after_days`, `backup` (nested).

### .env variables (SECRETS ONLY — API keys, tokens, passwords):
1. Add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` with metadata:
```python
"NEW_API_KEY": {
    "description": "What it's for",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
},
```

Non-secret settings (timeouts, thresholds, feature flags, paths, display
preferences) belong in `config.yaml`, not `.env`. If internal code needs an
env var mirror for backward compatibility, bridge it from `config.yaml` to
the env var in code (see `gateway_timeout`, `terminal.cwd` → `TERMINAL_CWD`).

### Config loaders (three paths — know which one you're in):

| Loader | Used by | Location |
|--------|---------|----------|
| `load_cli_config()` | CLI mode | `cli.py` — merges CLI-specific defaults + user YAML |
| `load_config()` | `hermes tools`, `hermes setup`, most CLI subcommands | `hermes_cli/config.py` — merges `DEFAULT_CONFIG` + user YAML |
| Direct YAML load | Gateway runtime | `gateway/run.py` + `gateway/config.py` — reads user YAML raw |

If you add a new key and the CLI sees it but the gateway doesn't (or vice
versa), you're on the wrong loader. Check `DEFAULT_CONFIG` coverage.

### Working directory:
- **CLI** — uses the process's current directory (`os.getcwd()`).
- **Messaging** — uses `terminal.cwd` from `config.yaml`. The gateway bridges this
  to the `TERMINAL_CWD` env var for child tools. **`MESSAGING_CWD` has been
  removed** — the config loader prints a deprecation warning if it's set in
  `.env`. Same for `TERMINAL_CWD` in `.env`; the canonical setting is
  `terminal.cwd` in `config.yaml`.

---

## Skin/Theme System

The skin engine (`hermes_cli/skin_engine.py`) provides data-driven CLI visual customization. Skins are **pure data** — no code changes needed to add a new skin.

## Skills

Two parallel surfaces:

- **`skills/`** — built-in skills shipped and loadable by default.
  Organized by category directories (e.g. `skills/github/`, `skills/mlops/`).
- **`optional-skills/`** — heavier or niche skills shipped with the repo but
  NOT active by default. Installed explicitly via
  `hermes skills install official/<category>/<skill>`. Adapter lives in
  `tools/skills_hub.py` (`OptionalSkillSource`). Categories include
  `autonomous-ai-agents`, `blockchain`, `communication`, `creative`,
  `devops`, `email`, `health`, `mcp`, `migration`, `mlops`, `productivity`,
  `research`, `security`, `web-development`.

When reviewing skill PRs, check which directory they target — heavy-dep or
niche skills belong in `optional-skills/`.

### SKILL.md frontmatter

Standard fields: `name`, `description`, `version`, `author`, `license`,
`platforms` (OS-gating list: `[macos]`, `[linux, macos]`, ...),
`metadata.hermes.tags`, `metadata.hermes.category`,
`metadata.hermes.related_skills`, `metadata.hermes.config` (config.yaml
settings the skill needs — stored under `skills.config.<key>`, prompted
during setup, injected at load time).

Top-level `tags:` and `category:` are also accepted and mirrored from
`metadata.hermes.*` by the loader.

### Skill authoring standards (HARDLINE)

Every new or modernized skill — bundled, optional, or contributed —
must meet these standards before merge. Reviewers reject PRs that
violate them.

1. **`description` ≤ 60 characters, one sentence, ends with a period.**
   Long descriptions bloat skill listings and dilute the model's
   attention when many skills are loaded. State the capability, not
   the implementation. No marketing words ("powerful",
   "comprehensive", "seamless", "advanced"). Don't repeat the skill
   name. Verify with:
   ```python
   import re, pathlib
   m = re.search(r'^description: (.*)$',
                 pathlib.Path('skills/<cat>/<name>/SKILL.md').read_text(),
                 re.MULTILINE)
   assert len(m.group(1)) <= 60, len(m.group(1))
   ```

2. **Tools referenced in SKILL.md prose must be native Hermes tools or
   MCP servers the skill explicitly expects.** When the skill needs a
   capability, point at the proper tool by name in backticks
   (`` `terminal` ``, `` `web_extract` ``, `` `read_file` ``,
   `` `patch` ``, `` `search_files` ``, `` `vision_analyze` ``,
   `` `browser_navigate` ``, `` `delegate_task` ``, etc.). Do NOT
   name shell utilities the agent already has wrapped — `grep` →
   `search_files`, `cat`/`head`/`tail` → `read_file`, `sed`/`awk` →
   `patch`, `find`/`ls` → `search_files target='files'`. If the skill
   depends on an MCP server, name the MCP server and document the
   expected setup in `## Prerequisites`. Anything else (third-party
   CLIs, shell pipelines, etc.) is fair game inside script files but
   should not be the headline interaction surface in the prose.

3. **`platforms:` gating audited against actual script imports.**
   Skills that use POSIX-only primitives (`fcntl`, `termios`,
   `os.setsid`, `os.kill(pid, 0)` for liveness, `/proc`, `/tmp`
   hardcoded, `signal.SIGKILL`, bash heredocs, `osascript`, `apt`,
   `systemctl`) must declare their supported platforms. Default
   posture: try to fix it cross-platform first — `tempfile.gettempdir`,
   `pathlib.Path`, `psutil.pid_exists`, Python-level filtering instead
   of `grep`. Gate to a narrower set only when the dependency is
   genuinely platform-bound.

4. **`author` credits the human contributor first.** For external
   contributions, the contributor's real name + GitHub handle goes
   first; "Hermes Agent" is the secondary collaborator. If the
   contributor's commit shows "Hermes Agent" as author (because they
   used Hermes to draft the skill), replace it with their actual name
   — credit the human, not the tool.

5. **SKILL.md body uses the modern section order.** `# <Skill> Skill`
   title, 2-3 sentence intro stating what it does and doesn't do,
   `## When to Use`, `## Prerequisites`, `## How to Run`,
   `## Quick Reference`, `## Procedure`, `## Pitfalls`,
   `## Verification`. Target ~200 lines for a complex skill,
   ~100 lines for a simple one. Cut redundant intro fluff, marketing
   prose, and re-explanations of env vars already in
   `## Prerequisites`.

6. **Scripts go in `scripts/`, references in `references/`,
   templates in `templates/`.** Don't expect the model to inline-write
   parsers, XML walkers, or non-trivial logic every call — ship a
   helper script. Reference it from SKILL.md by path relative to the
   skill directory.

7. **Tests live at `tests/skills/test_<skill>_skill.py`** and use only
   stdlib + pytest + `unittest.mock`. No live network calls. Run via
   `scripts/run_tests.sh tests/skills/test_<skill>_skill.py -q`.

8. **`.env.example` additions are isolated to a clearly delimited
   block.** Don't touch the surrounding file — contributor-supplied
   `.env.example` versions are usually stale and edits outside the
   skill's own block must be dropped during salvage.

The full salvage / modernization checklist for external skill PRs
lives in the `hermes-agent-dev` skill at
`references/new-skill-pr-salvage.md` — load it before polishing
contributor skill PRs.

---

## Important Policies

### Prompt Caching Must Not Break

Hermes-Agent ensures caching remains valid throughout a conversation. **Do NOT implement changes that would:**
- Alter past context mid-conversation
- Change toolsets mid-conversation
- Reload memories or rebuild system prompts mid-conversation

Cache-breaking forces dramatically higher costs. The ONLY time we alter context is during context compression.

Slash commands that mutate system-prompt state (skills, tools, memory, etc.)
must be **cache-aware**: default to deferred invalidation (change takes
effect next session), with an opt-in `--now` flag for immediate
invalidation. See `/skills install --now` for the canonical pattern.

### Background Process Notifications (Gateway)

When `terminal(background=true, notify_on_complete=true)` is used, the gateway runs a watcher that
detects process completion and triggers a new agent turn. Control verbosity of background process
messages with `display.background_process_notifications`
in config.yaml (or `HERMES_BACKGROUND_NOTIFICATIONS` env var):

- `all` — running-output updates + final message (default)
- `result` — only the final completion message
- `error` — only the final message when exit code != 0
- `off` — no watcher messages at all

---

## Profiles: Multi-Instance Support

Hermes supports **profiles** — multiple fully isolated instances, each with its own
`HERMES_HOME` directory (config, API keys, memory, sessions, skills, gateway, etc.).

The core mechanism: `_apply_profile_override()` in `hermes_cli/main.py` sets
`HERMES_HOME` before any module imports. All `get_hermes_home()` references
automatically scope to the active profile.

### Rules for profile-safe code

1. **Use `get_hermes_home()` for all HERMES_HOME paths.** Import from `hermes_constants`.
   NEVER hardcode `~/.hermes` or `Path.home() / ".hermes"` in code that reads/writes state.
   ```python
   # GOOD
   from hermes_constants import get_hermes_home
   config_path = get_hermes_home() / "config.yaml"

   # BAD — breaks profiles
   config_path = Path.home() / ".hermes" / "config.yaml"
   ```

2. **Use `display_hermes_home()` for user-facing messages.** Import from `hermes_constants`.
   This returns `~/.hermes` for default or `~/.hermes/profiles/<name>` for profiles.
   ```python
   # GOOD
   from hermes_constants import display_hermes_home
   print(f"Config saved to {display_hermes_home()}/config.yaml")

   # BAD — shows wrong path for profiles
   print("Config saved to ~/.hermes/config.yaml")
   ```

3. **Module-level constants are fine** — they cache `get_hermes_home()` at import time,
   which is AFTER `_apply_profile_override()` sets the env var. Just use `get_hermes_home()`,
   not `Path.home() / ".hermes"`.

4. **Tests that mock `Path.home()` must also set `HERMES_HOME`** — since code now uses
   `get_hermes_home()` (reads env var), not `Path.home() / ".hermes"`:
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"HERMES_HOME": str(tmp_path / ".hermes")}):
       ...
   ```

5. **Gateway platform adapters should use token locks** — if the adapter connects with
   a unique credential (bot token, API key), call `acquire_scoped_lock()` from
   `gateway.status` in the `connect()`/`start()` method and `release_scoped_lock()` in
   `disconnect()`/`stop()`. This prevents two profiles from using the same credential.
   See `plugins/platforms/irc/adapter.py` for the canonical pattern.

6. **Profile operations are HOME-anchored, not HERMES_HOME-anchored** — `_get_profiles_root()`
   returns `Path.home() / ".hermes" / "profiles"`, NOT `get_hermes_home() / "profiles"`.
   This is intentional — it lets `hermes -p coder profile list` see all profiles regardless
   of which one is active.

## Known Pitfalls

### DO NOT hardcode `~/.hermes` paths
Use `get_hermes_home()` from `hermes_constants` for code paths. Use `display_hermes_home()`
for user-facing print/log messages. Hardcoding `~/.hermes` breaks profiles — each profile
has its own `HERMES_HOME` directory. This was the source of 5 bugs fixed in PR #3575.

### DO NOT introduce new `simple_term_menu` usage
Existing call sites in `hermes_cli/main.py` remain for legacy fallback only;
the preferred UI is curses (stdlib) because `simple_term_menu` has
ghost-duplication rendering bugs in tmux/iTerm2 with arrow keys. New
interactive menus must use `hermes_cli/curses_ui.py` — see
`hermes_cli/tools_config.py` for the canonical pattern.

### DO NOT use `\033[K` (ANSI erase-to-EOL) in spinner/display code
Leaks as literal `?[K` text under `prompt_toolkit`'s `patch_stdout`. Use space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` is a process-global in `model_tools.py`
`_run_single_child()` in `delegate_tool.py` saves and restores this global around subagent execution. If you add new code that reads this global, be aware it may be temporarily stale during child agent runs.

### DO NOT hardcode cross-tool references in schema descriptions
Tool schema descriptions must not mention tools from other toolsets by name (e.g., `browser_navigate` saying "prefer web_search"). Those tools may be unavailable (missing API keys, disabled toolset), causing the model to hallucinate calls to non-existent tools. If a cross-reference is needed, add it dynamically in `get_tool_definitions()` in `model_tools.py` — see the `browser_navigate` / `execute_code` post-processing blocks for the pattern.

### The gateway has TWO message guards — both must bypass approval/control commands
When an agent is running, messages pass through two sequential guards:
(1) **base adapter** (`gateway/platforms/base.py`) queues messages in
`_pending_messages` when `session_key in self._active_sessions`, and
(2) **gateway runner** (`gateway/run.py`) intercepts `/stop`, `/new`,
`/queue`, `/status`, `/approve`, `/deny` before they reach
`running_agent.interrupt()`. Any new command that must reach the runner
while the agent is blocked (e.g. approval prompts) MUST bypass BOTH
guards and be dispatched inline, not via `_process_message_background()`
(which races session lifecycle).

### Squash merges from stale branches silently revert recent fixes
Before squash-merging a PR, ensure the branch is up to date with `main`
(`git fetch origin main && git reset --hard origin/main` in the worktree,
then re-apply the PR's commits). A stale branch's version of an unrelated
file will silently overwrite recent fixes on main when squashed. Verify
with `git diff HEAD~1..HEAD` after merging — unexpected deletions are a
red flag.

### Don't wire in dead code without E2E validation
Unused code that was never shipped was dead for a reason. Before wiring an
unused module into a live code path, E2E test the real resolution chain
with actual imports (not mocks) against a temp `HERMES_HOME`.

### Tests must not write to `~/.hermes/`
The `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. Never hardcode `~/.hermes/` paths in tests.

**Profile tests**: When testing profile features, also mock `Path.home()` so that
`_get_profiles_root()` and `_get_default_hermes_home()` resolve within the temp dir.
Use the pattern from `tests/hermes_cli/test_profiles.py`:
## Testing

### Python
**ALWAYS use `scripts/run_tests.sh`** — do not call `pytest` directly. The script enforces
hermetic environment parity with CI (unset credential vars, TZ=UTC, LANG=C.UTF-8,
per-file subprocess isolation via `scripts/run_tests_parallel.py` — no xdist,
worker count auto-scaled from CPU count). Direct `pytest`
on a 16+ core developer machine with API keys set diverges from CI in ways
that have caused multiple "works locally, fails in CI" incidents (and the reverse).

```bash
scripts/run_tests.sh                                  # full suite, CI-parity
scripts/run_tests.sh tests/gateway/                   # one directory
scripts/run_tests.sh tests/agent/test_foo.py -k test_x  # one test (file + -k; the runner is file-granular)
scripts/run_tests.sh -v --tb=long                     # pass-through pytest flags
```

**Flake policy:** the runner auto-retries a failing test FILE once in a fresh
subprocess (`--file-retries`, default 1; `HERMES_TEST_FILE_RETRIES=0` to
disable). Pass-on-retry counts as green but is printed in a `⚠ FLAKY` summary
section with both attempts' output. A FLAKY report is a bug to fix, not noise
to ignore — timing-sensitive tests must not assume a quiet runner (loose
wall-clock bounds ≥ 2s, event-based sync, no `assert not _wait_until(...)`
negative-timing races).
### Never read source code in tests

A test that reads a source file's text is testing *the shape of the
source code*, not its behavior. This is a hard antipattern, banned outright.
Any test that reads a .py, .ts, .tsx, etc., file is suspect.

**Why it's actively harmful, not just weak:**

- It passes when the implementation is subtly broken (the regex matches a
  call site that exists but is wired wrong) and fails when a correct
  refactor changes formatting, variable names, or control flow with
  identical runtime behavior. Both directions of failure are wrong.
- It can't be run against a built/bundled/minified artifact, so it silently
  stops testing anything the moment code moves, gets renamed, or a
  dependency reformats it.
- It actively blocks refactors: reviewers see "keeps a pattern intact" tests
  fail during pure structural cleanup with no behavior change, and either
  hand-wave the failure (dangerous) or waste time updating regexes that add
  nothing (waste).
- It gives false confidence. a green suite full of source-regex tests
  looks like coverage but has never once executed the code path it claims
  to guard.

**Do not write:**

```ts
const source = fs.readFileSync(path.join(__dirname, 'main.ts'), 'utf8')

test('backend spawn hides the Windows console', () => {
  assert.match(source, /spawn\(\s*backend\.command,\s*backend\.args[\s\S]{0,300}hiddenWindowsChildOptions/)
})
```

**Do write — extract the logic into a small pure/DI-testable function and
call it for real:**

```ts
// backend-spawn.ts
export function hiddenWindowsChildOptions(options: SpawnOptionsLike = {}, isWindows = process.platform === 'win32') {
  if (!isWindows || 'windowsHide' in options) return options
  return { ...options, windowsHide: true }
}

// backend-spawn.test.ts
test('windowsHide defaults to true on Windows, is left alone elsewhere', () => {
  assert.equal(hiddenWindowsChildOptions({}, true).windowsHide, true)
  assert.equal(hiddenWindowsChildOptions({}, false).windowsHide, undefined)
  assert.equal(hiddenWindowsChildOptions({ windowsHide: false }, true).windowsHide, false)
})
```

If the logic lives inline in a god-file (`main.ts`, `cli.py`,
`gateway/run.py`) and extracting it feels disruptive: that's the actual
signal to do the extraction, not to regex around it.
