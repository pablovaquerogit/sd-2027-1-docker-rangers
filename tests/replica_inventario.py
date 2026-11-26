"""Prueba local del catálogo al detener una réplica de Inventario."""
from collections import Counter
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ("compose", "-f", "compose.distribuido.yml")
CONSULTAS = 16
INTERVALO = 0.2


def docker(*args):
    return subprocess.check_output(("docker", *args), cwd=ROOT, text=True).strip()


def consultar(url):
    try:
        with urlopen(url, timeout=4) as respuesta:
            respuesta.read()
            return f"HTTP {respuesta.status}", respuesta.headers.get("X-Instancia")
    except HTTPError as error:
        with error:
            return f"HTTP {error.code}", error.headers.get("X-Instancia")
    except OSError:
        return "Error de conexión", None


def medir(url, etapa):
    resultados = []
    for _ in range(CONSULTAS):
        resultados.append(consultar(url))
        time.sleep(INTERVALO)

    print(f"\n{etapa} ({len(resultados)} consultas)")
    for (estado, instancia), total in Counter(resultados).items():
        print(f"  {total:2d} x {estado} | X-Instancia: {instancia or '-'}")
    return set(resultados)


def main():
    contenedores = docker(*COMPOSE, "ps", "-q", "inventario").splitlines()
    if len(contenedores) != 2:
        raise SystemExit("Levanta la versión distribuida con dos réplicas de Inventario.")

    a_detener, superviviente = contenedores
    instancia_detenida, instancia_activa = docker(
        "inspect", "--format", "{{.Config.Hostname}}", a_detener, superviviente
    ).splitlines()
    puerto = docker(*COMPOSE, "port", "gateway", "8000").rsplit(":", 1)[-1]
    url = f"http://127.0.0.1:{puerto}/api/productos"

    print(f"Catálogo: {url}")
    print(f"Réplica que se detendrá: {instancia_detenida}")
    print(f"Réplica que seguirá activa: {instancia_activa}")
    ambas = {("HTTP 200", instancia_detenida), ("HTTP 200", instancia_activa)}
    antes = medir(url, "Antes de la caída")
    if antes != ambas:
        raise SystemExit("FALLÓ: el catálogo no repartió las consultas entre ambas réplicas.")

    try:
        docker("stop", a_detener)
        durante = medir(url, "Con una réplica detenida")
    finally:
        docker("start", a_detener)

    limite = time.monotonic() + 15
    while time.monotonic() < limite:
        if consultar(url) == ("HTTP 200", instancia_detenida):
            break
        time.sleep(INTERVALO)

    despues = medir(url, "Después de levantar la réplica")

    if durante != {("HTTP 200", instancia_activa)}:
        raise SystemExit("FALLÓ: la réplica activa no atendió todas las consultas durante la caída.")
    if despues != ambas:
        raise SystemExit("FALLÓ: el catálogo no volvió a repartir las consultas entre ambas réplicas.")
    print("\nAPROBADA: el catálogo siguió disponible y recuperó el reparto.")


if __name__ == "__main__":
    main()
