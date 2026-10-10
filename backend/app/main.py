from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.core.csrf import security_middleware
from app.core.observability import configure_logging, request_logging_middleware
from app.db.session import engine


settings = get_settings()
configure_logging()


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
app.middleware("http")(security_middleware)
app.middleware("http")(request_logging_middleware)


@app.exception_handler(RequestValidationError)
async def safe_validation_errors(request, exc):
    # Do not echo passwords, setup/invitation tokens or authenticator codes.
    return JSONResponse(status_code=422, content={"detail":[{"type":e["type"],"loc":e["loc"],"msg":e["msg"]} for e in exc.errors()]})

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


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    """Readiness is database-backed; liveness remains independent at /health."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        from fastapi import HTTPException
        from app.core.observability import capture_exception

        capture_exception(exc)
        raise HTTPException(status_code=503, detail="Billing service dependencies are not ready") from None
    return {"status": "ready"}


app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
