from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings


settings = get_settings()


def _frontend_origins() -> list[str]:
    configured_origin = settings.frontend_origin.rstrip("/")
    origins = [configured_origin]
    if settings.app_environment.lower() in {"development", "dev", "test"}:
        origins.extend(
            origin
            for origin in (
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            )
            if origin not in origins
        )
    return origins


app = FastAPI(
    title="Pristine Bio Billing API",
    version="1.0.0",
    environment=settings.app_environment,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
