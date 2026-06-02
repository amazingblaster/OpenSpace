import React from "react";
import { Box, Text } from "ink";
import type {
  AgentRuntimeState,
  MCPClientState,
  RuntimeState,
} from "../state/AppStateStore.js";
import type { VimMode } from "../types/textInputTypes.js";
import { formatTokens, formatUsd } from "../screens/shared.js";
import { CoordinatorStatusBar } from "./CoordinatorStatusBar.js";

type Props = {
  runtime: RuntimeState;
  mcpClientStates?: MCPClientState[];
  agents?: AgentRuntimeState;
  vimMode?: VimMode;
};

function formatSandboxSummary(runtime: RuntimeState): string {
  const sandbox = runtime.sandbox;
  if (!sandbox) {
    return "n/a";
  }
  if (sandbox.sandboxing_enabled) {
    return sandbox.mode === "auto-allow"
      ? "on auto"
      : sandbox.mode === "regular"
        ? "on regular"
        : "on";
  }
  if (sandbox.enabled_in_settings) {
    return sandbox.status === "fail" ? "fail" : "warn";
  }
  return "off";
}

export function StatusLine({
  runtime,
  mcpClientStates = [],
  agents,
  vimMode,
}: Props): React.ReactElement {
  const connectedMcp = mcpClientStates.filter(
    client => client.status === "connected",
  ).length;
  const failingMcp = mcpClientStates.filter(
    client => client.status === "error",
  ).length;
  const tokenWarning = runtime.tokenWarning;
  const showTokenWarning =
    tokenWarning?.is_above_warning_threshold === true;
  const tokenWarningColor =
    tokenWarning?.is_above_error_threshold === true ||
    tokenWarning?.is_at_blocking_limit === true
      ? "red"
      : "yellow";
  const tokenWarningText = tokenWarning
    ? tokenWarning.is_above_auto_compact_threshold
      ? `Context compacting (${tokenWarning.percent_left}% left)`
      : `Context low (${tokenWarning.percent_left}% left)`
    : null;

  return (
    <Box flexDirection="column" height={4} overflowY="hidden">
      <Text bold color="cyan">
        OpenSpace | {runtime.model ?? "model n/a"} | {runtime.phase ?? "idle"} | Cost{" "}
        {formatUsd(runtime.costUsd)}
      </Text>
      <Text color="gray">
        Session {runtime.sessionId ?? "n/a"} | Task {runtime.activeTaskId ?? "n/a"} | Tokens{" "}
        {formatTokens(runtime.inputTokens)} / {formatTokens(runtime.outputTokens)} |{" "}
        Iterations {runtime.totalIterations ?? 0}
        {runtime.maxIterations !== undefined ? ` / ${runtime.maxIterations}` : ""} | MCP{" "}
        {connectedMcp}/{mcpClientStates.length}
        {failingMcp > 0 ? ` (${failingMcp} error)` : ""}
        {" | "}Sandbox {formatSandboxSummary(runtime)}
        {vimMode ? ` | Vim ${vimMode}` : ""}
      </Text>
      <Box height={1}>
        {showTokenWarning && tokenWarningText ? (
          <Text color={tokenWarningColor as never}>{tokenWarningText}</Text>
        ) : null}
      </Box>
      <Box height={1}>
        {agents ? (
          <CoordinatorStatusBar
            coordinator={agents.coordinator}
            backgroundTasks={agents.backgroundTasks}
          />
        ) : null}
      </Box>
    </Box>
  );
}
