// Capa de acceso a la API. Traduce los fallos a dos tipos que la UI distingue:
//   ApiError     -> el servidor respondió con un error de negocio/validación (tiene code y status)
//   NetworkError -> no hubo respuesta (sin conexión o "pérdida de conexión simulada")

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
export class NetworkError extends Error {}

const TOKEN_KEY = "agroiot_token";
const USER_KEY = "agroiot_user";

export const session = {
  token: () => sessionStorage.getItem(TOKEN_KEY),
  user: () => {
    try { return JSON.parse(sessionStorage.getItem(USER_KEY)); } catch { return null; }
  },
  save: (token, user) => {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(USER_KEY); },
};

// Interruptor para la demo: simula que el dispositivo perdió la conexión.
let simulatedOffline = false;
export const setSimulatedOffline = (v) => { simulatedOffline = v; };
export const isSimulatedOffline = () => simulatedOffline;

async function request(path, { method = "GET", body } = {}) {
  if (simulatedOffline || !navigator.onLine) throw new NetworkError("Sin conexión");

  const headers = { "Content-Type": "application/json" };
  const token = session.token();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new NetworkError("No se pudo contactar al servidor");
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(res.status, e?.code ?? "UNKNOWN", e?.message ?? `Error ${res.status}`, e?.details);
  }
  return data;
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  dashboard: () => request("/dashboard"),
  umbrales: () => request("/alertas/umbrales"),
  historial: (sectorId, limite = 10) => request(`/telemetria?sector_id=${sectorId}&limite=${limite}`),
  registrarLectura: (lectura) => request("/telemetria", { method: "POST", body: lectura }),
  sincronizarLote: (lecturas) => request("/telemetria/lote", { method: "POST", body: { lecturas } }),
  cambiarActuador: (sectorId, tipo, activo, accionEn) =>
    request(`/sectores/${sectorId}/actuadores/${tipo}`, { method: "PUT", body: { activo, accion_en: accionEn } }),
  reconocerAlerta: (id) => request(`/alertas/${id}/reconocer`, { method: "PATCH" }),
};
