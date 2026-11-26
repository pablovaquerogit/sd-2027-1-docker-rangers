"""Prueba de la caída del servicio Pedidos contra el sistema distribuido levantado.

1. Crea un usuario y un producto de prueba propios (stock 5).
2. Mata el proceso de Pedidos desde dentro del contenedor (kill 1), como si se cayera.
3. Intenta comprar mientras está caído y reintenta cada segundo con la MISMA Idempotency-Key.
4. Comprueba que Docker reinició Pedidos solo (restart: unless-stopped), que hay UN solo pedido
   CONFIRMADO y que el stock bajó una sola vez.

Uso:  python tests/caida_pedidos.py            (muestra el resultado)
      python tests/caida_pedidos.py --guardar  (además lo guarda en evidencia/prueba-caida-pedidos.txt)
Requiere Docker y el sistema levantado con compose.distribuido.yml. Solo usa la biblioteca estándar.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:" + os.getenv("PUERTO_DISTRIBUIDO", "18091")
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.distribuido.yml")]
LINEAS = []


def decir(texto=""):
    print(texto)
    LINEAS.append(texto)


def docker(*args):
    return subprocess.run([*args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def http(metodo, ruta, body=None, headers=None):
    datos = json.dumps(body).encode() if body is not None else None
    peticion = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                      headers={"Content-Type": "application/json", **(headers or {})})
    try:
        respuesta = urllib.request.urlopen(peticion, timeout=10)
    except urllib.error.HTTPError as error:
        respuesta = error
    except OSError as error:
        return None, str(error)
    with respuesta:
        crudo = respuesta.read().decode()
        try:
            return respuesta.status, json.loads(crudo) if crudo else None
        except ValueError:
            return respuesta.status, crudo


def reinicios_de_pedidos():
    contenedor = docker(*COMPOSE, "ps", "-q", "pedidos")
    if not contenedor:
        return None, "sin contenedor"
    salida = docker("docker", "inspect", "-f", "{{.RestartCount}} {{.State.Status}}", contenedor)
    cuenta, estado = salida.split()
    return int(cuenta), estado


def main():
    guardar = "--guardar" in sys.argv
    correo = str(uuid.uuid4()) + "@example.test"
    http("POST", "/api/usuarios", {"correo": correo, "nombre": "Prueba caída", "password": "password-demo-123"})
    _, sesion = http("POST", "/api/sesiones", {"correo": correo, "password": "password-demo-123"})
    auth = {"Authorization": "Bearer " + sesion["access_token"]}

    producto = "caida-" + str(uuid.uuid4())[:8]
    docker(*COMPOSE, "exec", "-T", "mongo", "mongosh", "--quiet", "inventario", "--eval",
           "db.productos.insertOne(" + json.dumps({"_id": producto, "nombre": "Producto de prueba",
                                                   "precio_centavos": 1234, "stock": 5, "reservas": {}}) + ")")
    clave = str(uuid.uuid4())
    compra = {"items": [{"producto_id": producto, "cantidad": 1}]}
    reinicios_antes, _ = reinicios_de_pedidos()

    decir("Caída de Pedidos · " + BASE)
    decir(f"Producto de prueba {producto} con stock 5; llave {clave[:8]}…")
    decir("Se mata el proceso de Pedidos (kill 1) y se intenta comprar mientras está caído")
    docker(*COMPOSE, "exec", "-T", "pedidos", "sh", "-c", "kill 1")

    respuestas = []
    inicio = time.monotonic()
    estado, cuerpo = None, None
    while time.monotonic() - inicio < 90:
        estado, cuerpo = http("POST", "/api/pedidos", compra, {**auth, "Idempotency-Key": clave})
        respuestas.append(estado if estado else "sin conexión")
        if estado in (200, 201, 202):
            break
        time.sleep(1)
    segundos = round(time.monotonic() - inicio, 1)
    resumen = {}
    for r in respuestas:
        resumen[r] = resumen.get(r, 0) + 1
    decir(f"  Intentos con la misma llave: {len(respuestas)} en {segundos} s → "
          + ", ".join(f"{n} × {'HTTP ' + str(r) if isinstance(r, int) else r}" for r, n in resumen.items()))

    resultados = []

    def revisar(descripcion, ok, detalle=""):
        decir(f"  [{'OK ' if ok else 'FALLO'}] {descripcion}{(': ' + detalle) if detalle else ''}")
        resultados.append(ok)

    revisar("Hubo al menos un intento fallido mientras Pedidos estaba caído",
            any(r not in (200, 201, 202) for r in respuestas))
    revisar("La compra terminó aceptada al volver Pedidos", estado in (200, 201, 202), f"HTTP {estado}")
    if estado not in (200, 201, 202):
        return terminar(resultados, guardar)

    pedido = cuerpo
    for _ in range(60):
        if pedido["estado"] not in ("PENDIENTE", "COMPENSANDO"):
            break
        time.sleep(1)
        _, pedido = http("GET", "/api/pedidos/" + pedido["id"], headers=auth)
    revisar("El pedido quedó CONFIRMADO", pedido["estado"] == "CONFIRMADO", pedido["estado"])

    reinicios_despues, estado_contenedor = reinicios_de_pedidos()
    revisar("Docker reinició Pedidos solo (restart: unless-stopped)",
            reinicios_despues is not None and reinicios_antes is not None and reinicios_despues > reinicios_antes,
            f"reinicios {reinicios_antes} → {reinicios_despues}, estado {estado_contenedor}")

    _, mis_pedidos = http("GET", "/api/pedidos", headers=auth)
    del_producto = [p for p in mis_pedidos if any(i["producto_id"] == producto for i in p["items"])]
    revisar("Hay un solo pedido para esa compra", len(del_producto) == 1, f"{len(del_producto)} pedido(s)")

    _, datos = http("GET", "/api/productos/" + producto)
    revisar("El stock bajó una sola vez", datos["stock"] == 4, f"5 → {datos['stock']}")
    return terminar(resultados, guardar)


def terminar(resultados, guardar):
    if all(resultados):
        decir("APROBADA: Pedidos volvió solo y la compra se hizo una sola vez con la misma llave.")
    else:
        decir("FALLIDA: revisa las líneas marcadas con FALLO.")
    if guardar:
        destino = ROOT / "evidencia" / "prueba-caida-pedidos.txt"
        destino.write_text("\n".join(LINEAS) + "\n", encoding="utf-8")
        print("Guardado en", destino.relative_to(ROOT))
    if not all(resultados):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
