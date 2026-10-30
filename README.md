# AgroIoT — Módulo funcional (Evaluación Sumativa 2)

Flujo vertical: **UI (React PWA) → API REST (FastAPI) → servicios → repositorios → BD**, con login por roles, validaciones, alertas y sincronización offline.

```
agro-iot/
├── backend/          FastAPI (Python)   routers -> services -> repositories (+ strategies)
├── frontend/         React + Vite       Login, Dashboard, cola offline (IndexedDB)
├── docs/             Documentacion_Evaluacion2.md  y  diagramas/*.puml (+ .png)
├── e2e/                 Pruebas de navegador real (Playwright): roles/LWW y PWA sin conexión
└── docker-compose.yml   PostgreSQL 16 (integrado, no se usa por defecto)
```

## Requisitos
Python ≥ 3.11 y Node ≥ 18. Versiones con las que se probó: Python 3.13, Node 22.

## 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Al iniciar crea las tablas y los datos de demostración (SQLite `agro_iot.db`). Swagger: http://localhost:8000/docs

| Usuario | Contraseña | Rol |
|---|---|---|
| agronomo@agro.cl | Agro2026! | Agrónomo (**solo lectura**, todos los sectores) |
| jefe.a@agro.cl | Terreno2026! | Jefe de Terreno (opera solo el Sector A: acciona actuadores, ingresa lecturas de prueba, reconoce alertas) |
| jefe.b@agro.cl | Terreno2026! | Jefe de Terreno (solo Sector B) |
| jefe.c@agro.cl | Terreno2026! | Jefe de Terreno (solo Sector C) |

## 2. Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (el proxy envía /api al backend en :8000)
```

## 3. Pruebas automatizadas
```bash
cd backend
python -m pytest -q  # 65 pruebas (49 + 16 de estado de sensores), usan SQLite en memoria (ver sección PostgreSQL para correrlas sobre PostgreSQL)
```

## 4. Guion de demostración (video 4–12 min)
1. Entrar como **jefe.a** → ver solo el Sector A. Probar una clave incorrecta (mensaje de error) y un correo inválido (validación).
2. Registrar lectura con temperatura **1.5** y humedad **28** → aparecen alertas *HELADA crítica* y *ESTRÉS HÍDRICO* (patrón Strategy). Probar un valor fuera de rango (humedad 140).
3. Pulsar **Simular pérdida de conexión** → aparece el banner *MODO OFFLINE*; registrar 2–3 lecturas → quedan "pendientes".
4. Pulsar **Restablecer conexión** → se sincroniza el lote y se informa cuántas lecturas son nuevas/duplicadas.
5. Cerrar sesión y entrar como **agronomo** → ve los 3 sectores, alertas y actuadores de todos, **sin ningún botón de acción** (solo lectura).
6. **Notificaciones y sensores:** con el gateway en marcha escribir `hB` → aparece un aviso emergente *CRÍTICA* (y la campana 🔔 sube). Luego `xB` (sensor desconectado) y `dC` (sensor dañado) → en ~15 s y ~10 s el panel *Estado de sensores* muestra *Desconectado* / *Dañado* con su aviso. `n` repara todo.
7. Mostrar `python -m pytest -q` y, en el código, `repositories/interfaces.py`, `strategies/alertas.py` y `services/telemetria_service.py`.

## 5. Arduino por cable USB (3 sectores A, B y C con datos distintos)
```
Arduino UNO --USB serial--> gateway/gateway.py (SQLite local) --HTTP + JWT--> API --> BD --> Dashboard
```
Un solo Arduino simula **tres sectores**, cada uno con su propio perfil y evolución aleatoria (temperatura, humedad de suelo, radiación y presión):

| Sector | Sensor | Perfil normal |
|---|---|---|
| A · invernadero | `UNO-A01` | ~22 °C, ~65 % humedad, ~450 W/m², ~1,0 bar |
| B · hidropónico | `UNO-B01` | ~24 °C, ~80 % humedad, ~250 W/m², ~2,5 bar (presión de bomba) |
| C · frutal | `UNO-C01` | ~14 °C, ~42 % humedad, ~750 W/m², ~1,8 bar |

Cada línea trae el campo `"s"` con el sector. El gateway enruta la lectura y **se autentica con el jefe de ESE sector** (`jefe.a/b/c@agro.cl`), porque un jefe solo puede escribir en su sector (RN1).
1. Abrir `arduino/simulador_sensores/simulador_sensores.ino` en el Arduino IDE, elegir *Arduino UNO* y el puerto, **Subir**. No necesita sensores conectados. **Cerrar el Monitor Serie** antes del paso 3 (solo un programa puede usar el puerto).
2. Con el backend corriendo (paso 1), en otra terminal:
   ```bash
   cd gateway
   pip install -r requirements.txt
   python gateway.py --listar-puertos        # ver el puerto: COM3 (Windows), /dev/ttyACM0 (Linux), /dev/cu.usbmodem* (Mac)
   ```
3. ```bash
   python gateway.py --puerto COM3           # reemplace por su puerto
   ```
4. Abrir el dashboard como **agronomo@agro.cl** (ve los 3 sectores) o como cada jefe (solo el suyo): las tarjetas y la tabla *Últimas lecturas* se actualizan solas cada 3 s. Cada sector muestra valores distintos.
5. En la terminal del gateway escriba un escenario y Enter: `h` helada, `s` sequía, `r` radiación alta, `n` normal. Sin letra de sector aplica a **todos**; con letra, solo a ese sector: `hB` = helada solo en el Sector B, `rC` = radiación alta solo en el C. La alerta y la acción automática (p. ej. riego) aparecen solo en el sector afectado, en ~15–25 s.
6. Prueba de resiliencia: detener el backend (Ctrl+C) unos segundos → el gateway sigue leyendo y guarda en `edge_cache.sqlite`; al volver a levantarlo, reenvía todo solo.

Sin Arduino a mano: `python gateway.py --simular` genera los mismos datos por software (también 3 sectores).
Cuenta única (opcional): `--email jefe.a@agro.cl` fuerza una sola cuenta para todos los sectores; las lecturas de otros sectores serán rechazadas por la API.
Pruebas del gateway: `cd gateway && python -m pytest -q` (19 pruebas).
Sin placa: `arduino/prueba_en_pc/` compila y ejecuta el mismo sketch en el PC (ver su README).

## 6. Control operativo por sector (riego, ventilación, dosificador de nutrientes)
Panel **"Control operativo por sector"** en el dashboard (Evaluación 1, pantalla 2 "Vista del jefe de terreno").
- **Manual:** botón Activar/Desactivar por actuador. **Solo el jefe de terreno acciona, y solo su sector.** El agrónomo ve el estado de todos los sectores en solo lectura (el servidor responde 403 si lo intenta). Se registra quién y cuándo.
- **Automático:** al crearse una alerta nueva, la regla (Strategy) declara una respuesta y el sistema la aplica: helada crítica / humedad baja → **Riego**; radiación alta → **Ventilación**. El dosificador de nutrientes es solo manual.
- **LWW (Last Write Wins):** cada acción lleva el instante en que se hizo. Si llega una acción más antigua que la última registrada (ej. el jefe apagó el riego sin conexión y mientras tanto el sistema lo activó por una helada más reciente), se **descarta** y se avisa. Una lectura antigua tampoco pisa una decisión humana más reciente.
- **Sin conexión:** la acción se guarda en el dispositivo (IndexedDB), se muestra como "⏳ Pendiente" y se envía al reconectar, en orden cronológico.

Prueba rápida: (1) Activar *Riego* → queda "● ACTIVO · Manual · su nombre". (2) Con el gateway en marcha, escribir `r` (radiación alta) → *Ventilación* se activa sola ("Automático"). (3) *Simular pérdida de conexión* → activar *Dosificador* → "Pendiente". (4) Con la conexión caída, apagar *Riego* y, mientras tanto, enviar una lectura de helada más reciente (gateway: `h`). (5) *Restablecer conexión* → el aviso dice "1 descartada por LWW" y el riego sigue ACTIVO (Automático).

**Parámetros de alerta:** son datos generados por el sistema (helada ≤2 °C crítica / ≤4 °C media; humedad ≤20 % crítica / ≤30 % media; radiación ≥900 W/m²). Se muestran en la tabla *Reglas de alerta del sistema* y **no son editables por nadie**.

**Notificaciones:** las alertas nuevas y los cambios de estado de un sensor aparecen como avisos emergentes (esquina superior derecha, sin mover la página). Las críticas quedan fijas hasta cerrarlas; el jefe puede *Reconocer* desde el mismo aviso. Si el usuario acepta *Activar avisos del dispositivo*, también llegan como notificación del sistema cuando la pestaña está en segundo plano.

**Estado de sensores:** panel con *Conectado / Desconectado* (sin datos hace más de 15 s) y *Bueno / Dañado* (valores congelados —5 lecturas idénticas— o en el límite del rango físico). Se calcula a partir de la telemetría (`services/estado_sensores.py`), sin tablas nuevas. Para probarlo, el gateway acepta `x` (desconectar), `d` (dañar) y `n` (reparar), opcionalmente con letra de sector (`xB`, `dC`).

**Control operativo:** botones de tamaño fijo (160×60 px) y filas de alto constante; los avisos usan un espacio reservado o flotan, de modo que nada se desplaza al pulsar.

**Lecturas de prueba:** el jefe puede ingresar una lectura manual (botones *Ejemplo: Normal / Helada / Sequía / Radiación alta*) para verificar las alertas y la respuesta automática. Repetir la misma condición avisa que ya hay una alerta activa (no se duplica).

> El gateway debe usar una cuenta de **jefe de terreno** (por defecto `jefe.a@agro.cl`); el agrónomo no puede registrar lecturas.

API: `GET /api/v1/sectores/{id}/actuadores` y `PUT /api/v1/sectores/{id}/actuadores/{RIEGO|VENTILACION|NUTRIENTES}` con `{"activo": true, "accion_en": "<ISO-8601>"}` (ver http://localhost:8000/docs).

## Pruebas de navegador real (E2E, Playwright) y PWA
```bash
cd frontend && npm install && cd ..
pip install -r e2e/requirements.txt && playwright install chromium
python e2e/test_ui_roles.py   # 28 comprobaciones: jefe opera, agrónomo solo lectura, lecturas de prueba, LWW
python e2e/test_pwa.py        # 6 comprobaciones: manifiesto con íconos, Service Worker, carga sin conexión
```
Levantan solos la API (con una SQLite temporal, sin tocar `agro_iot.db`) y el frontend. La **PWA** se puede instalar desde el navegador usando el build de producción (`npm run build && npm run preview`, http://localhost:4173); en `npm run dev` el Service Worker no se activa a propósito.

## Bases de datos: SQLite (activa) y PostgreSQL (integrada, sin uso por ahora)
| Motor | Uso | Cómo se elige |
|---|---|---|
| **SQLite** | Demo, pruebas y caché del Gateway (`edge_cache.sqlite`). **Es el motor por defecto.** | No requiere nada |
| **PostgreSQL 16** | Destino en la nube. Integrado y verificado, pero **no se usa hasta definir `DATABASE_URL`** | Variable de entorno o archivo `backend/.env` (ver `backend/.env.example`) |

El motor se elige solo por configuración (`backend/app/core/database.py`); el resto del código no cambia.

Para probar PostgreSQL (opcional):
```bash
docker compose up -d                                   # PostgreSQL 16 en localhost:5432
cd backend
export DATABASE_URL=postgresql+psycopg2://agro:agro@localhost:5432/agro   # PowerShell: $env:DATABASE_URL="..."
uvicorn app.main:app --port 8000                       # crea las tablas y los datos de demo en PostgreSQL
# Las mismas pruebas, sobre PostgreSQL:
TEST_DATABASE_URL=postgresql://agro:agro@localhost:5432/agro python -m pytest -q   # PowerShell: $env:TEST_DATABASE_URL="..."
```
Para volver a SQLite basta con quitar la variable `DATABASE_URL`.

> Verificado: las 49 pruebas del backend pasan sobre PostgreSQL 16 y la API real persiste datos ahí. El archivo `docker-compose.yml` como tal no se ejecutó en el desarrollo (se usó un PostgreSQL 16 instalado localmente).

## Diagramas
`docs/diagramas/*.puml` se renderizan con PlantUML. Para exportar en SVG (vectorial): `java -jar plantuml.jar -tsvg docs/diagramas/*.puml`
