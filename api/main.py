from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import load_config
from api.database import create_tables, init_db
from api.routers import health, inbound, operator, salesman

logger = logging.getLogger("reviewarmour.api")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    app.state.config = cfg
    init_db(cfg.database_url)
    await create_tables()

    from api.tasks.background import run_background_loop

    bg_task = asyncio.create_task(run_background_loop(cfg))
    logger.info("ReviewArmour API started (background loop active)")
    yield
    bg_task.cancel()
    logger.info("ReviewArmour API shutting down")


app = FastAPI(
    title="ReviewArmour Integration API",
    version="0.1.0",
    lifespan=lifespan,
)

from api.middleware.sla_tracker import SLATrackerMiddleware
from api.middleware.webhook_auth import WebhookAuthMiddleware

app.add_middleware(SLATrackerMiddleware)
app.add_middleware(WebhookAuthMiddleware)

app.include_router(health.router)
app.include_router(inbound.router, prefix="/api/inbound", tags=["inbound"])
app.include_router(salesman.router, prefix="/api/salesman", tags=["salesman"])
app.include_router(operator.router, prefix="/api/operator", tags=["operator"])
