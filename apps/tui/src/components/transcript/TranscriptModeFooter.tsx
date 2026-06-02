import React from "react";
import { Box, Text } from "ink";
import { useShortcutDisplay } from "../../keybindings/useShortcutDisplay.js";

type Props = {
  messageCount: number;
  showAllInTranscript?: boolean;
  searchQuery?: string;
  searchMatchCount?: number;
  searchCurrentMatch?: number;
  cursorMessageLabel?: string | null;
  selectedMessageLabel?: string | null;
  restoreAvailable?: boolean;
};

export function TranscriptModeFooter({
  messageCount,
  showAllInTranscript = false,
  searchQuery = "",
  searchMatchCount = 0,
  searchCurrentMatch = 0,
  cursorMessageLabel = null,
  selectedMessageLabel = null,
  restoreAvailable = false,
}: Props): React.ReactElement {
  const exitShortcut = useShortcutDisplay(
    "app:toggleTranscript",
    "Global",
    "ctrl+o",
  );
  const pageUpShortcut = useShortcutDisplay(
    "scroll:pageUp",
    "Transcript",
    "PageUp",
  );
  const pageDownShortcut = useShortcutDisplay(
    "scroll:pageDown",
    "Transcript",
    "PageDown",
  );
  const topShortcut = useShortcutDisplay(
    "scroll:top",
    "Transcript",
    "Home",
  );
  const bottomShortcut = useShortcutDisplay(
    "scroll:bottom",
    "Transcript",
    "End",
  );
  const selectorShortcut = useShortcutDisplay(
    "transcript:openSelector",
    "Transcript",
    "v",
  );
  const targetCursorShortcut = useShortcutDisplay(
    "transcript:targetCursor",
    "Transcript",
    "t",
  );
  const showAllShortcut = useShortcutDisplay(
    "transcript:toggleShowAll",
    "Transcript",
    "ctrl+e",
  );
  const exportShortcut = useShortcutDisplay(
    "transcript:export",
    "Transcript",
    "ctrl+s",
  );
  const editorShortcut = useShortcutDisplay(
    "transcript:externalEditor",
    "Transcript",
    "ctrl+x ctrl+e",
  );
  const rewindShortcut = useShortcutDisplay(
    "transcript:rewind",
    "Transcript",
    "ctrl+r",
  );
  const restoreShortcut = useShortcutDisplay(
    "transcript:restore",
    "Transcript",
    "u",
  );

  const searchStatus =
    searchQuery.trim().length > 0
      ? searchMatchCount > 0
        ? `Search: ${searchQuery} (${searchCurrentMatch}/${searchMatchCount})`
        : `Search: ${searchQuery} (no matches)`
      : "Search: inactive";

  const selectionStatus = selectedMessageLabel
    ? `Target: ${selectedMessageLabel}`
    : "Target: none";
  const cursorStatus = cursorMessageLabel
    ? `Cursor: ${cursorMessageLabel}`
    : "Cursor: none";
  const statusSegments = [
    `Transcript: ${messageCount} message${messageCount === 1 ? "" : "s"} (${showAllInTranscript ? "full" : "recent"})`,
    `${exitShortcut} exit`,
    "`/` search",
    searchQuery.trim().length > 0 ? searchStatus : null,
    selectedMessageLabel ? selectionStatus : cursorMessageLabel ? cursorStatus : null,
    `${pageUpShortcut}/${pageDownShortcut} scroll`,
    `${topShortcut}/${bottomShortcut} jump`,
    `${selectorShortcut} selector`,
    `${targetCursorShortcut} target`,
    `${showAllShortcut} ${showAllInTranscript ? "collapse" : "all"}`,
    `${rewindShortcut} rewind`,
    restoreAvailable ? `${restoreShortcut} restore` : null,
    `${exportShortcut} export`,
    `${editorShortcut} editor`,
  ].filter((segment): segment is string => segment !== null);

  return (
    <Box
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
      height={3}
      overflowY="hidden"
    >
      <Text color="gray" wrap="truncate">
        {statusSegments.join(" | ")}
      </Text>
    </Box>
  );
}
