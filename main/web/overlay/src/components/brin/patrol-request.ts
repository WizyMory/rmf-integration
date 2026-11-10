import { TaskRequest, TasksApi } from 'api-client';

export interface RobotChoice { fleet: string; robot: string; disabled?: boolean; }

export function makePatrolRequest(places: string[], rounds: number, requester: string): TaskRequest {
  if (!places.length || places.some((p) => !p.trim())) throw new Error('Pilih waypoint tujuan');
  if (!Number.isInteger(rounds) || rounds < 1 || rounds > 100) throw new Error('Putaran harus 1–100');
  const now = Date.now();
  return { category: 'patrol', description: { places, rounds }, requester,
    unix_millis_request_time: now, unix_millis_earliest_start_time: now };
}

export async function submitPatrol(api: TasksApi, request: TaskRequest, robot: RobotChoice | null) {
  const response = robot
    ? await api.postRobotTaskTasksRobotTaskPost({ type: 'robot_task_request',
        fleet: robot.fleet, robot: robot.robot, request })
    : await api.postDispatchTaskTasksDispatchTaskPost({ type: 'dispatch_task_request', request });
  // A rejected RMF request must never appear as successful in the dialog.
  const data: { success?: boolean; errors?: unknown } | undefined = response?.data;
  if (!data || data.success !== true) {
    throw new Error(JSON.stringify(data?.errors || 'RMF belum menerima task'));
  }
  return response.data;
}
