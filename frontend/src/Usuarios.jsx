import { useCallback, useEffect, useState } from "react";
import { ApiError, solicitudApi } from "./api.js";

const nombreRoles = {
  CORREDOR: "Corredor",
  OPERADOR_BOLSA: "Operador de Bolsa",
  AUDITOR: "Auditor",
};

function mostrarError(error) {
  const detalles = error instanceof ApiError ? error.details : null;
  if (detalles && typeof detalles === "object") {
    const texto = Object.values(detalles)
      .flat()
      .filter((valor) => typeof valor === "string")
      .join(" ");
    if (texto) return texto;
  }
  return error.message || "No fue posible completar la operación.";
}

function Usuarios({ usuarioId }) {
  const [datos, setDatos] = useState({ total: 0, corredores: [], resultados: [] });
  const [pagina, setPagina] = useState(1);
  const [modalAbierto, setModalAbierto] = useState(false);
  const [rolSeleccionado, setRolSeleccionado] = useState("CORREDOR");
  const [claveTemporal, setClaveTemporal] = useState("");
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  const cargarUsuarios = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const respuesta = await solicitudApi(
        `/api/v1/usuarios/?pagina=${pagina}&limite=25`,
      );
      setDatos(respuesta);
    } catch (caught) {
      setError(mostrarError(caught));
    } finally {
      setCargando(false);
    }
  }, [pagina]);

  useEffect(() => {
    cargarUsuarios();
  }, [cargarUsuarios]);

  async function crearUsuario(evento) {
    evento.preventDefault();
    const form = new FormData(evento.currentTarget);
    setGuardando(true);
    setError("");
    try {
      const respuesta = await solicitudApi("/api/v1/usuarios/", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email").toString().trim(),
          nombre: form.get("nombre").toString().trim(),
          rol: rolSeleccionado,
          ...(rolSeleccionado === "CORREDOR"
            ? { corredor_id: Number(form.get("corredor")) }
            : {}),
        }),
      });
      setClaveTemporal(respuesta.clave_temporal);
      setModalAbierto(false);
      await cargarUsuarios();
    } catch (caught) {
      setError(mostrarError(caught));
    } finally {
      setGuardando(false);
    }
  }

  async function cambiarEstado(usuario) {
    const activo = !usuario.activo;
    const accion = activo ? "activar" : "desactivar";
    if (!window.confirm(`¿${accion[0].toUpperCase()}${accion.slice(1)} la cuenta de ${usuario.email}?`)) {
      return;
    }
    setError("");
    try {
      await solicitudApi(`/api/v1/usuarios/${usuario.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ activo }),
      });
      await cargarUsuarios();
    } catch (caught) {
      setError(mostrarError(caught));
    }
  }

  async function restablecerClave(usuario) {
    if (!window.confirm(`¿Generar una nueva contraseña temporal para ${usuario.email}? La contraseña actual dejará de funcionar.`)) {
      return;
    }
    setError("");
    try {
      const respuesta = await solicitudApi(
        `/api/v1/usuarios/${usuario.id}/clave-temporal/`,
        { method: "POST", body: "{}" },
      );
      setClaveTemporal(respuesta.clave_temporal);
      await cargarUsuarios();
    } catch (caught) {
      setError(mostrarError(caught));
    }
  }

  const paginas = Math.max(1, Math.ceil(datos.total / 25));

  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">ADMINISTRACIÓN</div>
          <h1>Usuarios</h1>
          <p>Gestiona cuentas, roles y acceso de corredores.</p>
        </div>
        <button className="btn btn-primary create-button" onClick={() => { setError(""); setRolSeleccionado("CORREDOR"); setModalAbierto(true); }} type="button">
          <span className="plus-sign">+</span> Crear usuario
        </button>
      </section>

      {error && <div className="api-alert error" role="alert">{error}</div>}
      {claveTemporal && (
        <section className="temporary-password" role="status">
          <button className="temporary-password-close" onClick={() => setClaveTemporal("")} type="button" aria-label="Ocultar contraseña">×</button>
          <strong>Cuenta creada. Contraseña temporal de un solo uso:</strong>
          <code>{claveTemporal}</code>
          <span>Entrégala al usuario por un canal seguro. No volverá a mostrarse y deberá cambiarla al iniciar sesión.</span>
        </section>
      )}

      <section className="results-card">
        <div className="results-header">
          <div><h2>Cuentas del sistema</h2><p>Solo los administradores pueden gestionar usuarios.</p></div>
          <div className="results-tools"><span className="records-count">{cargando ? "Cargando…" : `${datos.total} usuarios`}</span></div>
        </div>
        <div className="table-responsive">
          <table className="table records-table users-table">
            <thead><tr><th>USUARIO</th><th>ROL</th><th>CORREDOR</th><th>ESTADO</th><th>ACCESO INICIAL</th><th>CREADO</th><th /></tr></thead>
            <tbody>
              {datos.resultados.map((usuario) => (
                <tr key={usuario.id}>
                  <td><strong className="instrument-name">{usuario.nombre}</strong><span className="sequence">{usuario.email}</span></td>
                  <td>{nombreRoles[usuario.rol] || "Administrador"}</td>
                  <td>{usuario.corredor || "—"}</td>
                  <td><span className={`status-tag ${usuario.activo ? "current" : "draft"}`}><i />{usuario.activo ? "Activo" : "Inactivo"}</span></td>
                  <td>{usuario.debe_cambiar_clave ? "Cambio pendiente" : "Configurado"}</td>
                  <td>{new Date(usuario.creado_en).toLocaleDateString("es-CL")}</td>
                  <td><div className="row-actions user-actions"><button className={`row-action ${usuario.activo ? "" : "edit"}`} onClick={() => cambiarEstado(usuario)} type="button">{usuario.activo ? "Desactivar" : "Activar"}</button>{usuario.activo && usuario.id !== usuarioId && <button className="row-action edit" onClick={() => restablecerClave(usuario)} type="button">Restablecer clave</button>}</div></td>
                </tr>
              ))}
              {!cargando && datos.resultados.length === 0 && <tr><td className="empty-row" colSpan="7">No hay usuarios registrados.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="table-footer audit-footer"><span>{datos.total} usuarios encontrados</span><div className="audit-pagination"><button className="btn btn-light" disabled={pagina <= 1 || cargando} onClick={() => setPagina(pagina - 1)} type="button">Anterior</button><span>Página {pagina} de {paginas}</span><button className="btn btn-light" disabled={pagina >= paginas || cargando} onClick={() => setPagina(pagina + 1)} type="button">Siguiente</button></div></div>
      </section>
      <footer className="page-footer"><span>NUAM · Administración de usuarios</span><span>Accesos auditados</span></footer>

      {modalAbierto && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !guardando) setModalAbierto(false); }}>
          <section className="create-modal" role="dialog" aria-modal="true" aria-labelledby="user-modal-title">
            <div className="modal-heading"><div><div className="eyebrow">NUEVA CUENTA</div><h2 id="user-modal-title">Datos del usuario</h2></div><button className="modal-close" type="button" onClick={() => setModalAbierto(false)} aria-label="Cerrar">×</button></div>
            <p className="modal-description">El sistema genera una contraseña temporal aleatoria, que se mostrará una sola vez después de crear la cuenta.</p>
            <form onSubmit={crearUsuario}>
              <label>Nombre completo<input className="form-control" name="nombre" maxLength="150" autoComplete="name" required /></label>
              <label>Correo electrónico<input className="form-control" name="email" type="email" maxLength="120" autoComplete="email" required /></label>
              <label>Rol<select className="form-select" name="rol" value={rolSeleccionado} onChange={(event) => setRolSeleccionado(event.target.value)}>{Object.entries(nombreRoles).map(([codigo, nombre]) => <option key={codigo} value={codigo}>{nombre}</option>)}</select></label>
              {rolSeleccionado === "CORREDOR" && <label>Corredor<select className="form-select" name="corredor" defaultValue="" required><option value="" disabled>Selecciona un corredor activo</option>{datos.corredores.map((corredor) => <option key={corredor.id} value={corredor.id}>{corredor.nombre} · {corredor.rut}</option>)}</select></label>}
              <div className="modal-warning">La contraseña temporal no se enviará por correo. Entrégala al usuario por un canal seguro; el primer acceso solo permitirá cambiarla.</div>
              <div className="modal-actions"><button className="btn btn-light" type="button" disabled={guardando} onClick={() => setModalAbierto(false)}>Cancelar</button><button className="btn btn-primary" type="submit" disabled={guardando}>{guardando ? "Creando…" : "Crear cuenta"}</button></div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}

export default Usuarios;
