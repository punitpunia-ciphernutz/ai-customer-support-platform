import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.infrastructure.events import event_bus
from app.infrastructure.logging import bind_request_context, configure_logging
from app.modules.automation.application.event_handler import register_automation_handlers
from app.modules.inbox.ws import ensure_listener_started, router as ws_router


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        correlation_id = request.headers.get("X-Correlation-ID", request_id)
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        bind_request_context(request_id, correlation_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def _setup_otel(app: FastAPI) -> None:
    resource = Resource.create({"service.name": "support-platform-backend"})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    # Foundation hook: instrument FastAPI; exporters can be added later.
    FastAPIInstrumentor.instrument_app(app)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    await event_bus.connect()
    register_automation_handlers()
    ensure_listener_started()
    yield
    await event_bus.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Customer Support Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    _setup_otel(app)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router)
    return app


app = create_app()
