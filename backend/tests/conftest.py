import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, crear_engine, get_db
from app.main import app
from app.seed import seed


@pytest.fixture()
def client():
    # Por defecto: SQLite en memoria aislada por test (no toca agro_iot.db).
    # Con TEST_DATABASE_URL=postgresql+psycopg2://... la MISMA suite corre contra PostgreSQL
    # (tablas recreadas en cada test).
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = crear_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        seed(db)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    # Sin "with": no se ejecuta lifespan (que usaría la BD real)
    yield TestClient(app)
    app.dependency_overrides.clear()
    if url:
        engine.dispose()


def login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture()
def agronomo(client):
    t = login(client, "agronomo@agro.cl", "Agro2026!").json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture()
def jefe_a(client):
    t = login(client, "jefe.a@agro.cl", "Terreno2026!").json()["access_token"]
    return {"Authorization": f"Bearer {t}"}
