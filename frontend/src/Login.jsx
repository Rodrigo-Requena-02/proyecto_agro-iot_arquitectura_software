import { useState } from "react";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login({ auth }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});

  const submit = (e) => {
    e.preventDefault();
    // Validación en cliente (feedback inmediato). El backend vuelve a validar: nunca se confía solo en la UI.
    const v = {};
    if (!EMAIL_RE.test(email)) v.email = "Ingrese un correo válido";
    if (!password) v.password = "Ingrese su contraseña";
    setErrors(v);
    if (Object.keys(v).length === 0) auth.login(email.trim().toLowerCase(), password);
  };

  return (
    <main className="login-wrap">
      <form className="card login" onSubmit={submit} noValidate>
        <h1>🌱 AgroIoT</h1>
        <p className="muted">Inicie sesión para acceder a la plataforma</p>

        {auth.error && <div className="banner error" role="alert">⛔ {auth.error}</div>}

        <label htmlFor="email">Correo</label>
        <input id="email" type="email" autoComplete="username" value={email}
               onChange={(e) => setEmail(e.target.value)} aria-invalid={!!errors.email} />
        {errors.email && <small className="field-error">{errors.email}</small>}

        <label htmlFor="password">Contraseña</label>
        <input id="password" type="password" autoComplete="current-password" value={password}
               onChange={(e) => setPassword(e.target.value)} aria-invalid={!!errors.password} />
        {errors.password && <small className="field-error">{errors.password}</small>}

        <button className="btn primary big" disabled={auth.loading}>
          {auth.loading ? "Ingresando…" : "Ingresar"}
        </button>

        <details className="demo">
          <summary>Usuarios de demostración</summary>
          <ul>
            <li><code>agronomo@agro.cl</code> / <code>Agro2026!</code> (Agrónomo)</li>
            <li><code>jefe.a@agro.cl</code> / <code>Terreno2026!</code> (Jefe, Sector A)</li>
            <li><code>jefe.b@agro.cl</code> / <code>Terreno2026!</code> (Jefe, Sector B)</li>
            <li><code>jefe.c@agro.cl</code> / <code>Terreno2026!</code> (Jefe, Sector C)</li>
          </ul>
        </details>
      </form>
    </main>
  );
}
