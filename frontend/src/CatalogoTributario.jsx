import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { ApiError, solicitudApi } from "./api.js";

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
  return error.message || "No fue posible actualizar el catálogo.";
}

function CatalogoTributario() {
  const [columnas, setColumnas] = useState([]);
  const [ediciones, setEdiciones] = useState({});
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(null);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");

  useEffect(() => {
    let vigente = true;
    solicitudApi("/api/v1/catalogos/")
      .then((respuesta) => {
        if (!vigente) return;
        setColumnas(respuesta.columnas_tributarias);
        setEdiciones(
          Object.fromEntries(
            respuesta.columnas_tributarias.map((columna) => [
              columna.nro_columna,
              {
                nombre_homologado: columna.nombre_homologado,
                tipo_dato: columna.tipo_dato,
                formula: columna.formula,
                reglas_provisionales: columna.reglas_provisionales,
              },
            ]),
          ),
        );
      })
      .catch((caught) => {
        if (vigente) setError(mostrarError(caught));
      })
      .finally(() => {
        if (vigente) setCargando(false);
      });
    return () => {
      vigente = false;
    };
  }, []);

  function actualizarEdicion(numero, campo, valor) {
    setEdiciones((actuales) => ({
      ...actuales,
      [numero]: {
        ...actuales[numero],
        [campo]: valor,
      },
    }));
  }

  async function guardar(numero) {
    setGuardando(numero);
    setError("");
    setMensaje("");
    try {
      const actualizada = await solicitudApi(
        `/api/v1/catalogos/columnas/${numero}/`,
        {
          method: "PATCH",
          body: JSON.stringify(ediciones[numero]),
        },
      );
      setColumnas((actuales) =>
        actuales.map((columna) =>
          columna.nro_columna === numero ? actualizada : columna,
        ),
      );
      setMensaje(`Se actualizaron los metadatos de la columna ${numero}.`);
    } catch (caught) {
      setError(mostrarError(caught));
    } finally {
      setGuardando(null);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">CONFIGURACIÓN TRIBUTARIA</div>
          <h1>Catálogo tributario</h1>
          <p>Administra nombres y metadatos de las columnas tributarias.</p>
        </div>
      </section>
      <div className="api-alert info" role="note">
        Los cambios se guardan en PostgreSQL y quedan auditados. El tipo y la
        fórmula son metadatos descriptivos: editarlos no cambia los cálculos ni
        las validaciones de las cargas.
      </div>
      <div className="api-alert info" role="note">
        Las columnas 34–37 tienen sus nombres tomados del HDU. El tipo y la
        fórmula propuestos son provisionales hasta confirmación del docente.
      </div>
      {error && <div className="api-alert error" role="alert">{error}</div>}
      {mensaje && <div className="api-alert success" role="status">{mensaje}</div>}
      <section className="results-card catalogo-tributario">
        <div className="results-header">
          <div>
            <h2>Columnas 8–37</h2>
            <p>
              {cargando
                ? "Cargando catálogo…"
                : `${columnas.length} definiciones · Solo administración`}
            </p>
          </div>
        </div>
        <div className="table-responsive">
          <table className="table records-table">
            <thead>
              <tr>
                <th>N.º</th>
                <th>NOMBRE HOMOLOGADO</th>
                <th>TIPO</th>
                <th>FÓRMULA / DESCRIPCIÓN</th>
                <th>ESTADO</th>
                <th>ACCIÓN</th>
              </tr>
            </thead>
            <tbody>
              {columnas.map((columna) => {
                const edicion = ediciones[columna.nro_columna];
                if (!edicion) return null;
                return (
                  <tr key={columna.nro_columna}>
                    <td>{columna.nro_columna}</td>
                    <td>
                      <input
                        aria-label={`Nombre de columna ${columna.nro_columna}`}
                        className="form-control catalogo-input"
                        maxLength="250"
                        onChange={(evento) =>
                          actualizarEdicion(
                            columna.nro_columna,
                            "nombre_homologado",
                            evento.target.value,
                          )
                        }
                        value={edicion.nombre_homologado}
                      />
                    </td>
                    <td>
                      <select
                        aria-label={`Tipo de columna ${columna.nro_columna}`}
                        className="form-select catalogo-input"
                        onChange={(evento) =>
                          actualizarEdicion(
                            columna.nro_columna,
                            "tipo_dato",
                            evento.target.value,
                          )
                        }
                        value={edicion.tipo_dato}
                      >
                        <option value="MONTO">Monto</option>
                        <option value="TASA">Tasa</option>
                      </select>
                    </td>
                    <td>
                      <input
                        aria-label={`Fórmula de columna ${columna.nro_columna}`}
                        className="form-control catalogo-input"
                        maxLength="200"
                        onChange={(evento) =>
                          actualizarEdicion(
                            columna.nro_columna,
                            "formula",
                            evento.target.value,
                          )
                        }
                        value={edicion.formula}
                      />
                    </td>
                    <td>
                      <label className="catalogo-provisional">
                        <input
                          checked={edicion.reglas_provisionales}
                          onChange={(evento) =>
                            actualizarEdicion(
                              columna.nro_columna,
                              "reglas_provisionales",
                              evento.target.checked,
                            )
                          }
                          type="checkbox"
                        />
                        Provisional
                      </label>
                    </td>
                    <td>
                      <button
                        aria-label={`Guardar columna ${columna.nro_columna}`}
                        className="btn btn-light catalogo-save"
                        disabled={guardando === columna.nro_columna || cargando}
                        onClick={() => guardar(columna.nro_columna)}
                        type="button"
                      >
                        <Save size={14} />
                        {guardando === columna.nro_columna ? "Guardando…" : "Guardar"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!cargando && columnas.length === 0 && (
                <tr>
                  <td className="empty-row" colSpan="6">
                    El catálogo no tiene columnas activas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      <footer className="page-footer">
        <span>NUAM · Catálogo tributario</span>
        <span>Ediciones auditadas</span>
      </footer>
    </>
  );
}

export default CatalogoTributario;
