import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.files import router as files_router
from .routes.files import init_db
from .settings import get_settings
from .storage import get_minio_client, ensure_bucket


def create_app() -> FastAPI:
    app = FastAPI(title="PCD Backend")

    # Allow CORS for local dev and via nginx proxy in compose
    origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup():
        settings = get_settings()
        init_db(settings)
        client = get_minio_client(settings)
        ensure_bucket(client, settings.minio_bucket)

    app.include_router(files_router, prefix="/api")
    return app


app = create_app()


