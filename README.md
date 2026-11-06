# Docker Rangers · Tienda en línea

Proyecto de Sistemas Distribuidos 2027-1, grupo 2, FI-UNAM. Registro, sesiones, catálogo y compra directa con control de stock. Esta rama contiene la separación funcional en **Usuarios, Inventario y Pedidos**, con bases propias, gateway y dos réplicas de Inventario.

| Integrante | GitHub |
| --- | --- |
| Rojas Jiménez Claudia Alin | @Alin021002RJ |
| Hernández Rubio Josué | @Herjoru1 |
| Santana Cardoso Derek | @DerekMstn114 |
| Vaquero Malvaez José Pablo | @pablovaquerogit |

Profesor: @OscarRuiz21. El trabajo inicial y las pruebas se prepararon por Pablo con apoyo de Codex. Los demás integrantes deben aportar cambios propios y comprenderlos; no se atribuyen contribuciones que aún no ocurrieron.

## Ejecutar

```sh
git clone https://github.com/pablovaquerogit/sd-2027-1-docker-rangers.git
cd sd-2027-1-docker-rangers
git switch 02-separacion
docker compose -f compose.distribuido.yml up --build -d --wait
```

Entrada: http://localhost:18091/api/productos · salud de Pedidos: http://localhost:18091/health.

Solo el gateway publica un puerto, enlazado a localhost. Cambiarlo con `PUERTO_DISTRIBUIDO=18092`. Las claves predeterminadas son de desarrollo local: configurar `DB_PASSWORD` e `INTERNAL_KEY` para otro entorno antes de crear sus volúmenes. No hay despliegue público ni TLS en esta demo. Detener conservando las bases: `docker compose -f compose.distribuido.yml down`.

## Ramas y documentación

- `main`: presentación y PRD.
- `01-monolito`: FastAPI modular con una base PostgreSQL; siete pruebas aprobadas.
- `02-separacion`: tres servicios con datos propios y saga recuperable. Conserva también el código monolítico para comparar; el Compose distribuido ejecuta `dist/`.

[PRD](docs/PRD.md) · [Decisiones y diagrama](docs/DECISIONES.md) · [Pitch, demo y defensa](docs/DEMO-Y-DEFENSA.md).

## Compra por API

1. `POST /api/usuarios`: `{"correo":"ana@example.test","nombre":"Ana","password":"password-demo-123"}`.
2. `POST /api/sesiones`: correo y contraseña; devuelve `access_token`.
3. `GET /api/productos`: precios en centavos MXN y stock disponible.
4. `POST /api/pedidos`: `Authorization: Bearer TOKEN`, `Idempotency-Key: UUID` y `{"items":[{"producto_id":"teclado","cantidad":1}]}`.
5. `GET /api/pedidos/ID` o `GET /api/pedidos`: misma sesión; otro dueño recibe 404, sin sesión 401.

201 significa pedido confirmado nuevo; repetir la misma llave y contenido devuelve 200 y el mismo ID. Cambiar el contenido con esa llave devuelve 409. Un rechazo de stock conserva un pedido RECHAZADO para explicar el intento y devuelve 409. Si el resultado remoto es incierto, devuelve **202 PENDIENTE**: consultar ese pedido o repetir con la misma llave, sin crear una compra nueva. El trabajador persiste progreso y reintenta con espera exponencial de 2 a 30 segundos, incluso tras reiniciar Pedidos.

Inventario descuenta y guarda la reserva idempotente de un producto en una sola actualización MongoDB. Pedidos confirma únicamente después de confirmar todas las reservas. Si un producto es rechazado, persiste COMPENSANDO antes de devolver reservas previas. Un timeout deja el resultado incierto: no se anuncia rechazo ni se devuelven reservas a ciegas.

## Pruebas reales

```sh
python3 tests/distribuido.py
```

Requiere Python 3 estándar, Docker y el sistema ya levantado. Crea usuarios y productos ficticios propios; apaga temporalmente el balanceador interno y reinicia Pedidos para comprobar recuperación. Conviene ejecutarlo sin otras demos simultáneas. No borra las bases. Resultado del 6 de noviembre: balanceo entre dos instancias, cinco solicitudes simultáneas con una llave y un descuento, diez compras por tres unidades (tres confirmadas y siete rechazadas), autorización, compensación de varios productos, validación y recuperación tras reinicio aprobados. Salida y respuestas sin tokens en `evidencia/`.

La prueba del reinicio detectó direcciones antiguas en el gateway. Nginx ahora usa DNS interno con `resolve`, memoria compartida y refresco de un segundo, para volver a descubrir servicios sin reiniciar el gateway. No se reintentan POST automáticamente desde el proxy; Pedidos controla los reintentos con identificadores estables.

## Límites que hay que defender

Es una demo local con un único host, gateway, MongoDB y base por servicio: las réplicas de API **no** dan alta disponibilidad de los datos. MongoDB se eligió para practicar reservas atómicas por documento y un catálogo documental; no se midió que sea más rápido que PostgreSQL. No hay transacción global: catálogo, reservas y pedido pueden verse en estados intermedios.

Las reservas permanecen embebidas en el documento del producto para deduplicar: el límite de 16 MB y su crecimiento requieren una estrategia de retención o rediseño antes de producción. No se borran marcas de pedidos todavía reintentables. No hay TTL automático de reservas: una devolución automática sin coordinar con Pedidos podría vender stock de un pedido ya confirmado. Si se pierde definitivamente la base de Pedidos, hace falta conciliación de reservas y respaldos, no basta con un reintento.

Se conservan precios y nombres congelados al reservar; dinero en enteros. Los tokens vencen en ocho horas y se guardan como hash. No hay pagos reales ni mock de cobro, envíos, recuperación de contraseña, administración del catálogo, interfaz web, broker/Outbox o trazas OpenTelemetry. Sí hay logs estructurados y propagación de `X-Request-ID`. Un estado REVISION_PENDIENTE requiere conciliación manual; no se esconde como éxito.
