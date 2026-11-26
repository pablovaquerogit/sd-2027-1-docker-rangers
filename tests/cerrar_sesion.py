"""Prueba de cierre de sesión contra el sistema distribuido levantado (gateway en localhost:18091).

Crea un usuario ficticio, inicia sesión, cierra la sesión con DELETE /api/sesiones y comprueba que
el mismo token ya no sirve ni en Usuarios ni en Pedidos. Solo usa la biblioteca estándar de Python.
"""
import json
import os
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:" + os.getenv("PUERTO_DISTRIBUIDO", "18091")


def http(metodo, ruta, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    datos = json.dumps(body).encode() if body is not None else None
    peticion = urllib.request.Request(BASE + ruta, data=datos, headers=headers, method=metodo)
    try:
        respuesta = urllib.request.urlopen(peticion, timeout=10)
    except urllib.error.HTTPError as error:
        respuesta = error
    with respuesta:
        crudo = respuesta.read().decode()
        return respuesta.status, (json.loads(crudo) if crudo else None)


def revisar(descripcion, obtenido, esperado):
    marca = "OK " if obtenido == esperado else "FALLO"
    print(f"  [{marca}] {descripcion}: HTTP {obtenido} (esperado {esperado})")
    return obtenido == esperado


def main():
    correo = str(uuid.uuid4()) + "@example.test"
    password = "password-demo-123"
    resultados = []

    print("Cierre de sesión ·", BASE)
    estado, _ = http("POST", "/api/usuarios", {"correo": correo, "nombre": "Prueba cierre", "password": password})
    resultados.append(revisar("Registrar usuario", estado, 201))
    estado, sesion = http("POST", "/api/sesiones", {"correo": correo, "password": password})
    resultados.append(revisar("Iniciar sesión", estado, 200))
    token = sesion["access_token"]

    print("Con la sesión abierta")
    resultados.append(revisar("Perfil en Usuarios", http("GET", "/api/usuarios/me", token=token)[0], 200))
    resultados.append(revisar("Mis pedidos en Pedidos", http("GET", "/api/pedidos", token=token)[0], 200))

    print("Cerrar sesión")
    resultados.append(revisar("DELETE /api/sesiones sin token", http("DELETE", "/api/sesiones")[0], 401))
    resultados.append(revisar("DELETE /api/sesiones", http("DELETE", "/api/sesiones", token=token)[0], 204))

    print("Con el mismo token después de cerrar")
    resultados.append(revisar("Perfil en Usuarios", http("GET", "/api/usuarios/me", token=token)[0], 401))
    resultados.append(revisar("Mis pedidos en Pedidos", http("GET", "/api/pedidos", token=token)[0], 401))
    resultados.append(revisar("Cerrar otra vez (idempotente)", http("DELETE", "/api/sesiones", token=token)[0], 204))

    print("Una sesión nueva sigue funcionando")
    estado, sesion = http("POST", "/api/sesiones", {"correo": correo, "password": password})
    resultados.append(revisar("Iniciar sesión de nuevo", estado, 200))
    resultados.append(revisar("Perfil con el token nuevo", http("GET", "/api/usuarios/me", token=sesion["access_token"])[0], 200))

    if all(resultados):
        print("APROBADA: el token cerrado ya no sirve en Usuarios ni en Pedidos.")
    else:
        print("FALLIDA: revisa las líneas marcadas con FALLO.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
