import { useState } from "react";
import { ArrowRight, LockKeyhole } from "lucide-react";
import { ApiError, iniciarSesion } from "./api.js";

function Login({ alIniciarSesion }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function enviar(event) {
    event.preventDefault();
    setError("");
    setCargando(true);
    try {
      const usuario = await iniciarSesion(email, password);
      alIniciarSesion(usuario);
    } catch (caught) {
      if (caught instanceof ApiError && caught.statusCode === 429) {
        setError("Demasiados intentos. Espera un momento antes de intentar nuevamente.");
      } else {
        setError(caught.message || "No fue posible iniciar sesión.");
      }
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand-panel">
        <div className="login-brand">
          <div className="brand-mark">N</div>
          <div><strong>NUAM</strong><span>Mercados integrados</span></div>
        </div>
        <div className="login-brand-copy">
          <span className="eyebrow">PLATAFORMA DE OPERACIONES</span>
          <h1>Calificaciones tributarias, con trazabilidad y control.</h1>
          <p>Acceso centralizado para gestionar información tributaria de instrumentos financieros.</p>
        </div>
        <span className="login-brand-footer">NUAM · Mantenedor Centralizado</span>
      </section>

      <section className="login-form-panel">
        <div className="login-card">
          <div className="login-lock"><LockKeyhole size={20} /></div>
          <div className="eyebrow">BIENVENIDO</div>
          <h2>Iniciar sesión</h2>
          <p>Ingresa con las credenciales de tu cuenta.</p>
          <form onSubmit={enviar}>
            <label htmlFor="login-email">Correo electrónico</label>
            <input
              autoComplete="username"
              className="form-control"
              id="login-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="nombre@empresa.cl"
              required
              type="email"
              value={email}
            />
            <label htmlFor="login-password">Contraseña</label>
            <input
              autoComplete="current-password"
              className="form-control"
              id="login-password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Ingresa tu contraseña"
              required
              type="password"
              value={password}
            />
            {error && <div className="login-error" role="alert">{error}</div>}
            <button className="btn btn-primary login-submit" disabled={cargando} type="submit">
              {cargando ? "Validando..." : "Ingresar"}
              {!cargando && <ArrowRight size={16} />}
            </button>
          </form>
          <div className="login-security-note">
            Tu sesión está protegida con autenticación segura.
          </div>
        </div>
        <span className="login-version">Acceso seguro · NUAM</span>
      </section>
    </main>
  );
}

export default Login;
