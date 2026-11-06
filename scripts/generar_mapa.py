"""Genera app/static/datos/mapa_colombia.json: los contornos de Colombia listos para dibujar en SVG.

Fuente: Marco Geoestadístico Nacional 2018 del DANE (división política de departamentos y municipios),
simplificado y publicado en GeoJSON en https://github.com/caticoa3/colombia_mapa. Descargue
co_2018_MGN_DPTO_POLITICO.geojson y co_2018_MGN_MPIO_POLITICO.geojson y ejecute:

    python -m scripts.generar_mapa ruta/departamentos.geojson ruta/municipios.geojson

Se guardan los 33 departamentos y solo los municipios que aparecen en los datos de ZNI.
San Andrés y Providencia se dibujan en un recuadro ampliado, como en los mapas oficiales. El contorno
departamental de la fuente no trae Providencia, así que el del archipiélago se arma con sus dos municipios.
"""
import json
import math
import sys

import pandas as pd

from app import config, limpieza

ALTO = 760                      # alto del mapa continental en unidades SVG
LON0, LAT0 = -79.1, 12.6        # esquina superior izquierda del continente
LAT_MEDIA = math.cos(math.radians(4.5))
K = ALTO / (12.6 - (-4.3))      # unidades por grado de latitud
ISLAS = "88"                    # código DANE de San Andrés y Providencia
RECUADRO = (8, 8, 132, 110)     # x, y, ancho, alto del recuadro de las islas
# Cada isla va en su mitad del recuadro, con su propia escala (están a 90 km una de otra)
ISLAS_BBOX = {"San Andrés": (-81.745, 12.52, -81.695, 12.605), "Providencia": (-81.40, 13.33, -81.352, 13.39)}


def proyectar(lon, lat, islas=False):
    if not islas:
        return (lon - LON0) * LAT_MEDIA * K, (LAT0 - lat) * K
    x0, y0, w, h = RECUADRO
    isla = "San Andrés" if lat < 13 else "Providencia"
    lo0, la0, lo1, la1 = ISLAS_BBOX[isla]
    bx, by, bw, bh = (x0 + 6 if isla == "San Andrés" else x0 + w / 2 + 2), y0 + 40, w / 2 - 8, 44  # la fuente trae contornos de pocos puntos: se dibujan pequeños
    esc = min(bw / ((lo1 - lo0) * LAT_MEDIA), bh / (la1 - la0))
    ox = bx + (bw - (lo1 - lo0) * LAT_MEDIA * esc) / 2
    return ox + (lon - lo0) * LAT_MEDIA * esc, by + (la1 - lat) * esc


def _dp(puntos, tol):
    """Douglas-Peucker: quita puntos que se apartan menos de tol de la línea."""
    if len(puntos) < 3:
        return puntos
    (x1, y1), (x2, y2) = puntos[0], puntos[-1]
    dx, dy = x2 - x1, y2 - y1
    largo = math.hypot(dx, dy) or 1e-9
    dmax, imax = 0, 0
    for i in range(1, len(puntos) - 1):
        x, y = puntos[i]
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / largo if largo > 1e-9 else math.hypot(x - x1, y - y1)
        if d > dmax:
            dmax, imax = d, i
    if dmax <= tol:
        return [puntos[0], puntos[-1]]
    return _dp(puntos[:imax + 1], tol)[:-1] + _dp(puntos[imax:], tol)


def _area(p):
    return abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1] for i in range(len(p)))) / 2


def trazo(geom, islas=False, tol=0.35):
    poligonos = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    partes = []
    for poli in poligonos:
        for anillo in poli:
            p = [proyectar(lon, lat, islas) for lon, lat in anillo]
            p = _dp(p, tol / 4 if islas else tol)
            if len(p) < 4 or (_area(p) < 0.6 and not islas):
                continue
            partes.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in p[:-1]) + "Z")
    return "".join(partes)


def main(ruta_dptos, ruta_mpios):
    raw = pd.read_csv(next((config.BASE / "datos" / "crudos").glob("*.csv")), sep=None, engine="python", dtype=str)
    usados = {f"{c:05d}" for c in limpieza.limpiar(raw).ID_MUN.unique()}

    dptos = json.load(open(ruta_dptos, encoding="utf-8"))["features"]
    mpios = json.load(open(ruta_mpios, encoding="utf-8"))["features"]
    salida = {"fuente": "DANE, Marco Geoestadístico Nacional 2018 (simplificado)", "recuadro_islas": RECUADRO,
              "departamentos": [], "municipios": []}
    islas = "".join(trazo(f["geometry"], True) for f in mpios if f["properties"]["DPTO_CCDGO"] == ISLAS)
    for f in dptos:
        cod = f["properties"]["DPTO_CCDGO"]
        salida["departamentos"].append({"codigo": int(cod), "nombre": f["properties"]["DPTO_CNMBR"],
                                        "d": islas if cod == ISLAS else trazo(f["geometry"])})
    for f in mpios:
        cod = f["properties"]["MPIO_CCNCT"]
        if cod in usados:
            salida["municipios"].append({"codigo": int(cod), "nombre": f["properties"]["MPIO_CNMBR"],
                                         "departamento": int(cod[:2]),
                                         "d": trazo(f["geometry"], cod[:2] == ISLAS, tol=0.25)})
    ancho = math.ceil(proyectar(-66.8, -4.3)[0]) + 6
    salida["viewBox"] = f"0 0 {ancho} {ALTO + 6}"
    destino = config.BASE / "app" / "static" / "datos" / "mapa_colombia.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{destino}: {len(salida['departamentos'])} departamentos, {len(salida['municipios'])} municipios, "
          f"{destino.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
