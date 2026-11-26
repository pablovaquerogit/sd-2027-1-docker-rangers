"""Prueba de la caída del servicio Usuarios contra el sistema distribuido levantado.

1. Crea un usuario con sesión y un producto de prueba propio (stock 5).
2. Apaga Usuarios (docker compose stop) y comprueba qué sigue funcionando y qué no:
   el catálogo sigue respondiendo, pero Pedidos no puede verificar la sesión (503) y nadie puede iniciar sesión.
3. Lo vuelve a encender y reintenta la MISMA compra con la MISMA Idempotency-Key: un solo pedido, stock −1.
4. Mata el proceso de Usuarios (kill 1) y comprueba que Docker lo reinicia solo (restart: unless-stopped).

Uso:  python tests/caida_usuarios.py            (muestra el resultado)
      python tests/caida_usuarios.py --guardar  (además lo guarda en evidencia/prueba-caida-usuarios.txt)
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
PASSWORD = "password-demo-123"
LINEAS = []
RESULTADOS = []


def decir(texto=""):
    print(texto)
    LINEAS.append(texto)


def revisar(descripcion, ok, detalle=""):
    decir(f"  [{'OK ' if ok else 'FALLO'}] {descripcion}{(': ' + detalle) if detalle else ''}")
    RESULTADOS.append(ok)


def ejecutar(*args):
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


def texto(estado):
    return f"HTTP {estado}" if estado else "sin conexión"


def reinicios_de_usuarios():
    contenedor = ejecutar(*COMPOSE, "ps", "-q", "usuarios")
    if not contenedor:
        return None, "sin contenedor"
    cuenta, estado = ejecutar("docker", "inspect", "-f", "{{.RestartCount}} {{.State.Status}}", contenedor).split()
    return int(cuenta), estado


def esperar_login(correo, limite=90):
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        estado, cuerpo = http("POST", "/api/sesiones", {"correo": correo, "password": PASSWORD})
        if estado == 200:
            return round(time.monotonic() - inicio, 1), cuerpo
        time.sleep(1)
    return None, None


def main():
    guardar = "--guardar" in sys.argv
    correo = str(uuid.uuid4()) + "@example.test"
    http("POST", "/api/usuarios", {"correo": correo, "nombre": "Prueba caída Usuarios", "password": PASSWORD})
    _, sesion = http("POST", "/api/sesiones", {"correo": correo, "password": PASSWORD})
    auth = {"Authorization": "Bearer " + sesion["access_token"]}
    producto = "usuarios-" + str(uuid.uuid4())[:8]
    ejecutar(*COMPOSE, "exec", "-T", "mongo", "mongosh", "--quiet", "inventario", "--eval",
             "db.productos.insertOne(" + json.dumps({"_id": producto, "nombre": "Producto de prueba",
                                                     "precio_centavos": 1234, "stock": 5, "reservas": {}}) + ")")
    clave = str(uuid.uuid4())
    compra = {"items": [{"producto_id": producto, "cantidad": 1}]}

    decir("Caída de Usuarios · " + BASE)
    decir(f"Producto de prueba {producto} con stock 5; llave {clave[:8]}…")
    decir("Con Usuarios apagado (docker compose stop usuarios)")
    ejecutar(*COMPOSE, "stop", "usuarios")
    try:
        estado, _ = http("GET", "/api/productos/" + producto)
        revisar("El catálogo sigue respondiendo (Inventario no depende de Usuarios)", estado == 200, texto(estado))
        estado, cuerpo = http("POST", "/api/pedidos", compra, {**auth, "Idempotency-Key": clave})
        detalle = cuerpo.get("detail", "") if isinstance(cuerpo, dict) else ""
        revisar("Comprar: Pedidos no puede verificar la sesión (503)", estado == 503,
                f"{texto(estado)} {detalle}".strip())
        estado, _ = http("POST", "/api/sesiones", {"correo": correo, "password": PASSWORD})
        revisar("Iniciar sesión no está disponible", estado != 200, texto(estado))
        estado, _ = http("GET", "/api/pedidos/" + str(uuid.uuid4()), headers=auth)
        revisar("Consultar pedidos tampoco (503)", estado == 503, texto(estado))
    finally:
        decir("Se vuelve a encender Usuarios (docker compose start usuarios)")
        ejecutar(*COMPOSE, "start", "usuarios")

    segundos, _ = esperar_login(correo)
    revisar("Iniciar sesión vuelve a funcionar", segundos is not None, f"en {segundos} s" if segundos else "no volvió")

    estado, pedido = http("POST", "/api/pedidos", compra, {**auth, "Idempotency-Key": clave})
    revisar("La misma compra, con la misma llave, se acepta al volver", estado in (200, 201, 202), texto(estado))
    if estado in (200, 201, 202):
        for _ in range(60):
            if pedido["estado"] not in ("PENDIENTE", "COMPENSANDO"):
                break
            time.sleep(1)
            _, pedido = http("GET", "/api/pedidos/" + pedido["id"], headers=auth)
        revisar("El pedido quedó CONFIRMADO", pedido["estado"] == "CONFIRMADO", pedido["estado"])
        _, mis_pedidos = http("GET", "/api/pedidos", headers=auth)
        cuantos = len([p for p in mis_pedidos if any(i["producto_id"] == producto for i in p["items"])])
        revisar("Hay un solo pedido para esa compra", cuantos == 1, f"{cuantos} pedido(s)")
        _, datos = http("GET", "/api/productos/" + producto)
        revisar("El stock bajó una sola vez", datos["stock"] == 4, f"5 → {datos['stock']}")

    decir("Caída real del proceso (kill 1)")
    antes, _ = reinicios_de_usuarios()
    ejecutar(*COMPOSE, "exec", "-T", "usuarios", "sh", "-c", "kill 1")
    segundos, _ = esperar_login(correo)
    despues, estado_contenedor = reinicios_de_usuarios()
    revisar("Docker reinició Usuarios solo (restart: unless-stopped)",
            antes is not None and despues is not None and despues > antes,
            f"reinicios {antes} → {despues}, estado {estado_contenedor}")
    revisar("Iniciar sesión vuelve a funcionar sin intervención", segundos is not None,
            f"en {segundos} s" if segundos else "no volvió")

    if all(RESULTADOS):
        decir("APROBADA: sin Usuarios no se compra ni se inicia sesión, pero el catálogo sigue; "
              "al volver, la misma llave crea un solo pedido y Docker lo reinicia solo.")
    else:
        decir("FALLIDA: revisa las líneas marcadas con FALLO.")
    if guardar:
        destino = ROOT / "evidencia" / "prueba-caida-usuarios.txt"
        destino.write_text("\n".join(LINEAS) + "\n", encoding="utf-8")
        print("Guardado en", destino.relative_to(ROOT))
    if not all(RESULTADOS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
