### UNIVERSIDAD NACIONAL AUTÓNOMA DE MÉXICO

Facultad de Ingeniería · Sistemas Distribuidos 2027-1 · Grupo 2

DOCKER RANGERS

Reporte final del proyecto

Tienda distribuida con reservas idempotentes y recuperación de pedidos

Integrantes | Usuario de GitHub

--- | ---

Rojas Jiménez Claudia Alin | Alin021002RJ

Hernández Rubio Josué | Herjoru1

Santana Cardoso Derek | DerekMstn114

Vaquero Malvaez José Pablo | pablovaquerogit

Profesor: Oscar Ruiz · @OscarRuiz21

Documentación: Derek Santana · Revisión ampliada: 27 de noviembre de 2026

### Repositorio del equipo

https://github.com/pablovaquerogit/sd-2027-1-docker-rangers

Versión técnica analizada: caida-usuarios, commit ee71ef7d0809b81fda62d3ad7db223fca16c7699. Documentación inicial: main f33e90f.

Entrega prevista: antes del 28 de noviembre de 2026 a las 07:00, hora de Ciudad de México.

## Resumen e índice de lectura

Docker Rangers es un prototipo de tienda que permite registrar clientes, consultar un catálogo y comprar varios productos. Su objetivo técnico es impedir sobreventa y evitar efectos duplicados cuando una solicitud se repite o la red pierde una respuesta. La versión distribuida separa Usuarios, Inventario y Pedidos, conserva datos por servicio y utiliza una saga persistida para completar o compensar las compras.

El resultado principal es la recuperación de una operación con identidad estable. La evidencia registrada incluye tres compras confirmadas entre diez intentos por tres unidades, cinco solicitudes con una sola llave sin descuento repetido y recuperación tras caídas. El prototipo acepta estados intermedios y sigue dependiendo de bases únicas y de un solo host. Estas limitaciones forman parte del diseño evaluado.

### Organización del reporte

Apartado | Contenido

--- | ---

1–2 | Problema, usuarios, alcance y flujo funcional

3–4 | Arquitectura, propiedad de datos y contratos HTTP

5 | Saga, idempotencia y recuperación del progreso

6–7 | Decisiones, alternativas y costos aceptados

8–9 | Manejo de fallas, pruebas y resultados registrados

10 | Ejecución reproducible y recorrido de validación

11 | Limitaciones y mejoras priorizadas

12 | Aportaciones, conclusiones y referencias

### Criterio de elaboración

Este reporte relaciona el código de ee71ef7 con sus evidencias, evitando presentar características propuestas como implementadas. El PRD inicial excluía la interfaz web; las ramas posteriores sí la incorporaron. Por ello, la descripción funcional utiliza el código más reciente revisado y señala ese cambio de alcance. La rama final de presentación todavía debe confirmarse en equipo.

Las salidas de pruebas citadas provienen del repositorio del equipo. No se ejecutaron de nuevo al elaborar esta revisión. El documento se preparó con asistencia de IA y requiere comprensión y revisión de los cuatro integrantes. La rúbrica asigna al reporte el 30% del proyecto, equivalente al 9% del curso [R1].

## 1. Problema, usuarios y alcance

### 1.1 Necesidad que atiende el sistema

El cliente necesita saber qué puede comprar, enviar su solicitud y conocer su resultado. El catálogo es una fotografía que puede cambiar después de leerla: mostrar una unidad disponible no garantiza que siga libre al reservar. Si dos clientes compiten por ella, el sistema debe decidir mediante una operación coordinada sobre el inventario, no mediante la lectura previa de la pantalla.

Una segunda dificultad aparece cuando una respuesta se pierde. El cliente puede recibir un error aunque Inventario ya haya descontado. Repetir la compra como una operación nueva podría descontar dos veces. El sistema conserva la identidad del intento y distingue una negativa de negocio de un resultado remoto todavía desconocido.

### 1.2 Objetivos y criterios de aceptación

Objetivo | Criterio observable

--- | ---

Evitar sobreventa | Con tres unidades y diez compras concurrentes, solo tres se confirman y el stock termina en cero.

Evitar duplicados | La misma llave, usuario y contenido recuperan el mismo pedido. Otro contenido con esa llave produce 409.

Recuperar una operación | Tras reiniciar Pedidos, el trabajador retoma progreso persistido cuando la dependencia vuelve.

Proteger datos de clientes | Una sesión inválida devuelve 401. Otro dueño no puede consultar un pedido ajeno.

Comunicar incertidumbre | Un 202 mantiene la compra pendiente y permite consultar su estado sin anunciar éxito.

### 1.3 Incluido y fuera del alcance

Incluido: registro, sesiones, revocación al cerrar sesión, catálogo, compra directa de varios productos, precios congelados, consulta de pedidos, reservas, compensación e interfaz web. El entorno usa cuentas y productos ficticios para demostración local.

Fuera del alcance: pagos reales o simulados, logística, direcciones de envío, administración de catálogo, recuperación de contraseña y operación productiva. La evidencia prueba escenarios funcionales concretos; no establece capacidad máxima, un SLA ni superioridad de rendimiento frente al monolito. Fuentes: [F1], [F2] y [E1].

## 2. Flujo funcional de punta a punta

[Diagrama flow incluido en el PDF; generado por docs/generar-reporte.py.]

Figura 1. Flujo de compra y resultados alternativos. Las ramas representan éxito, rechazo e incertidumbre. El cliente consulta el pedido existente mientras Pedidos continúa su trabajo. La compensación puede tardar y también puede requerir intervención.

### Intervención de cada componente

Usuarios registra y autentica. Inventario atiende la consulta del catálogo. Al comprar, el gateway envía la petición a Pedidos, que verifica la sesión con Usuarios, guarda la intención y solicita reservas a Inventario. Tras confirmar todas las reservas, Pedidos publica el resultado definitivo. El navegador muestra ese estado y consulta su evolución cuando queda pendiente.

Si un producto no puede reservarse, Pedidos registra COMPENSANDO antes de liberar reservas anteriores. Al terminar queda RECHAZADO. Si hay un conflicto durante confirmación o liberación, puede registrarse REVISION_PENDIENTE para conciliación manual. Un timeout conserva el estado recuperable, sin confundirlo con falta de stock [F3].

## 3. Arquitectura y comunicación

[Diagrama arch incluido en el PDF; generado por docs/generar-reporte.py.]

Figura 2. Componentes y almacenes. Las flechas representan llamadas HTTP o acceso al almacén propio. Pedidos consulta Usuarios y usa el Nginx interno para las operaciones de reserva. El gateway balancea las lecturas del catálogo directamente hacia las instancias de Inventario.

El gateway publica únicamente 127.0.0.1:18091 y sirve la interfaz web. Usuarios y Pedidos tienen instancias PostgreSQL independientes. Las dos API de Inventario comparten MongoDB. Ningún servicio necesita consultar directamente la base de otro para ejecutar el flujo de compra [F4].

El directorio es el DNS de Compose. Ambos Nginx usan resolución dinámica con resolver, zone y resolve para volver a descubrir destinos tras reiniciar contenedores. DNS proporciona direcciones y Nginx reparte solicitudes. Replicar la API no replica sus datos: MongoDB, las bases PostgreSQL, el gateway y el host continúan siendo puntos únicos de falla [F5].

## 4. Datos y contratos de la API

### 4.1 Propiedad y persistencia

Componente | Información propia | Regla relevante

--- | --- | ---

Usuarios / PostgreSQL | Cuentas y sesiones | Contraseñas con sal/PBKDF2 y tokens almacenados como hash. Sesiones de ocho horas.

Pedidos / PostgreSQL | Dueño, llave, contenido, estado, historial y progreso | Conservar intención antes de llamar por HTTP. Persistir cada avance de la saga.

Inventario / MongoDB | Productos, stock y reservas embebidas | Condición de stock, descuento y marca en una actualización por producto.

Las reservas conservan nombre y precio al crearse. El dinero se representa en enteros, en centavos MXN, para evitar cálculos monetarios con punto flotante. La suma confirmada corresponde a los precios reservados, aunque el catálogo cambie después. Las reservas de distintos productos no forman una única transacción global.

### 4.2 Contratos públicos principales

Método y ruta | Uso y respuesta significativa

--- | ---

POST /api/usuarios | Registrar una cuenta con correo, nombre y contraseña.

POST /api/sesiones | Autenticar y obtener access_token.

DELETE /api/sesiones | Revocar sesión. 204 al cerrar o repetir el cierre autenticado de un token ya revocado. Sin token: 401.

GET /api/productos | Consultar catálogo y observar X-Instancia.

POST /api/pedidos | Bearer token e Idempotency-Key. 201 al confirmar uno nuevo, 200 al repetir uno confirmado, 202 si queda pendiente y 409 ante conflicto.

GET /api/pedidos[/ID] | Consultar pedidos propios. Sin sesión válida: 401. Pedido de otro dueño: 404.

El código limita cada compra a 1–20 renglones y cada cantidad a un entero de 1–100. Las operaciones internas de Inventario exigen X-Internal-Key. El gateway no publica esas rutas y limpia ese encabezado en las solicitudes externas. Esto acota la demo local, pero no sustituye controles productivos de red, TLS y gestión de secretos [F1, F3, F5].

## 5. Saga e idempotencia

### 5.1 Orden de los efectos

Pedidos primero valida la identidad del usuario y la solicitud, y guarda un pedido. Solo entonces llama a Inventario. Cada reserva une pedido y producto como identidad. Pedidos persiste la respuesta y el avance de cada renglón antes de continuar. Un candado de sesión PostgreSQL serializa el procesamiento por pedido, mientras los commits de progreso permanecen separados de las llamadas HTTP.

Después de reservar los productos, la saga confirma las reservas. El pedido alcanza CONFIRMADO únicamente cuando ese proceso concluye. Si una reserva se rechaza por una regla de negocio, se guarda COMPENSANDO antes de iniciar devoluciones. Cada liberación puede repetirse y, al completar todas, se registra RECHAZADO. Un conflicto no recuperable automáticamente queda visible como REVISION_PENDIENTE [F3].

### 5.2 Ejemplo: respuesta perdida

Paso | Hecho y consecuencia

--- | ---

1 | Inventario recibe una reserva, descuenta una unidad y guarda la marca.

2 | La respuesta no llega a Pedidos. El timeout no permite saber si hubo efecto.

3 | Pedidos conserva el trabajo pendiente y reintenta con el mismo pedido/producto.

4 | Inventario encuentra la reserva previa y devuelve su resultado. No descuenta de nuevo.

5 | Pedidos persiste ese progreso, confirma la reserva y completa el pedido cuando corresponde.

### 5.3 Garantías y frontera de la solución

La deduplicación depende de conservar las identidades y el almacenamiento. No se promete entrega de mensajes exactamente una vez: puede haber varios intentos, pero las operaciones controlan la repetición de efectos. Una pérdida definitiva de la base de Pedidos excede la recuperación por reinicio y exige restauración y conciliación con Inventario.

La atomicidad de un producto protege stock y marca juntos. No garantiza que catálogo y pedidos muestren un estado global idéntico en cada instante. Se sacrifica confirmación inmediata cuando el resultado remoto es incierto, priorizando no anunciar una compra sin reservas confirmadas.

## 6. Decisiones y alternativas I

### D1. Separar por responsabilidad de negocio

Elección: Usuarios, Inventario y Pedidos con datos propios. Permite explicar y operar límites de responsabilidad y fallas parciales. Alternativa descartada para esta etapa: conservar todo el flujo en el monolito PostgreSQL. Lo que se dejó atrás fue una compra resuelta con una sola transacción local y un despliegue más sencillo.

Costo aceptado: contratos HTTP, varias bases, estados intermedios y mayor trabajo de operación. La separación responde al objetivo del curso; no se afirma que un monolito no escale ni que aumentar servicios mejore automáticamente el sistema.

### D2. Saga persistida en lugar de coordinación en memoria

Elección: guardar intención, avances y compensación en Pedidos. Alternativa descartada: ejecutar llamadas remotas y conservar el progreso solo en memoria. Un reinicio perdería qué operaciones ya se realizaron. También se evita tratar una cadena de llamadas HTTP como si tuviera rollback global.

Costo aceptado: lógica de reanudación, liberaciones idempotentes y conciliación. Lo que se dejó atrás es la simplicidad de devolver éxito o error inmediatamente. La persistencia permite retomar tras una caída del proceso, mientras sobreviva su base de datos.

### D3. Reserva embebida y atómica por producto

Elección: guardar stock y marca de reserva en el mismo documento MongoDB. Alternativa descartada: descontar y después escribir la marca en operaciones separadas. Una caída entre ambas dejaría un descuento sin registro para deduplicar.

Costo aceptado: crecimiento del documento y necesidad de diseñar retención antes de alcanzar el límite de 16 MB. Lo que se dejó atrás es separar fácilmente un historial ilimitado en otra colección sin coordinación adicional. MongoDB se usa para practicar esta estructura documental; no existe una medición que demuestre superioridad frente a PostgreSQL.

Base de las decisiones: docs/DECISIONES.md, PRD y código de reservas y saga. Las alternativas explican los compromisos del diseño, no una comparación experimental de rendimiento [F2, F3, F6].

## 7. Decisiones y alternativas II

### D4. Identidad durable de la compra

Elección: asociar la llave de idempotencia al usuario y al contenido. Alternativa descartada: deduplicar únicamente en memoria o generar una llave distinta después de cada timeout. La primera pierde protección al reiniciar; la segunda puede representar otra compra.

Costo aceptado: conservar identidades y detectar conflictos. Lo que se dejó atrás es considerar cada POST como una intención independiente. El cliente también participa: conserva su llave y consulta el pedido existente cuando desconoce el resultado.

### D5. Descubrimiento con DNS y balanceo con Nginx

Elección: usar el DNS de Compose y resolución dinámica en Nginx. Alternativas descartadas: fijar IP de contenedores o añadir un directorio independiente para esta demo. Las IP antiguas causaron problemas en pruebas de reinicio y justificaron redescubrir destinos.

Costo aceptado: dependencia del host, de DNS y de las ventanas de refresco. Lo que se dejó atrás es administrar direcciones manualmente, a cambio de asumir la infraestructura de Compose. Dos instancias permiten probar reparto y caída de una API, pero no demuestran capacidad horizontal ilimitada.

### D6. Conservar reservas hasta resolver su relación con Pedidos

Elección: no liberar reservas automáticamente por un vencimiento de reloj desconectado de la saga. Alternativa descartada: aplicar un TTL que devuelva stock de forma unilateral. Una reserva podría corresponder a un pedido ya confirmado; devolverla permitiría volver a vender esas unidades.

Costo aceptado: retención y operación de conciliación. Lo que se dejó atrás es una limpieza automática simple. La evolución del sistema necesita reglas explícitas para cerrar o archivar identidades sin permitir que una petición antigua vuelva a producir efectos.

### Relación entre las decisiones

La persistencia de Pedidos, la reserva idempotente y la retención de identidades funcionan juntas. Quitar una de ellas debilita la recuperación. El balanceo mejora la continuidad de la API, mientras la corrección de la compra depende de los datos y del protocolo de saga [F3–F6].

## 8. Manejo de fallas

Falla | Respuesta y recuperación | Límite

--- | --- | ---

Una réplica de Inventario cae | El catálogo puede reenviar internamente tras 502/504 a otra instancia. | La otra API también depende del mismo MongoDB.

Inventario no responde a la saga | Timeout y circuito. Se conserva progreso y se reintenta con la misma identidad. | La compra puede quedar pendiente durante una caída prolongada.

Proceso Pedidos termina | Docker lo reinicia. El trabajador lee PENDIENTE/COMPENSANDO persistidos. | Requiere conservar PostgreSQL. Un stop intencional no equivale a caída del proceso.

Usuarios no está disponible | El catálogo sigue disponible. Pedidos no puede verificar la sesión y responde 503. | No se permite comprar sin validar identidad.

Falla durante compensación | COMPENSANDO ya está guardado y la liberación es idempotente. | Conflictos pueden exigir REVISION_PENDIENTE.

Se pierde definitivamente una base | Se requiere restauración y conciliación de información. | No hay evidencia de restauración ni réplica de datos probada.

### Parámetros implementados

Las llamadas de Pedidos a Inventario usan timeout de conexión de 1 segundo y de lectura de 3 segundos. El circuito abre después de tres fallas, espera 10 segundos y permite una prueba semiabierta. El trabajador agenda reintentos con espera de 2 a 30 segundos. Son mecanismos para limitar presión y permitir recuperación, no un plazo máximo global para la compra [F7].

### Diagnóstico

Los servicios registran JSON con servicio, ruta, duración, estado y trace_id, y propagan X-Request-ID en la saga. Esto permite relacionar llamadas durante la demo. No hay recolector central, métricas operativas ni una plataforma completa de trazas. Una respuesta /health confirma una comprobación puntual, no el éxito del recorrido completo.

## 9. Evidencias y lectura de resultados

La tabla resume salidas conservadas en el repositorio. Las pruebas distribuidas iniciales corresponden al 6 de noviembre. Las pruebas adicionales están incluidas en ee71ef7. No se presentan como mediciones repetidas para este reporte ni como una prueba de estrés de producción.

Escenario | Resultado registrado | Fuente

--- | --- | ---

Concurrencia de stock | 10 compras por 3 unidades: 3 confirmadas, 7 rechazadas y stock 0. | E1

Llave repetida | 5 solicitudes simultáneas: un pedido y un descuento. | E1

Compra con varios productos | El rechazo de un producto devuelve la reserva previa del otro. | E1

Reinicio del orquestador | Un pedido pendiente persiste y termina al recuperar Inventario. | E1

Caída de una API de Inventario | Antes del ajuste: 1 HTTP 504 entre 16 lecturas. Después: 16 HTTP 200. Al volver, reparto 8/8. | E2

Cierre de sesión | 204 al revocar; el token recibe 401 en Usuarios y Pedidos. Repetir cierre: 204. | E3

Caída de Pedidos | 7 intentos en 30 s: 3 respuestas 502, 3 respuestas 504 y 1 respuesta 201. Un pedido, stock 5 a 4. | E4

Caída de Usuarios | Catálogo 200; compra y consulta de pedidos 503; login 504. Al volver: un pedido y un descuento. | E5

### Qué permiten concluir

Los resultados respaldan las invariantes de esos escenarios: controlar el descuento concurrente, deduplicar intentos y recuperar progreso. La prueba de Pedidos también demuestra que hubo una interrupción observable antes de recuperarse. El resultado de la réplica mejoró después de una corrección concreta del catálogo.

No permiten inferir un SLA, latencia típica, capacidad máxima o recuperación ante pérdida de discos. Tampoco basta que un contenedor esté running para afirmar que todas las operaciones de negocio funcionan. Para repetir los escenarios se incluyen los comandos del siguiente apartado.

## 10. Cómo levantarlo y probarlo

### 10.1 Entorno y arranque reproducible

Requisitos: Git, Docker con Compose y Python 3. El entorno usa FastAPI, PostgreSQL 17, MongoDB 8.0 y Nginx 1.27.5. Se fija el commit analizado para evitar que una rama posterior cambie lo que se intenta reproducir. El primer arranque necesita descargar imágenes y construir las API.

```sh
git clone https://github.com/pablovaquerogit/sd-2027-1-docker-rangers.git
cd sd-2027-1-docker-rangers
git switch --detach ee71ef7
docker compose -f compose.distribuido.yml up --build -d --wait
docker compose -f compose.distribuido.yml ps
```

Abrir http://localhost:18091/. Verificar el catálogo en /api/productos y la salud de Pedidos en /health. Si el puerto está ocupado, definir PUERTO_DISTRIBUIDO antes de levantar. DB_PASSWORD e INTERNAL_KEY tienen valores locales de desarrollo; cambiarlos antes de crear volúmenes si se prepara otro entorno.

### 10.2 Pruebas automatizadas

```sh
python3 tests/distribuido.py
python3 tests/replica_inventario.py
python3 tests/cerrar_sesion.py
python3 tests/caida_pedidos.py
python3 tests/caida_usuarios.py
```

Ejecutar secuencialmente, con el entorno levantado y sin otra demo simultánea. Los scripts crean datos ficticios y varios detienen o reinician componentes. Comprobar sus aserciones y el resultado final de cada operación, no solo el código HTTP de un intento. Conservar la salida y el commit usado si se agregan nuevas evidencias.

### 10.3 Recorrido manual y cierre

Registrar usuario e iniciar sesión. Consultar el catálogo y enviar una compra con llave nueva. Repetir la misma llave y contenido: verificar el mismo ID y un solo descuento. Cambiar contenido conservando la llave: esperar 409. Consultar con el dueño y cerrar sesión. Ante 202, consultar ese pedido hasta resolverlo; no generar una compra nueva para “corregir” el timeout.

```sh
docker compose -f compose.distribuido.yml down
```

Este cierre conserva los volúmenes. La eliminación de datos no forma parte del procedimiento normal de la demo. Para diagnosticar, usar docker compose -f compose.distribuido.yml logs con el servicio afectado.

## 11. Límites y mejoras priorizadas

### 11.1 Limitaciones vigentes

La demo funciona en un solo host y publica un puerto local sin TLS. El gateway y los almacenes son únicos. La configuración no proporciona replicación de datos, restauración probada ni despliegue público endurecido. La continuidad demostrada ante una API caída no equivale a alta disponibilidad de todo el sistema.

Las reservas embebidas crecen y necesitan retención segura. Un pedido en REVISION_PENDIENTE requiere conciliación. No hay broker ni Outbox, pagos, logística, administración del catálogo o recuperación de contraseña. Los logs actuales ayudan a observar solicitudes, pero no detectan por sí solos todos los pedidos que llevan demasiado tiempo pendientes.

### 11.2 Qué haríamos distinto al evolucionar

Prioridad | Cambio propuesto | Criterio de validación futuro

--- | --- | ---

1 | Respaldos y recuperación de bases | Restaurar un entorno y reconciliar pedidos y reservas sin duplicar efectos.

2 | Herramienta de conciliación | Listar y resolver REVISION_PENDIENTE con decisiones auditables.

3 | Retención idempotente | Archivar marcas con una política que impida reejecutar operaciones antiguas.

4 | Observabilidad | Medir antigüedad de pendientes, errores por dependencia y duración del flujo completo.

5 | Seguridad y capacidad | Gestionar secretos, TLS y límites de tráfico. Medir carga antes de añadir réplicas o motores.

Antes de distribuir más componentes, mediríamos dónde está el límite real. Para un alcance pequeño, el monolito puede seguir siendo una alternativa adecuada. Conservaríamos la disciplina de hacer explícitos los estados y la identidad de la compra, porque esos contratos resultan útiles incluso antes de aumentar la infraestructura.

### Conclusión técnica

La solución hace visible el costo de distribuir una operación: se pierde el rollback global y se necesita persistencia, reintentos idempotentes y compensación. La evidencia documenta esos mecanismos bajo fallas concretas. El siguiente paso no consiste solo en añadir servicios, sino en hacer verificable la operación y recuperación de sus datos.

## 12. Aportaciones y trazabilidad

Integrante | Aportación respaldada | Commits de referencia

--- | --- | ---

José Pablo Vaquero | PRD, monolito, separación de servicios, saga, pruebas y documentación inicial. | f59ff1c, c6a9861, 9d315bb, f33e90f

Josué Hernández | Interfaz web y prueba de caída de una réplica de Inventario. | 1fa3860, a315d8e

Claudia Alin Rojas | Cierre de sesión, seguimiento de pendientes, recuperación y pruebas de Pedidos y Usuarios. | 4d3e194, 7fb8d26, 3e4370e, 602cb4b, 4499ab0, ee71ef7

Derek Santana | Reporte, diagramas, análisis de decisiones y evidencias, presentación y guion repartido entre los cuatro. | be64dd7, 27a1129, 33485fd y revisión ampliada del reporte

Las atribuciones se basan en el historial revisado. El reparto de exposición es una propuesta de ensayo y no sustituye la comprensión individual del flujo completo. La elaboración documental contó con asistencia de IA. El equipo debe revisar el documento, confirmar la versión de demo y preparar las respuestas de defensa.

### Correspondencia con la rúbrica

Requisito del reporte | Ubicación

--- | ---

Portada, integrantes y repositorio | Portada

Problema y usuarios | Apartado 1

Diagrama funcional y de arquitectura | Apartados 2 y 3

Decisiones, alternativas y sacrificios | Apartados 6 y 7

Manejo de fallas | Apartados 5, 8 y 9

Ejecución y pruebas | Apartado 10

Qué falta y qué haríamos distinto | Apartado 11

Quién hizo qué | Apartado 12

El PDF debe incorporarse como docs/reporte-final.pdf al repositorio del equipo antes del cierre indicado por la rúbrica. La existencia de una propuesta de integración no equivale a haber incorporado el documento a la rama de entrega [R1].

## Referencias y archivos de evidencia

Repositorio base: https://github.com/pablovaquerogit/sd-2027-1-docker-rangers. Los identificadores F y E remiten a rutas dentro de la revisión ee71ef7, salvo indicación expresa. La versión fijada permite inspeccionar las mismas fuentes aunque las ramas cambien.

ID | Fuente y uso

--- | ---

F1 | README.md: rutas públicas, puesta en marcha y descripción de pruebas.

F2 | docs/PRD.md: problema, reglas e historias de aceptación. Su exclusión inicial de interfaz queda superada por web/ en ee71ef7.

F3 | dist/pedidos_app.py: intención persistida, procesamiento de saga, compensación, trabajador y respuestas de compra.

F4 | compose.distribuido.yml: servicios, dependencias, imágenes, volúmenes, puerto local y política de reinicio.

F5 | nginx/gateway.conf y nginx/inventario-lb.conf: rutas, balanceo y resolución dinámica.

F6 | dist/inventario_app.py y docs/DECISIONES.md: reserva atómica, idempotencia, invariantes y decisiones.

F7 | dist/remotos.py: timeouts, errores y circuito hacia Inventario.

F8 | dist/usuarios_app.py y web/: sesiones, revocación e interacción del cliente.

E1 | evidencia/pruebas-distribuidas.json y pruebas-distribuidas.txt: concurrencia, balanceo, autorización, compensación y recuperación.

E2 | evidencia/prueba-replica-inventario.txt: comparación antes y después del ajuste ante la caída de una API.

E3 | evidencia/prueba-cerrar-sesion.txt: revocación y rechazo del token en ambos servicios.

E4 | evidencia/prueba-caida-pedidos.txt: reinicio, respuestas transitorias y compra única.

E5 | evidencia/prueba-caida-usuarios.txt: alcance de la caída, recuperación y stock.

R1 | OscarRuiz21/sd-2027-1, proyecto/RUBRICA.md: criterios, ponderaciones y fecha de entrega.

Rúbrica: https://github.com/OscarRuiz21/sd-2027-1/blob/main/proyecto/RUBRICA.md

Implementación fijada: https://github.com/pablovaquerogit/sd-2027-1-docker-rangers/tree/ee71ef7
