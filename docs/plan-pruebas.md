# Plan y protocolo de pruebas NUAM

## Control del documento

| Campo | Valor |
|---|---|
| Sistema | Mantenedor Centralizado de Calificaciones Tributarias |
| Versión | 1.0 |
| Objetivo | Definir casos repetibles, resultados esperados y evidencia de ejecución |
| Alcance | Autenticación, permisos, calificaciones, cargas, persistencia y entorno local |

## Alcance y criterios

Las pruebas automatizadas verifican los comportamientos listados en la matriz
con la base PostgreSQL de pruebas y dependencias simuladas cuando corresponde.
Los casos manuales están identificados expresamente y no se consideran aprobados
hasta registrar evidencia de ejecución. La suite automatizada no reemplaza la
validación con usuarios del negocio, la homologación tributaria ni pruebas de
carga/estrés.

Los nombres de las columnas 34–37 se respaldan en el HDU. Sus tipos y fórmulas
son provisionales hasta confirmación docente. La suite verifica que queden
marcados como provisionales, pero no certifica que esas propuestas sean reglas
tributarias correctas.

## Entorno de ejecución

- Docker Compose con PostgreSQL 16, MongoDB 7, API Django y cliente React/Vite.
- PostgreSQL con roles de administración, aplicación, migración, reporte y
  respaldo; MongoDB con cuentas de aplicación, lectura y respaldo.
- PostgreSQL requiere SCRAM/TLS; el tráfico de la aplicación a MongoDB usa
  autenticación y TLS. Las conexiones de la base están aisladas en una red
  interna de Compose y sus puertos no se publican al host.
- Entorno local Python con dependencias de `backend/requirements-dev.txt`.
- Node/npm según `frontend/package-lock.json`.
- Para ejecución automatizada se usan las credenciales efímeras definidas para
  CI; nunca utilizar datos reales ni credenciales productivas.
- Las pruebas de worker usan un fake de MongoDB y verifican las llamadas,
  reintentos y compensaciones. La suite normal no demuestra disponibilidad,
  rendimiento ni recuperación de una instancia real de MongoDB.

## Protocolo reproducible

Desde PowerShell en la raíz del proyecto:

1. Levantar los servicios:

   ```powershell
   docker compose up -d postgres mongo backend outbox-worker frontend
   ```

2. Comprobar migraciones y configuración:

   ```powershell
   docker compose exec backend python manage.py check
   docker compose exec backend python manage.py makemigrations --check --dry-run
   ```

3. Ejecutar backend:

   ```powershell
   docker compose exec backend python manage.py test apps.cuentas.tests apps.calificaciones.tests apps.calificaciones.test_calculo
   ```

4. Ejecutar calidad estática y compilación:

   ```powershell
   Set-Location backend
   .\.venv\Scripts\python.exe -m flake8 --config .flake8 apps\cuentas apps\calificaciones config
   .\.venv\Scripts\python.exe -m bandit -r apps config -ll
   Set-Location ..\frontend
   npm run build
   Set-Location ..
   ```

5. Para los casos manuales, iniciar sesión con un usuario de prueba de cada rol,
   realizar las acciones de la matriz y guardar captura o salida sin datos
   personales. Registrar la versión del código, fecha, entorno, usuario/rol,
   resultado esperado, resultado observado y evidencia.

6. Ante una discrepancia, guardar el identificador de caso, entrada utilizada,
   respuesta/estado observado y log pertinente; no marcar el caso como aprobado
   hasta volver a ejecutarlo tras la corrección.

## Casos automatizados y trazabilidad

| ID | Área / escenario | Resultado esperado | Prueba automatizada |
|---|---|---|---|
| AUT-01 | Cambio de clave temporal y restricciones previas | La cuenta cambia su clave; APIs permanecen restringidas hasta hacerlo | `apps/cuentas/tests/test_auth.py`, `apps/cuentas/tests/test_admin_api.py` |
| SEG-01 | Gestión administrativa y contraseña temporal | Solo administradores gestionan usuarios; secretos no aparecen en auditoría | `apps/cuentas/tests/test_admin_api.py` |
| CAL-01 | Visibilidad por rol y corredor | El corredor ve sus registros y los de Bolsa, no los de otro corredor | `apps/calificaciones/tests/test_api.py` |
| CAL-02 | Escritura y concurrencia optimista | Se requiere versión vigente; cambios obsoletos no pisan datos | `apps/calificaciones/tests/test_api.py` |
| DB-01 | Llaves, rangos y auditoría inmutable | Restricciones de base rechazan duplicados, montos/factores inválidos y mutaciones del log | `apps/calificaciones/tests/test_modelos.py` |
| MAT-01 | Cálculo y precisión | Denominador cero se rechaza; factores se redondean y validan según rangos aprobados | `apps/calificaciones/test_calculo.py` |
| CARG-01 | Plantillas CSV/XLSX | Se exponen los 37 encabezados esperados | `apps/calificaciones/tests/test_cargas_api.py::test_plantillas_csv_y_xlsx_exponen_las_37_columnas` |
| CARG-02 | Previsualización válida | Se guarda borrador temporal, no se crean calificaciones hasta confirmar | `apps/calificaciones/tests/test_cargas_api.py::test_previsualiza_csv_guarda_borrador_temporal_sin_confirmarlo` |
| CARG-03 | Datos inválidos | Se devuelven errores y se encolan para registrar rechazos; no se aplican filas válidas | `apps/calificaciones/tests/test_cargas_api.py::test_error_de_datos_persiste_rechazo_pendiente_de_mongo`, `test_registra_rechazos_en_mongo_sin_aplicar_filas_validas` |
| CARG-04 | Suma de factores 8–16 | La suma superior a 1 se rechaza | `apps/calificaciones/tests/test_cargas_api.py::test_suma_de_factores_se_valida_en_columnas_8_a_16` |
| CARG-05 | Llave ya existente por ámbito | Se rechaza en el mismo ámbito y se conserva la separación Bolsa/corredor | `apps/calificaciones/tests/test_cargas_api.py::test_llave_existente_se_rechaza_solo_en_el_mismo_ambito` |
| CARG-06 | Aislamiento de borradores | Usuario distinto no lista, lee ni confirma la carga ajena | `apps/calificaciones/tests/test_cargas_api.py::test_estado_y_lista_de_cargas_solo_exponen_al_propietario` |
| CARG-07 | Confirmación repetida | Solo se crea un outbox por carga; procesamiento no duplica calificaciones | `apps/calificaciones/tests/test_cargas_api.py::test_confirma_y_procesa_outbox_idempotente_en_mongo_y_postgres` |
| CARG-08 | MongoDB no disponible | Carga sigue pendiente, se programa reintento y no se confirma en PostgreSQL | `apps/calificaciones/tests/test_cargas_api.py::test_reintenta_falla_de_mongo_sin_confirmar_el_lote` |
| CARG-09 | Conflicto tardío de llave | Mongo se compensa y el lote acaba fallido sin sobrescribir registros | `apps/calificaciones/tests/test_cargas_api.py::test_compensa_mongo_si_aparece_conflicto_de_llave_al_persistir` |
| CARG-10 | Mongo no disponible durante compensación | Se reintenta la limpieza sin perder el motivo del conflicto original | `apps/calificaciones/tests/test_cargas_api.py::test_reintenta_compensacion_sin_perder_el_motivo_original` |
| CARG-11 | Vencimiento | El worker cancela borradores vencidos y elimina el contenido temporal | `apps/calificaciones/tests/test_cargas_api.py::test_worker_cancela_borradores_vencidos_y_limpia_datos_temporales` |
| CARG-12 | Entrada/formato/rol inválido | Cabeceras incorrectas, archivos no admitidos y roles sin permiso son rechazados | `apps/calificaciones/tests/test_cargas_api.py::test_rechaza_encabezados_incorrectos_archivos_no_admitidos_y_roles` |
| CARG-13 | Metadatos y rechazos Mongo | Se registra la metadata de carga y cada fila rechazada de forma idempotente; un archivo con errores no crea calificaciones | `apps/calificaciones/tests/test_cargas_api.py::test_registra_rechazos_en_mongo_sin_aplicar_filas_validas` |
| CAT-01 | Homologación inicial 34–37 | Nombres del HDU y tipos/fórmulas provisionales aparecen como metadata del catálogo | `apps/calificaciones/tests/test_catalogos_api.py::test_catalogo_expone_nombres_y_reglas_provisionales_homologadas` |
| CAT-02 | Edición de catálogo | Solo administrador cambia metadata; cambios se auditan y no alteran cálculos | `apps/calificaciones/tests/test_catalogos_api.py::test_administrador_edita_metadatos_y_se_audita_sin_cambiar_calculos`, `test_catalogo_no_administrador_no_puede_editar`, `test_tipo_invalido_se_rechaza_y_no_actualiza_el_catalogo` |
| CAT-03 | Semilla repetible | Ejecutar la semilla no revierte ediciones administrativas | `apps/calificaciones/tests/test_catalogos_api.py::test_semilla_idempotente_preserva_ediciones_del_catalogo` |

## Relación con la rúbrica

| Criterio | Evidencia automatizada/documental | Validación aún necesaria |
|---|---|---|
| 3.1.1.1 Coherencia interfaz-negocio | Casos CAL, CARG y CAT; catálogo identifica campos provisionales | Confirmación docente de tipos/fórmulas y aprobación de flujos por cliente |
| 3.1.1.2 Lineamientos estéticos/funcionales | Build frontend; pantallas existentes | UI-01, comparación con Figma en escritorio/tablet/móvil |
| 3.1.2.3 Estructura de base de datos | DB-01, migraciones Django, restricciones y DB-02 en Mongo real | UI-02 para comprobar persistencia completa desde navegador |
| 3.1.2.4 Optimización/normalización | Relaciones e índices declarados en modelos; lotes de persistencia | PERF-01 y análisis de consultas con volumen acordado |
| 3.1.3.5 Patrones de seguridad | SEG-01, controles por rol, Bandit y aislamiento CARG-06 | Revisión de configuración productiva y gestión de secretos |
| 3.1.3.6 Colaboración en equipo | Documentación de decisiones y protocolo compartido | Añadir evidencias reales de tareas, revisiones y acuerdos del equipo |
| 3.1.4.7 Configuración del entorno | Compose y pasos reproducibles documentados | Validar desde una instalación limpia en equipo del evaluador |
| 3.1.4.8 Documentación | Este protocolo y README | Mantener resultados de cada ejecución con evidencia |
| 3.1.5.9 Cobertura del plan de pruebas | Casos automatizados y pendientes identificados | Acordar umbrales de estrés y cerrar casos manuales |
| 3.1.5.10 Ejecución del protocolo | Comandos reproducibles de este documento | Registrar salidas/URL de CI y ejecución manual |
| 3.1.5.11 Validación de resultados | Resultado esperado definido por caso | Registrar resultado real y análisis de discrepancias |
| 3.1.6.12 Comparación esperado/obtenido | Plantilla de registro de ejecución | Completar tabla con salidas verificables, sin inferir resultados |

## Casos manuales pendientes

| ID | Escenario | Resultado esperado | Evidencia |
|---|---|---|---|
| UI-01 | Revisar pantallas en escritorio, tablet y móvil frente a las referencias de Figma | Navegación, formularios, tablas, estados y accesibilidad visual coherentes con cada rol | Pendiente |
| UI-02 | Flujo completo de carga desde navegador contra MongoDB real | Vista previa, confirmación y cambio de estado hasta `CONFIRMADA`; la fila aparece en PostgreSQL y el detalle en MongoDB | Aprobado 2026-10-28: `prueba-e2e.csv`, 1 fila válida; estado final `CONFIRMADA`; PostgreSQL 1 calificación y MongoDB metadata + detalle, 0 rechazos. Se desactivaron el usuario y el instrumento temporales; los datos de carga quedan como evidencia local. |
| DB-02 | Inspeccionar índices y restricciones desplegados en PostgreSQL/MongoDB | Migraciones e índices corresponden al modelo aprobado; ninguna colección queda sin validar | Aprobado 2026-10-28: migraciones 0008/0009 aplicadas; validadores e índices de las tres colecciones verificados en MongoDB real; formato inválido y duplicados rechazados |
| OPS-01 | Detener MongoDB y restaurarlo durante una carga | El worker conserva el lote pendiente, reintenta y termina sin duplicados | Pendiente |
| OPS-02 | Reiniciar worker y API con una carga en cola | El outbox persiste y otro worker retoma el proceso sin perder ni duplicar datos | Pendiente |
| PERF-01 | Ejecutar carga con tamaño límite y concurrencia representativa | Memoria, duración, consultas y errores permanecen dentro de límites acordados | Pendiente de fijar umbrales con el equipo |
| BIZ-01 | Validar reglas funcionales de montos/factores y columnas 34–37 con cliente/docente | Importación coincide con planilla tributaria homologada | Pendiente de confirmación funcional |

## Registro de ejecución

Completar este registro en cada validación formal. No inferir el resultado a
partir del estado del pipeline; conservar la salida real del comando o la URL
del job.

| Fecha/hora | Commit/versión | Entorno | Comando o casos | Resultado observado | Discrepancias/evidencia |
|---|---|---|---|---|---|
| 2026-10-28 | Árbol de trabajo; sin SHA registrado | Windows, Python 3.13.14, PostgreSQL 16 y MongoDB 7 en Docker; frontend npm local | 76 pruebas Django; `check`; `makemigrations --check --dry-run`; flake8; Bandit `-ll`; `npm run build`; validadores/índices Mongo; flujo UI-02 | 76 pruebas OK; checks de Django, migraciones, lint y build correctos; Bandit sin hallazgos medios/altos; esquema real aceptó documentos válidos y rechazó formato inválido/duplicados; UI-02 completado hasta `CONFIRMADA` | Backend y worker reiniciados; migraciones 0008/0009 aplicadas. Se corrigió el guardado del perfil nulo en frontend y se permitió el host interno `backend` usado por el proxy Vite. El usuario y el instrumento de prueba quedaron desactivados; los registros de carga se conservan como evidencia local. |

## Limitaciones conocidas y acciones

- Los fakes cubren el contrato de operaciones Mongo usadas por el worker, pero
  no reemplazan una integración automatizada del flujo completo contra MongoDB
  real. El esquema real `nuam_cargas`, sus restricciones y el flujo UI-02 fueron
  verificados manualmente en el entorno local.
- Las conexiones locales usan una CA de desarrollo dentro de volúmenes Docker;
  no se debe reutilizar ese esquema de certificados en producción. La cifración
  en reposo depende de BitLocker/volumen cifrado del host. La programación de
  respaldos fuera del equipo y su prueba de restauración siguen pendientes de
  definir para el destino real.
- Los eventos DDL de PostgreSQL se registran como metadatos en
  `registro_cambios_ddl`; no se habilita el log de sentencias SQL completas
  para evitar que una sentencia de administración registre credenciales.
- No existe suite automatizada de componentes frontend; UI-01 es manual.
- Los umbrales de estrés, recuperación y retención deben acordarse antes de
  certificar esos escenarios.
- La confirmación docente de los tipos y fórmulas propuestos para las columnas
  34–37 y la validación del cliente son prerrequisitos para afirmar cobertura
  completa del negocio.
