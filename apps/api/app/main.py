from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine
from app.routes.alert_channels import router as alert_channels_router
from app.routes.checks import router as checks_router
from app.routes.monitors import router as monitors_router
from app.routes.projects import router as projects_router
from app.routes.auth import router as auth_router

app = FastAPI(
    title=settings.app_name,
    description="Website and API uptime monitoring service",
    version="0.1.0",
)

# Register API routers
app.include_router(projects_router)
app.include_router(monitors_router)
app.include_router(checks_router)
app.include_router(alert_channels_router)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Website & API Uptime Monitor API",
        "docs": "/docs",
    }


@app.get("/health/live", tags=["Health"])
def health_live():
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
def health_ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ready",
            "database": "connected",
        }

    except SQLAlchemyError:
        return {
            "status": "not_ready",
            "database": "unavailable",
        }
