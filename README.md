# Docker Rangers · Tienda en línea

Proyecto de Sistemas Distribuidos 2027-1, grupo 2, FI-UNAM. Usuarios consultan productos, compran con stock disponible y revisan sus pedidos. La primera versión concentra las reglas de negocio en un monolito modular con FastAPI y PostgreSQL.

## Equipo

| Integrante | GitHub |
| --- | --- |
| Rojas Jiménez Claudia Alin | @Alin021002RJ |
| Hernández Rubio Josué | @Herjoru1 |
| Santana Cardoso Derek | @DerekMstn114 |
| Vaquero Malvaez José Pablo | @pablovaquerogit |

Profesor: @OscarRuiz21.

## Ramas

- `main`: presentación del proyecto, [PRD](docs/PRD.md) y [decisiones](docs/DECISIONES.md).
- `01-monolito`: código ejecutable, Compose y pruebas de esta primera versión.

El PRD describe la evolución distribuida. En `01-monolito`, Usuarios, Inventario y Pedidos son módulos de una sola aplicación y usan una sola base. La separación en servicios es la siguiente etapa.

## Cómo levantarlo

Requisitos: Git y Docker con Compose.

```sh
git clone https://github.com/pablovaquerogit/sd-2027-1-docker-rangers.git
cd sd-2027-1-docker-rangers
git switch 01-monolito
docker compose up --build -d --wait
```

API: http://localhost:18090 · Documentación interactiva: http://localhost:18090/docs · Salud: http://localhost:18090/health.

Si el puerto está ocupado: `PUERTO_API=18091 docker compose up --build -d --wait`. La contraseña predeterminada es exclusivamente de desarrollo local. Puede cambiarse con `DB_PASSWORD` antes de crear el volumen. PostgreSQL no publica un puerto al host.

## Flujo de compra

1. `POST /api/usuarios`: `{"correo":"ana@example.test","nombre":"Ana","password":"password-demo-123"}`.
2. `POST /api/sesiones`: enviar correo y contraseña. Guardar el `access_token`.
3. `GET /api/productos`: catálogo inicial con teclado, mouse y monitor. Precios en centavos de MXN.
4. `POST /api/pedidos`: cabeceras `Authorization: Bearer TOKEN` e `Idempotency-Key: UUID`; cuerpo `{"items":[{"producto_id":"teclado","cantidad":1}]}`.
5. `GET /api/pedidos/ID`: con la misma sesión. Solo el dueño puede leerlo; para otro usuario responde 404.

La primera compra responde 201. Repetir la llave y el mismo contenido responde 200 con el mismo pedido y la cabecera `Idempotent-Replayed: true`. Cambiar el contenido con esa llave responde 409. Si no alcanza el stock, responde 409 y no guarda ni pedido ni descuentos parciales.

Se bloquean los productos en un orden fijo y pedido, detalles y stock se confirman en una sola transacción. El precio del pedido queda congelado. La llave se identifica por usuario y se conserva con el pedido; no expira en esta versión. Si se cae el servidor después del commit y antes de responder, el cliente puede repetir la misma llave.

## Pruebas

```sh
docker compose --profile test run --rm tests
docker compose --profile test stop db-test
```

Las pruebas usan una base separada y temporal `tienda_test`. Comprueban siete escenarios: reintentos y cambios de contenido, sobreventa bajo diez compras concurrentes, una llave concurrente, autorización de pedidos, rollback de compra con varios productos, precio congelado y validación. Resultado de la ejecución del 6 de noviembre: **7 pruebas aprobadas**. La salida está en `evidencia/pruebas-monolito.txt` en la rama del código.

## Organización y límites

`app/usuarios.py` maneja registro y sesiones; `app/inventario.py`, catálogo; `app/pedidos.py`, compra y consulta; `app/db.py`, esquema y conexión. Los módulos comparten una transacción local porque todavía son un monolito.

Las contraseñas se guardan con sal y PBKDF2; los tokens se guardan como hash y vencen en ocho horas. Es un prototipo local: no hay recuperación de contraseña, verificación de correo, pagos reales, envíos, administración del catálogo ni interfaz web. El stock inicial es demostrativo y no se repone al reiniciar.

Para detener conservando datos: `docker compose down`. El trabajo inicial y su validación se prepararon por Pablo con apoyo de Codex. Cada integrante deberá aportar cambios propios y comprenderlos antes de la defensa.
