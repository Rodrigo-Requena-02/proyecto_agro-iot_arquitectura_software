import { useState } from "react";
import EstadoSensores from "./EstadoSensores.jsx";
import Notificaciones from "./Notificaciones.jsx";
import { ETIQUETA, ORDEN_ACTUADORES, useDashboardViewModel, utc } from "./viewmodels.js";

const ROL_LABEL = { AGRONOMO: "Ingeniero Agrónomo", JEFE_TERRENO: "Jefe de Terreno" };
// Severidad: color + ícono + texto (accesible para daltonismo, según análisis de la Evaluación 1)
const SEV = { CRITICA: { icon: "🔴", label: "CRÍTICA" }, MEDIA: { icon: "🟠", label: "MEDIA" } };

const REGLA = { HELADA: "helada", ESTRES_HIDRICO: "estrés hídrico", RADIACION_ALTA: "radiación alta" };

// Ejemplos para probar las alertas con un clic (el jefe igual puede escribir sus propios valores)
const EJEMPLOS = {
  "Normal": { temperatura_c: "18", humedad_suelo_pct: "60", radiacion_wm2: "600", presion_bar: "1.013" },
  "Helada": { temperatura_c: "1.5", humedad_suelo_pct: "60", radiacion_wm2: "600", presion_bar: "1.013" },
  "Sequía": { temperatura_c: "18", humedad_suelo_pct: "15", radiacion_wm2: "600", presion_bar: "1.013" },
  "Radiación alta": { temperatura_c: "20", humedad_suelo_pct: "60", radiacion_wm2: "1000", presion_bar: "1.013" },
};

const RANGOS = {
  temperatura_c: [-40, 60, "Temperatura (°C)"],
  humedad_suelo_pct: [0, 100, "Humedad suelo (%)"],
  radiacion_wm2: [0, 1500, "Radiación (W/m²)"],
  presion_bar: [0, 10, "Presión (bar)"],
};

function LecturaForm({ sectores, user, onSubmit }) {
  const sectorInicial = user.sector_id ?? sectores[0]?.sector_id ?? 1;
  const [f, setF] = useState({ sector_id: sectorInicial, sensor_id: "PRUEBA-01", temperatura_c: "", humedad_suelo_pct: "", radiacion_wm2: "", presion_bar: "" });
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const v = {};
    if (!/^[A-Za-z0-9_-]{3,40}$/.test(f.sensor_id)) v.sensor_id = "3-40 caracteres: letras, números, _ o -";
    for (const [k, [min, max, label]] of Object.entries(RANGOS)) {
      const n = Number(f[k]);
      if (f[k] === "" || Number.isNaN(n)) v[k] = `${label}: ingrese un número`;
      else if (n < min || n > max) v[k] = `${label}: debe estar entre ${min} y ${max}`;
    }
    setErrors(v);
    if (Object.keys(v).length) return;

    setBusy(true);
    const payload = { ...f, sector_id: Number(f.sector_id) };
    for (const k of Object.keys(RANGOS)) payload[k] = Number(f[k]);
    const r = await onSubmit(payload);
    setBusy(false);
    setResult(r);
    // Errores de validación devueltos por el servidor, por campo
    if (r.details) setErrors(Object.fromEntries(r.details.map((d) => [d.campo, d.motivo])));
  };

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2>Ingresar lectura de prueba</h2>
      <p className="muted">
        Simula una lectura de sensor para probar las alertas. Si ya hay una alerta activa del mismo tipo,
        reconózcala antes de repetir la prueba.
      </p>
      <div className="presets" role="group" aria-label="Ejemplos de prueba">
        {Object.entries(EJEMPLOS).map(([nombre, valores]) => (
          <button type="button" key={nombre} className="btn" onClick={() => { setF({ ...f, ...valores }); setErrors({}); }}>
            Ejemplo: {nombre}
          </button>
        ))}
      </div>
      <div className="grid2">
        <div>
          <label htmlFor="sector">Sector</label>
          <select id="sector" value={f.sector_id} onChange={set("sector_id")} disabled={user.rol === "JEFE_TERRENO"}>
            {sectores.map((s) => <option key={s.sector_id} value={s.sector_id}>{s.nombre}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="sensor">ID del sensor</label>
          <input id="sensor" value={f.sensor_id} onChange={set("sensor_id")} />
          {errors.sensor_id && <small className="field-error">{errors.sensor_id}</small>}
        </div>
        {Object.entries(RANGOS).map(([k, [, , label]]) => (
          <div key={k}>
            <label htmlFor={k}>{label}</label>
            <input id={k} inputMode="decimal" value={f[k]} onChange={set(k)} />
            {errors[k] && <small className="field-error">{errors[k]}</small>}
          </div>
        ))}
      </div>
      <button className="btn primary big" disabled={busy}>{busy ? "Enviando…" : "Registrar lectura"}</button>

      {result && (
        <div className={`banner ${result.ok ? "ok" : "error"}`} role="status">
          {result.ok ? "✅" : "⛔"} {result.mensaje}
          {result.alertas?.map((a) => (
            <div key={a.id}>{SEV[a.severidad]?.icon} Alerta {SEV[a.severidad]?.label}: {a.mensaje}</div>
          ))}
          {result.repetidas?.map((a) => (
            <div key={a.id}>
              ℹ️ Se cumple la condición de {REGLA[a.regla] ?? a.regla}, pero ya hay una alerta {SEV[a.severidad]?.label} activa:
              reconózcala para poder generar otra.
            </div>
          ))}
        </div>
      )}
    </form>
  );
}

const ICONO = { RIEGO: "💧", VENTILACION: "🌀", NUTRIENTES: "🧪" };

function detalleActuador(a) {
  if (a.pendiente) return "⏳ Pendiente de sincronizar";
  const hora = a.actualizado_en ? utc(a.actualizado_en).toLocaleTimeString() : "";
  if (a.origen === "MANUAL") return `Manual · ${a.actualizado_por ?? "—"} · ${hora}`;
  if (a.origen === "AUTOMATICO") return `Automático (${a.detalle ?? "alerta"}) · ${hora}`;
  return "Sin acciones registradas";
}

function ControlOperativo({ sectores, vm, soloLectura }) {
  const ordenados = (acts) => [...acts].sort((a, b) => ORDEN_ACTUADORES.indexOf(a.tipo) - ORDEN_ACTUADORES.indexOf(b.tipo));
  return (
    <section className="card">
      <h2>Control operativo por sector{soloLectura ? " (solo lectura)" : ""}</h2>
      {/* Espacio SIEMPRE reservado: el aviso aparece sin empujar los botones hacia abajo */}
      <div className="ctrl-msg" role="status" aria-live="polite">
        {vm.ctrlMsg && (
          <div className={`banner ${vm.ctrlMsg.nivel}`}>
            {vm.ctrlMsg.nivel === "ok" ? "✅" : vm.ctrlMsg.nivel === "warn" ? "⚠️" : "⛔"} {vm.ctrlMsg.texto}
          </div>
        )}
      </div>
      <div className="ctrl-grid">
        {sectores.map((s) => (
          <div key={s.sector_id} className="ctrl-sector">
            <h3>{s.nombre}</h3>
            {ordenados(s.actuadores).map((a) => (
              <div className={`ctrl-row ${soloLectura ? "solo-lectura" : ""}`} key={a.tipo}>
                <div className="ctrl-info">
                  <strong>{ICONO[a.tipo]} {ETIQUETA[a.tipo]}</strong>
                  <small className="muted ctrl-detalle" title={detalleActuador(a)}>{detalleActuador(a)}</small>
                </div>
                <div className="ctrl-acciones">
                  {/* Estado con texto + símbolo + color (no depende solo del color) */}
                  <span className={`pill fijo ${a.activo ? "on" : "off"}`}>{a.activo ? "● ACTIVO" : "○ INACTIVO"}</span>
                  {!soloLectura && (
                    <button className={`btn btn-ctrl ${a.activo ? "" : "primary"}`} aria-pressed={a.activo}
                            onClick={() => vm.cambiarActuador(s.sector_id, a.tipo, !a.activo)}>
                      {a.activo ? "Desactivar" : "Activar"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function ReglasAlerta({ umbrales }) {
  if (!umbrales.length) return null;
  return (
    <section className="card">
      <h2>Reglas de alerta del sistema</h2>
      <p className="muted">Solo lectura: son datos generados por el sistema y nadie puede editarlos.</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Variable</th><th>🔴 Crítica</th><th>🟠 Media</th><th>Respuesta automática</th></tr></thead>
          <tbody>
            {umbrales.map((u) => (
              <tr key={u.regla}>
                <td>{u.variable}</td><td>{u.condicion_critica ?? "—"}</td><td>{u.condicion_media ?? "—"}</td><td>{u.respuesta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Dashboard({ user, onLogout }) {
  const vm = useDashboardViewModel(onLogout, user);
  const { data, error, offline, pendientes } = vm;
  const soloLectura = user.rol === "AGRONOMO"; // el agrónomo consulta; el jefe de terreno opera
  const noti = vm.notificaciones;
  const alertasSinReconocer = data ? data.sectores.reduce((n, s) => n + s.alertas_activas, 0) : 0;

  return (
    <div className="app">
      <Notificaciones avisos={noti.avisos} onCerrar={noti.cerrar} onCerrarTodos={noti.cerrarTodos}
                      onReconocer={vm.reconocer} puedeReconocer={!soloLectura && !offline} />
      <header className="topbar">
        <div>
          <strong>🌱 AgroIoT</strong>
          <span className="badge">{ROL_LABEL[user.rol]}</span>
        </div>
        <div className="topbar-actions">
          <a className={`campana ${alertasSinReconocer ? "activa" : ""}`} href="#alertas"
             aria-label={`${alertasSinReconocer} alerta(s) sin reconocer. Ir a alertas recientes`}>
            🔔 <span className="campana-n">{alertasSinReconocer}</span>
          </a>
          <span className="muted">{user.nombre}</span>
          <button className="btn" onClick={onLogout}>Salir</button>
        </div>
      </header>

      <div className="toolbar">
        <button className="btn btn-fijo-sm" onClick={vm.cargar}>↻ Actualizar</button>
        <button className={`btn btn-fijo-lg ${vm.auto ? "primary" : ""}`} onClick={() => vm.setAuto(!vm.auto)} aria-pressed={vm.auto}>
          {vm.auto ? "⏱ Auto-actualizar: ACTIVO (3 s)" : "⏱ Auto-actualizar: pausado"}
        </button>
        {!soloLectura && (
          <button className={`btn btn-fijo-lg ${offline ? "warn" : ""}`} onClick={vm.toggleOffline}>
            {offline ? "📶 Restablecer conexión" : "📴 Simular pérdida de conexión"}
          </button>
        )}
        {noti.permiso === "default" && (
          <button className="btn" onClick={noti.pedirPermiso}>🔔 Activar avisos del dispositivo</button>
        )}
        {!soloLectura && pendientes > 0 && !offline && <button className="btn" onClick={vm.sincronizar}>Sincronizar ({pendientes})</button>}
      </div>

      {soloLectura && (
        <div className="banner info" role="note">
          👁 Acceso de solo lectura: ve todos los sectores. Accionar actuadores e ingresar lecturas es tarea del jefe de terreno.
        </div>
      )}
      {/* Avisos de estado (sin conexión, error, sincronización): flotan abajo para no empujar el contenido ni los botones */}
      <div className="flotantes">
        {(offline || error === "offline") && (
          <div className="banner warn" role="status">
            📴 MODO OFFLINE — se muestran los datos de la última sincronización. {pendientes} operación(es) pendiente(s) de sincronizar.
          </div>
        )}
        {error && error !== "offline" && <div className="banner error" role="alert">⛔ {error}</div>}
        {vm.syncMsg && <div className="banner ok">🔄 {vm.syncMsg}</div>}
      </div>

      <section className="sectors">
        {data?.sectores.map((s) => (
          <article className="card" key={s.sector_id}>
            <h3>{s.nombre}</h3>
            {s.ultima_lectura ? (
              <>
                <dl className="metrics">
                  <div><dt>Temperatura</dt><dd>{s.ultima_lectura.temperatura_c.toFixed(1)} °C</dd></div>
                  <div><dt>Humedad suelo</dt><dd>{s.ultima_lectura.humedad_suelo_pct.toFixed(0)} %</dd></div>
                  <div><dt>Radiación</dt><dd>{s.ultima_lectura.radiacion_wm2.toFixed(0)} W/m²</dd></div>
                  <div><dt>Presión</dt><dd>{s.ultima_lectura.presion_bar.toFixed(1)} bar</dd></div>
                </dl>
                <small className="muted">Última lectura: {utc(s.ultima_lectura.tomada_en).toLocaleString()}</small>
              </>
            ) : <p className="muted">Sin lecturas todavía.</p>}
            <p>{s.alertas_activas > 0 ? `⚠️ ${s.alertas_activas} alerta(s) activa(s)` : "✅ Sin alertas activas"}</p>
          </article>
        ))}
      </section>

      {data && <ControlOperativo sectores={data.sectores} vm={vm} soloLectura={soloLectura} />}

      {data && <EstadoSensores sectores={data.sectores} />}

      <section className="card">
        <div className="hist-head">
          <h2>Últimas lecturas (sensores / Arduino)</h2>
          {user.rol === "AGRONOMO" && data && (
            <select aria-label="Sector del historial" value={vm.sectorHist ?? data.sectores[0]?.sector_id ?? ""}
                    onChange={(e) => vm.setSectorHist(Number(e.target.value))}>
              {data.sectores.map((s) => <option key={s.sector_id} value={s.sector_id}>{s.nombre}</option>)}
            </select>
          )}
        </div>
        {vm.historial.length === 0 ? <p className="muted">Aún no llegan lecturas a este sector.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Hora</th><th>Sensor</th><th>Temp (°C)</th><th>Humedad (%)</th><th>Radiación (W/m²)</th><th>Presión (bar)</th></tr></thead>
              <tbody>
                {vm.historial.map((l) => (
                  <tr key={l.id}>
                    <td>{utc(l.tomada_en).toLocaleTimeString()}</td><td>{l.sensor_id}</td>
                    <td>{l.temperatura_c.toFixed(1)}</td><td>{l.humedad_suelo_pct.toFixed(1)}</td>
                    <td>{l.radiacion_wm2.toFixed(0)}</td><td>{l.presion_bar.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {!soloLectura && data && <LecturaForm key={user.id} sectores={data.sectores} user={user} onSubmit={vm.registrar} />}

      <ReglasAlerta umbrales={vm.umbrales} />

      <section className="card" id="alertas">
        <h2>Alertas recientes</h2>
        {data?.alertas_recientes.length === 0 && <p className="muted">No hay alertas.</p>}
        <ul className="alerts">
          {data?.alertas_recientes.map((a) => (
            <li key={a.id} className={a.reconocida ? "done" : ""}>
              <span>{SEV[a.severidad]?.icon} <b>{SEV[a.severidad]?.label}</b> · {a.mensaje}
                <small className="muted"> — {utc(a.creada_en).toLocaleString()}</small></span>
              {a.reconocida ? <small>Reconocida ✔</small>
                : soloLectura ? <small className="muted">Activa</small>
                : <button className="btn" onClick={() => vm.reconocer(a.id)} disabled={offline}>Reconocer</button>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
