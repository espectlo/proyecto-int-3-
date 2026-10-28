import { useState } from "react";
import { LogOut, ShieldCheck } from "lucide-react";
import { ApiError, cambiarClave } from "./api.js";

function CambiarClave({ perfil, alCompletar, alCerrarSesion }) {
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function enviar(evento) {
    evento.preventDefault();
    setError("");
    setGuardando(true);
    const datos = new FormData(evento.currentTarget);
    try {
      const actualizado = await cambiarClave(
        datos.get("claveActual").toString(),
        datos.get("claveNueva").toString(),
        datos.get("confirmacion").toString(),
      );
      alCompletar(actualizado);
    } catch (caught) {
      if (caught instanceof ApiError && caught.details) {
        const detalle = Object.values(caught.details)
          .flat()
          .filter((valor) => typeof valor === "string")
          .join(" ");
        setError(detalle || caught.message);
      } else {
        setError(caught.message || "No fue posible cambiar la contraseña.");
      }
    } finally {
      setGuardando(false);
    }
  }

  return (
    <main className="password-change-page">
      <header className="password-change-header">
        <div className="brand-mark">N</div>
        <div><strong>NUAM</strong><span>Mercados integrados</span></div>
        <button className="icon-button" onClick={alCerrarSesion} type="button" aria-label="Cerrar sesión"><LogOut size={17} /></button>
      </header>
      <section className="password-change-card">
        <div className="login-lock"><ShieldCheck size={20} /></div>
        <div className="eyebrow">PRIMER ACCESO</div>
        <h1>Actualiza tu contraseña</h1>
        <p>La contraseña temporal debe cambiarse antes de acceder al sistema.</p>
        <div className="password-account">{perfil.email}</div>
        {error && <div className="login-error" role="alert">{error}</div>}
        <form onSubmit={enviar}>
          <label htmlFor="current-password">Contraseña temporal</label>
          <input className="form-control" id="current-password" name="claveActual" type="password" autoComplete="current-password" required />
          <label htmlFor="new-password">Nueva contraseña</label>
          <input className="form-control" id="new-password" name="claveNueva" type="password" autoComplete="new-password" minLength="12" required />
          <label htmlFor="confirm-password">Confirma la nueva contraseña</label>
          <input className="form-control" id="confirm-password" name="confirmacion" type="password" autoComplete="new-password" minLength="12" required />
          <div className="password-hint">Usa al menos 12 caracteres y evita una contraseña común o fácil de asociar a tu cuenta.</div>
          <button className="btn btn-primary login-submit" disabled={guardando} type="submit">{guardando ? "Actualizando…" : "Cambiar contraseña"}</button>
        </form>
      </section>
    </main>
  );
}

export default CambiarClave;
