# Mantenedor Centralizado de Calificaciones Tributarias

Implementación inicial del proyecto NUAM-101. El ZIP de referencia contiene 37
exportaciones PDF de pantallas de Figma, no el código fuente del diseño. La
interfaz inicial se basa en esas referencias.

## Decisiones de esta iteración

- **Cálculo:** la base configurable por variables de entorno es la suma de los
  montos 8–19. Se calculan factores para las columnas 8–37 y se redondean a
  ocho decimales usando `ROUND_HALF_UP`.
- **Denominador cero:** no se calculan factores; se rechaza la operación con un
  error de validación explícito.
- **Montos y factores:** no se aceptan montos negativos ni factores fuera de
  `[0, 1]`.
- **Suma validada:** se valida la suma de factores 8–16 y se exige que sea
  `<= 1`.
- **Llave de carga:** ejercicio, mercado/instrumento, fecha de pago y secuencia
  de evento; se aplica por ámbito Bolsa o corredor. Las filas existentes se
  rechazan y no se sobrescriben.
- **Ámbito corredor/Bolsa:** el diseño de datos deberá mantener registros
  generales (sin corredor) separados de los registros locales del corredor.
  La regla de precedencia para consulta aún requiere validación del cliente.
- **Carga masiva:** se aceptan CSV y XLSX, hasta 10.000 filas y 50 MB. Las
  filas válidas se conservan temporalmente en PostgreSQL por 30 minutos; la
  confirmación usa un outbox transaccional, reintentos idempotentes en MongoDB y
  compensación si PostgreSQL detecta un conflicto tras el acuse.
- **Instrumentos:** se distinguirá entre instrumento existente pero no inscrito
  y código de instrumento inexistente. El primero puede ingresarse manualmente;
  el segundo deberá validarse contra el catálogo.
- **Columnas 34–37:** sus nombres provienen del HDU. Los tipos y fórmulas
  iniciales son propuestas provisionales pendientes de confirmación docente.

Estas decisiones son valores iniciales para desarrollo, no homologación
tributaria definitiva. Los rangos se pueden configurar con `.env`.

## Estado

- Interfaz responsiva conectada a la API para consultar, crear, editar los datos
  del evento y eliminar lógicamente calificaciones según el rol.
- Backend Django conectado a PostgreSQL y motor de cálculo con pruebas.
- Modelos persistentes para perfiles de usuario, roles, corredores, catálogos,
  calificaciones, montos, factores, cargas y auditoría; migraciones aplicadas y
  catálogos semilla.
- Auditoría protegida contra actualización y eliminación en la aplicación y en
  PostgreSQL.
- Login JWT por correo, refresh rotatorio en cookie HttpOnly con CSRF,
  bloqueo de cuenta y permisos que validan rol/perfil vigente en PostgreSQL.
- API de consulta, alta, modificación optimista y eliminación lógica de
  calificaciones, con aislamiento por rol/corredor y auditoría transaccional.
- Formulario de inicio de sesión y mantenedor web conectados a la API; el access
  token queda en memoria y el refresh solo en cookie HttpOnly.
- La edición de los datos del evento se audita y usa control optimista de versión.
  La edición de montos y factores queda pendiente hasta homologar sus reglas.
- Visor web de auditoría de solo lectura para ADMINISTRADOR y AUDITOR, con filtros
  por acción/fecha y paginación.
- Administración de cuentas para ADMINISTRADOR: alta de corredores, operadores y
  auditores, desactivación/reactivación y restablecimiento de clave temporal.
- Clave temporal aleatoria visible una sola vez; la cuenta queda restringida a
  cambiarla en el primer acceso. El flujo no envía credenciales por correo.
- Plantillas y previsualización de cargas CSV/XLSX para montos y factores, con
  validación estructural, de tipos, llave de negocio, suma 8–16 y cálculo desde
  montos 8–19. El borrador válido vence en 30 minutos.
- Catálogo tributario editable por ADMINISTRADOR: nombres, tipos y fórmulas
  descriptivas quedan guardados y auditados en PostgreSQL; editar estos
  metadatos no modifica el motor de cálculo.
- Confirmación asíncrona de cargas con outbox transaccional, escritura
  idempotente en MongoDB, persistencia de calificaciones en PostgreSQL solo
  después del acuse y compensación de documentos Mongo ante conflictos. La base
  `nuam_cargas` almacena metadatos de cada carga y filas rechazadas; las filas
  aceptadas confirmadas se conservan en `calificaciones_detalle`.
- Worker `procesar_outbox_cargas` ejecutado como servicio independiente en
  Docker Compose; la interfaz muestra estado y reintentos.
- Workflow de CI en GitHub con pruebas, flake8, Bandit, auditoría de dependencias
  y build del frontend.
- La llave acordada es ejercicio + mercado/instrumento + fecha de pago +
  secuencia, separada por ámbito Bolsa/corredor; las filas existentes se
  rechazan. La suma de factores se valida en columnas 8–16 y los factores
  derivados de montos usan base 8–19. Los nombres de 34–37 vienen del HDU;
  sus tipos y fórmulas son propuestas provisionales pendientes de confirmación
  del docente.

El perfil NUAM se vincula uno a uno con el usuario estándar de Django. Esto
conserva las migraciones de autenticación que ya se habían ejecutado en la base
local, mientras se completa el perfil de rol, corredor y bloqueo.

## Ejecución local

Requiere Docker Desktop con Compose, WSL 2 y virtualización habilitada en
firmware (Intel VT-x/AMD-V). Generar las credenciales locales y luego iniciar
los servicios:

```powershell
.\infra\security\configurar-entorno.ps1
docker compose up --build
```

- Interfaz Vite: `http://localhost:5173`
- API Django: `http://localhost:8000`

PostgreSQL y MongoDB no publican puertos al host; solo backend y worker acceden
por la red interna de Docker. Para administración, usar `docker compose exec`.
Los puertos web quedan ligados a `127.0.0.1`.

### Protección de bases de datos

- PostgreSQL y MongoDB usan credenciales separadas y aleatorias guardadas en el
  `.env` local, que no debe compartirse ni versionarse. La aplicación recibe
  solo los accesos de `nuam_app` y `app_cargas`; `nuam_migrator` se usa para
  migraciones, y existen cuentas separadas de lectura y respaldo.
- PostgreSQL requiere SCRAM y conexiones TLS con validación del certificado;
  MongoDB activa autenticación, deshabilita JavaScript del servidor y el
  backend/worker verifican TLS. Los certificados autofirmados son solo para
  desarrollo local; un despliegue real debe usar una autoridad y certificados
  administrados y rotables.
- MongoDB usa `preferTLS` para que el inicializador del contenedor pueda
  preparar una instalación nueva; por ello aún acepta conexiones autenticadas
  sin TLS dentro de la red privada de Docker. La API y el worker siempre usan
  TLS. Para exigir TLS a todos los clientes en producción, el aprovisionamiento
  debe completarse antes de iniciar MongoDB en modo `requireTLS`.
- Las cuentas de aplicación, migración, reportes y respaldo de PostgreSQL no
  son superusuarios. El administrador de PostgreSQL y el usuario `nuam_root`
  de MongoDB se reservan para tareas operativas; no se entregan a la aplicación.
- PostgreSQL registra conexiones y desconexiones. Los cambios estructurales se
  anotan en `registro_cambios_ddl` como metadatos de objetos, sin guardar la
  sentencia SQL completa. Los cambios y eliminaciones del log de auditoría se
  bloquean por trigger y por permisos del rol de aplicación.
- Las imágenes de PostgreSQL y MongoDB están fijadas por digest. Actualizar los
  digests periódicamente después de revisar parches de seguridad.
- Los volúmenes Docker no cifran por sí solos los datos en reposo. En Windows,
  habilitar BitLocker en la unidad donde Docker/WSL guarda sus volúmenes.

Como política inicial, generar respaldos diarios cifrados, conservar siete
copias diarias y una copia semanal fuera del equipo. La programación, el cifrado
y el destino externo deben configurarse para el entorno de despliegue; no se
debe considerar validado el respaldo hasta probar una restauración.

El `.env` existente se actualiza sin mostrar secretos al ejecutar
`configurar-entorno.ps1`; el script conserva credenciales ya generadas y solo
crea valores aleatorios para variables secretas ausentes o de ejemplo.

Para ejecutar las pruebas del motor desde el contenedor backend:

```powershell
docker compose exec backend python manage.py test apps.cuentas.tests apps.calificaciones.tests apps.calificaciones.test_calculo
```

El [plan y protocolo de pruebas](./docs/plan-pruebas.md) documenta escenarios
automatizados, pendientes manuales, pasos reproducibles y el registro necesario
para comparar resultados esperados con los observados.

El servicio `outbox-worker` procesa los lotes confirmados. Para ejecutar una
sola operación manualmente:

```powershell
docker compose exec backend python manage.py procesar_outbox_cargas --una-vez
```

El worker prepara automáticamente los validadores e índices de las colecciones
MongoDB al arrancar. Para ejecutar esa preparación manualmente:

```powershell
docker compose exec backend python manage.py preparar_mongo_cargas
```

Las previsualizaciones con filas inválidas también se registran de forma
asíncrona en `cargas_detalle` y `cargas_filas_rechazadas`; no aplican las filas
válidas del mismo archivo a las calificaciones.

Para instalar las herramientas de pruebas y calidad en el entorno virtual local:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Set-Location frontend
npm install
```

El backend usa Django REST Framework, PostgreSQL, MongoDB, pandas y openpyxl.
Las dependencias y herramientas de pruebas se declaran en
`backend/requirements.txt` y `backend/requirements-dev.txt`. El frontend usa
React, Vite y Bootstrap; `frontend/package-lock.json` fija las dependencias
instaladas.

No usar los servicios ni las credenciales de desarrollo fuera de un entorno
local. El archivo `.env` no debe versionarse.

Al iniciar el backend, Compose aplica migraciones y ejecuta
`python manage.py sembrar_catalogos`. El comando crea roles, mercados, orígenes y
las 30 columnas tributarias sin crear usuarios ni contraseñas de demostración.

## API de autenticación

- `GET /api/v1/auth/csrf/`: obtiene la cookie y el token CSRF.
- `POST /api/v1/auth/login/`: JSON `{ "email": "...", "password": "..." }`;
  devuelve un access token y establece el refresh HttpOnly.
- `POST /api/v1/auth/refresh/`: renueva y rota el refresh; requiere cookie y
  encabezado `X-CSRFToken`.
- `POST /api/v1/auth/logout/`: invalida el refresh; requiere CSRF.
- `GET /api/v1/auth/me/`: devuelve el perfil activo; requiere `Authorization:
  Bearer <access>`.
- `GET /api/v1/catalogos/`: entrega mercados, instrumentos y orígenes para
  perfiles autenticados, junto con las definiciones del catálogo tributario.
- `PATCH /api/v1/catalogos/columnas/{nro_columna}/`: permite a
  ADMINISTRADOR editar el nombre, tipo, fórmula descriptiva y estado provisional
  de una columna. Cada cambio queda auditado; la fórmula no se ejecuta y no
  modifica el cálculo hasta que se implemente y apruebe una regla funcional.
- `GET /api/v1/auditoria/`: devuelve eventos inmutables paginados; solo
  ADMINISTRADOR y AUDITOR. Admite `accion`, `desde`, `hasta`, `corredor`,
  `pagina` y `limite` (máximo 100).
- `GET/POST /api/v1/usuarios/`: lista cuentas y crea perfiles (solo
  ADMINISTRADOR); la creación devuelve una clave temporal de un solo uso.
- `PATCH /api/v1/usuarios/{id}/`: activa o desactiva un perfil (solo
  ADMINISTRADOR).
- `POST /api/v1/usuarios/{id}/clave-temporal/`: invalida la clave anterior y
  emite otra temporal de un solo uso.
- `POST /api/v1/auth/cambiar-clave/`: cambia la clave temporal, revoca los
  refresh anteriores y libera el acceso normal a la plataforma.
- `GET /api/v1/cargas/plantilla/?tipo=MONTOS|FACTORES&formato=CSV|XLSX`:
  descarga una plantilla técnica para corredores y operadores.
- `POST /api/v1/cargas/previsualizar/`: recibe `tipo` y `archivo` multipart,
  valida hasta 10.000 filas y devuelve una muestra, conteos y errores. Si todas
  son válidas, conserva temporalmente el borrador por 30 minutos. Solo
  CORREDOR y OPERADOR_BOLSA.
- `GET /api/v1/cargas/`: lista las últimas 20 cargas del usuario autenticado.
- `GET /api/v1/cargas/{id}/`: consulta el estado de una carga propia.
- `POST /api/v1/cargas/{id}/confirmar/`: revalida las llaves e inicia el
  procesamiento con outbox. Devuelve `PENDIENTE_MONGO`; el lote pasa a
  `CONFIRMADA` solo después del acuse de MongoDB.

Las columnas 34–37 están catalogadas inicialmente como:

| Columna | Nombre respaldado por HDU | Tipo propuesto | Fórmula descriptiva propuesta |
|---|---|---|---|
| 34 | Crédito por impuesto tasa adicional, Ex. Art. 21 LIR | Monto | Monto / SUMA(Montos 8..19) |
| 35 | Tasa Efectiva del Crédito del FUT (TEF) | Tasa | Ingreso directo, sin fórmula |
| 36 | Tasa Efectiva del Crédito del FUNT (TEX) | Tasa | Ingreso directo, sin fórmula |
| 37 | Devolución de capital Art. 17 N° 7 LIR | Monto | Monto / SUMA(Montos 8..19) |

Los nombres se basan en el HDU. Los tipos y fórmulas de la tabla son
provisionales, requieren confirmación del docente y no alteran las reglas de
importación actuales. El catálogo es editable por el administrador para
corregir sus metadatos sin cambiar el código.

Las plantillas técnicas usan `mercado`, `codigo_instrumento`, `ejercicio`,
`secuencia_evento`, `numero_dividendo`, `fecha_pago`, `descripcion_dividendo` y
`monto_8`–`monto_37` o `factor_8`–`factor_37`. El mapeo es un formato inicial
para validar archivos, no una homologación tributaria completa.
- `GET/POST /api/v1/calificaciones/`: consulta con filtros y registra una
  calificación manual según el ámbito del rol.
- `GET/PATCH/DELETE /api/v1/calificaciones/{id}/`: consulta, modifica con control
  de versión o elimina lógicamente un registro propio/del ámbito autorizado.

Las modificaciones y eliminaciones requieren el `version` recibido en la
consulta. Una versión obsoleta devuelve HTTP 409 y no sobrescribe el cambio
concurrente. El corredor puede consultar registros propios y generales de Bolsa,
pero solo modificar los propios; el operador solo gestiona los generales; el
auditor consulta y toda lectura de registros de corredores se audita.

Para crear el primer usuario sin almacenar su contraseña en archivos, inicia el
backend con `.env` local y ejecuta interactivamente:

```powershell
docker compose exec backend python manage.py crear_admin_inicial --email admin@tu-dominio.cl
```

El comando pide la contraseña de forma oculta y exige al menos 12 caracteres,
sin permitir contraseñas comunes o únicamente numéricas.

Los usuarios creados desde la interfaz reciben una clave aleatoria mostrada una
sola vez al administrador. Debe entregarse por un canal seguro externo; no se
envía por correo ni se almacena en la bitácora. Si la clave no se conserva, el
administrador puede emitir otra desde la pantalla de usuarios.

El access token dura 15 minutos; el refresh dura como máximo 8 horas por token.
Cinco intentos erróneos bloquean el perfil por 15 minutos. El backend vuelve a
leer el rol y el corredor desde PostgreSQL en cada autorización; las
afirmaciones del JWT no conceden permisos por sí solas.
#   p r o y e c t o - i n t - 3 -  
 