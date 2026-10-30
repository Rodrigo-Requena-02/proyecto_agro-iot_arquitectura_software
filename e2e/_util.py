"""Utilidades comunes de las pruebas de navegador (E2E): levantan la API real y el frontend."""
import os, subprocess, sys, tempfile, time
import requests

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API = "http://localhost:8000"


class Entorno:
    """Levanta backend (SQLite temporal, no toca agro_iot.db) y el servidor del frontend indicado."""

    def __init__(self, front_cmd, front_url):
        self.front_cmd, self.front_url = front_cmd, front_url
        self.tmp = tempfile.mkdtemp(prefix="agro_e2e_")
        self.procs = []

    def __enter__(self):
        env = dict(os.environ, DATABASE_URL=f"sqlite:///{self.tmp}/e2e.db")
        self.procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"],
                          cwd=f"{RAIZ}/backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        self.procs.append(subprocess.Popen(self.front_cmd, cwd=f"{RAIZ}/frontend",
                          stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        for _ in range(120):
            try:
                if requests.get(API + "/health", timeout=1).ok and requests.get(self.front_url, timeout=1).ok:
                    return self
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError("No arrancaron el backend o el frontend")

    def __exit__(self, *a):
        for p in self.procs:
            p.terminate()
        time.sleep(1)
        for p in self.procs:
            p.kill()


def token(email, password):
    r = requests.post(API + "/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


class Resultados:
    def __init__(self): self.res = {}
    def check(self, nombre, cond, extra=""):
        self.res[nombre] = bool(cond)
        print(("  OK   " if cond else "  FALLA"), nombre, extra)
    def fin(self):
        ok = all(self.res.values())
        print("\nRESULTADO:", "OK" if ok else "FALLO", f"({sum(self.res.values())}/{len(self.res)})")
        sys.exit(0 if ok else 1)
