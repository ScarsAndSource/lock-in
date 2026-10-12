from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_tasks_service
from app.ratelimit import rate_limit
from app.schemas_tasks import (
    CaptureOut, FocusOut, TaskCaptureRequest, TaskCreateRequest, TaskOut, TaskPatchRequest, TaskSnoozeRequest,
)
from app.security import get_current_user_id
from app.services.tasks_service import TasksService, TaskView

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(rate_limit("api"))])


def _out(v: TaskView) -> TaskOut:
    t = v.task
    return TaskOut(
        id=t.id, title=t.title, notes=t.notes, importance=t.importance, status=t.status, state=v.state,
        due=v.due_local, due_has_time=t.due_has_time, remind=v.remind_local, repeat_days=t.repeat_days,
        snoozed_until=t.snoozed_until, nudge_count=t.nudge_count, last_done_at=t.last_done_at,
        done_count=t.done_count, ai_parsed=t.ai_parsed, created_at=t.created_at,
    )


# Static paths BEFORE the parameterized ones.
@router.post(
    "/capture", response_model=CaptureOut,
    dependencies=[Depends(rate_limit("tasks_capture", limit_setting="rate_limit_capture_per_minute"))],
)
async def capture_tasks(
    body: TaskCaptureRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> CaptureOut:
    """Free text in, structured tasks out. mode=fallback means the AI was unavailable and your words were saved as-is."""
    result = await service.capture(user_id, body.text)
    return CaptureOut(
        mode=result.mode, tasks=[_out(v) for v in result.tasks],
        skipped_duplicates=result.skipped_duplicates, support=result.support,
    )


@router.get("/focus", response_model=FocusOut)
async def focus(
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> FocusOut:
    f = await service.focus(user_id)
    return FocusOut(
        now=[_out(v) for v in f.now], small=[_out(v) for v in f.small],
        later_today=[_out(v) for v in f.later_today], stale=[_out(v) for v in f.stale],
        hidden_now=f.hidden_now, backlog_count=f.backlog_count,
    )


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> TaskOut:
    return _out(await service.create(
        user_id, body.title, body.notes, body.importance, body.due, body.remind, body.repeat_days,
    ))


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status_filter: Literal["open", "done", "dropped"] | None = Query("open", alias="status"),
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> list[TaskOut]:
    return [_out(v) for v in await service.list(user_id, status_filter)]


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: UUID,
    body: TaskPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> TaskOut:
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    return _out(await service.update(user_id, task_id, changes))


@router.post("/{task_id}/done", response_model=TaskOut)
async def complete_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> TaskOut:
    """One-off tasks close. Cadence tasks (repeat_days) come due again that many days from NOW."""
    return _out(await service.complete(user_id, task_id))


@router.post("/{task_id}/snooze", response_model=TaskOut)
async def snooze_task(
    task_id: UUID,
    body: TaskSnoozeRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> TaskOut:
    return _out(await service.snooze(user_id, task_id, body.minutes))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TasksService = Depends(get_tasks_service),
) -> Response:
    await service.delete(user_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
