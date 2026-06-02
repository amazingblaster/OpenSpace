import React from "react";
import { Text } from "ink";
import type {
  BackgroundAgentTaskState,
  CoordinatorRuntimeState,
} from "../state/AppStateStore.js";
import { getColor } from "./design-system/theme.js";

type Props = {
  coordinator: CoordinatorRuntimeState;
  backgroundTasks: Record<string, BackgroundAgentTaskState>;
};

function countRunningTeamTasks(
  tasks: Record<string, BackgroundAgentTaskState>,
  teamName: string | undefined,
): number {
  return Object.values(tasks).filter(task => {
    if (teamName && task.teamName !== teamName) {
      return false;
    }
    return ["running", "pending", "starting"].includes(task.status.toLowerCase());
  }).length;
}

export function CoordinatorStatusBar({
  coordinator,
  backgroundTasks,
}: Props): React.ReactElement | null {
  const derivedRunning = countRunningTeamTasks(
    backgroundTasks,
    coordinator.teamName,
  );
  const runningWorkers = Math.max(
    coordinator.runningWorkers,
    derivedRunning,
  );
  const totalWorkers = Math.max(
    coordinator.totalWorkers,
    Object.values(backgroundTasks).filter(task =>
      coordinator.teamName ? task.teamName === coordinator.teamName : Boolean(task.teamName),
    ).length,
  );

  if (!coordinator.teamName && runningWorkers === 0 && totalWorkers === 0) {
    return null;
  }

  const teamLabel = coordinator.teamName ?? "default";
  const status = coordinator.status ? ` ${coordinator.status}` : "";

  return (
    <Text color={getColor("accent")}>
      Coordinator: {teamLabel}{status} | {runningWorkers}/{totalWorkers} workers running
    </Text>
  );
}
