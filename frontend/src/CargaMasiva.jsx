import { useEffect, useState } from "react";
import { Download, FileUp, ShieldCheck } from "lucide-react";
import { ApiError, descargarArchivo, solicitudApi } from "./api.js";

function mostrarError(error) {
  const detalles = error instanceof ApiError ? error.details : null;
  if (detalles && typeof detalles === "object") {
    const texto = Object.entries(detalles)
      .map(([campo, valor]) => {
        const detalle = Array.isArray(valor) ? valor.join(" ") : valor;
        return typeof detalle === "string" ? `${campo}: ${detalle}` : "";
      })
      .filter(Boolean)
      .join(" · ");
    if (texto) return texto;
  }
  return error.message || "No fue posible procesar el archivo.";
}

function CargaMasiva() {
  const [tipo, setTipo] = useState("MONTOS");
  const [archivo, setArchivo] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const [descargando, setDescargando] = useState("");
  const [cargas, setCargas] = useState([]);
  const [confirmando, setConfirmando] = useState(null);

  useEffect(() => {
    let activa = true;
    solicitudApi("/api/v1/cargas/")
      .then((respuesta) => {
        if (activa) setCargas(respuesta);
      })
      .catch((caught) => {
        if (activa) setError(mostrarError(caught));
      });
    return () => {
      activa = false;
    };
  }, []);

  const idsPendientes = cargas
    .filter((carga) => carga.estado === "PENDIENTE_MONGO")
    .map((carga) => carga.id)
    .join(",");

  useEffect(() => {
    if (!idsPendientes) return undefined;
    let activa = true;
    let consultando = false;
    const consultarEstados = async () => {
      if (consultando) return;
      consultando = true;
      try {
        const pendientes = idsPendientes.split(",").filter(Boolean);
        const estados = await Promise.all(
          pendientes.map((id) => solicitudApi(`/api/v1/cargas/${id}/`)),
        );
        if (activa) {
          setCargas((actuales) =>
            actuales.map(
              (carga) => estados.find((estado) => estado.id === carga.id) || carga,
            ),
          );
        }
      } catch (caught) {
        if (activa) setError(mostrarError(caught));
      } finally {
        consultando = false;
      }
    };
    const intervalo = window.setInterval(consultarEstados, 3000);
    return () => {
      activa = false;
      window.clearInterval(intervalo);
    };
  }, [idsPendientes]);

  function guardarCarga(carga) {
    setCargas((actuales) => {
      const existe = actuales.some((actual) => actual.id === carga.id);
      const actualizadas = existe
        ? actuales.map((actual) => (actual.id === carga.id ? carga : actual))
        : [carga, ...actuales];
      return actualizadas.slice(0, 20);
    });
  }

  async function descargarPlantilla(formato) {
    setError("");
    setDescargando(formato);
    try {
      const { archivo: contenido, disposicion } = await descargarArchivo(
        `/api/v1/cargas/plantilla/?tipo=${tipo}&formato=${formato}`,
      );
      const coincidencia = disposicion.match(/filename="([^"]+)"/i);
      const nombre = coincidencia?.[1] || `plantilla_nuam_${tipo.toLowerCase()}.${formato.toLowerCase()}`;
      const url = URL.createObjectURL(contenido);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = nombre;
      document.body.append(enlace);
      enlace.click();
      enlace.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {
      setError(mostrarError(caught));
    } finally {
      setDescargando("");
    }
  }

  async function previsualizar(evento) {
    evento.preventDefault();
    if (!archivo) {
      setError("Selecciona un archivo CSV o XLSX.");
      return;
    }
    if (archivo.size > 50 * 1024 * 1024) {
      setError("El archivo supera el límite de 50 MB.");
      return;
    }
    setCargando(true);
    setError("");
    setResultado(null);
    const formulario = new FormData();
    formulario.append("tipo", tipo);
    formulario.append("archivo", archivo);
    try {
      const respuesta = await solicitudApi("/api/v1/cargas/previsualizar/", {
        method: "POST",
        body: formulario,
      });
      setResultado(respuesta);
      if (respuesta.carga_id) {
        const estado = await solicitudApi(`/api/v1/cargas/${respuesta.carga_id}/`);
        guardarCarga(estado);
      }
    } catch (caught) {
      setError(mostrarError(caught));
    } finally {
      setCargando(false);
    }
  }

  async function confirmarCarga(cargaId) {
    setConfirmando(cargaId);
    setError("");
    try {
      const estado = await solicitudApi(
        `/api/v1/cargas/${cargaId}/confirmar/`,
        { method: "POST" },
      );
      guardarCarga(estado);
    } catch (caught) {
      setError(mostrarError(caught));
      if (caught instanceof ApiError && [409, 410].includes(caught.statusCode)) {
        try {
          setCargas(await solicitudApi("/api/v1/cargas/"));
        } catch (refreshError) {
          setError(
            `${mostrarError(caught)} No se pudo actualizar el estado: ${mostrarError(refreshError)}`,
          );
        }
      }
    } finally {
      setConfirmando(null);
    }
  }

  function estadoCarga(estado) {
    return {
      PREVISUALIZADA: "Lista para confirmar",
      PENDIENTE_MONGO: "Pendiente de confirmación",
      CONFIRMADA: "Confirmada",
      FALLIDA: "Fallida",
      CANCELADA: "Vencida",
    }[estado] || estado;
  }

  const cargaResultado = cargas.find(
    (carga) => carga.id === resultado?.carga_id,
  );

  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">IMPORTACIÓN</div>
          <h1>Carga masiva</h1>
          <p>Valida y confirma archivos de montos o factores con seguimiento del proceso.</p>
        </div>
      </section>
      <div className="api-alert info" role="note">
        <ShieldCheck size={15} />
        El archivo original no se conserva. Las filas válidas quedan temporalmente en
        PostgreSQL durante 30 minutos y solo se aplican tras confirmar y recibir el
        acuse de MongoDB.
      </div>
      {error && <div className="api-alert error" role="alert">{error}</div>}
      <section className="upload-card">
        <div className="upload-section-heading"><div className="upload-icon"><FileUp size={19} /></div><div><h2>Preparar archivo</h2><p>Selecciona el tipo de carga y descarga una plantilla compatible.</p></div></div>
        <div className="upload-settings">
          <label><span>Tipo de datos</span><select className="form-select" value={tipo} onChange={(event) => { setTipo(event.target.value); setArchivo(null); setResultado(null); }}><option value="MONTOS">Montos tributarios</option><option value="FACTORES">Factores</option></select></label>
          <div className="template-downloads"><span>Plantillas vacías</span><div><button className="export-button" disabled={Boolean(descargando)} onClick={() => descargarPlantilla("CSV")} type="button"><Download size={14} />{descargando === "CSV" ? "Preparando…" : "CSV"}</button><button className="export-button" disabled={Boolean(descargando)} onClick={() => descargarPlantilla("XLSX")} type="button"><Download size={14} />{descargando === "XLSX" ? "Preparando…" : "Excel XLSX"}</button></div></div>
        </div>
        <form className="upload-form" onSubmit={previsualizar}>
          <label className="file-picker">
            <span>Archivo de origen</span>
            <input accept=".csv,.xlsx" className="form-control" onChange={(event) => { setArchivo(event.target.files?.[0] || null); setResultado(null); setError(""); }} type="file" />
            <small>Solo CSV (UTF-8) o Excel XLSX · Máximo 50 MB y 10.000 filas</small>
          </label>
          {archivo && <div className="selected-file"><FileUp size={15} /><span>{archivo.name}</span><small>{(archivo.size / 1024).toFixed(1)} KB</small></div>}
          <div className="upload-actions"><span>El borrador válido vence en 30 minutos; la carga aún no está aplicada.</span><button className="btn btn-primary create-button" disabled={cargando || !archivo} type="submit">{cargando ? "Validando…" : "Validar y previsualizar"}</button></div>
        </form>
      </section>

      {resultado && (
        <section className="results-card upload-results">
          <div className="results-header">
            <div><h2>Resultado de validación</h2><p>{resultado.archivo} · {resultado.tipo} · {resultado.formato}</p></div>
            <div className="results-tools"><span className="records-count">{resultado.filas_validas} válidas · {resultado.filas_error} con errores</span></div>
          </div>
          <div className="upload-summary">
            <div><strong>{resultado.total_filas}</strong><span>filas revisadas</span></div>
            <div><strong>{resultado.filas_validas}</strong><span>sin errores</span></div>
            <div><strong>{resultado.filas_error}</strong><span>requieren corrección</span></div>
          </div>
          {resultado.advertencias.length > 0 && <div className="upload-warnings"><strong>Alcance de esta previsualización</strong><ul>{resultado.advertencias.map((advertencia) => <li key={advertencia}>{advertencia}</li>)}</ul></div>}
          {resultado.errores.length > 0 && <div className="upload-errors"><strong>Errores encontrados{resultado.errores_truncados ? " (se muestran hasta 100)" : ""}</strong><ul>{resultado.errores.map((item, index) => <li key={`${item.fila}-${index}`}>Fila {item.fila}: {item.detalle}</li>)}</ul></div>}
          {resultado.confirmacion_habilitada && <div className="upload-warnings"><strong>{cargaResultado && cargaResultado.estado !== "PREVISUALIZADA" ? "Estado de la carga" : "Borrador listo"}</strong><p>{cargaResultado?.mensaje || "Al confirmar, se comprobarán nuevamente las llaves. La carga puede tardar mientras MongoDB confirma el almacenamiento."}</p>{(!cargaResultado || cargaResultado.estado === "PREVISUALIZADA") && <button className="btn btn-primary create-button" disabled={confirmando === resultado.carga_id} onClick={() => confirmarCarga(resultado.carga_id)} type="button">{confirmando === resultado.carga_id ? "Enviando…" : "Confirmar carga"}</button>}</div>}
          <div className="table-responsive">
            <table className="table records-table">
              <thead><tr><th>FILA</th><th>ESTADO</th><th>INSTRUMENTO</th><th>MERCADO</th><th>EJERCICIO</th><th>FECHA DE PAGO</th><th>VALORES</th></tr></thead>
              <tbody>
                {resultado.muestra.map((fila) => (
                  <tr key={fila.fila}>
                    <td>{fila.fila}</td><td><span className={`status-tag ${fila.valida ? "current" : "draft"}`}><i />{fila.valida ? "Válida" : "Corregir"}</span></td>
                    <td>{fila.datos.codigo_instrumento || "—"}</td><td>{fila.datos.mercado || "—"}</td><td>{fila.datos.ejercicio || "—"}</td><td>{fila.datos.fecha_pago || "—"}</td>
                    <td><details className="audit-details"><summary>Ver fila</summary><div className="audit-json"><pre>{JSON.stringify(fila.datos, null, 2)}</pre></div></details></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="upload-preview-footer">La carga permanece sin aplicar hasta recibir confirmación de MongoDB.</div>
        </section>
      )}
      <section className="results-card upload-results">
        <div className="results-header"><div><h2>Cargas recientes</h2><p>El estado se actualiza automáticamente mientras se procesa una carga.</p></div></div>
        <div className="table-responsive">
          <table className="table records-table">
            <thead><tr><th>ARCHIVO</th><th>TIPO</th><th>FILAS</th><th>ESTADO</th><th>DETALLE</th><th>ACCIÓN</th></tr></thead>
            <tbody>
              {cargas.map((carga) => (
                <tr key={carga.id}>
                  <td>{carga.archivo}</td><td>{carga.tipo}</td><td>{carga.filas_ok}/{carga.total_filas}</td>
                  <td><span className={`status-tag ${carga.estado === "CONFIRMADA" ? "current" : "draft"}`}><i />{estadoCarga(carga.estado)}</span></td>
                  <td>{carga.mensaje}</td>
                  <td>{carga.estado === "PREVISUALIZADA" && <button className="btn btn-light" disabled={confirmando === carga.id} onClick={() => confirmarCarga(carga.id)} type="button">{confirmando === carga.id ? "Enviando…" : "Confirmar"}</button>}{carga.estado === "PENDIENTE_MONGO" && `Intentos: ${carga.intentos}`}</td>
                </tr>
              ))}
              {cargas.length === 0 && <tr><td className="empty-row" colSpan="6">Todavía no hay cargas registradas.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <footer className="page-footer"><span>NUAM · Carga masiva</span><span>Previsualización segura</span></footer>
    </>
  );
}

export default CargaMasiva;
