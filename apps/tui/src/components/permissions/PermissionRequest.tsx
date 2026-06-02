import React from "react";
import { Box, Text } from "ink";
import {
  buildAskUserQuestionAllowResponse,
  buildAskUserQuestionDenyResponse,
  getAskUserQuestionQuestions,
  isAskUserQuestionRequest,
} from "../../bridge/askUserQuestionState.js";
import type {
  AskUserQuestionData,
  AskUserQuestionOptionData,
  PermissionRequestData,
  ToolPermissionOptionData,
} from "../../bridge/protocol.js";
import {
  getAllowAlwaysLabel,
  getPermissionRequestSummary,
  isSandboxPermissionRequest,
  isWorkerPermissionRequest,
} from "../../bridge/permissionRequestState.js";
import { useQueuedMessage } from "../../context/QueuedMessageContext.js";
import { useRegisterOverlay } from "../../context/overlayContext.js";
import type { PermissionResolution } from "../../hooks/toolPermission/PermissionContext.js";
import {
  useKeybindingInput,
  useKeybindings,
} from "../../keybindings/useKeybinding.js";
import { useShortcutDisplay } from "../../keybindings/useShortcutDisplay.js";
import { stringifyUnknown, truncate } from "../../screens/shared.js";
import {
  isBackspaceInput,
  isDeleteInput,
} from "../../utils/keyInput.js";

type Props = {
  request: PermissionRequestData;
  queueLength?: number;
  onResolve?: (resolution: PermissionResolution) => void;
};

function riskColor(riskLevel: string | undefined): string {
  switch (riskLevel) {
    case "high":
      return "red";
    case "low":
      return "green";
    case "medium":
    default:
      return "yellow";
  }
}

function hasAllowAlwaysOption(request: PermissionRequestData): boolean {
  return (
    request.response_channel !== "tool_permission_response" ||
    request.options?.some(option => option.option_id === "allow_always") === true
  );
}

function getCommandInput(request: PermissionRequestData): string | null {
  const command = request.tool_input.command;
  if (typeof command === "string" && command.trim()) {
    return command.trim();
  }
  return null;
}

function formatToolPermissionOptions(
  options: ToolPermissionOptionData[] | undefined,
): string | null {
  if (!options || options.length === 0) {
    return null;
  }
  return options.map((option, index) => `${index + 1}. ${option.label}`).join(" | ");
}

function getQuestionKey(question: AskUserQuestionData): string {
  return question.question;
}

const OTHER_OPTION_LABEL = "__other__";

function buildSelectableOptions(
  question: AskUserQuestionData,
): AskUserQuestionOptionData[] {
  const hasOther = question.options.some(
    option => option.label === OTHER_OPTION_LABEL,
  );
  return hasOther
    ? question.options
    : [
        ...question.options,
        {
          label: OTHER_OPTION_LABEL,
          description: "Custom answer",
        },
      ];
}

function optionLabelForDisplay(option: AskUserQuestionOptionData): string {
  return option.label === OTHER_OPTION_LABEL ? "Other" : option.label;
}

function answerFromState(
  question: AskUserQuestionData,
  selected: Record<string, string[]>,
  customInput: Record<string, string>,
): string {
  const key = getQuestionKey(question);
  const labels = selected[key] ?? [];
  const custom = customInput[key]?.trim();
  const regularLabels = labels.filter(label => label !== OTHER_OPTION_LABEL);

  if (labels.includes(OTHER_OPTION_LABEL)) {
    return custom ? [...regularLabels, custom].join(", ") : regularLabels.join(", ");
  }

  return regularLabels.join(", ");
}

function buildAnswersFromState(
  questions: AskUserQuestionData[],
  selected: Record<string, string[]>,
  customInput: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(
    questions
      .map(question => [question.question, answerFromState(question, selected, customInput)])
      .filter((entry): entry is [string, string] => entry[1].trim().length > 0),
  );
}

function questionIsAnswered(
  question: AskUserQuestionData,
  selected: Record<string, string[]>,
  customInput: Record<string, string>,
): boolean {
  return answerFromState(question, selected, customInput).trim().length > 0;
}

function GenericPermissionRequest({
  request,
  queueLength,
}: Props): React.ReactElement {
  const queuedMessage = useQueuedMessage();
  const allowShortcut = useShortcutDisplay("confirm:yes", "Confirmation", "y");
  const denyShortcut = useShortcutDisplay("confirm:no", "Confirmation", "n");
  const alwaysShortcut = useShortcutDisplay(
    "permission:allowAlways",
    "Confirmation",
    "a",
  );
  const borderColor = riskColor(request.risk_level);
  const heading = isSandboxPermissionRequest(request)
    ? request.request_kind === "network"
      ? "Network Permission Request"
      : "Sandbox Permission Request"
    : request.tool_name.toLowerCase() === "bash"
      ? "Bash Command Permission"
      : "Permission Request";
  const workerOrigin = isWorkerPermissionRequest(request);
  const workerName = request.agent_name ?? request.agent_id;
  const originLabel = workerOrigin
    ? `Worker ${workerName ?? "worker"}`
    : "Primary session";
  const summary = request.message ?? getPermissionRequestSummary(request);
  const allowAlwaysLabel = getAllowAlwaysLabel(request);
  const command = getCommandInput(request);
  const optionLabels = formatToolPermissionOptions(request.options);
  const showAllowAlways = hasAllowAlwaysOption(request);
  const highRisk = request.risk_level === "high";

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={borderColor}
      paddingX={1}
      marginTop={1}
    >
      <Text bold color={borderColor as never}>
        {queuedMessage?.isQueued ? `Queued ${heading}` : heading}
      </Text>
      {queueLength !== undefined && queueLength > 1 ? (
        <Text color="gray">{queueLength} pending approval request(s)</Text>
      ) : null}
      <Text>
        Tool: {request.tool_name} | Risk: {request.risk_level ?? "medium"}
      </Text>
      <Text>Origin: {originLabel}</Text>
      {request.host ? <Text>Host: {request.host}</Text> : null}
      {request.blocked_path ? (
        <Text color={highRisk ? "red" : "yellow"}>
          Blocked path: {request.blocked_path}
        </Text>
      ) : null}
      {command ? (
        <Text color={highRisk ? "red" : undefined}>Command: {command}</Text>
      ) : null}
      {highRisk ? (
        <Text color="red">High-risk command requires explicit approval.</Text>
      ) : null}
      <Text>{summary}</Text>
      {request.decision_reason ? (
        <Text color="gray">
          Reason: {truncate(stringifyUnknown(request.decision_reason), 160)}
        </Text>
      ) : null}
      {optionLabels ? <Text color="gray">Options: {optionLabels}</Text> : null}
      <Text color="gray">
        {truncate(
          stringifyUnknown(request.tool_input),
          queuedMessage ? Math.max(120, 180 - queuedMessage.paddingWidth * 8) : 180,
        )}
      </Text>
      <Text>
        {allowShortcut} allow | {denyShortcut} deny
        {showAllowAlways ? ` | ${alwaysShortcut} ${allowAlwaysLabel}` : ""}
      </Text>
    </Box>
  );
}

function AskUserQuestionPermissionRequest({
  request,
  queueLength,
  onResolve,
}: Props): React.ReactElement {
  const questions = React.useMemo(
    () => getAskUserQuestionQuestions(request),
    [request],
  );
  const [questionIndex, setQuestionIndex] = React.useState(0);
  const [optionIndex, setOptionIndex] = React.useState(0);
  const [selected, setSelected] = React.useState<Record<string, string[]>>({});
  const [customInput, setCustomInput] = React.useState<Record<string, string>>({});
  const [notes, setNotes] = React.useState<Record<string, string>>({});
  const [inputMode, setInputMode] = React.useState<"options" | "other" | "notes">(
    "options",
  );
  const [error, setError] = React.useState<string | null>(null);
  const currentQuestion = questions[questionIndex];
  const options = currentQuestion ? buildSelectableOptions(currentQuestion) : [];
  const currentKey = currentQuestion ? getQuestionKey(currentQuestion) : "";
  const currentSelection = selected[currentKey] ?? [];
  const currentCustom = customInput[currentKey] ?? "";
  const currentNotes = notes[currentKey] ?? "";
  const focusedOption = options[optionIndex] ?? null;
  const readyAnswers = buildAnswersFromState(questions, selected, customInput);

  React.useEffect(() => {
    setQuestionIndex(0);
    setOptionIndex(0);
    setSelected({});
    setCustomInput({});
    setNotes({});
    setInputMode("options");
    setError(null);
  }, [request.tool_use_id]);

  const resolveAllow = React.useCallback(
    (answers: Record<string, string>) => {
      onResolve?.(buildAskUserQuestionAllowResponse(request, answers, notes));
    },
    [notes, onResolve, request],
  );

  const trySubmit = React.useCallback(
    (
      nextSelected = selected,
      nextCustomInput = customInput,
      targetIndex = questionIndex,
    ) => {
      const question = questions[targetIndex];
      if (!question) {
        onResolve?.(buildAskUserQuestionDenyResponse(request));
        return;
      }

      if (!questionIsAnswered(question, nextSelected, nextCustomInput)) {
        setError("Select an option or enter Other text.");
        return;
      }

      const nextAnswers = buildAnswersFromState(
        questions,
        nextSelected,
        nextCustomInput,
      );
      if (Object.keys(nextAnswers).length < questions.length) {
        const nextIndex = Math.min(targetIndex + 1, questions.length - 1);
        setQuestionIndex(nextIndex);
        setOptionIndex(0);
        setInputMode("options");
        setError(null);
        return;
      }

      resolveAllow(nextAnswers);
    },
    [customInput, onResolve, questionIndex, questions, request, resolveAllow, selected],
  );

  const selectOption = React.useCallback(
    (option: AskUserQuestionOptionData | null) => {
      if (!currentQuestion || !option) {
        return;
      }

      const key = getQuestionKey(currentQuestion);
      if (option.label === OTHER_OPTION_LABEL) {
        setSelected(previous => ({
          ...previous,
          [key]: currentQuestion.multiSelect
            ? Array.from(new Set([...(previous[key] ?? []), OTHER_OPTION_LABEL]))
            : [OTHER_OPTION_LABEL],
        }));
        setInputMode("other");
        setError(null);
        return;
      }

      if (currentQuestion.multiSelect) {
        setSelected(previous => {
          const existing = previous[key] ?? [];
          const next = existing.includes(option.label)
            ? existing.filter(label => label !== option.label)
            : [...existing, option.label];
          return {
            ...previous,
            [key]: next,
          };
        });
        setError(null);
        return;
      }

      const nextSelected = {
        ...selected,
        [key]: [option.label],
      };
      setSelected(nextSelected);
      trySubmit(nextSelected, customInput);
    },
    [currentQuestion, customInput, selected, trySubmit],
  );

  const handleConfirm = React.useCallback(() => {
    if (!currentQuestion) {
      onResolve?.(buildAskUserQuestionDenyResponse(request));
      return;
    }

    if (inputMode === "other" || inputMode === "notes") {
      setInputMode("options");
      setError(null);
      if (inputMode === "other" && !currentCustom.trim()) {
        setError("Enter text for Other before continuing.");
      }
      return;
    }

    if (currentQuestion.multiSelect) {
      trySubmit();
      return;
    }

    if (currentSelection.length === 0) {
      selectOption(focusedOption);
      return;
    }

    trySubmit();
  }, [
    currentCustom,
    currentQuestion,
    currentSelection.length,
    focusedOption,
    inputMode,
    onResolve,
    request,
    selectOption,
    trySubmit,
  ]);

  const handleDeny = React.useCallback(() => {
    onResolve?.(buildAskUserQuestionDenyResponse(request));
  }, [onResolve, request]);

  useKeybindings(
    {
      "confirm:yes": handleConfirm,
      "confirm:no": handleDeny,
      "confirm:next": () => {
        if (inputMode !== "options" || options.length === 0) {
          return;
        }
        setOptionIndex(current => (current + 1) % options.length);
      },
      "confirm:previous": () => {
        if (inputMode !== "options" || options.length === 0) {
          return;
        }
        setOptionIndex(current => (current - 1 + options.length) % options.length);
      },
      "confirm:nextField": () => {
        setInputMode(current => (current === "notes" ? "options" : "notes"));
      },
      "confirm:previousField": () => {
        setInputMode(current => (current === "options" ? "notes" : "options"));
      },
    },
    { context: "Confirmation" },
  );

  useKeybindingInput(
    (value, key) => {
      if (!currentQuestion) {
        return;
      }

      const updateText = (
        setter: React.Dispatch<React.SetStateAction<Record<string, string>>>,
      ) => {
        if (isBackspaceInput(value, key) || isDeleteInput(value, key)) {
          setter(previous => ({
            ...previous,
            [currentKey]: (previous[currentKey] ?? "").slice(0, -1),
          }));
          return;
        }
        if (key.return) {
          setInputMode("options");
          return;
        }
        if (key.escape) {
          setInputMode("options");
          return;
        }
        if (value) {
          setter(previous => ({
            ...previous,
            [currentKey]: `${previous[currentKey] ?? ""}${value}`,
          }));
        }
      };

      if (inputMode === "other") {
        updateText(setCustomInput);
        setError(null);
        return;
      }

      if (inputMode === "notes") {
        updateText(setNotes);
        setError(null);
        return;
      }

      const digit = Number.parseInt(value, 10);
      if (!Number.isNaN(digit) && digit >= 1 && digit <= options.length) {
        setOptionIndex(digit - 1);
        selectOption(options[digit - 1] ?? null);
        return;
      }

      if (value.toLowerCase() === "o") {
        selectOption(options.find(option => option.label === OTHER_OPTION_LABEL) ?? null);
        return;
      }

      if (value.toLowerCase() === "t") {
        setInputMode("notes");
      }
    },
    { context: "Confirmation" },
  );

  if (!currentQuestion) {
    return (
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor="yellow"
        paddingX={1}
        marginTop={1}
      >
        <Text bold color="yellow">AskUserQuestion Permission</Text>
        <Text>No valid questions were provided.</Text>
        <Text>y deny | n deny</Text>
      </Box>
    );
  }

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
      marginTop={1}
    >
      <Text bold color="cyan">
        AskUserQuestion Permission
        {queueLength !== undefined && queueLength > 1
          ? ` (${queueLength} pending)`
          : ""}
      </Text>
      <Text>
        {questionIndex + 1}/{questions.length}:{" "}
        {currentQuestion.header ?? currentQuestion.question}
      </Text>
      {currentQuestion.header ? <Text>{currentQuestion.question}</Text> : null}
      {options.map((option, index) => {
        const selectedMarker = currentSelection.includes(option.label) ? "x" : " ";
        const focusMarker = index === optionIndex ? ">" : " ";
        return (
          <Text key={`${currentQuestion.question}-${option.label}`}>
            {focusMarker} [{selectedMarker}] {index + 1}. {optionLabelForDisplay(option)}
            {option.description ? ` - ${option.description}` : ""}
          </Text>
        );
      })}
      {focusedOption?.preview ? (
        <Text color="gray">Preview: {truncate(focusedOption.preview, 160)}</Text>
      ) : null}
      {inputMode === "other" ? (
        <Text color="yellow">Other: {currentCustom}</Text>
      ) : (
        <Text color="gray">Other: {currentCustom || "(empty)"}</Text>
      )}
      {inputMode === "notes" ? (
        <Text color="yellow">Notes: {currentNotes}</Text>
      ) : currentNotes ? (
        <Text color="gray">Notes: {currentNotes}</Text>
      ) : null}
      {Object.keys(readyAnswers).length > 0 ? (
        <Text color="gray">Answers: {truncate(stringifyUnknown(readyAnswers), 160)}</Text>
      ) : null}
      {error ? <Text color="red">{error}</Text> : null}
      <Text color="gray">
        Enter/y continue | n cancel | up/down choose | 1-{options.length} select | o other | tab notes
      </Text>
    </Box>
  );
}

export function PermissionRequest({
  request,
  queueLength,
  onResolve,
}: Props): React.ReactElement {
  useRegisterOverlay("permission-request");

  if (isAskUserQuestionRequest(request)) {
    return (
      <AskUserQuestionPermissionRequest
        request={request}
        queueLength={queueLength}
        onResolve={onResolve}
      />
    );
  }

  return <GenericPermissionRequest request={request} queueLength={queueLength} />;
}
