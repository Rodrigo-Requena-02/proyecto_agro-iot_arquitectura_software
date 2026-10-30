"""E2E de la PWA sobre el build de producción: manifiesto con íconos, Service Worker activo y carga sin conexión.
Uso:  python e2e/test_pwa.py   (hace `npm run build` y sirve con `vite preview`)."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
import requests
from playwright.sync_api import sync_playwright
from _util import Entorno, Resultados, RAIZ

R = Resultados(); check = R.check
subprocess.run(["npm", "run", "build"], cwd=f"{RAIZ}/frontend", check=True, stdout=subprocess.DEVNULL)
URL = "http://localhost:4173"

try:
    with Entorno(["npx", "vite", "preview", "--port", "4173"], URL):
        m = requests.get(URL + "/manifest.webmanifest").json()
        iconos = m.get("icons", [])
        check("manifiesto con íconos 192 y 512", {"192x192", "512x512"} <= {i["sizes"] for i in iconos})
        check("manifiesto con ícono maskable", any(i.get("purpose") == "maskable" for i in iconos))
        check("los íconos existen y son PNG", all(requests.get(URL + i["src"]).headers.get("content-type", "").startswith("image/png") for i in iconos))
        check("display standalone y start_url", m.get("display") == "standalone" and m.get("start_url") == "/")

        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox"])
            ctx = b.new_context()
            pg = ctx.new_page()
            pg.goto(URL)
            pg.wait_for_selector("text=Inicie sesión")
            pg.evaluate("navigator.serviceWorker.ready")
            check("Service Worker activo", pg.evaluate("navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))"))
            pg.reload()  # la segunda carga ya queda controlada por el SW y llena el caché
            pg.wait_for_selector("text=Inicie sesión")
            ctx.set_offline(True)
            pg.reload()
            pg.wait_for_selector("text=Inicie sesión", timeout=8000)
            check("la app carga SIN conexión (shell cacheado por el Service Worker)", True)
            b.close()
except Exception as e:
    check("ejecución sin errores", False, repr(e))
R.fin()
