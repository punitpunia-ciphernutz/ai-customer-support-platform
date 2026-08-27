from fastapi import APIRouter

from app.modules.ai.api.routes import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.conversations.router import router as conversations_router
from app.modules.customers.router import router as customers_router
from app.modules.knowledge.api.routes import router as knowledge_router
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
