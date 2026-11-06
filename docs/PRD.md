# PRD · Plataforma E-commerce Simplificada

Equipo: docker-rangers · Integrantes: @Alin021002RJ, @Herjoru1, @DerekMstn114, @pablovaquerogit · Fecha: 10 de octubre de 2026

## 1. Problema y usuarios
Una plataforma básica de comercio electrónico para clientes que desean registrarse, consultar un catálogo de productos y realizar compras. El reto técnico central es garantizar que las transacciones y el inventario sean consistentes, evitando la venta de "inventario fantasma" en caso de fallas de red durante la creación de pedidos.

## 2. Por qué es un sistema distribuido
Las cargas de trabajo no son uniformes: los clientes realizan muchas más consultas de lectura al catálogo de productos que compras reales. Ser distribuido permite separar los módulos y escalar únicamente el servicio de Inventario (con múltiples réplicas) para soportar altos volúmenes de tráfico, ahorrando infraestructura al no tener que replicar toda una aplicación monolítica.

## 3. Objetivos y lo que no vamos a hacer
**Dentro del alcance:**
- Registro y autenticación de clientes.
- Consulta de catálogo de productos.
- Realización de compras.
- Consulta de estado del pedido.

**Fuera del alcance:**
- Integraciones con pasarelas de pago reales (se utilizará un *mock*).
- Sistemas complejos de logística, cálculos de flete y envíos.
- Carritos de compras persistentes o complejos (se limitará a compra directa o carrito temporal en memoria del navegador).

## 4. El requisito que perseguimos y lo que dejamos atrás
**Prioridad:** La Consistencia estricta de los datos (Enfoque CP). Garantizamos que bajo ninguna circunstancia se generará un pedido de un producto que no existe, asegurando que Inventario y Pedidos sean 100% exactos.
**Lo que dejamos atrás:** La Disponibilidad al momento del pago. Estamos dispuestos a que el sistema rechace peticiones temporalmente, mostrando errores al cliente si hay fallos, antes de enfrentarnos a problemas logísticos de inventario que no poseemos.

## 5. Historias de usuario

**Realizar compras**
- *Como cliente autenticado, quiero realizar la compra de un producto del catálogo para asegurar que el artículo me sea asignado exitosamente y generar mi orden.*
  - **Criterio de aceptación 1 (Consistencia):** Dado que intento comprar con stock disponible, Pedidos guarda el estado como "Confirmado" en PostgreSQL y el stock disminuye la cantidad solicitada en MongoDB.
  - **Criterio de aceptación 2 (Rechazo):** Dado que intento comprar un producto con stock 0, la transacción se rechaza, devolviendo un error sin generar órdenes fantasmas en Pedidos.
  - **Criterio de aceptación 3 (Idempotencia):** Dado que la red falla y Pedidos reintenta enviar la orden, Inventario valida la Idempotency Key (UUID), devuelve éxito, pero NO descuenta el stock por segunda vez.

**Consultar estado del pedido**
- *Como cliente de la tienda, quiero consultar el estado de mis órdenes recientes para saber si mi intento de compra fue confirmado, está pendiente o fue rechazado por problemas de red o inventario.*
  - **Criterio de aceptación 1 (Lectura Exitosa):** Dado que tengo una compra previa y consulto mi orden, el sistema devuelve detalles del producto, el precio congelado y su estado final.
  - **Criterio de aceptación 2 (Aislamiento/Seguridad):** Dado que intento consultar el ID de orden que pertenece a otro cliente, el sistema deniega el acceso validando mi identidad contra el servicio de Usuarios.

## 6. Del monolito a los servicios
Si fuera un monolito, la aplicación se dividiría internamente en Usuarios, Inventario y Pedidos.
Al partirlos como servicios independientes, la frontera y el dominio de datos queda así:
- **Usuarios:** Único dueño de Clientes y Direcciones.
- **Inventario:** Único dueño de Catalogo_Productos y Stock.
- **Pedidos:** Único dueño de Ordenes y Detalles_Orden.

**Flujo y llamadas cruzadas:** Durante la compra, Pedidos valida identidad contra Usuarios (o vía token JWT) y hace un `POST /inventario/reservar` hacia Inventario. Si el stock se reserva exitosamente pero Pedidos falla internamente al guardar su orden en PostgreSQL, Pedidos ejecuta una transacción de compensación (`POST /inventario/devolver`) para evitar dejar bloqueado el artículo.

## 7. Dónde vive cada pieza

| Pieza | Dónde vive | Por qué | Qué pasa si falla |
|---|---|---|---|
| **API gateway** | Nginx, Traefik, o código Node/Spring. | Para centralizar el tráfico como único punto de entrada público, ocultando la red interna y exponiendo rutas base como `/api/pedidos/*`. | Es un Punto Único de Fallo (SPOF). Si colapsa, la tienda queda fuera de servicio desde el exterior. |
| **Directorio / DNS** | DNS interno nativo de Docker Compose. | Porque un directorio como Eureka sería sobreingeniería para nuestra arquitectura inicial de tres servicios. | Si Docker pierde la resolución de nombres, los servicios no pueden comunicarse internamente. |
| **Balanceo** | Gateway (hacia el exterior) y el DNS interno de Docker (hacia el interior) con Round-Robin. | Para distribuir equitativamente el gran volumen de peticiones de lectura hacia las réplicas del Inventario. | Las peticiones pueden abrumar una sola réplica si el reparto falla. |
| **Datos** (tipo de base) | Pedidos y Usuarios en SQL (PostgreSQL/MySQL). Inventario en NoSQL (MongoDB) con Read Replicas. | SQL por necesidad de transacciones ACID. NoSQL para acelerar lecturas masivas. Si a futuro hay Sharding, será por hash(ID_Producto). | Si el Maestro de MongoDB cae, fallarán los descuentos de stock; si cae PostgreSQL, no habrá compras procesables. |
| **Operaciones entre servicios** | Orquestado desde Pedidos con transacciones de compensación. | Para deshacer operaciones si la transacción falla a la mitad, regresando los artículos virtualmente al estante. | Requiere monitoreo; si falla la compensación puede quedar inventario inconsistente. |
| **Manejo de fallas** | Fail-fast: Timeout de 3 a 5s, reintentos (max 3), Circuit Breaker y Llaves de Idempotencia. | Para proteger la red, evitar bloqueos de interfaz al usuario y asegurar que los reintentos no cobren o descuenten de más. | Si la validación de idempotencia llegara a fallar, el inventario quedaría desajustado. |

## 8. Stack y cómo se levanta
- **Lenguaje y Framework:** Python con FastAPI. Elegido por su velocidad de desarrollo, validación automática de datos y la capacidad de autogenerar documentación interactiva (Swagger) para facilitar pruebas rápidas entre microservicios.
- **Entorno Local y Despliegue:** Todo el ecosistema (Bases de datos SQL y MongoDB, Proxy Inverso y el código de los servicios) se levantará usando **Docker Compose**. Con un solo comando (`docker compose up`) se asegura que el entorno de desarrollo sea idéntico para todos, eliminando el problema de "en mi computadora sí funciona".

## 9. Decisiones de arquitectura
- *Consistencia (CP) sobre Disponibilidad:* Preferimos rechazar una petición devolviendo un error al cliente que generar falsas expectativas de compra.
- *DNS nativo sobre Eureka:* Descartamos implementar un *Service Discovery* avanzado en favor de mayor simplicidad apoyándonos en la red de contenedores de Docker.
- *Transacción de compensación vs Bloqueos:* Utilizamos un patrón reactivo (Saga) donde Pedidos lanza una orden de retorno de stock si falla internamente, minimizando candados pesados.

## 10. Preguntas abiertas y desacuerdos
- El equipo mantiene total acuerdo sobre el modelo, el enfoque estricto en la consistencia y la priorización de las réplicas de lectura en MongoDB. No hay preguntas abiertas.
