from fastapi import APIRouter

from app.modules.agents.router import router as agents_router
from app.modules.ai.api.routes import router as ai_router
from app.modules.attachments.router import router as attachments_router
from app.modules.auth.router import router as auth_router
from app.modules.automation.api.routes import executions_router as automation_executions_router
from app.modules.automation.api.routes import router as automations_router
from app.modules.business_hours.api.routes import router as business_hours_router
from app.modules.channels.router import router as channels_router
from app.modules.channels.webhooks import router as webhooks_router
from app.modules.conversations.router import router as conversations_router
from app.modules.customers.router import router as customers_router
from app.modules.knowledge.api.routes import router as knowledge_router
from app.modules.notifications.api.routes import preferences_router as notification_preferences_router
from app.modules.notifications.api.routes import router as notifications_router
from app.modules.teams.router import router as teams_router
from app.modules.tickets.router import router as tickets_router

api_router = APIRouter()


@api_router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(conversations_router)
api_router.include_router(tickets_router)
api_router.include_router(teams_router)
api_router.include_router(knowledge_router)
api_router.include_router(ai_router)
api_router.include_router(agents_router)
api_router.include_router(channels_router)
api_router.include_router(webhooks_router)
api_router.include_router(attachments_router)
api_router.include_router(automations_router)
api_router.include_router(automation_executions_router)
api_router.include_router(business_hours_router)
api_router.include_router(notifications_router)
api_router.include_router(notification_preferences_router)
