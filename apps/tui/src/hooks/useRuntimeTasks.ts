import React from "react";
import type {
  TaskProgressData,
  TaskStartData,
  StatusUpdateData,
  TaskCompleteData,
  TaskErrorData,
} from "../bridge/protocol.js";
import { useSetAppState } from "../state/AppState.js";
import type { TaskState } from "../state/AppStateStore.js";

function upsertTask(
  tasks: Record<string, TaskState>,
  id: string,
  patch: Partial<TaskState>,
): Record<string, TaskState> {
  const current = tasks[id] ?? {
    id,
    status: "idle",
    updatedAt: Date.now(),
  };

  return {
    ...tasks,
    [id]: {
      ...current,
      ...patch,
      id,
      updatedAt: Date.now(),
    },
  };
}

function isTerminalRuntimePhase(phase: string | undefined): boolean {
  return (
    phase === "query_complete" ||
    phase === "query_cancelled" ||
    phase === "query_error" ||
    phase === "completed" ||
    phase === "error" ||
    phase === "cancelled"
  );
}

export function useRuntimeTasks(): {
  applyStatusUpdate: (data: StatusUpdateData) => void;
  markTaskStart: (data: TaskStartData) => void;
  markTaskProgress: (data: TaskProgressData) => void;
  markTaskComplete: (data: TaskCompleteData) => void;
  markTaskError: (data: TaskErrorData) => void;
} {
  const setAppState = useSetAppState();

  const applyStatusUpdate = React.useCallback(
    (data: StatusUpdateData) => {
      setAppState(prev => {
        const taskId = data.task_id ?? prev.runtime.activeTaskId;
        const nextTasks =
          taskId !== undefined
            ? upsertTask(prev.tasks, taskId, {
                status:
                  data.phase === "execution_start"
                    ? "running"
                    : (prev.tasks[taskId]?.status ?? "running"),
                phase: data.phase ?? prev.tasks[taskId]?.phase,
                maxIterations:
                  data.max_iterations ?? prev.tasks[taskId]?.maxIterations,
                iterations:
                  data.total_iterations ?? prev.tasks[taskId]?.iterations,
              })
            : prev.tasks;

        return {
          ...prev,
          isQuerying: isTerminalRuntimePhase(data.phase)
            ? false
            : prev.isQuerying,
          tasks: nextTasks,
          mainLoopModel: data.model ?? prev.mainLoopModel,
          runtime: {
            ...prev.runtime,
            model: data.model ?? prev.runtime.model,
            sessionId: data.session_id ?? prev.runtime.sessionId,
            costUsd: data.cost_usd ?? prev.runtime.costUsd,
            inputTokens: data.input_tokens ?? prev.runtime.inputTokens,
            outputTokens: data.output_tokens ?? prev.runtime.outputTokens,
            phase: data.phase ?? prev.runtime.phase,
            activeTaskId: taskId ?? prev.runtime.activeTaskId,
            maxIterations:
              data.max_iterations ?? prev.runtime.maxIterations,
            totalIterations:
              data.total_iterations ?? prev.runtime.totalIterations,
            sandbox: data.sandbox ?? prev.runtime.sandbox,
          },
        };
      });
    },
    [setAppState],
  );

  const markTaskComplete = React.useCallback(
    (data: TaskCompleteData) => {
      const taskId = data.task_id ?? "active";
      setAppState(prev => ({
        ...prev,
        isQuerying: false,
        tasks: upsertTask(prev.tasks, taskId, {
          status: data.status === "incomplete" ? "incomplete" : "success",
          iterations: data.iterations,
          toolCalls: data.tool_calls,
          executionTime: data.execution_time,
          title: data.result,
        }),
      }));
    },
    [setAppState],
  );

  const markTaskError = React.useCallback(
    (data: TaskErrorData) => {
      const taskId = data.task_id ?? "active";
      setAppState(prev => ({
        ...prev,
        isQuerying: false,
        tasks: upsertTask(prev.tasks, taskId, {
          status: "error",
          error: data.error,
          executionTime: data.execution_time,
        }),
      }));
    },
    [setAppState],
  );

  const markTaskStart = React.useCallback(
    (data: TaskStartData) => {
      setAppState(prev => ({
        ...prev,
        tasks: upsertTask(prev.tasks, data.task_id, {
          status: "running",
          title: data.title,
          phase: data.status,
        }),
        runtime: {
          ...prev.runtime,
          activeTaskId: data.task_id,
          phase: data.status ?? prev.runtime.phase,
        },
      }));
    },
    [setAppState],
  );

  const markTaskProgress = React.useCallback(
    (data: TaskProgressData) => {
      const taskId = data.task_id;
      setAppState(prev => ({
        ...prev,
        tasks: upsertTask(prev.tasks, taskId, {
          status: "running",
          title: data.title ?? prev.tasks[taskId]?.title,
          phase: data.progress ?? data.status ?? prev.tasks[taskId]?.phase,
        }),
        runtime: {
          ...prev.runtime,
          activeTaskId: taskId,
          phase: data.progress ?? data.status ?? prev.runtime.phase,
        },
      }));
    },
    [setAppState],
  );

  return {
    applyStatusUpdate,
    markTaskStart,
    markTaskProgress,
    markTaskComplete,
    markTaskError,
  };
}
