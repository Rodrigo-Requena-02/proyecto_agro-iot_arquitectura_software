// ViewModels (patrón MVVM definido en la Evaluación 1): hooks que concentran el estado y
// las operaciones; los componentes (View) solo pintan y delegan.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, NetworkError, session, setSimulatedOffline } from "./api.js";
import { offlineQueue } from "./offlineQueue.js";

// El backend entrega instantes UTC sin sufijo "Z": se fuerza para mostrarlos en hora local.
export const ETIQUETA = { RIEGO: "Riego", VENTILACION: "Ventilación", NUTRIENTES: "Dosificador de nutrientes" };

export const utc = (s) => new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");

// Orden fijo de los actuadores: la pantalla no debe reordenarse nunca, aunque cambie la respuesta del servidor.
export const ORDEN_ACTUADORES = ["RIEGO", "VENTILACION", "NUTRIENTES"];

const MAX_AVISOS = 5;
const SEV_TXT = { CRITICA: "CRÍTICA", MEDIA: "MEDIA" };

// Aviso del sistema operativo (visible aunque la pestaña esté en segundo plano). Solo si el usuario lo permitió.
async function avisoDelSistema(titulo, cuerpo) {
  try {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    if (document.visibilityState !== "hidden") return; // con la app a la vista basta el aviso en pantalla
    const reg = await navigator.serviceWorker?.getRegistration?.();
    if (reg?.showNotification) await reg.showNotification(titulo, { body: cuerpo, icon: "/icons/icon-192.png", tag: titulo });
    else new Notification(titulo, { body: cuerpo, icon: "/icons/icon-192.png" });
  } catch { /* el aviso del sistema es un extra: nunca debe romper la app */ }
}

/**
 * Notificaciones emergentes (toasts). Detecta lo NUEVO entre una actualización y la siguiente:
 *  - alertas nuevas sin reconocer (las críticas quedan fijas hasta cerrarlas),
 *  - sensores que se desconectan, se dañan o se recuperan.
 * En la primera carga solo resume lo que ya estaba pendiente, sin inundar la pantalla.
 */
export function useNotificaciones(data) {
  const [avisos, setAvisos] = useState([]);
  const alertasVistas = useRef(null); // null = aún no hubo primera carga
  const estadoSensores = useRef(new Map());
  const contador = useRef(0);
  const [permiso, setPermiso] = useState(() => (typeof Notification === "undefined" ? "no-soportado" : Notification.permission));

  const cerrar = useCallback((id) => setAvisos((a) => a.filter((x) => x.id !== id)), []);
  const cerrarTodos = useCallback(() => setAvisos([]), []);

  const pedirPermiso = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    try { setPermiso(await Notification.requestPermission()); } catch { /* navegador sin soporte */ }
  }, []);

  useEffect(() => {
    if (!data) return;
    const nombreSector = (id) => data.sectores.find((s) => s.sector_id === id)?.nombre ?? `Sector ${id}`;
    const nuevos = [];
    const nuevo = (aviso) => nuevos.push({ id: ++contador.current, ...aviso });

    const primeraCarga = alertasVistas.current === null;

    // --- Alertas
    const ids = new Set(data.alertas_recientes.map((a) => a.id));
    if (primeraCarga) {
      const activas = data.alertas_recientes.filter((a) => !a.reconocida);
      if (activas.length) {
        const criticas = activas.filter((a) => a.severidad === "CRITICA").length;
        nuevo({ nivel: criticas ? "critica" : "media", titulo: "Alertas pendientes",
                texto: `Hay ${activas.length} alerta(s) sin reconocer${criticas ? `, ${criticas} crítica(s)` : ""}.`,
                fijo: criticas > 0 });
      }
    } else {
      for (const a of data.alertas_recientes) {
        if (alertasVistas.current.has(a.id) || a.reconocida) continue;
        const critica = a.severidad === "CRITICA";
        nuevo({ nivel: critica ? "critica" : "media", alertaId: a.id, sistema: true, fijo: critica,
                titulo: `Alerta ${SEV_TXT[a.severidad] ?? a.severidad} · ${nombreSector(a.sector_id)}`, texto: a.mensaje });
      }
    }
    alertasVistas.current = new Set([...(alertasVistas.current ?? []), ...ids]);

    // --- Sensores: avisar solo cuando CAMBIA el estado
    let conProblemas = 0;
    for (const s of data.sectores) {
      for (const sen of s.sensores ?? []) {
        const clave = `${s.sector_id}|${sen.sensor_id}`;
        const antes = estadoSensores.current.get(clave);
        const ahora = { conexion: sen.conexion, salud: sen.salud };
        estadoSensores.current.set(clave, ahora);
        const donde = `${sen.sensor_id} · ${s.nombre}`;
        if (!antes) { // sensor visto por primera vez: no es un cambio
          if (primeraCarga && (ahora.conexion !== "CONECTADO" || ahora.salud !== "BUENO")) conProblemas++;
          continue;
        }
        if (antes.conexion === "CONECTADO" && ahora.conexion === "DESCONECTADO")
          nuevo({ nivel: "critica", sistema: true, fijo: true, titulo: "Sensor desconectado", texto: `${donde}: dejó de enviar datos.` });
        else if (antes.conexion === "DESCONECTADO" && ahora.conexion === "CONECTADO")
          nuevo({ nivel: "ok", titulo: "Sensor reconectado", texto: `${donde}: volvió a enviar datos.` });
        if (antes.salud === "BUENO" && ahora.salud === "DANADO")
          nuevo({ nivel: "critica", sistema: true, fijo: true, titulo: "Sensor dañado", texto: `${donde}: ${sen.motivo ?? "lecturas anormales"}.` });
        else if (antes.salud === "DANADO" && ahora.salud === "BUENO")
          nuevo({ nivel: "ok", titulo: "Sensor recuperado", texto: `${donde}: vuelve a entregar lecturas normales.` });
      }
    }
    if (conProblemas) {
      nuevo({ nivel: "media", fijo: false, titulo: "Sensores con problemas",
              texto: `${conProblemas} sensor(es) desconectado(s) o dañado(s). Revise el panel «Estado de sensores».` });
    }

    if (nuevos.length) {
      setAvisos((a) => [...nuevos.reverse(), ...a].slice(0, MAX_AVISOS)); // lo más nuevo arriba
      nuevos.filter((n) => n.sistema).forEach((n) => avisoDelSistema(n.titulo, n.texto));
    }
  }, [data]);

  return { avisos, cerrar, cerrarTodos, permiso, pedirPermiso };
}

export function useAuthViewModel() {
  const [user, setUser] = useState(session.user());
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const login = async (email, password) => {
    setError(null);
    setLoading(true);
    try {
      const r = await api.login(email, password);
      session.save(r.access_token, r.usuario);
      setUser(r.usuario);
    } catch (e) {
      if (e instanceof NetworkError) setError("No hay conexión con el servidor. Verifique su red e intente de nuevo.");
      else if (e instanceof ApiError) setError(e.message);
      else setError("Ocurrió un error inesperado.");
    } finally {
      setLoading(false);
    }
  };

  const logout = () => { session.clear(); setUser(null); };
  return { user, error, loading, login, logout };
}

export function useDashboardViewModel(onSessionExpired, user) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [auto, setAuto] = useState(true); // actualización automática (datos del Arduino en vivo)
  const [historial, setHistorial] = useState([]);
  const [sectorHist, setSectorHist] = useState(user?.sector_id ?? null);
  const sectorRef = useRef(sectorHist);
  sectorRef.current = sectorHist;
  const [offline, setOffline] = useState(false); // simulación de pérdida de conexión
  const [pendientes, setPendientes] = useState(0);
  const [syncMsg, setSyncMsg] = useState(null);
  const [ctrlMsg, setCtrlMsg] = useState(null); // resultado de la última acción de control
  const [umbrales, setUmbrales] = useState([]); // reglas de alerta (solo lectura, generadas por el sistema)
  useEffect(() => { api.umbrales().then(setUmbrales).catch(() => {}); }, []);

  const refreshPending = useCallback(() => offlineQueue.count().then(setPendientes), []);

  const cargar = useCallback(async () => {
    try {
      const d = await api.dashboard();
      setData(d);
      setError(null);
      // Agrónomo: sin sector fijo, se muestra el primero hasta que elija otro.
      const sid = sectorRef.current ?? d.sectores[0]?.sector_id;
      if (sid) setHistorial(await api.historial(sid, 10));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSessionExpired();
      // Sin conexión: se conserva el último dato mostrado (cache en memoria) y se avisa.
      setError(e instanceof NetworkError ? "offline" : e.message);
    }
  }, [onSessionExpired]);

  useEffect(() => { cargar(); refreshPending(); }, [cargar, refreshPending]);

  // Recarga al cambiar el sector del historial
  useEffect(() => { if (sectorHist) cargar(); }, [sectorHist]); // eslint-disable-line react-hooks/exhaustive-deps

  // Polling cada 3 s mientras "auto" esté activo
  useEffect(() => {
    if (!auto) return undefined;
    const id = setInterval(cargar, 3000);
    return () => clearInterval(id);
  }, [auto, cargar]);

  const sincronizar = useCallback(async () => {
    const cola = await offlineQueue.all();
    if (cola.length === 0) return;
    const lecturas = cola.filter((i) => !i.kind || i.kind === "lectura");
    const controles = cola.filter((i) => i.kind === "control").sort((a, b) => (a.accion_en < b.accion_en ? -1 : 1));
    const partes = [];
    try {
      if (lecturas.length) {
        const r = await api.sincronizarLote(lecturas.map(({ id, kind, ...resto }) => resto));
        await offlineQueue.removeMany(lecturas.map((i) => i.id)); // solo se borra lo confirmado
        partes.push(`${r.nuevas} lectura(s) (${r.duplicadas} ya existían, ${r.alertas_generadas} alertas)`);
      }
      let aplicados = 0, descartados = 0, rechazados = 0;
      for (const c of controles) { // en orden cronológico
        try {
          const r = await api.cambiarActuador(c.sector_id, c.tipo, c.activo, c.accion_en);
          r.aplicado ? aplicados++ : descartados++;
        } catch (e) {
          if (!(e instanceof ApiError) || e.status === 401) throw e; // red caída o sesión vencida: reintentar luego
          rechazados++; // el servidor la rechazó definitivamente (ej. sin permiso): no tiene sentido reintentar
        }
        await offlineQueue.removeMany([c.id]);
      }
      if (controles.length) {
        partes.push(`${aplicados} acción(es) de control aplicada(s)`
          + (descartados ? `, ${descartados} descartada(s) por LWW (había un cambio más reciente)` : "")
          + (rechazados ? `, ${rechazados} rechazada(s)` : ""));
      }
      setSyncMsg(`Sincronizado: ${partes.join("; ")}.`);
      setCtrlMsg(null); // el aviso "sin conexión" ya no aplica
      await refreshPending();
      await cargar();
    } catch (e) {
      await refreshPending();
      setSyncMsg(e instanceof NetworkError
        ? "Sigue sin conexión: las operaciones permanecen guardadas en el dispositivo."
        : `No se pudo sincronizar: ${e.message}`);
    }
  }, [cargar, refreshPending]);

  const toggleOffline = async () => {
    const next = !offline;
    setOffline(next);
    setSimulatedOffline(next);
    if (!next) await sincronizar(); // al "reconectar" se sube la cola automáticamente
  };

  const registrar = async (lectura) => {
    try {
      const r = await api.registrarLectura(lectura);
      await cargar();
      return { ok: true, mensaje: r.duplicada ? "La lectura ya estaba registrada." : "Lectura registrada.", alertas: r.alertas, repetidas: r.alertas_repetidas };
    } catch (e) {
      if (e instanceof NetworkError) {
        // Resiliencia: se guarda localmente con su instante real y se sincroniza después.
        await offlineQueue.add({ kind: "lectura", ...lectura, tomada_en: new Date().toISOString() });
        await refreshPending();
        return { ok: true, mensaje: "Sin conexión: lectura guardada en el dispositivo y pendiente de sincronizar.", alertas: [] };
      }
      if (e instanceof ApiError && e.status === 401) { onSessionExpired(); return { ok: false, mensaje: e.message }; }
      return { ok: false, mensaje: e.message, details: e.details };
    }
  };

  const cambiarActuador = async (sectorId, tipo, activo) => {
    const accion_en = new Date().toISOString(); // instante real de la acción (base del LWW)
    const nombre = ETIQUETA[tipo];
    try {
      const r = await api.cambiarActuador(sectorId, tipo, activo, accion_en);
      await cargar();
      setCtrlMsg(r.aplicado
        ? { nivel: "ok", texto: `${nombre} ${activo ? "activado" : "desactivado"}.` }
        : { nivel: "warn", texto: r.motivo });
    } catch (e) {
      if (e instanceof NetworkError) {
        // Sin conexión: se encola con su instante real y se refleja en pantalla como "pendiente".
        await offlineQueue.add({ kind: "control", sector_id: sectorId, tipo, activo, accion_en });
        await refreshPending();
        setData((d) => d && {
          ...d,
          sectores: d.sectores.map((s) => (s.sector_id !== sectorId ? s : {
            ...s,
            actuadores: s.actuadores.map((a) => (a.tipo !== tipo ? a : { ...a, activo, origen: "MANUAL", pendiente: true })),
          })),
        });
        setCtrlMsg({ nivel: "warn", texto: `Sin conexión: la acción sobre ${nombre.toLowerCase()} quedó guardada y se enviará al reconectar. Si hubo un cambio más reciente, se descartará (LWW).` });
      } else if (e instanceof ApiError && e.status === 401) {
        onSessionExpired();
      } else {
        setCtrlMsg({ nivel: "error", texto: e.message });
      }
    }
  };

  const reconocer = async (id) => {
    try { await api.reconocerAlerta(id); await cargar(); } catch (e) { setError(e.message); }
  };

  const notificaciones = useNotificaciones(data);

  return {
    notificaciones, data, error, offline, pendientes, syncMsg, cargar, registrar, reconocer, sincronizar, toggleOffline,
    auto, setAuto, historial, sectorHist, setSectorHist, ctrlMsg, cambiarActuador, umbrales,
  };
}
