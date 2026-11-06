# Docker Rangers · Tienda en línea

Proyecto de Sistemas Distribuidos 2027-1, grupo 2, FI-UNAM. Registro y sesiones, catálogo y compra directa con control de stock, idempotencia y recuperación ante fallas.

| Integrante | GitHub |
| --- | --- |
| Rojas Jiménez Claudia Alin | @Alin021002RJ |
| Hernández Rubio Josué | @Herjoru1 |
| Santana Cardoso Derek | @DerekMstn114 |
| Vaquero Malvaez José Pablo | @pablovaquerogit |

Profesor: @OscarRuiz21. Las invitaciones están enviadas y requieren aceptación de cada persona. Preparación inicial por Pablo con apoyo de Codex; los demás integrantes deben aportar cambios propios y comprenderlos antes de la defensa.

## Dónde está cada versión

| Rama | Contenido |
| --- | --- |
| main | Presentación, PRD y documentación |
| [01-monolito](https://github.com/pablovaquerogit/sd-2027-1-docker-rangers/tree/01-monolito) | Monolito modular FastAPI/PostgreSQL, Compose y siete pruebas aprobadas |
| [02-separacion](https://github.com/pablovaquerogit/sd-2027-1-docker-rangers/tree/02-separacion) | Usuarios, Inventario y Pedidos con bases propias, gateway, balanceo y saga persistida; pruebas HTTP de concurrencia, compensación y reinicio |

[PRD](docs/PRD.md) · [Diagrama y decisiones](docs/DECISIONES.md) · [Pitch, demo y defensa](docs/DEMO-Y-DEFENSA.md).

## Ejecutar la versión distribuida

```sh
git clone https://github.com/pablovaquerogit/sd-2027-1-docker-rangers.git
cd sd-2027-1-docker-rangers
git switch 02-separacion
docker compose -f compose.distribuido.yml up --build -d --wait
python3 tests/distribuido.py
```

API local: http://localhost:18091/api/productos. El README de esa rama contiene el flujo de compra, resultados y límites. El script crea datos ficticios y apaga temporalmente el balanceador interno para probar recuperación. No hay interfaz web ni pagos.

Para el monolito: cambiar a `01-monolito` y ejecutar `docker compose up --build -d --wait`. Documentación interactiva en http://localhost:18090/docs. Su Compose usa otro proyecto y bases; no migra los datos a la versión distribuida.

## Garantía y costo

No se confirma una compra sin reservas de todos sus productos. Inventario une stock y marca idempotente en una operación atómica por documento. Pedidos persiste la intención y su progreso antes de cada recuperación. Un timeout puede dejar estado PENDIENTE: el cliente conserva la misma llave y consulta el resultado. Si falta otro producto, se compensan las reservas anteriores.

La saga permite estados intermedios y no ofrece una transacción global estricta. Dos réplicas de API no eliminan el punto de falla de MongoDB ni del host. No se midió ventaja de rendimiento sobre PostgreSQL. El PRD y las decisiones describen reservas, conciliación y límites de crecimiento que el equipo debe defender.

Presentación del proyecto: 28 de noviembre de 2026; material preparado para ensayo y revisión del equipo.
