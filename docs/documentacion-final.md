Docker Rangers

## Reporte del proyecto: tienda distribuida

Sistemas Distribuidos 2027-1 · Grupo 2 · FI-UNAM · 26 de noviembre de 2026

Integrantes: Rojas Jiménez Claudia Alin; Hernández Rubio Josué; Santana Cardoso Derek; Vaquero Malvaez José Pablo.

Repositorio: https://github.com/pablovaquerogit/sd-2027-1-docker-rangers

Referencia documental: main f33e90f. Versión funcional revisada: caida-usuarios, commit ee71ef7, que contiene la separación 9d315bb, la interfaz y las mejoras de recuperación. La rama definitiva de presentación debe confirmarse en equipo. Este reporte se preparó con asistencia de IA a partir de los archivos publicados. Las pruebas citadas son evidencias guardadas por el equipo en el repositorio, no una nueva ejecución realizada para este reporte. La revisión conjunta y la defensa individual siguen pendientes.

## 1. Problema y alcance

La tienda permite registrar clientes, iniciar sesión, consultar catálogo y comprar varios productos. Busca evitar sobreventa y efectos duplicados cuando la red falla. El precio se congela al reservar. Incluye interfaz web y API para registro, sesión, catálogo, compra y seguimiento de pedidos. La web conserva la identidad de la compra al reintentar y permite cerrar la sesión en el servidor. No incluye pagos reales, mock de cobro, envíos ni administración de catálogo.

## 2. Diagrama funcional



Cliente: registro y login -> token de sesión

Cliente: consulta catálogo -> selecciona productos

POST pedido + Idempotency-Key -> validar usuario y contenido

Pedidos: guardar intención PENDIENTE antes de llamadas remotas

Inventario: reservar cada producto de forma idempotente

Todas las reservas confirmadas -> pedido CONFIRMADO

Stock insuficiente -> COMPENSANDO -> liberar -> RECHAZADO

Timeout o caída -> PENDIENTE -> reintentar misma identidad

Cliente: GET pedido -> estado recuperable o resultado final



La cadena describe decisiones alternativas, no una transacción global. Un 202 no confirma una compra. El cliente consulta el resultado y conserva su llave; una nueva llave representaría otra operación.

## 3. Diagrama de arquitectura



Cliente -> Gateway Nginx :18091

Gateway -> Usuarios -> PostgreSQL de Usuarios

Gateway -> Pedidos y trabajador -> PostgreSQL de Pedidos

Pedidos -> Usuarios: validar sesión

Pedidos -> balanceador Nginx interno -> Inventario 1 / 2

Gateway -> Inventario 1 / 2: catálogo balanceado

Inventario 1 / 2 -> MongoDB único: stock + reservas

DNS de Compose -> resolución dinámica de ambos Nginx



Usuarios y Pedidos se comunican por HTTP para verificar sesiones; Pedidos llama al balanceador interno para reservar. La web se sirve desde el gateway.

Las flechas indican llamadas HTTP y acceso a almacenes propios. Nginx hace round robin; DNS descubre direcciones. Dos instancias de Inventario comparten MongoDB y no constituyen alta disponibilidad de datos. Gateway, bases y host siguen siendo puntos únicos de falla.

## 4. Decisiones, alternativas y costos

Separar Usuarios, Inventario y Pedidos: permite límites de datos y evolución por servicio. Se dejó atrás la simplicidad de una única transacción PostgreSQL del monolito; se descartó mantener todo junto para practicar recuperación distribuida, no porque un monolito no escale.

Saga persistida: se guarda intención y progreso antes de efectos remotos, y cada reserva/liberación es idempotente. Se descartó tratar HTTP como transacción o hacer compensaciones solo en memoria. Costo: estados intermedios y conciliación.

MongoDB con reserva embebida: stock, condición y marca se actualizan atómicamente por producto. Se descartó separar descuento y marca en escrituras no coordinadas. Costo: crecimiento y límite de 16 MB; no se afirma ventaja de rendimiento sobre SQL.

DNS de Compose y Nginx dinámico: evita mantener un directorio adicional como Eureka en este entorno. Se descartaron direcciones fijas, que fallaron tras reiniciar. Costo: dependencia del host y ventana de refresco de un segundo.

Idempotencia durable por usuario y contenido: una llave repetida conserva resultado; otro contenido da conflicto. Se descartó deduplicar solo en memoria. Costo: retención de identidades y coordinación.

## 5. Fallas y evidencia disponible

Respuesta perdida al reservar: el timeout no demuestra que no hubo efecto. Pedidos conserva el estado pendiente y repite la misma pareja pedido/producto; Inventario devuelve la reserva existente.

Caída del orquestador: el trabajador retoma estados persistidos. Un candado de sesión PostgreSQL serializa trabajadores por pedido; los commits de progreso no abarcan llamadas HTTP.

Rechazo de otro producto: antes de liberar las reservas anteriores se persiste COMPENSANDO. La liberación es idempotente y puede retomarse.

Dependencia caída: conexión 1 s y lectura 3 s hacia Inventario; circuito tras tres fallas, abierto 10 s y prueba semiabierta. Trabajador con espera 2–30 s. No garantiza progreso bajo una caída permanente.

Resultados documentados: diez compras por tres unidades dieron tres confirmadas, siete rechazadas y stock cero; cinco solicitudes con la misma llave dieron un pedido y un descuento; compensación de dos productos y recuperación tras reinicio aprobadas. Consultar evidencia/pruebas-distribuidas.json en 02-separacion.

Se detectaron IP antiguas en Nginx durante pruebas de reinicio. Resolver dinámico, zone y resolve permitieron redescubrir destinos. El catálogo GET tiene recuperación interna ante 502/504; esto no equivale a reintentar compras POST a ciegas.

## 6. Evidencia de las mejoras

Réplica de Inventario: inicialmente hubo un 504 en 16 consultas durante la caída. Tras ajustar el catálogo, 16 de 16 devolvieron 200 desde la réplica activa. Al recuperarse hubo reparto 8/8. Fuente: evidencia/prueba-replica-inventario.txt.

Pedidos: siete intentos con la misma llave en 30 segundos registraron tres 502, tres 504 y un 201. El contenedor reinició; hubo un pedido CONFIRMADO y stock de 5 a 4. Esto demuestra recuperación en esa ejecución, no ausencia de interrupción. Fuente: evidencia/prueba-caida-pedidos.txt.

Usuarios: durante la caída el catálogo devolvió 200, comprar y consultar pedidos 503 e iniciar sesión 504. Después se creó un solo pedido y el stock bajó una vez. El proceso también se recuperó tras kill mediante restart: unless-stopped. Fuente: evidencia/prueba-caida-usuarios.txt.

Cerrar sesión: DELETE devuelve 204; el token revocado recibe 401 tanto en Usuarios como en Pedidos. Repetir el cierre devuelve 204. Fuente: evidencia/prueba-cerrar-sesion.txt.

La web muestra el pedido pendiente y consulta su evolución. Un fallo de red conserva incertidumbre: no debe interpretarse como compra cancelada. Las capturas de evidencia/ complementan las salidas automáticas.

## 7. Levantar, probar y demostrar

git clone https://github.com/pablovaquerogit/sd-2027-1-docker-rangers.git

cd sd-2027-1-docker-rangers

git switch --detach ee71ef7

docker compose -f compose.distribuido.yml up --build -d --wait

python3 tests/distribuido.py

python3 tests/replica_inventario.py

python3 tests/cerrar_sesion.py

python3 tests/caida_pedidos.py

python3 tests/caida_usuarios.py

Requisitos: Docker Compose y Python 3. La prueba crea datos ficticios y detiene temporalmente el balanceador interno y reinicia Pedidos; no ejecutarla durante otra demo. Abrir la tienda en http://localhost:18091/; catálogo API en /api/productos. El checkout fija la versión documentada; no presupone que esté integrada en main. Para detener conservando datos: docker compose -f compose.distribuido.yml down.

Demo: registrar usuario y sesión; consultar catálogo y X-Instancia; comprar con Idempotency-Key; repetir y verificar mismo pedido; cambiar contenido y obtener 409; consultar pedido con su dueño; mostrar prueba de recuperación con 202 y confirmación posterior. No mostrar tokens en evidencia pública.

Pitch: problema de última unidad y reintentos; evolución desde el monolito; reserva atómica y saga; evidencia de concurrencia y recuperación; límites y siguientes pasos. La guía docs/DEMO-Y-DEFENSA.md ya contiene el recorrido de cinco a siete minutos.

## 8. Límites y siguientes pasos

Faltan alta disponibilidad y respaldos probados, retención segura de reservas, operación de conciliación, métricas y recolector de trazas, pagos y despliegue productivo. No hay broker ni Outbox. Los logs JSON y X-Request-ID ayudan a diagnosticar, pero no equivalen a una plataforma completa de OpenTelemetry. Una pérdida definitiva de la base de Pedidos exige conciliación y restauración.

Qué haríamos distinto: medir necesidades antes de separar componentes; definir retención idempotente; probar restauración; mejorar la conciliación de estados pendientes que ya muestra la web; añadir observabilidad y alertas sobre antigüedad de pedidos, además de salud HTTP.

## 9. Aportaciones verificables

José Pablo Vaquero: PRD, monolito, separación de servicios, saga, pruebas y documentación inicial; commits f59ff1c, c6a9861, 9d315bb y f33e90f.

Josué Hernández: interfaz web (1fa3860) y prueba de caída de una réplica de Inventario (a315d8e).

Claudia Alin Rojas: cierre de sesión (4d3e194), seguimiento de pedidos pendientes (7fb8d26), recuperación y pruebas de Pedidos (3e4370e, 602cb4b), recuperación y pruebas de Usuarios (4499ab0, ee71ef7).

Derek Santana: elaboración y actualización de este reporte, diagramas funcional y de arquitectura, explicación de decisiones, consolidación de evidencias y guía de ejecución y defensa, con asistencia de IA. El historial respalda los cambios técnicos anteriores; no permite atribuir por sí solo todas las actividades del equipo.

## Pendiente de cierre de equipo

Integrar este reporte mediante una rama de revisión, confirmar la versión de entrega y ensayar la demo y defensa con todos. Código y reporte deben quedar en el repositorio antes del 28 de noviembre de 2026 a las 07:00; presentación ese día. El reporte no certifica aceptación de entregas previas fuera de plazo.

Fuentes: README.md, docs/PRD.md, docs/DECISIONES.md y docs/DEMO-Y-DEFENSA.md del repositorio del equipo; rúbrica oficial: https://github.com/OscarRuiz21/sd-2027-1/blob/main/proyecto/RUBRICA.md
