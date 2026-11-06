# Decisiones de arquitectura

Estado al 6 de noviembre de 2026: monolito ejecutable. El diseño distribuido del PRD todavía requiere implementación y revisión con el equipo.

| Decisión | Monolito actual | Evolución propuesta | Beneficio y costo |
| --- | --- | --- | --- |
| Fronteras | Usuarios, Inventario y Pedidos como módulos | Separar propiedad y contrato por servicio | Primero se comprueba negocio; luego aparecen fallas parciales |
| Entrada | Una API FastAPI con rutas `/api` | Gateway frente a los tres servicios | Una puerta simplifica al cliente; necesita supervisión y capacidad |
| Directorio | DNS de Compose para encontrar PostgreSQL | Nombres de servicio de Compose para entorno local | Evita IPs fijas; depende de la red del host |
| Balanceo | Una instancia de API | Proxy explícito para repartir entre réplicas sin estado | DNS por sí solo no demuestra reparto equitativo por petición; debe medirse |
| Datos | Una base PostgreSQL, restricciones y candados de fila | Cada servicio es dueño de sus datos; justificar MongoDB con acceso medido | Se pierde la transacción local que hoy une pedido e inventario |
| Operaciones | Compra atómica, llave idempotente por usuario y precio congelado | Reserva idempotente, saga persistida, compensación y conciliación | Evita duplicar efectos; necesita estados intermedios y recuperación |
| Fallas y observabilidad | Rollback y códigos HTTP; pruebas de concurrencia | Timeouts, circuit breaker, Outbox, consumidor idempotente y trazas | Reintentos seguros y diagnóstico añaden estado y operación |

## Invariante de compra

No se confirma una cantidad mayor que el stock disponible. En el monolito se comprueba bloqueando los productos y confirmando pedido, detalles y descuento juntos. Diez compras por un producto con tres unidades producen tres pedidos y siete rechazos, con stock cero.

Una saga no crea por sí sola consistencia global estricta entre bases distintas. Al separar Inventario y Pedidos hay que representar reservas pendientes y distinguir rechazo confirmado de resultado remoto incierto. Esta precisión debe incorporarse al PRD por acuerdo del equipo.

## Trabajo por repartir

Usuarios: validación y ciclo de sesiones. Inventario: reservas y prevención de sobreventa. Pedidos: estados, orquestación y consulta. Integración: gateway, pruebas de fallas y trazas. La asignación de responsables queda para el equipo; no se atribuyen aportes que aún no ocurrieron.
