"use strict";

const buscar = (selector) => document.querySelector(selector);
const acceso = buscar("#acceso");
const formularioAcceso = buscar("#form-acceso");
const pedidos = buscar("#lista-pedidos");
const botonSesion = buscar("#sesion");
const actualizarPedidos = buscar("#recargar-pedidos");
const estadoCompra = buscar("#compra-estado");
const clavesPorCompra = new Map();
const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
let token = "";
let registro = false;
let comprando = false;

// Seguimiento de un pedido que quedó en proceso (202 PENDIENTE): la saga sigue en el servidor
// y la web pregunta por él hasta que termina.
const ESTADOS_EN_CURSO = new Set(["PENDIENTE", "COMPENSANDO"]);
const ESPERA_SEGUIMIENTO_MS = 2000;
const LIMITE_SEGUIMIENTO_MS = 3 * 60 * 1000;
let seguimiento = 0;
const esperar = (ms) => new Promise((listo) => setTimeout(listo, ms));

// Reintento de la compra cuando Pedidos no responde (caído o reiniciándose). Se reintenta con la
// MISMA Idempotency-Key: si la primera petición sí llegó a guardarse, el servidor devuelve ese mismo
// pedido en lugar de crear otro.
const ESPERA_REINTENTO_MS = 2000;
const LIMITE_REINTENTO_MS = 60 * 1000;
const esFallaTemporal = (error) => !error.status || [502, 503, 504].includes(error.status);

// Pedidos responde 503 "No se pudo verificar la sesión" cuando el que no contesta es Usuarios.
const fallaDeUsuarios = (error) => error.status === 503 && /verificar la sesi/i.test(error.message);
const codigo = (error) => (error.status ? "HTTP " + error.status : "sin conexión");
function quienNoResponde(error, servicio) {
  return fallaDeUsuarios(error) ? "Usuarios no responde: no se puede verificar tu sesión" : servicio + " no responde";
}

// Repite una acción mientras la falla sea temporal (sin conexión, 502, 503, 504), hasta LIMITE_REINTENTO_MS.
async function conReintentos(accion, avisar) {
  const inicio = Date.now();
  let intento = 1;
  while (true) {
    try {
      return await accion(intento);
    } catch (error) {
      if (!esFallaTemporal(error) || Date.now() - inicio >= LIMITE_REINTENTO_MS) throw error;
      avisar(error, intento);
      intento++;
      await esperar(ESPERA_REINTENTO_MS);
    }
  }
}

async function solicitar(url, { body, sesion = "", clave = "" } = {}) {
  const headers = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (sesion) headers.Authorization = "Bearer " + sesion;
  if (clave) headers["Idempotency-Key"] = clave;
  const respuesta = await fetch(url, {
    method: body ? "POST" : "GET",
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const datos = await respuesta.json().catch(() => null);
  if (!respuesta.ok && !(clave && respuesta.status === 409 && datos?.id)) {
    const mensaje = typeof datos?.detail === "string"
      ? datos.detail
      : "La solicitud falló (HTTP " + respuesta.status + ").";
    const error = new Error(mensaje);
    error.status = respuesta.status;
    throw error;
  }
  if (!datos) throw new Error("Respuesta inesperada del servidor.");
  return { datos, respuesta };
}

function mostrarProducto(producto) {
  const ficha = buscar("#ficha").content.cloneNode(true);
  ficha.querySelector("h3").textContent = producto.nombre;
  ficha.querySelector(".existencias").textContent = producto.stock + " en existencia";
  ficha.querySelector(".precio").textContent = pesos.format(producto.precio_centavos / 100);
  const formulario = ficha.querySelector("form");
  const cantidad = formulario.elements.cantidad;
  cantidad.max = Math.min(100, producto.stock);
  cantidad.disabled = producto.stock === 0;
  const boton = formulario.querySelector("button");
  boton.disabled = producto.stock === 0;
  if (boton.disabled) boton.textContent = "Agotado";
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    comprar(producto, cantidad.valueAsNumber, boton);
  });
  return ficha;
}

async function cargarCatalogo() {
  const boton = buscar("#actualizar");
  const estado = buscar("#inventario-estado");
  boton.disabled = true;
  try {
    const { datos, respuesta } = await solicitar("/api/productos");
    buscar("#productos").replaceChildren(...datos.map(mostrarProducto));
    buscar("#productos-total").textContent = datos.length + " productos";
    buscar("#instancia").textContent = respuesta.headers.get("X-Instancia") || "—";
    estado.textContent = "Catálogo disponible";
  } catch (error) {
    estado.textContent = "No se pudo actualizar el catálogo. " + error.message;
    buscar("#instancia").textContent = "—";
  } finally {
    boton.disabled = false;
  }
}

function pedidoEnLista(pedido) {
  const fila = document.createElement("li");
  const detalles = document.createElement("details");
  const resumen = document.createElement("summary");
  const estado = document.createElement("strong");
  estado.textContent = pedido.estado;
  resumen.append(estado, " · ", pedido.id.slice(0, 8));
  if (pedido.total_centavos !== null) {
    resumen.append(" · ", pesos.format(pedido.total_centavos / 100));
  }
  const contenido = document.createElement("p");
  contenido.textContent = pedido.items.map(
    (item) => item.cantidad + " × " + (item.nombre || item.producto_id)
  ).join(", ");
  detalles.append(resumen, contenido);
  if (pedido.motivo) {
    const motivo = document.createElement("p");
    motivo.textContent = pedido.motivo;
    detalles.append(motivo);
  }
  fila.append(detalles);
  return fila;
}

async function cargarPedidos() {
  const sesion = token;
  const estado = buscar("#pedidos-estado");
  actualizarPedidos.disabled = true;
  try {
    const { datos } = await solicitar("/api/pedidos", { sesion });
    if (sesion !== token) return;
    pedidos.replaceChildren(...datos.map(pedidoEnLista));
    estado.textContent = datos.length ? "" : "Todavía no tienes pedidos.";
  } catch (error) {
    if (sesion !== token) return;
    estado.textContent = fallaDeUsuarios(error)
      ? quienNoResponde(error, "Pedidos") + ". Intenta de nuevo en unos segundos."
      : error.message;
  } finally {
    actualizarPedidos.disabled = false;
  }
}

function textoPedido(pedido) {
  return "Pedido " + pedido.id.slice(0, 8) + " · " + pedido.estado
    + (pedido.motivo ? " · " + pedido.motivo : "");
}

async function seguirPedido(pedido, sesion) {
  // Cada seguimiento tiene su turno: si empieza otro (nueva compra) o se cierra la sesión, este se detiene.
  const turno = ++seguimiento;
  const inicio = Date.now();
  let actual = pedido;
  while (ESTADOS_EN_CURSO.has(actual.estado)) {
    const transcurrido = Date.now() - inicio;
    if (transcurrido >= LIMITE_SEGUIMIENTO_MS) {
      estadoCompra.textContent = textoPedido(actual)
        + " · Sigue en proceso; el sistema lo terminará solo. Revisa «Mis pedidos» más tarde.";
      return;
    }
    estadoCompra.textContent = "Pedido " + actual.id.slice(0, 8) + " · " + actual.estado
      + " · esperando a Inventario (" + Math.round(transcurrido / 1000) + " s)"
      + (actual.motivo ? " · último intento: " + actual.motivo : "") + "…";
    await esperar(ESPERA_SEGUIMIENTO_MS);
    if (turno !== seguimiento || sesion !== token) return;
    try {
      const { datos } = await solicitar("/api/pedidos/" + actual.id, { sesion });
      actual = datos;
    } catch (error) {
      // Falla de red o de Pedidos al consultar: no cambia el pedido; se vuelve a preguntar en la siguiente vuelta.
    }
    if (turno !== seguimiento || sesion !== token) return;
    cargarPedidos();
  }
  estadoCompra.textContent = textoPedido(actual);
  await Promise.all([cargarCatalogo(), cargarPedidos()]);
}

async function comprar(producto, cantidad, boton) {
  if (!token) {
    abrirAcceso();
    return;
  }
  if (comprando) return;
  const sesion = token;
  const compra = { items: [{ producto_id: producto.id, cantidad }] };
  const contenido = JSON.stringify(compra);
  if (!clavesPorCompra.has(contenido)) clavesPorCompra.set(contenido, crypto.randomUUID());
  const clave = clavesPorCompra.get(contenido);
  comprando = true;
  boton.disabled = true;
  estadoCompra.textContent = "Enviando pedido…";
  const inicio = Date.now();
  let intento = 1;
  try {
    while (true) {
      try {
        const { datos } = await solicitar("/api/pedidos", { body: compra, sesion, clave });
        if (sesion !== token) return;
        clavesPorCompra.delete(contenido);
        seguimiento++;
        estadoCompra.textContent = textoPedido(datos) + (intento > 1 ? " · tras " + intento + " intentos con la misma llave" : "");
        await Promise.all([cargarCatalogo(), cargarPedidos()]);
        // 202 PENDIENTE: la compra quedó guardada y la saga sigue en el servidor. Se sigue sin bloquear la página.
        if (ESTADOS_EN_CURSO.has(datos.estado)) seguirPedido(datos, sesion);
        return;
      } catch (error) {
        if (sesion !== token) return;
        const temporal = esFallaTemporal(error);
        if (!temporal || Date.now() - inicio >= LIMITE_REINTENTO_MS) {
          // La llave se conserva: si el usuario vuelve a presionar "Comprar", no se crea una compra doble.
          estadoCompra.textContent = (fallaDeUsuarios(error) ? quienNoResponde(error, "Pedidos") : error.message)
            + (temporal ? " · Sigue sin responder. Vuelve a intentar: se usará la misma llave y no se cobrará doble." : "");
          return;
        }
        estadoCompra.textContent = quienNoResponde(error, "Pedidos") + " (" + codigo(error)
          + "); reintentando con la misma llave · intento " + intento + "…";
        intento++;
        await esperar(ESPERA_REINTENTO_MS);
        if (sesion !== token) return;
      }
    }
  } finally {
    comprando = false;
    boton.disabled = false;
  }
}

function mostrarModo(crearCuenta) {
  registro = crearCuenta;
  buscar("#titulo-acceso").textContent = registro ? "Crear cuenta" : "Iniciar sesión";
  buscar("#etiqueta-nombre").hidden = !registro;
  formularioAcceso.elements.nombre.required = registro;
  formularioAcceso.elements.password.minLength = registro ? 10 : 1;
  formularioAcceso.elements.password.autocomplete = registro ? "new-password" : "current-password";
  buscar("#enviar-acceso").textContent = registro ? "Registrar" : "Entrar";
  buscar("#modo-acceso").textContent = registro ? "Ya tengo cuenta" : "Crear cuenta";
  buscar("#acceso-estado").textContent = "";
}

function abrirAcceso() {
  formularioAcceso.reset();
  mostrarModo(false);
  acceso.showModal();
}

formularioAcceso.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const boton = buscar("#enviar-acceso");
  const modo = buscar("#modo-acceso");
  const campos = new FormData(formularioAcceso);
  const login = { correo: campos.get("correo"), password: campos.get("password") };
  const aviso = buscar("#acceso-estado");
  const avisar = (error, intento) => {
    aviso.textContent = "Usuarios no responde (" + codigo(error) + "); reintentando · intento " + intento + "…";
  };
  boton.disabled = true;
  modo.disabled = true;
  try {
    if (registro) {
      let reintento = false;
      try {
        await conReintentos((intento) => {
          reintento = intento > 1;
          return solicitar("/api/usuarios", { body: { ...login, nombre: campos.get("nombre") } });
        }, avisar);
      } catch (error) {
        // El registro no es idempotente: si un intento anterior sí creó la cuenta pero su respuesta se
        // perdió, el reintento recibe 409 "correo ya registrado". Se sigue con el inicio de sesión;
        // si la cuenta fuera de otra persona, la contraseña no coincidirá y el servidor responderá 401.
        if (!(reintento && error.status === 409)) throw error;
      }
      mostrarModo(false);
    }
    const { datos } = await conReintentos(() => solicitar("/api/sesiones", { body: login }), avisar);
    token = datos.access_token;
    aviso.textContent = "";
    botonSesion.textContent = "Cerrar sesión";
    actualizarPedidos.hidden = false;
    formularioAcceso.reset();
    acceso.close();
    await cargarPedidos();
  } catch (error) {
    aviso.textContent = esFallaTemporal(error)
      ? "Usuarios sigue sin responder (" + codigo(error) + "). Intenta de nuevo en unos segundos."
      : error.message;
  } finally {
    boton.disabled = false;
    modo.disabled = false;
  }
});

async function cerrarSesion() {
  const sesion = token;
  let aviso = "";
  botonSesion.disabled = true;
  try {
    // Se invalida el token en el servidor, no solo en el navegador.
    const respuesta = await fetch("/api/sesiones", {
      method: "DELETE",
      headers: { Authorization: "Bearer " + sesion },
    });
    if (!respuesta.ok && respuesta.status !== 401) {
      aviso = "No se pudo cerrar la sesión en el servidor (HTTP " + respuesta.status + "); vence sola en 8 horas.";
    }
  } catch (error) {
    aviso = "No se pudo contactar al servidor; la sesión vence sola en 8 horas.";
  } finally {
    botonSesion.disabled = false;
  }
  token = "";
  seguimiento++;
  clavesPorCompra.clear();
  botonSesion.textContent = "Iniciar sesión";
  actualizarPedidos.hidden = true;
  estadoCompra.textContent = aviso;
  pedidos.replaceChildren();
  buscar("#pedidos-estado").textContent = "Inicia sesión para ver tus pedidos.";
}

botonSesion.addEventListener("click", () => {
  if (!token) {
    abrirAcceso();
    return;
  }
  cerrarSesion();
});

buscar("#cerrar").addEventListener("click", () => acceso.close());
buscar("#modo-acceso").addEventListener("click", () => mostrarModo(!registro));
buscar("#actualizar").addEventListener("click", cargarCatalogo);
actualizarPedidos.addEventListener("click", cargarPedidos);
cargarCatalogo();
