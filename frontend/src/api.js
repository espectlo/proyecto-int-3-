let accessToken = null;
let csrfToken = null;

export class ApiError extends Error {
  constructor(message, statusCode = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

async function leerRespuesta(response) {
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    const detail = data?.detalle || data?.detail || data;
    const message = typeof detail === "string"
      ? detail
      : `No se pudo completar la solicitud (HTTP ${response.status}).`;
    throw new ApiError(message, response.status, data);
  }
  return data;
}

async function obtenerCsrf() {
  const response = await fetch("/api/v1/auth/csrf/", {
    credentials: "include",
  });
  const data = await leerRespuesta(response);
  csrfToken = data.csrfToken;
  return csrfToken;
}

async function renovarAccess() {
  if (!csrfToken) await obtenerCsrf();
  const response = await fetch("/api/v1/auth/refresh/", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: "{}",
  });
  const data = await leerRespuesta(response);
  accessToken = data.access;
  return accessToken;
}

export async function iniciarSesion(email, password) {
  await obtenerCsrf();
  const response = await fetch("/api/v1/auth/login/", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({ email, password }),
  });
  const data = await leerRespuesta(response);
  accessToken = data.access;
  return obtenerPerfil();
}

export async function restaurarSesion() {
  try {
    await obtenerCsrf();
    await renovarAccess();
    return await obtenerPerfil();
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 401) {
      accessToken = null;
      return null;
    }
    throw error;
  }
}

export async function solicitudApi(path, options = {}) {
  const enviar = () => fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(options.headers || {}),
    },
  });

  let response = await enviar();
  if (response.status === 401 && accessToken && options.reintento !== false) {
    try {
      await renovarAccess();
      response = await enviar();
    } catch (error) {
      accessToken = null;
      throw error;
    }
  }
  return leerRespuesta(response);
}

export async function descargarArchivo(path) {
  const enviar = () => fetch(path, {
    credentials: "include",
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  let response = await enviar();
  if (response.status === 401 && accessToken) {
    try {
      await renovarAccess();
      response = await enviar();
    } catch (error) {
      accessToken = null;
      throw error;
    }
  }
  if (!response.ok) {
    await leerRespuesta(response);
  }
  return {
    archivo: await response.blob(),
    disposicion: response.headers.get("content-disposition") || "",
  };
}

export async function obtenerPerfil() {
  return solicitudApi("/api/v1/auth/me/");
}

export async function cambiarClave(claveActual, claveNueva, confirmacion) {
  const data = await solicitudApi("/api/v1/auth/cambiar-clave/", {
    method: "POST",
    body: JSON.stringify({
      clave_actual: claveActual,
      clave_nueva: claveNueva,
      confirmacion,
    }),
  });
  accessToken = data.access;
  return obtenerPerfil();
}

export async function cerrarSesion() {
  try {
    await obtenerCsrf();
    const response = await fetch("/api/v1/auth/logout/", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: "{}",
    });
    await leerRespuesta(response);
  } finally {
    accessToken = null;
  }
}
