"""Day 6 missed chat delayed Celery tests."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_schedule_missed_chat_check_enqueues_eta_task() -> None:
    with patch("app.workers.tasks.check_missed_chat") as mock_task:
        mock_task.apply_async.return_value = None
        from app.modules.automation.infrastructure.scheduler import schedule_missed_chat_check

        schedule_missed_chat_check("conv-1", "org-1", 5)
        mock_task.apply_async.assert_called_once()
        kwargs = mock_task.apply_async.call_args.kwargs
        assert kwargs["args"] == ["conv-1", "org-1"]
        assert kwargs["eta"] is not None
