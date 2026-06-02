import React from "react";
import { Box, Text } from "ink";
import { useRegisterOverlay } from "../../context/overlayContext.js";
import { useSetPromptOverlay } from "../../context/promptOverlayContext.js";
import { useTerminalSize } from "../../hooks/useTerminalSize.js";
import type { InputMode } from "../../state/AppStateStore.js";
import type { SandboxStatusData } from "../../bridge/protocol.js";
import type { VimMode } from "../../types/textInputTypes.js";
import type { CompletionItem } from "./SlashCommandComplete.js";
import { SlashCommandComplete } from "./SlashCommandComplete.js";
import PromptInputFooter from "./PromptInputFooter.js";
import { PromptInputModeIndicator } from "./PromptInputModeIndicator.js";

type Props = {
  value: string;
  disabled: boolean;
  busy?: boolean;
  inputMode: InputMode;
  vimMode?: VimMode;
  cursorOffset?: number;
  placeholder?: string;
  suggestions?: CompletionItem[];
  selectedSuggestion?: number;
  showSuggestions?: boolean;
  renderSuggestionsInline?: boolean;
  publishSuggestionsOverlay?: boolean;
  sandbox?: SandboxStatusData;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function renderWithCursor(
  value: string,
  cursorOffset: number,
  disabled: boolean,
): React.ReactElement {
  const boundedOffset = clamp(cursorOffset, 0, value.length);
  const before = value.slice(0, boundedOffset);
  const cursor = value[boundedOffset] ?? " ";
  const after =
    boundedOffset < value.length ? value.slice(boundedOffset + 1) : "";

  return (
    <Text>
      <Text>{before}</Text>
      <Text inverse={!disabled}>{cursor}</Text>
      <Text>{after}</Text>
    </Text>
  );
}

export default function PromptInput({
  value,
  disabled,
  busy = false,
  inputMode,
  vimMode,
  cursorOffset = value.length,
  placeholder,
  suggestions = [],
  selectedSuggestion = 0,
  showSuggestions = false,
  renderSuggestionsInline = true,
  publishSuggestionsOverlay = true,
  sandbox,
}: Props): React.ReactElement {
  const terminalSize = useTerminalSize();
  const color =
    inputMode === "command"
      ? "cyan"
      : vimMode === "NORMAL"
        ? "yellow"
        : "green";
  const shouldRenderOverlay =
    publishSuggestionsOverlay &&
    showSuggestions &&
    !renderSuggestionsInline &&
    suggestions.length > 0;
  const emptyPlaceholder =
    placeholder ??
    (disabled ? "Waiting for the current task..." : "Type a prompt and press Enter");

  useRegisterOverlay("autocomplete", shouldRenderOverlay);
  useSetPromptOverlay(
    shouldRenderOverlay
      ? {
          suggestions,
          selectedSuggestion,
          maxColumnWidth: Math.max(24, Math.floor(terminalSize.columns * 0.7)),
        }
      : null,
  );

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={disabled ? "gray" : (color as never)}
      borderLeft={false}
      borderRight={false}
      borderBottom={false}
      paddingX={1}
      marginTop={1}
      width="100%"
      flexShrink={0}
    >
      <Box alignItems="flex-start" width="100%">
        <PromptInputModeIndicator
          inputMode={inputMode}
          disabled={disabled}
          vimMode={vimMode}
        />
        <Box flexDirection="column" flexGrow={1} flexShrink={1}>
          {value ? (
            renderWithCursor(value, cursorOffset, disabled)
          ) : (
            <Text color="gray" wrap="truncate">{emptyPlaceholder}</Text>
          )}
        </Box>
      </Box>

      {showSuggestions && renderSuggestionsInline ? (
        <Box marginTop={1}>
          <SlashCommandComplete
            items={suggestions}
            selectedIndex={selectedSuggestion}
            visible={showSuggestions}
            bordered={false}
          />
        </Box>
      ) : null}

      <PromptInputFooter
        disabled={disabled}
        busy={busy}
        inputMode={inputMode}
        vimMode={vimMode}
        suggestionsVisible={showSuggestions}
        sandbox={sandbox}
      />
    </Box>
  );
}
