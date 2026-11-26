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
    throw new Error(mensaje);
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
    if (sesion === token) estado.textContent = error.message;
  } finally {
    actualizarPedidos.disabled = false;
  }
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
  comprando = true;
  boton.disabled = true;
  estadoCompra.textContent = "Enviando pedido…";
  try {
    const { datos } = await solicitar("/api/pedidos", {
      body: compra,
      sesion,
      clave: clavesPorCompra.get(contenido),
    });
    if (sesion !== token) return;
    clavesPorCompra.delete(contenido);
    estadoCompra.textContent = "Pedido " + datos.id.slice(0, 8) + " · " + datos.estado
      + (datos.motivo ? " · " + datos.motivo : "");
    await Promise.all([cargarCatalogo(), cargarPedidos()]);
  } catch (error) {
    if (sesion === token) estadoCompra.textContent = error.message;
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
  boton.disabled = true;
  modo.disabled = true;
  try {
    if (registro) {
      await solicitar("/api/usuarios", { body: { ...login, nombre: campos.get("nombre") } });
      mostrarModo(false);
    }
    const { datos } = await solicitar("/api/sesiones", { body: login });
    token = datos.access_token;
    botonSesion.textContent = "Cerrar sesión";
    actualizarPedidos.hidden = false;
    formularioAcceso.reset();
    acceso.close();
    await cargarPedidos();
  } catch (error) {
    buscar("#acceso-estado").textContent = error.message;
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
