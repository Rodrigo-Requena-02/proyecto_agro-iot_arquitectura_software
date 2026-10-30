import { useEffect } from "react";

// Severidad / tipo: color + ícono + texto (no depende solo del color, igual que el resto de la app)
const NIVEL = {
  critica: { icon: "🔴", etiqueta: "Crítica" },
  media: { icon: "🟠", etiqueta: "Media" },
  ok: { icon: "✅", etiqueta: "Información" },
};
const AUTO_CIERRE_MS = 12000;

function Aviso({ aviso, onCerrar, onReconocer, puedeReconocer }) {
  const { id, nivel, titulo, texto, alertaId, fijo } = aviso;

  // Las críticas quedan fijas hasta que el usuario las cierre; el resto se cierra solo.
  useEffect(() => {
    if (fijo) return undefined;
    const t = setTimeout(() => onCerrar(id), nivel === "ok" ? 6000 : AUTO_CIERRE_MS);
    return () => clearTimeout(t);
  }, [id, fijo, nivel, onCerrar]);

  return (
    <div className={`toast ${nivel}`} role={nivel === "critica" ? "alert" : "status"}>
      <span className="toast-icon" aria-hidden="true">{NIVEL[nivel].icon}</span>
      <div className="toast-body">
        <strong>{titulo}</strong>
        <span>{texto}</span>
        {alertaId && puedeReconocer && (
          <button className="btn toast-action" onClick={() => { onReconocer(alertaId); onCerrar(id); }}>Reconocer</button>
        )}
      </div>
      <button className="toast-close" onClick={() => onCerrar(id)} aria-label={`Cerrar aviso: ${titulo}`}>✕</button>
    </div>
  );
}

/** Pila de avisos emergentes (esquina superior derecha, no desplaza el contenido de la página). */
export default function Notificaciones({ avisos, onCerrar, onCerrarTodos, onReconocer, puedeReconocer }) {
  if (avisos.length === 0) return null;
  return (
    <div className="toasts" aria-label="Notificaciones">
      {avisos.length > 1 && (
        <button className="btn toasts-clear" onClick={onCerrarTodos}>Cerrar todos ({avisos.length})</button>
      )}
      {avisos.map((a) => (
        <Aviso key={a.id} aviso={a} onCerrar={onCerrar} onReconocer={onReconocer} puedeReconocer={puedeReconocer} />
      ))}
    </div>
  );
}
