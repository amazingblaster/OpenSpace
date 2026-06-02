# 🔧 Configuration Guide

## 1. LLM Credentials (`.env`)

> [!NOTE]
> Create `openspace/.env` from [`../.env.example`](../.env.example) and set at least one LLM API key.

Resolution priority (first match wins):

| Priority | Source | Example |
|----------|--------|---------|
| **Tier 1** | `OPENSPACE_LLM_*` env vars | `OPENSPACE_LLM_API_KEY=sk-xxx` |
| **Tier 2** | Provider-native env vars | `OPENROUTER_API_KEY=sk-or-xxx` |
| **Tier 3** | Host agent config | `~/.nanobot/config.json` / `~/.openclaw/openclaw.json` |

> [!IMPORTANT]
> Tier 2 blocks Tier 3 — if `.env` has a provider key, host agent config is skipped.

```bash
# Provider-native — litellm reads automatically
OPENROUTER_API_KEY=sk-or-v1-xxx

# Or: OpenSpace-native — higher priority, same effect
OPENSPACE_LLM_API_KEY=sk-or-v1-xxx
```

## 2. Environment Variables

Set via `.env`, MCP config `env` block, or system environment.

Set `OPENSPACE_SKIP_DOTENV=1` in the process environment before startup to
ignore local `.env` files; it cannot be enabled from `.env` itself.

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSPACE_MODEL` | LLM model | `openrouter/anthropic/claude-sonnet-4.5` |
| `OPENSPACE_SKIP_DOTENV` | Disable automatic `openspace/.env` and CWD `.env` loading | `false` |
| `OPENSPACE_LLM_API_KEY` | LLM API key (Tier 1 override) | — |
| `OPENSPACE_LLM_API_BASE` | LLM API base URL | — |
| `OLLAMA_API_BASE` | Local Ollama endpoint for `ollama/*` models | `http://127.0.0.1:11434` |
| `OLLAMA_API_KEY` | Placeholder key for Ollama-compatible clients | `ollama` |
| `OPENSPACE_LLM_EXTRA_HEADERS` | Extra LLM headers (JSON) | — |
| `OPENSPACE_LLM_CONFIG` | Arbitrary litellm kwargs (JSON) | — |
| `OPENSPACE_CLOUD_MODE` | Cloud mode, either `off` or `live` | `off` |
| `OPENSPACE_CLOUD_BASE_URL` | Cloud service root URL; do not include `/api`, `/api/v1`, or `/api/v2` | `https://open-space.cloud` |
| `OPENSPACE_CLOUD_API_KEY` | Cloud agent API key (`X-API-Key`) | — |
| `OPENSPACE_CLOUD_TELEMETRY_MODE` | Cloud telemetry mode, either `off` or `outbox` | `off` |
| `OPENSPACE_MAX_ITERATIONS` | Max agent iterations per task | `20` |
| `OPENSPACE_BACKEND_SCOPE` | Enabled backends (comma-separated) | `shell,mcp,meta` |
| `OPENSPACE_HOST_SKILL_DIRS` | Agent skill directories (comma-separated) | — |
| `OPENSPACE_WORKSPACE` | Project root for logs/workspace | — |
| `OPENSPACE_SHELL_CONDA_ENV` | Conda env for shell backend | — |

Provision cloud credentials with `openspace-cloud-auth bootstrap-agent-key --email you@example.com --agent-name openspace-local-agent`. The command writes `OPENSPACE_CLOUD_MODE=live`, `OPENSPACE_CLOUD_BASE_URL`, and `OPENSPACE_CLOUD_API_KEY` locally without printing the raw key.
| `OPENSPACE_SHELL_WORKING_DIR` | Working dir for shell backend | — |
| `OPENSPACE_CONFIG_PATH` | Custom grounding config JSON | — |
| `OPENSPACE_MCP_SERVERS_JSON` | MCP server definitions (JSON) | — |
| `ANTHROPIC_API_KEY` | Optional Anthropic key for `web_search` server-side search | — |
| `TAVILY_API_KEY` / `BRAVE_SEARCH_API_KEY` / `SERPAPI_API_KEY` | Optional fallback search provider keys | — |
| `OPENSPACE_WEB_FETCH_MODEL` | Optional model override for applying prompts to fetched pages | — |
| `OPENSPACE_ENABLE_RECORDING` | Record execution traces | `true` |
| `OPENSPACE_EVOLUTION_STORAGE_ROOT` | Root used to resolve `.openspace/openspace.db`, `.openspace/evidence.db`, staging, and backups | workspace |
| `OPENSPACE_SKILL_STORE_DB_PATH` | Explicit SkillStore SQLite path; also anchors the evolution storage root when no storage root is set | — |
| `OPENSPACE_EVOLUTION_EVIDENCE_DB_PATH` | Explicit evidence SQLite path; takes precedence over storage-root resolution for evidence | — |
| `OPENSPACE_EVOLUTION_EVIDENCE_ENABLED` | Enable durable evolution evidence collection | `true` |
| `OPENSPACE_EVOLUTION_TRIGGERS_ENABLED` | Enable durable TriggerJob creation from evidence checkpoints; set `false` to keep evidence ingest but pause trigger jobs | `true` |
| `OPENSPACE_EVOLUTION_ENGINE_ENABLED` | Enable TriggerJob processing through decision, admission, staged authoring, validation, and commit | `true` |
| `OPENSPACE_EVOLUTION_MODE` | Evolution mode: `audit_only` audits only, `fix_only` commits explicit direct FIX only, `autonomous` allows all validated admitted actions | `autonomous` |
| `OPENSPACE_EVOLUTION_ALLOWED_READ_ROOTS` | Extra evidence file-read roots, separated by the platform path separator | — |
| `OPENSPACE_LOG_LEVEL` | Log level | `INFO` |

## 3. User Settings (`settings.json`)

Use user/project settings for runtime preferences that should persist across runs. These are separate from `openspace/config/*.json`, which configures backend implementation details.

Load order, later entries override earlier ones:

| Source | Path | Use for |
|--------|------|---------|
| User settings | `~/.openspace/settings.json` or `$OPENSPACE_CONFIG_HOME/settings.json` | Personal defaults |
| Project settings | `<project>/.openspace/settings.json` | Team/project defaults that may be committed |
| Local settings | `<project>/.openspace/settings.local.json` | Machine-local overrides, gitignored |
| Environment | `OPENSPACE_*` | CI, temporary overrides, deployment |
| Runtime | CLI/TUI updates | Current session state |

Settings are grouped by stability:

| Group | Keys |
|-------|------|
| Stable engine | `model`, `alwaysThinkingEnabled`, `autoCompactEnabled`, `autoMemoryEnabled`, `autoDream.*`, `memory.*`, `permissions.*`, `todoFeatureEnabled`, `fileCheckpointingEnabled`, `language` |
| Stable UI | `theme`, `editorMode`, `verbose`, `preferredNotifChannel`, `showTurnDuration`, `terminalProgressBarEnabled` |
| Experimental | `teammateMode`, `outputStyle`, `attachments.todoReminderEnabled` |

Example:

```json
{
  "model": "openrouter/qwen/qwen3.6-plus",
  "alwaysThinkingEnabled": true,
  "autoCompactEnabled": true,
  "permissions": {
    "defaultMode": "default",
    "allow": ["Bash(git status:*)"]
  },
  "autoDream": {
    "enabled": true,
    "minHours": 12,
    "minSessions": 3
  },
  "memory": {
    "mode": "daily_log"
  },
  "theme": "dark",
  "attachments": {
    "todoReminderEnabled": true
  }
}
```

Notes:

- Use `autoDream.enabled`; the old `autoDreamEnabled` alias is not part of the runtime settings schema.
- Only `attachments.todoReminderEnabled` is currently public. Future attachment gates will be added only when the runtime feature is actually wired.
- OpenSpace does not currently expose `flagSettings` or `policySettings`; enterprise policy sources will be modeled only when there is a real backend.
- There is no published SchemaStore URL yet, so do not add `$schema: "https://json.schemastore.org/openspace-settings.json"`.

You can inspect or update settings with slash commands:

```text
/settings
/settings model openrouter/qwen/qwen3.6-plus
/settings autoDream.enabled true
/settings permissions.defaultMode plan
```

## 4. MCP Servers (`config_mcp.json`)

Register external MCP servers that OpenSpace connects to as a **client** (e.g. GitHub, Slack, databases):

```bash
cp openspace/config/config_mcp.json.example openspace/config/config_mcp.json
```

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}" }
    }
  }
}
```

## 5. Execution Mode

The shell backend supports only local execution. This keeps Bash sandbox
decisions, foreground/background tasks, `TaskGet`, and `TaskStop` in one
process-level runtime. The GUI backend still supports local and server modes.

| Backend | Supported Modes | Notes |
|---|---|---|
| `shell` | `"local"` only | `asyncio.subprocess` in-process with runtime task lifecycle |
| `gui` | `"local"` or `"server"` | Server mode uses the private `local_server` transport |

> [!TIP]
> Do not set `shell.mode` to `"server"`. The HTTP local server does not expose the shell spawn/status/tail/kill contract required by the runtime.

## 6. Config Files (`openspace/config/`)

Layered system — later files override earlier ones:

| File | Purpose |
|------|---------|
| `config_grounding.json` | Backend settings, smart tool retrieval, tool quality, skill discovery |
| `config_agents.json` | Agent definitions, backend scope, max iterations |
| `config_mcp.json` | MCP servers OpenSpace connects to as a client |
| `config_security.json` | Security policies, blocked commands, sandboxing |
| `config_dev.json` | Dev overrides — copy from `config_dev.json.example` (highest priority) |
| `config_communication.json` | Communication gateway settings for WhatsApp and Feishu. Use `agent` for per-message OpenSpace execution and `sessions` for queue/history limits. LLM model stays in `openspace/.env`. |

### Agent config (`config_agents.json`)

```json
{ "agents": [{ "name": "GroundingAgent", "backend_scope": ["shell", "mcp", "web"], "max_iterations": 30 }] }
```

| Field | Description | Default |
|-------|-------------|---------|
| `backend_scope` | Enabled backends | `["gui", "shell", "mcp", "meta", "web"]` |
| `max_iterations` | Max execution cycles | `20` |

### Backend & tool config (`config_grounding.json`)

| Section | Key Fields | Description |
|---------|-----------|-------------|
| `shell` | `mode`, `timeout`, `conda_env`, `working_dir` | `"local"` only, command timeout (default: `60`s) |
| `web.search` | `search_model`, `search_api_key`, `search_base_url`, `max_searches_per_call`, `fallback_search_provider` | Web search settings; uses provider server-side search when configured, then provider fallback |
| `web.fetch` | `summarize_model`, `max_content_length`, `request_timeout`, `user_agent`, `preapproved_domains` | Web fetch settings; fetches URLs locally and applies a secondary model when needed |
| `gui` | `mode`, `timeout`, `driver_type`, `screenshot_on_error`, `enable_visual_analysis`, `visual_analysis_mode`, `visual_analysis_timeout`, `visual_analysis_model` | Local/server mode, automation driver, GUI visual analysis fallback policy |
| `mcp` | `timeout`, `sandbox`, `eager_sessions` | Request timeout (`30`s), E2B sandbox, lazy/eager server init |
| `tool_search` | `search_mode`, `max_tools`, `enable_llm_filter` | `"hybrid"` (semantic + LLM), max tools to return (`40`), embedding cache |
| `tool_quality` | `enabled`, `enable_persistence`, `enable_quality_ranking` | Quality tracking for ranking and reporting |
| `skills` | `enabled`, `skill_dirs`, `listing_enabled`, `discovery_enabled`, `discovery_max_results`, `post_tool_query_builder_*` | Skill exposure uses lightweight listing/discovery plus explicit `Skill` invocation. |

### Security config (`config_security.json`)

| Field | Description | Default |
|-------|-------------|---------|
| `allow_shell_commands` | Enable shell execution | `true` |
| `blocked_commands` | Platform-specific blacklists (common/linux/darwin/windows) | `rm -rf`, `shutdown`, `dd`, etc. |
| `sandbox_enabled` | Enable sandboxing for all operations | `false` |
| Per-backend overrides | Shell, MCP, GUI, Web each have independent security policies | Inherit global |

## 7. Communication Gateway

The tracked communication config is safe-by-default: loopback-only, channels disabled, and deny-by-default access control. Copy the example config, fill in credentials and `allowed_users`, then explicitly enable the channels you want. The gateway model is not configured here; it inherits `OPENSPACE_MODEL` from `openspace/.env`.

`config_communication.json` accepts only the canonical top-level `agent` and `sessions` sections for execution and queue/history settings. The old `openspace` and `runtime` root keys are rejected instead of being mapped silently.

```bash
cp openspace/config/config_communication.json.example openspace/config/config_communication.json
```

Install the Feishu SDK extra when you need Feishu support:

```bash
pip install -e '.[communication]'
```

Start the gateway:

```bash
openspace-gateway --config openspace/config/config_communication.json
```

Check health:

```bash
openspace-gateway health --config openspace/config/config_communication.json
```

Notes:

- The tracked `config_communication.json` now stays local-only and deny-by-default. Keep credentials out of git and populate them from a private working copy or environment variables.
- Set `server.host` to `0.0.0.0` only when Feishu needs to reach the webhook from outside the machine, and pair that with a populated allowlist plus webhook verification secrets.
- Feishu now supports both `webhook` and `websocket` modes. `websocket` matches nanobot's long-connection setup and does not require a public webhook URL.
- WhatsApp requires Node.js and npm. The bundled bridge installs its dependencies on first start when `auto_install_dependencies` is enabled.
- Set `feishu.bot_open_id` if you want strict group mention gating and automatic bot identity discovery is unavailable in your deployment.
- Group chats are gated by `group_policy`. `reply_or_mention` is the default and only accepts messages that mention the bot or reply to a prior assistant message.
- `allowed_users` is enforced when `allow_all_users` is `false`. The secure default is deny-by-default until you populate the allowlist.
- Attachment caching is limited by `sessions.max_attachment_bytes` and `sessions.max_session_attachment_bytes` to bound disk usage per file and per session.
