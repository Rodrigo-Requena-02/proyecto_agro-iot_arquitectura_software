"""Punto de entrada. Ejecutar:  uvicorn app.main:app --reload --port 8000
Documentación interactiva (Swagger): http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.errors import register_error_handlers
from app.routers import auth, control, telemetria
from app.seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Plataforma IoT Agrícola - API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(telemetria.router)
app.include_router(control.router)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}
