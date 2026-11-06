# PRD · Tienda Docker Rangers

Sistemas Distribuidos 2027-1 · Grupo 2. Integrantes: @Alin021002RJ, @Herjoru1, @DerekMstn114 y @pablovaquerogit. Actualización operativa del 6 de noviembre de 2026 sobre el PRD inicial del 10 de octubre; preparada por Pablo para revisión del equipo.

## Problema y alcance

Un cliente necesita registrarse, consultar productos, comprar cantidades disponibles y conocer el resultado de su pedido. El reto es impedir sobreventa y descuentos repetidos incluso con concurrencia, respuestas perdidas y reinicios entre servicios.

Incluye registro, sesiones de ocho horas, catálogo, compra directa de varios productos, precios congelados, consulta exclusiva del dueño, reservas, compensación y recuperación de pedidos pendientes. Fuera del alcance actual: pagos reales y mock de cobro, logística, direcciones, administración del catálogo, carrito persistente e interfaz web. La demostración usa HTTP y datos ficticios.

## Por qué distribuir

Se separa la propiedad de Usuarios, Inventario y Pedidos, y se replica solo la API de Inventario para practicar descubrimiento y balanceo. El prototipo comprueba reparto entre dos instancias. No demuestra todavía mayor capacidad ni que MongoDB supere PostgreSQL. Se acepta el costo de varias bases y recuperación de operaciones para estudiar el problema del curso.

## Reglas y sacrificios

1. No confirmar una compra sin haber reservado y confirmado todos sus productos. No permitir stock negativo.
2. Una llave de compra pertenece al usuario y a su contenido. Repetirla no crea otro pedido ni otro descuento; reutilizarla con otro contenido se rechaza.
3. Un timeout deja un pedido PENDIENTE. El sistema no anuncia éxito ni devuelve stock a ciegas; conserva progreso y reintenta con las mismas llaves.
4. Un rechazo de stock compensa reservas previas y conserva el intento como RECHAZADO. Al distribuir se pierde el rollback global del monolito: la compensación puede verse y tardar.
5. Conservar precio y nombre de los productos al reservar, aunque el catálogo cambie después.

La prioridad es evitar confirmaciones incorrectas; se sacrifica respuesta final inmediata. No existe una transacción global ni una promesa de inventario y pedidos idénticos en cada instante. Bajo una falla permanente puede necesitarse conciliación manual.

## Historias y aceptación

| Historia | Criterio comprobable |
| --- | --- |
| Registrarme e iniciar sesión | Correo único, contraseña con sal/PBKDF2 y token aleatorio guardado como hash; sesión inválida devuelve 401 |
| Consultar catálogo | Lista y detalle con ID, nombre, precio entero en centavos MXN y stock disponible |
| Comprar | Con stock, termina CONFIRMADO; diez compras concurrentes con tres unidades producen tres confirmados y siete rechazados |
| Reintentar compra | Cinco peticiones simultáneas con una llave producen un pedido; contenido distinto devuelve 409 |
| Fallar a mitad | Si falta el segundo producto se devuelve la reserva del primero y termina RECHAZADO |
| Recuperar | Con Inventario inaccesible queda PENDIENTE; reiniciar Pedidos y recuperar Inventario permite terminar sin descuento doble |
| Consultar mis pedidos | Sin sesión 401, otro dueño 404; dueño obtiene detalles, historial y resultado |

## Fronteras y contratos

- Usuarios: clientes y sesiones, PostgreSQL propio. `/api/usuarios`, `/api/sesiones`, `/api/usuarios/me`.
- Inventario: productos, stock y reservas por pedido, MongoDB propio. Lecturas `/api/productos`; operaciones internas autenticadas `/interno/productos/{id}/reservas` y `/{pedido_id}/{confirmar|liberar}`. La actualización de un documento une condición de stock, descuento y marca idempotente.
- Pedidos: solicitud, llave, dueño, detalles congelados, estado, historial y progreso de saga, PostgreSQL propio. `/api/pedidos`. Verifica sesión con Usuarios y orquesta Inventario. Ningún servicio hace consultas directas a la base del otro.

El pedido se guarda antes de llamar a Inventario. Reservar con la misma pareja pedido/producto devuelve el resultado previo; confirmar y liberar también son idempotentes. Un trabajador reanuda estados PENDIENTE/COMPENSANDO al reiniciar. El estado REVISION_PENDIENTE muestra conflictos que necesitan intervención.

## Piezas y operación

| Pieza | Decisión y falla |
| --- | --- |
| Gateway | Nginx, único puerto local 18091; su caída impide acceso exterior |
| Directorio | DNS de Compose, resolución dinámica de Nginx; su falla afecta descubrimiento |
| Balanceo | Nginx reparte hacia dos réplicas de API Inventario, también en llamadas internas |
| Datos | Dos PostgreSQL independientes y un MongoDB; cada nodo único es un punto de falla, sin réplica de datos ni sharding |
| Operaciones | Saga persistida en Pedidos, actualización atómica por producto y compensaciones; no hay broker/Outbox |
| Fallas | Timeouts, circuit breaker y reintentos persistidos con espera; no reintentos ciegos del proxy |
| Observación | X-Request-ID y logs JSON; sin recolector ni sistema de alertas |

## Ejecución, evidencia y preguntas abiertas

Python/FastAPI, PostgreSQL 17, MongoDB 8, Nginx 1.27.5 y Docker Compose. Desde `02-separacion`: `docker compose -f compose.distribuido.yml up --build -d --wait`; prueba real: `python3 tests/distribuido.py`. El [README](../README.md) y [diagrama](DECISIONES.md) detallan uso y resultados.

La demo está implementada; el equipo debe revisar las decisiones y aportar trabajo propio. Quedan decisiones de operación para una evolución de producción: retención segura de reservas embebidas (límite de 16 MB), conciliación ante pérdida definitiva de Pedidos, respaldos, alta disponibilidad, TLS y límites de tráfico. No se declara acuerdo unánime ni rendimiento medido que no exista.
