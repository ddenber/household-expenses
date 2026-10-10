import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .config import get_settings
from .db import engine
from .errors import AppError
from .routers import admin, auth, expenses, ledger, reconciliation, reports

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Household Expense Manager API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
get_settings()

for r in (auth.router, admin.router, ledger.router, expenses.router, reconciliation.router, reports.router):
    app.include_router(r, prefix="/api/v1")


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, **exc.extra}})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation", "message": "Invalid request", "fields": fields}})


@app.exception_handler(DBAPIError)
async def db_error(request: Request, exc: DBAPIError):
    logging.getLogger("hem").error("database error type=%s", type(exc.orig).__name__)
    return JSONResponse(status_code=409, content={"error": {"code": "db_integrity", "message": "Operation rejected by database rules"}})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logging.getLogger("hem").warning("readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
