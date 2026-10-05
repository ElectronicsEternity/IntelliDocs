import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.billing_routes import router as billing_router
from app.config import settings
from app.services.retention import retention_worker


@asynccontextmanager
async def lifespan(application: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(retention_worker(stop)) if settings.RETENTION_CLEANUP_ENABLED else None
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task


def create_app() -> FastAPI:
    application = FastAPI(title="IntelliDocs API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(router)
    application.include_router(billing_router)
    return application


app = create_app()
