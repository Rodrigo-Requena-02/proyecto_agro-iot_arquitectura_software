"""E2E de roles en navegador real (Chromium): jefe opera y prueba alertas; agrónomo solo lectura; LWW.
Uso:  pip install -r e2e/requirements.txt && playwright install chromium && python e2e/test_ui_roles.py
Requiere:  cd frontend && npm install   (el script levanta la API y Vite solo)."""
import os, sys, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
import requests
from playwright.sync_api import sync_playwright
from _util import API, Entorno, Resultados, RAIZ, token as tok

R = Resultados(); check = R.check
SCR = os.path.join(os.path.dirname(__file__), "capturas"); os.makedirs(SCR, exist_ok=True)

with Entorno(["npx", "vite", "--port", "5173"], "http://localhost:5173"):
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox"])
            pg = b.new_page(viewport={"width": 1280, "height": 1000})
            logs = []
            pg.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: logs.append(f"PAGEERROR {e}"))
            fila = lambda nombre: pg.locator(".ctrl-row", has_text=nombre)

            pg.goto("http://localhost:5173")
            pg.fill("#email", "jefe.a@agro.cl"); pg.fill("#password", "Terreno2026!")
            pg.click("button:has-text('Ingresar')")
            pg.wait_for_selector("text=Reglas de alerta del sistema")

            print("1) Jefe de terreno: puede operar")
            check("ve botones de accion en los 3 actuadores", pg.locator(".ctrl-row button").count() == 3)
            check("ve el formulario 'Ingresar lectura de prueba'", pg.locator("h2:has-text('Ingresar lectura de prueba')").count() == 1)
            check("ve los 4 ejemplos de prueba", pg.locator("button:has-text('Ejemplo:')").count() == 4)
            check("reglas de alerta visibles y de solo lectura (3 filas, sin inputs)",
                  pg.locator("section:has-text('Reglas de alerta del sistema') tbody tr").count() == 3
                  and pg.locator("section:has-text('Reglas de alerta del sistema') input").count() == 0)
            check("umbral de helada mostrado", "≤ 2 °C" in pg.locator("section:has-text('Reglas de alerta del sistema')").inner_text())

            print("2) Riego manual")
            fila("Riego").locator("button").click()
            pg.wait_for_selector(".ctrl-row:has-text('Riego') .pill.on")
            check("Riego ACTIVO (Manual)", "Manual" in fila("Riego").locator("small").inner_text())

            print("3) Lectura de prueba con ejemplo 'Radiación alta'")
            pg.click("button:has-text('Ejemplo: Radiación alta')")
            check("el ejemplo rellena el formulario", pg.input_value("#radiacion_wm2") == "1000" and pg.input_value("#temperatura_c") == "20")
            pg.click("button:has-text('Registrar lectura')")
            pg.wait_for_selector("text=Alerta MEDIA: Radiación alta", timeout=8000)
            check("aparece la alerta generada en el formulario", True)
            pg.wait_for_selector(".ctrl-row:has-text('Ventilación') .pill.on", timeout=8000)
            check("la ventilacion se activa sola (Automatico)", "Automático" in fila("Ventilación").locator("small").inner_text())
            pg.click("button:has-text('Registrar lectura')")  # misma prueba otra vez
            pg.wait_for_selector("text=ya hay una alerta", timeout=8000)
            check("la prueba repetida avisa que la alerta ya esta activa (no duplica)", pg.locator("li:has-text('Radiación alta')").count() == 1)

            print("4) Offline: accion sin conflicto (Nutrientes -> Activar)")
            pg.click("button:has-text('Simular pérdida de conexión')")
            fila("Nutrientes").locator("button").click()
            pg.wait_for_selector(".ctrl-row:has-text('Nutrientes') >> text=Pendiente de sincronizar")
            check("Nutrientes queda pendiente", True)

            print("5) Offline: jefe apaga el riego (t1) y mientras tanto llega una helada mas reciente (t2)")
            fila("Riego").locator("button").click()
            pg.wait_for_selector(".ctrl-row:has-text('Riego') >> text=Pendiente de sincronizar")
            h = tok("jefe.a@agro.cl", "Terreno2026!")   # lo que haria el gateway con el Arduino
            t2 = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
            r = requests.post(API + "/api/v1/telemetria", headers=h, json=dict(sector_id=1, sensor_id="UNO-A01", temperatura_c=1.0,
                              humedad_suelo_pct=60, radiacion_wm2=600, presion_bar=1.0, tomada_en=t2))
            check("helada critica genera alerta nueva", r.status_code == 201 and r.json()["alertas"][0]["regla"] == "HELADA")
            riego = {a["tipo"]: a for a in requests.get(f"{API}/api/v1/sectores/1/actuadores", headers=h).json()}["RIEGO"]
            check("servidor: riego ACTIVO y AUTOMATICO (reafirmado por la helada)", riego["activo"] and riego["origen"] == "AUTOMATICO")

            print("6) Reconectar -> LWW")
            pg.click("button:has-text('Restablecer conexión')")
            pg.wait_for_selector("text=Sincronizado:", timeout=8000)
            msg = pg.locator(".banner.ok", has_text="Sincronizado:").first.inner_text().replace("\n", " ")
            print("   mensaje:", msg)
            check("1 aplicada (nutrientes) y 1 descartada por LWW (riego)", "1 acción(es) de control aplicada(s)" in msg and "1 descartada(s) por LWW" in msg)
            time.sleep(3.5)
            est = {a["tipo"]: a for a in requests.get(f"{API}/api/v1/sectores/1/actuadores", headers=h).json()}
            check("riego sigue ACTIVO (la orden manual antigua perdio)", est["RIEGO"]["activo"] is True and est["RIEGO"]["origen"] == "AUTOMATICO")
            check("nutrientes ACTIVO (accion offline sin conflicto aplicada)", est["NUTRIENTES"]["activo"] is True)
            check("pantalla coincide: Riego ACTIVO Automatico",
                  fila("Riego").locator(".pill").inner_text().strip() == "● ACTIVO" and "Automático" in fila("Riego").locator("small").inner_text())
            pg.screenshot(path=f"{SCR}/ui_roles_jefe.png", full_page=True)

            print("7) Agronomo: solo lectura")
            pg.click("button:has-text('Salir')")
            pg.fill("#email", "agronomo@agro.cl"); pg.fill("#password", "Agro2026!")
            pg.click("button:has-text('Ingresar')")
            pg.wait_for_selector("text=Acceso de solo lectura")
            time.sleep(3.5)
            check("ve 3 sectores x 3 actuadores", pg.locator(".ctrl-row").count() == 9)
            check("NO hay ningun boton Activar/Desactivar", pg.locator(".ctrl-row button").count() == 0)
            check("titulo indica (solo lectura)", pg.locator("h2:has-text('(solo lectura)')").count() == 1)
            check("NO hay formulario de lectura de prueba", pg.locator("text=Ingresar lectura de prueba").count() == 0)
            check("NO hay boton Reconocer", pg.locator("button:has-text('Reconocer')").count() == 0)
            check("NO hay boton de simular conexion", pg.locator("button:has-text('Simular pérdida')").count() == 0)
            check("ve el estado real que dejo el jefe (Riego del Sector A ACTIVO)",
                  pg.locator(".ctrl-sector", has_text="Sector A").locator(".ctrl-row", has_text="Riego").locator(".pill").inner_text().strip() == "● ACTIVO")
            check("ve las reglas de alerta (3 filas)", pg.locator("section:has-text('Reglas de alerta del sistema') tbody tr").count() == 3)
            ag = tok("agronomo@agro.cl", "Agro2026!")
            codes = [requests.put(f"{API}/api/v1/sectores/{s}/actuadores/RIEGO", headers=ag, json={"activo": False}).status_code for s in (1, 2, 3)]
            check("API rechaza (403) que el agronomo accione en cualquier sector", codes == [403, 403, 403], str(codes))
            check("API rechaza (403) que el agronomo ingrese lecturas",
                  requests.post(API + "/api/v1/telemetria", headers=ag, json=dict(sector_id=1, sensor_id="X-001", temperatura_c=10, humedad_suelo_pct=50, radiacion_wm2=1, presion_bar=1)).status_code == 403)
            pg.screenshot(path=f"{SCR}/ui_roles_agronomo.png", full_page=True)
            check("sin errores en consola", not logs, str(logs[:3]))
            b.close()

R.fin()
