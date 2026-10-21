import { request, isDemoMode } from './client';

export type ActionKind = 'task' | 'checkin' | 'habit' | 'risk' | 'winddown' | 'study';

export interface ActionResult {
  status: 'done' | 'already' | 'failed';
  message: string;
}

/**
 * Run a notification's action from inside the app (signed in). This is the iOS path: iOS web push has no action
 * buttons, so a tap deep-links to /?a=checkin and the app finishes the job with one request.
 * Android and desktop never need it: their buttons call the API from the service worker.
 */
export async function runInAppAction(
  kind: ActionKind,
  action: string,
  args: Record<string, string> = {}
): Promise<ActionResult> {
  if (isDemoMode()) return { status: 'done', message: 'Done (demo).' };
  return request<ActionResult>('/actions/in-app', { method: 'POST', body: JSON.stringify({ kind, action, args }) });
}
