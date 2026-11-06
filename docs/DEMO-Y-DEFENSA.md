# Pitch, demostración y defensa

Material para preparar la presentación del 28 de noviembre. Ensayar y repartir intervenciones con el equipo; no sustituye comprender ni aportar al proyecto.

## Pitch de un minuto

Docker Rangers es una tienda con registro, catálogo y compra directa. Nuestro problema central es que dos clientes no compren la misma última unidad y que un reintento de red no descuente dos veces. Primero resolvimos el negocio en un monolito con una transacción PostgreSQL; después lo separamos en Usuarios, Inventario y Pedidos con datos propios.

La versión distribuida tiene gateway, directorio DNS y dos réplicas de Inventario. Una compra se guarda como pendiente antes de reservar. Inventario une stock y llave de reserva en una operación atómica; Pedidos confirma todas las reservas o compensa las anteriores. Si una respuesta se pierde, conserva la incertidumbre y repite las mismas llaves. Su trabajador recupera el progreso tras reiniciar.

Probamos diez compras por tres unidades, cinco solicitudes simultáneas con una llave y una caída con reinicio. Las tres unidades se asignaron una sola vez y el pedido pendiente terminó al volver el servicio. El costo es perder la transacción global: hay estados intermedios y operación adicional. Las réplicas de API no hacen que una base única sea altamente disponible.

## Recorrido de cinco a siete minutos

1. Mostrar el diagrama de DECISIONES.md y los contenedores. Identificar gateway, DNS, balanceo y dueño de cada base.
2. Registrar un usuario, iniciar sesión y consultar catálogo. Mostrar `X-Instancia` alternando en las lecturas y `X-Request-ID`.
3. Comprar un teclado con una llave nueva. Mostrar estado CONFIRMADO, precio congelado y stock reducido. Repetir la misma llave y contenido: mismo ID y sin nuevo descuento. Cambiar cantidad con esa llave: 409.
4. Ejecutar `python3 tests/distribuido.py` y mostrar la evidencia: tres confirmados entre diez intentos con stock tres, compensación y autorización. El script tarda por los reinicios y crea productos de prueba propios.
5. En la recuperación, Inventario queda inaccesible y el pedido responde 202 PENDIENTE. El script reinicia Pedidos, comprueba que el pedido persiste, devuelve Inventario y espera CONFIRMADO con un solo descuento. Relacionar historial y logs de esa compra.
6. Cerrar mostrando qué se sacrifica y los límites: reservas parciales, único host/bases, retención de marcas, ausencia de pagos y ausencia de Outbox. No prometer producción ni consistencia global estricta.

## Código que conviene localizar

- `dist/pedidos_app.py`: crear intención antes de HTTP, llave por usuario/contenido, `procesar`, COMPENSANDO, trabajador y commits de progreso.
- `dist/inventario_app.py`: `find_one_and_update`, condición de stock, reserva embebida y liberación idempotente.
- `dist/remotos.py`: timeout y circuito CLOSED/OPEN/HALF_OPEN.
- `nginx/*.conf`: gateway, balanceo y resolución dinámica de servicios.
- `tests/distribuido.py`: escenarios reales y evidencia sin tokens.

## Preguntas para todos los integrantes

- ¿Por qué 202 no significa compra confirmada? ¿Qué debe hacer el cliente con su llave?
- ¿Qué ocurre si Inventario descontó pero Pedidos no recibió la respuesta? Repetir pedido/producto devuelve la reserva existente.
- ¿Qué ocurre si el proceso muere en mitad de liberar? COMPENSANDO ya está guardado y liberar se puede repetir.
- ¿Por qué una reserva que vence por reloj, sin coordinación, puede causar sobreventa? Podría devolver stock mientras Pedidos ya lo considera confirmado.
- ¿Qué protege la transacción local y qué no? Mongo une stock/marca por producto; PostgreSQL guarda pedido/progreso. Ninguna cubre ambos motores.
- ¿DNS reparte cada petición? Nginx hace el reparto; DNS descubre direcciones. No se atribuye round robin de HTTP al DNS.
- ¿Por qué dos API no protegen frente a la caída de MongoDB? Ambas dependen del mismo nodo de datos.
- ¿Qué cambiarías para crecer? Medir primero, después retención segura de reservas, réplica/respaldos, conciliación y controles de acceso/operación. No añadir motores sin justificar el acceso.

## Reparto propuesto, pendiente de acuerdo

Usuarios/sesiones, Inventario/reservas, Pedidos/recuperación e Integración/observación son cuatro ámbitos posibles. Cada integrante debe hacer cambios reales, conservar sus commits, revisar a otro y ensayar todo el sistema. La implementación inicial se preparó por Pablo con apoyo de Codex; no demuestra participación de los demás.
