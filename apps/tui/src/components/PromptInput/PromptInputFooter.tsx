import React from "react";
import { Box, Text } from "ink";
import { useShortcutDisplay } from "../../keybindings/useShortcutDisplay.js";
import type { InputMode } from "../../state/AppStateStore.js";
import type { SandboxStatusData } from "../../bridge/protocol.js";
import type { VimMode } from "../../types/textInputTypes.js";
import { sandboxHint } from "../../utils/sandboxPromptFooter.js";

type Props = {
  disabled: boolean;
  busy?: boolean;
  inputMode: InputMode;
  vimMode?: VimMode;
  suggestionsVisible: boolean;
  sandbox?: SandboxStatusData;
};

export default function PromptInputFooter({
  disabled,
  busy = false,
  inputMode,
  vimMode,
  suggestionsVisible,
  sandbox,
}: Props): React.ReactElement {
  const submitShortcut = useShortcutDisplay("chat:submit", "Chat", "Enter");
  const newlineShortcut = useShortcutDisplay("chat:newline", "Chat", "shift+Enter");
  const cancelShortcut = useShortcutDisplay("app:interrupt", "Global", "ctrl+c");
  const autocompleteAcceptShortcut = useShortcutDisplay(
    "autocomplete:accept",
    "Autocomplete",
    "Tab",
  );
  const autocompletePrevShortcut = useShortcutDisplay(
    "autocomplete:previous",
    "Autocomplete",
    "Up",
  );
  const autocompleteNextShortcut = useShortcutDisplay(
    "autocomplete:next",
    "Autocomplete",
    "Down",
  );
  const dismissShortcut = useShortcutDisplay(
    "chat:cancel",
    "Chat",
    "Esc",
  );

  let hint = disabled
    ? "Waiting for the current task to finish"
    : busy
      ? `Task running | ${cancelShortcut} cancel`
      : `${submitShortcut} send | ${newlineShortcut} newline | ${cancelShortcut} cancel`;

  if (!disabled && busy && inputMode === "command") {
    hint = suggestionsVisible
      ? `${autocompleteAcceptShortcut} complete | ${autocompletePrevShortcut}/${autocompleteNextShortcut} select | ${cancelShortcut} cancel`
      : `Task running | ${autocompleteAcceptShortcut} complete | ${cancelShortcut} cancel`;
  } else if (!disabled && inputMode === "command") {
    hint = suggestionsVisible
      ? `${autocompleteAcceptShortcut} complete | ${autocompletePrevShortcut}/${autocompleteNextShortcut} select | ${submitShortcut} run`
      : `${submitShortcut} run | ${autocompleteAcceptShortcut} complete | ${dismissShortcut} clear`;
  }
  const sandboxStatus = sandboxHint(sandbox);

  return (
    <Box marginTop={1} width="100%" height={2} justifyContent="space-between">
      <Box flexDirection="column" flexGrow={1} flexShrink={1}>
        <Text color="gray" wrap="truncate">{hint}</Text>
        {sandboxStatus ? (
          <Text color={sandboxStatus.color} wrap="truncate">
            {sandboxStatus.text}
          </Text>
        ) : (
          <Text> </Text>
        )}
      </Box>
      {vimMode ? <Text color="gray">vim {vimMode}</Text> : null}
    </Box>
  );
}
