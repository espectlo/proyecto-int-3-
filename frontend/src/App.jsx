import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Bell,
  BookOpenCheck,
  CircleHelp,
  Database,
  FileUp,
  LayoutDashboard,
  LogOut,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { ApiError, cerrarSesion, restaurarSesion, solicitudApi } from "./api.js";
import CargaMasiva from "./CargaMasiva.jsx";
import CatalogoTributario from "./CatalogoTributario.jsx";
import CambiarClave from "./CambiarClave.jsx";
import Login from "./Login.jsx";
import Usuarios from "./Usuarios.jsx";

const navegacion = [
  { nombre: "Inicio", icono: LayoutDashboard },
  { nombre: "Calificaciones", icono: BookOpenCheck },
  { nombre: "Carga masiva", icono: FileUp },
  { nombre: "Auditoría", icono: ShieldCheck },
  { nombre: "Usuarios", icono: Users },
  { nombre: "Catálogo tributario", icono: Database },
];

const origenes = {
  ARCHIVO_CARGA: "Archivo",
  INGRESO_MANUAL: "Manual",
  SISTEMA: "Sistema",
};

const accionesAuditoria = {
  INGRESO: "Ingreso",
  MODIFICACION: "Modificación",
  ELIMINACION: "Eliminación",
  CARGA: "Carga",
  ACCESO_DENEGADO: "Acceso denegado",
  CONSULTA_AUDITOR: "Consulta de auditor",
  ADMIN_USUARIO: "Administración de usuario",
  CAMBIO_CLAVE: "Cambio de contraseña",
};

function paginaInicial(perfil) {
  return ["ADMINISTRADOR", "AUDITOR"].includes(perfil?.rol)
    ? "Auditoría"
    : "Calificaciones";
}

function mostrarFecha(fecha) {
  if (!fecha) return "—";
  const [anio, mes, dia] = fecha.split("-");
  return `${dia}-${mes}-${anio}`;
}

function errorDeFormulario(error) {
  if (error instanceof ApiError && error.details && typeof error.details === "object") {
    const campos = Object.entries(error.details)
      .map(([campo, mensaje]) => {
        const detalle = Array.isArray(mensaje) ? mensaje.join(" ") : mensaje;
        return `${campo}: ${detalle}`;
      });
    if (campos.length) return campos.join(" · ");
  }
  return error.message || "No fue posible completar la operación.";
}

function VistaAuditoria({
  cargando,
  eventos,
  filtros,
  pagina,
  setFiltros,
  setPagina,
  total,
}) {
  const paginas = Math.max(1, Math.ceil(total / 25));
  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">CONTROL Y TRAZABILIDAD</div>
          <h1>Auditoría</h1>
          <p>Registro inmutable de operaciones y accesos al sistema.</p>
        </div>
      </section>
      <section className="filter-card">
        <div className="filter-title"><SlidersHorizontal size={16} /><strong>Filtros de auditoría</strong><span>Consulta de solo lectura</span></div>
        <div className="audit-filters">
          <label><span>Acción</span><select className="form-select" value={filtros.accion} onChange={(event) => { setFiltros({ ...filtros, accion: event.target.value }); setPagina(1); }}><option value="">Todas las acciones</option>{Object.entries(accionesAuditoria).map(([codigo, nombre]) => <option key={codigo} value={codigo}>{nombre}</option>)}</select></label>
          <label><span>Desde</span><input className="form-control" type="date" value={filtros.desde} onChange={(event) => { setFiltros({ ...filtros, desde: event.target.value }); setPagina(1); }} /></label>
          <label><span>Hasta</span><input className="form-control" type="date" value={filtros.hasta} onChange={(event) => { setFiltros({ ...filtros, hasta: event.target.value }); setPagina(1); }} /></label>
          <button className="clear-filters" type="button" onClick={() => { setFiltros({ accion: "", desde: "", hasta: "" }); setPagina(1); }}>Limpiar filtros</button>
        </div>
      </section>
      <section className="results-card">
        <div className="results-header">
          <div><h2>Eventos registrados</h2><p>Los registros de auditoría no se pueden editar ni eliminar.</p></div>
          <div className="results-tools"><span className="records-count">{cargando ? "Cargando…" : `${total} eventos`}</span></div>
        </div>
        <div className="table-responsive">
          <table className="table records-table audit-table">
            <thead><tr><th>FECHA Y HORA</th><th>USUARIO</th><th>ÁMBITO</th><th>ACCIÓN</th><th>ENTIDAD / ID</th><th>MÉTODO</th><th>CAMBIOS</th></tr></thead>
            <tbody>
              {eventos.map((evento) => (
                <tr key={evento.id}>
                  <td>{new Date(evento.fecha_hora).toLocaleString("es-CL")}</td>
                  <td>{evento.usuario}</td>
                  <td>{evento.corredor || "Bolsa / sistema"}</td>
                  <td>{accionesAuditoria[evento.accion] || evento.accion}</td>
                  <td>{evento.entidad} #{evento.id_registro}</td>
                  <td>{evento.metodo || "—"}</td>
                  <td><details className="audit-details"><summary>Ver detalle</summary><div className="audit-json"><strong>Antes</strong><pre>{evento.valor_anterior ? JSON.stringify(evento.valor_anterior, null, 2) : "Sin valor anterior"}</pre><strong>Después</strong><pre>{evento.valor_nuevo ? JSON.stringify(evento.valor_nuevo, null, 2) : "Sin valor nuevo"}</pre></div></details></td>
                </tr>
              ))}
              {!cargando && eventos.length === 0 && <tr><td className="empty-row" colSpan="7">No hay eventos que coincidan con los filtros.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="table-footer audit-footer"><span>{total} eventos encontrados</span><div className="audit-pagination"><button className="btn btn-light" disabled={pagina <= 1 || cargando} onClick={() => setPagina(pagina - 1)} type="button">Anterior</button><span>Página {pagina} de {paginas}</span><button className="btn btn-light" disabled={pagina >= paginas || cargando} onClick={() => setPagina(pagina + 1)} type="button">Siguiente</button></div></div>
      </section>
      <footer className="page-footer"><span>NUAM · Registro de auditoría inmutable</span><span>Solo lectura</span></footer>
    </>
  );
}

function LoginCargando() {
  return <main className="login-loading">Verificando la sesión…</main>;
}

function App() {
  const [sesion, setSesion] = useState(null);
  const [paginaActiva, setPaginaActiva] = useState("Calificaciones");
  const [sesionLista, setSesionLista] = useState(false);
  const [usuario, setUsuario] = useState(null);
  const [registros, setRegistros] = useState([]);
  const [eventosAuditoria, setEventosAuditoria] = useState([]);
  const [totalAuditoria, setTotalAuditoria] = useState(0);
  const [paginaAuditoria, setPaginaAuditoria] = useState(1);
  const [filtrosAuditoria, setFiltrosAuditoria] = useState({
    accion: "",
    desde: "",
    hasta: "",
  });
  const [catalogos, setCatalogos] = useState({ mercados: [], instrumentos: [] });
  const [busqueda, setBusqueda] = useState("");
  const [mercado, setMercado] = useState("");
  const [ejercicio, setEjercicio] = useState("");
  const [origen, setOrigen] = useState("");
  const [modalAbierto, setModalAbierto] = useState(false);
  const [registroEnEdicion, setRegistroEnEdicion] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");
  const contadorSolicitudes = useRef(0);

  useEffect(() => {
    let vigente = true;
    restaurarSesion()
      .then((perfil) => {
        if (vigente) {
          setSesion(perfil);
          setUsuario(perfil);
          setPaginaActiva(paginaInicial(perfil));
        }
      })
      .catch(() => {
        if (vigente) setError("No se pudo comprobar la sesión. Intenta nuevamente.");
      })
      .finally(() => {
        if (vigente) setSesionLista(true);
      });
    return () => { vigente = false; };
  }, []);

  const cargarDatos = useCallback(async () => {
    if (!sesion || !["CORREDOR", "OPERADOR_BOLSA", "AUDITOR"].includes(sesion.rol)) return;
    const solicitud = ++contadorSolicitudes.current;
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams();
    if (busqueda.trim()) parametros.set("q", busqueda.trim());
    if (mercado) parametros.set("mercado", mercado);
    if (ejercicio) parametros.set("ejercicio", ejercicio);
    if (origen) parametros.set("origen", origen);
    const sufijo = parametros.size ? `?${parametros.toString()}` : "";
    try {
      const [respuestaCatalogos, respuestaRegistros] = await Promise.all([
        solicitudApi("/api/v1/catalogos/"),
        solicitudApi(`/api/v1/calificaciones/${sufijo}`),
      ]);
      if (solicitud === contadorSolicitudes.current) {
        setCatalogos(respuestaCatalogos);
        setRegistros(respuestaRegistros);
      }
    } catch (caught) {
      if (solicitud === contadorSolicitudes.current) {
        setError(errorDeFormulario(caught));
        if (caught instanceof ApiError && caught.statusCode === 401) {
          setSesion(null);
          setUsuario(null);
        }
      }
    } finally {
      if (solicitud === contadorSolicitudes.current) setCargando(false);
    }
  }, [busqueda, ejercicio, mercado, origen, sesion]);

  useEffect(() => {
    if (paginaActiva === "Calificaciones" && sesion) cargarDatos();
  }, [paginaActiva, sesion, cargarDatos]);

  const cargarAuditoria = useCallback(async () => {
    if (!sesion || !["ADMINISTRADOR", "AUDITOR"].includes(sesion.rol)) return;
    const solicitud = ++contadorSolicitudes.current;
    setCargando(true);
    setError("");
    const parametros = new URLSearchParams({ pagina: String(paginaAuditoria), limite: "25" });
    Object.entries(filtrosAuditoria).forEach(([clave, valor]) => {
      if (valor) parametros.set(clave, valor);
    });
    try {
      const respuesta = await solicitudApi(`/api/v1/auditoria/?${parametros.toString()}`);
      if (solicitud === contadorSolicitudes.current) {
        setEventosAuditoria(respuesta.resultados);
        setTotalAuditoria(respuesta.total);
      }
    } catch (caught) {
      if (solicitud === contadorSolicitudes.current) {
        setError(errorDeFormulario(caught));
        if (caught instanceof ApiError && caught.statusCode === 401) {
          setSesion(null);
          setUsuario(null);
        }
      }
    } finally {
      if (solicitud === contadorSolicitudes.current) setCargando(false);
    }
  }, [filtrosAuditoria, paginaAuditoria, sesion]);

  useEffect(() => {
    if (paginaActiva === "Auditoría" && sesion) cargarAuditoria();
  }, [paginaActiva, sesion, cargarAuditoria]);

  const instrumentosVisibles = useMemo(
    () => catalogos.instrumentos.filter(
      (instrumento) => !mercado || instrumento.mercado === mercado,
    ),
    [catalogos.instrumentos, mercado],
  );
  const permiteCrear = ["CORREDOR", "OPERADOR_BOLSA"].includes(sesion?.rol);
  const permiteAuditoria = ["ADMINISTRADOR", "AUDITOR"].includes(sesion?.rol);
  const permiteUsuarios = sesion?.rol === "ADMINISTRADOR";

  if (!sesionLista) return <LoginCargando />;
  if (!sesion) return <Login alIniciarSesion={(perfil) => {
    setUsuario(perfil);
    setSesion(perfil);
    setPaginaActiva(paginaInicial(perfil));
    setError("");
  }} />;

  if (sesion.debe_cambiar_clave) {
    return (
      <CambiarClave
        perfil={sesion}
        alCerrarSesion={salir}
        alCompletar={(perfil) => {
          setSesion(perfil);
          setUsuario(perfil);
          setPaginaActiva(paginaInicial(perfil));
        }}
      />
    );
  }

  async function crearRegistro(evento) {
    evento.preventDefault();
    const datos = new FormData(evento.currentTarget);
    setError("");
    setMensaje("");
    try {
      await solicitudApi("/api/v1/calificaciones/", {
        method: "POST",
        body: JSON.stringify({
          instrumento: Number(datos.get("instrumento")),
          ejercicio: Number(datos.get("ejercicio")),
          secuencia_evento: Number(datos.get("secuencia")),
          fecha_pago: datos.get("fecha"),
          descripcion_dividendo: datos.get("descripcion").toString().trim(),
          numero_dividendo: Number(datos.get("dividendo") || 0),
        }),
      });
      setModalAbierto(false);
      setMensaje("La calificación se guardó correctamente.");
      await cargarDatos();
    } catch (caught) {
      setError(errorDeFormulario(caught));
    }
  }

  async function guardarEdicion(evento) {
    evento.preventDefault();
    const datos = new FormData(evento.currentTarget);
    setError("");
    setMensaje("");
    try {
      await solicitudApi(`/api/v1/calificaciones/${registroEnEdicion.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          version: registroEnEdicion.version,
          ejercicio: Number(datos.get("ejercicio")),
          secuencia_evento: Number(datos.get("secuencia")),
          fecha_pago: datos.get("fecha"),
          descripcion_dividendo: datos.get("descripcion").toString().trim(),
          numero_dividendo: Number(datos.get("dividendo") || 0),
        }),
      });
      setRegistroEnEdicion(null);
      setMensaje("Los cambios se guardaron correctamente.");
      await cargarDatos();
    } catch (caught) {
      setError(errorDeFormulario(caught));
    }
  }

  async function eliminarRegistro(registro) {
    const confirmado = window.confirm(
      `¿Eliminar la calificación ${registro.codigo_instrumento}? Esta acción será lógica y quedará auditada.`,
    );
    if (!confirmado) return;
    setError("");
    setMensaje("");
    try {
      await solicitudApi(`/api/v1/calificaciones/${registro.id}/`, {
        method: "DELETE",
        body: JSON.stringify({ version: registro.version }),
      });
      setMensaje("La calificación se eliminó correctamente.");
      await cargarDatos();
    } catch (caught) {
      setError(errorDeFormulario(caught));
    }
  }

  async function salir() {
    try {
      await cerrarSesion();
    } finally {
      setSesion(null);
      setUsuario(null);
      setRegistros([]);
    }
  }

  function abrirEdicion(registro) {
    setError("");
    setMensaje("");
    setRegistroEnEdicion(registro);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div><strong>NUAM</strong><span>Mercados integrados</span></div>
        </div>
        <div className="workspace-label">PLATAFORMA</div>
        <nav className="side-nav" aria-label="Navegación principal">
          {navegacion.map(({ nombre, icono: Icono }) => {
            const habilitado = nombre === "Calificaciones"
              ? ["CORREDOR", "OPERADOR_BOLSA", "AUDITOR"].includes(sesion.rol)
              : nombre === "Carga masiva"
                ? ["CORREDOR", "OPERADOR_BOLSA"].includes(sesion.rol)
              : nombre === "Auditoría"
                ? permiteAuditoria
                : ["Usuarios", "Catálogo tributario"].includes(nombre)
                  && permiteUsuarios;
            return <button className={`nav-item ${paginaActiva === nombre ? "active" : ""}`} key={nombre} type="button" disabled={!habilitado} onClick={() => { if (habilitado) { setPaginaActiva(nombre); setError(""); setMensaje(""); } }}>
              <Icono size={17} strokeWidth={1.8} /><span>{nombre}</span>
            </button>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <button className="nav-item" type="button" disabled><Settings size={17} /><span>Configuración</span></button>
          <button className="nav-item" type="button" disabled><CircleHelp size={17} /><span>Centro de ayuda</span></button>
          <div className="profile-card">
            <div className="avatar">{(usuario?.nombre || usuario?.email || "NU").slice(0, 2).toUpperCase()}</div>
            <div className="profile-copy"><strong>{usuario?.nombre || usuario?.email}</strong><span>{usuario?.rol?.replaceAll("_", " ")}</span></div>
            <button className="icon-button profile-menu" onClick={salir} type="button" aria-label="Cerrar sesión"><LogOut size={15} /></button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>Operaciones</span><span className="crumb-slash">/</span><strong>{paginaActiva === "Auditoría" || paginaActiva === "Usuarios" || paginaActiva === "Carga masiva" || paginaActiva === "Catálogo tributario" ? paginaActiva : "Calificaciones tributarias"}</strong></div>
          <div className="topbar-actions">
            <span className="environment-tag"><Activity size={13} /> Sesión segura</span>
            <button className="icon-button notification-button" type="button" aria-label="Notificaciones"><Bell size={18} /><i /></button>
            <div className="topbar-divider" />
            <span className="topbar-user">{(usuario?.nombre || usuario?.email || "NU").slice(0, 2).toUpperCase()}</span>
          </div>
        </header>

        <div className="content">
          {paginaActiva === "Auditoría" ? (
            <>
              {error && <div className="api-alert error" role="alert">{error}</div>}
              <VistaAuditoria
                cargando={cargando}
                eventos={eventosAuditoria}
                filtros={filtrosAuditoria}
                pagina={paginaAuditoria}
                setFiltros={setFiltrosAuditoria}
                setPagina={setPaginaAuditoria}
                total={totalAuditoria}
              />
            </>
          ) : paginaActiva === "Usuarios" ? (
            <Usuarios usuarioId={sesion.id} />
          ) : paginaActiva === "Catálogo tributario" ? (
            <CatalogoTributario />
          ) : paginaActiva === "Carga masiva" ? (
            <CargaMasiva />
          ) : <>
          <div className="demo-notice">
            <span className="notice-indicator" />
            La consulta aplica el alcance de tu rol. La prioridad entre registros de Bolsa y corredor aún está pendiente de confirmación funcional.
          </div>
          <section className="page-heading">
            <div>
              <div className="eyebrow">MANTENEDOR</div>
              <h1>Calificaciones tributarias</h1>
              <p>Consulta y administra las calificaciones de instrumentos financieros.</p>
            </div>
            {permiteCrear && (
              <button className="btn btn-primary create-button" onClick={() => setModalAbierto(true)} type="button">
                <span className="plus-sign">+</span> Nueva calificación
              </button>
            )}
          </section>

          {error && <div className="api-alert error" role="alert">{error}</div>}
          {mensaje && <div className="api-alert success" role="status">{mensaje}</div>}

          <section className="filter-card">
            <div className="filter-title"><SlidersHorizontal size={16} /><strong>Filtros de búsqueda</strong><span>Refina los resultados</span></div>
            <div className="filters-grid">
              <label className="search-field">
                <span>Buscar</span>
                <div className="input-with-icon"><Search size={16} /><input value={busqueda} onChange={(event) => setBusqueda(event.target.value)} placeholder="Código o instrumento" /></div>
              </label>
              <label><span>Mercado</span><select className="form-select" value={mercado} onChange={(event) => setMercado(event.target.value)}><option value="">Todos los mercados</option>{catalogos.mercados.map((item) => <option key={item.codigo} value={item.codigo}>{item.nombre}</option>)}</select></label>
              <label><span>Ejercicio</span><input className="form-control" inputMode="numeric" maxLength="4" onChange={(event) => setEjercicio(event.target.value.replace(/\D/g, ""))} placeholder="Todos los años" value={ejercicio} /></label>
              <label><span>Origen</span><select className="form-select" value={origen} onChange={(event) => setOrigen(event.target.value)}><option value="">Todos los orígenes</option>{catalogos.origenes?.map((item) => <option key={item.codigo} value={item.codigo}>{item.descripcion}</option>)}</select></label>
              <button className="clear-filters" type="button" onClick={() => { setBusqueda(""); setMercado(""); setEjercicio(""); setOrigen(""); }}>Limpiar filtros</button>
            </div>
          </section>

          <section className="results-card">
            <div className="results-header">
              <div><h2>Registros tributarios</h2><p>Datos persistidos en el mantenedor.</p></div>
              <div className="results-tools"><span className="records-count">{cargando ? "Cargando…" : `${registros.length} registros`}</span></div>
            </div>
            <div className="table-responsive">
              <table className="table records-table">
                <thead><tr><th>CÓDIGO</th><th>INSTRUMENTO</th><th>MERCADO</th><th>EJERCICIO</th><th>FECHA DE PAGO</th><th>DESCRIPCIÓN</th><th>FACTOR ACTUALIZACIÓN</th><th>ORIGEN</th><th>ÁMBITO</th><th>ESTADO</th><th /></tr></thead>
                <tbody>
                  {registros.map((registro) => {
                    const puedeModificar = sesion.rol === "AUDITOR" ? false
                      : sesion.rol === "CORREDOR" ? registro.corredor === sesion.corredor_id
                        : sesion.rol === "OPERADOR_BOLSA" ? registro.corredor === null
                          : false;
                    return (
                      <tr key={registro.id}>
                        <td><span className="code-cell">CL-{String(registro.id).padStart(4, "0")}</span></td>
                        <td><strong className="instrument-name">{registro.codigo_instrumento}</strong><span className="sequence">Sec. {registro.secuencia_evento}</span></td>
                        <td>{registro.mercado_nombre}</td><td>{registro.ejercicio}</td><td>{mostrarFecha(registro.fecha_pago)}</td><td>{registro.descripcion_dividendo || "—"}</td>
                        <td><span className="factor-value">{registro.factor_actualizacion}</span></td>
                        <td><span className="origin-tag">{origenes[registro.origen_codigo] || registro.origen_codigo}</span></td>
                        <td>{registro.corredor_nombre || "Bolsa"}</td>
                        <td><span className="status-tag current"><i />Vigente</span></td>
                        <td>{puedeModificar && <div className="row-actions">
                          <button className="row-action edit" type="button" onClick={() => abrirEdicion(registro)}>Editar</button>
                          <button className="row-action" type="button" onClick={() => eliminarRegistro(registro)}>Eliminar</button>
                        </div>}</td>
                      </tr>
                    );
                  })}
                  {!cargando && registros.length === 0 && <tr><td className="empty-row" colSpan="11">No hay calificaciones que coincidan con los filtros.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="table-footer"><span>{registros.length} registros encontrados</span></div>
          </section>

          <footer className="page-footer"><span>NUAM · Mantenedor Centralizado de Calificaciones Tributarias</span><span>Versión inicial · 2026</span></footer>
          </>}
        </div>
      </main>

      {modalAbierto && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModalAbierto(false); }}>
          <section className="create-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div className="modal-heading"><div><div className="eyebrow">NUEVO REGISTRO</div><h2 id="modal-title">Datos básicos</h2></div><button className="modal-close" type="button" onClick={() => setModalAbierto(false)} aria-label="Cerrar">×</button></div>
            <p className="modal-description">Registra los datos básicos del evento. El origen y el corredor se determinan en el servidor según tu rol.</p>
            <form onSubmit={crearRegistro}>
              <label>Instrumento<select className="form-select" name="instrumento" required defaultValue=""><option value="" disabled>Selecciona un instrumento</option>{instrumentosVisibles.map((item) => <option key={item.id} value={item.id}>{item.codigo} · {item.mercado_nombre}</option>)}</select></label>
              <div className="modal-fields"><label>Ejercicio<input className="form-control" name="ejercicio" type="number" defaultValue="2025" min="1900" max="2200" required /></label><label>Número de dividendo<input className="form-control" name="dividendo" type="number" min="0" defaultValue="0" required /></label></div>
              <div className="modal-fields"><label>Secuencia del evento<input className="form-control" name="secuencia" type="number" min="10001" required placeholder="Mayor a 10.000" /></label><label>Fecha de pago<input className="form-control" name="fecha" type="date" required /></label></div>
              <label>Descripción del dividendo<input className="form-control" name="descripcion" maxLength="200" placeholder="Descripción" /></label>
              <div className="modal-warning">El registro se guardará en PostgreSQL y quedará auditado.</div>
              <div className="modal-actions"><button className="btn btn-light" type="button" onClick={() => setModalAbierto(false)}>Cancelar</button><button className="btn btn-primary" type="submit">Guardar calificación</button></div>
            </form>
          </section>
        </div>
      )}
      {registroEnEdicion && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setRegistroEnEdicion(null); }}>
          <section className="create-modal" role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
            <div className="modal-heading"><div><div className="eyebrow">EDITAR REGISTRO</div><h2 id="edit-modal-title">{registroEnEdicion.codigo_instrumento} · {registroEnEdicion.ejercicio}</h2></div><button className="modal-close" type="button" onClick={() => setRegistroEnEdicion(null)} aria-label="Cerrar">×</button></div>
            <p className="modal-description">Corrige los datos del evento. El cambio se audita y requiere que la versión del registro siga vigente.</p>
            <form key={registroEnEdicion.id} onSubmit={guardarEdicion}>
              <div className="modal-fields"><label>Ejercicio<input className="form-control" name="ejercicio" type="number" defaultValue={registroEnEdicion.ejercicio} min="1900" max="2200" required /></label><label>Número de dividendo<input className="form-control" name="dividendo" type="number" defaultValue={registroEnEdicion.numero_dividendo} min="0" required /></label></div>
              <div className="modal-fields"><label>Secuencia del evento<input className="form-control" name="secuencia" type="number" defaultValue={registroEnEdicion.secuencia_evento} min="10001" required /></label><label>Fecha de pago<input className="form-control" name="fecha" type="date" defaultValue={registroEnEdicion.fecha_pago} required /></label></div>
              <label>Descripción del dividendo<input className="form-control" name="descripcion" defaultValue={registroEnEdicion.descripcion_dividendo} maxLength="200" placeholder="Descripción" /></label>
              <div className="modal-warning">Los montos y factores no se modifican aquí; dependen de reglas de negocio aún por confirmar.</div>
              <div className="modal-actions"><button className="btn btn-light" type="button" onClick={() => setRegistroEnEdicion(null)}>Cancelar</button><button className="btn btn-primary" type="submit">Guardar cambios</button></div>
            </form>
          </section>
        </div>
      )}
      <button className="logout-shortcut" onClick={salir} type="button" title="Cerrar sesión"><LogOut size={15} /></button>
    </div>
  );
}

export default App;
