// Cola de operaciones pendientes (lecturas {kind:'lectura'} y acciones de control {kind:'control'}) en IndexedDB (la misma tecnología definida en la Evaluación 1).
// Cada lectura guarda su instante real de medición (tomada_en): el backend usa
// (sensor_id + tomada_en) para ser idempotente si el lote se reenvía.
const DB_NAME = "agroiot";
const STORE = "pendientes";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const result = fn(t.objectStore(STORE));
    t.oncomplete = () => { db.close(); resolve(result.result); };
    t.onerror = () => { db.close(); reject(t.error); };
  });
}

export const offlineQueue = {
  add: (lectura) => tx("readwrite", (s) => s.add(lectura)),
  all: () => tx("readonly", (s) => s.getAll()),
  count: () => tx("readonly", (s) => s.count()),
  // Borra solo lo confirmado por el servidor (la cola ahora mezcla lecturas y acciones de control).
  removeMany: (ids) => tx("readwrite", (s) => { ids.forEach((id) => s.delete(id)); return { result: undefined }; }),
  clear: () => tx("readwrite", (s) => s.clear()),
};
