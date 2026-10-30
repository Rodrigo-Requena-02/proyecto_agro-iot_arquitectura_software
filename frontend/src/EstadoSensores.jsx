// Estado de cada sensor por sector. Cada estado se comunica con símbolo + texto + color.
const CONEXION = {
  CONECTADO: { clase: "on", texto: "● Conectado" },
  DESCONECTADO: { clase: "bad", texto: "⊘ Desconectado" },
};
const SALUD = {
  BUENO: { clase: "on", texto: "✔ Bueno" },
  DANADO: { clase: "bad", texto: "✖ Dañado" },
};
const SIN_VERIFICAR = { clase: "off", texto: "— Sin verificar" };

function hace(seg) {
  if (seg < 60) return `${seg} s`;
  if (seg < 3600) return `${Math.floor(seg / 60)} min`;
  return `${Math.floor(seg / 3600)} h`;
}

export default function EstadoSensores({ sectores }) {
  const todos = sectores.flatMap((s) => s.sensores ?? []);
  const conectados = todos.filter((x) => x.conexion === "CONECTADO").length;
  const desconectados = todos.length - conectados;
  const danados = todos.filter((x) => x.salud === "DANADO").length;

  return (
    <section className="card" id="sensores">
      <h2>Estado de sensores</h2>
      <p className="sensor-resumen" aria-live="polite">
        <span>{todos.length} sensor(es)</span>
        <span className="pill on">● {conectados} conectado(s)</span>
        <span className={`pill ${desconectados ? "bad" : "off"}`}>⊘ {desconectados} desconectado(s)</span>
        <span className={`pill ${danados ? "bad" : "off"}`}>✖ {danados} dañado(s)</span>
      </p>
      <div className="table-wrap">
        <table className="sensores">
          <thead>
            <tr><th>Sector</th><th>Sensor</th><th>Conexión</th><th>Salud</th><th>Último dato</th><th>Observación</th></tr>
          </thead>
          <tbody>
            {sectores.map((s) => {
              const sensores = s.sensores ?? [];
              if (sensores.length === 0) {
                return (
                  <tr key={s.sector_id}>
                    <td>{s.nombre}</td><td colSpan={5} className="muted">Sin sensores registrados todavía.</td>
                  </tr>
                );
              }
              return sensores.map((x) => {
                const conexion = CONEXION[x.conexion] ?? SIN_VERIFICAR;
                // Un sensor desconectado no se puede declarar "bueno": su última lectura ya es vieja.
                const salud = x.salud === "BUENO" && x.conexion !== "CONECTADO" ? SIN_VERIFICAR : (SALUD[x.salud] ?? SIN_VERIFICAR);
                return (
                  <tr key={`${s.sector_id}-${x.sensor_id}`}>
                    <td>{s.nombre}</td>
                    <td>{x.sensor_id}</td>
                    <td><span className={`pill fijo ${conexion.clase}`}>{conexion.texto}</span></td>
                    <td><span className={`pill fijo ${salud.clase}`}>{salud.texto}</span></td>
                    <td>hace {hace(x.segundos_sin_datos)}</td>
                    <td className="obs" title={x.motivo ?? ""}>{x.motivo ?? "—"}</td>
                  </tr>
                );
              });
            })}
          </tbody>
        </table>
      </div>
      <p className="muted leyenda">
        <b>Desconectado:</b> sin datos hace más de 15 s. <b>Dañado:</b> valores congelados (lecturas idénticas) o en el límite del rango físico del sensor.
      </p>
    </section>
  );
}
