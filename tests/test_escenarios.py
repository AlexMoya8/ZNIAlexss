"""Pruebas obligatorias de la actividad: un caso por escenario. Ejecutar con: pytest -q"""
import os
import shutil
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
ESC = BASE / "pruebas" / "escenarios"


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("zni")
    shutil.copytree(BASE / "modelos", tmp / "modelos")  # no se tocan los modelos reales
    os.environ["ZNI_DIR_MODELOS"] = str(tmp / "modelos")
    os.environ["ZNI_DIR_PROCESOS"] = str(tmp / "procesos")
<<<<<<< HEAD
    os.environ["ZNI_DIR_SEGURIDAD"] = str(tmp / "seguridad")
    os.environ["ZNI_CODIGO_REGISTRO"] = "CODIGO-PRUEBA"
=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


<<<<<<< HEAD

@pytest.fixture(scope="module")
def admin_cliente(cliente):
    r = cliente.post("/api/auth/registro", data={"usuario": "admin", "nombre": "Admin",
                                               "contrasena": "clave1234", "codigo": "CODIGO-PRUEBA"})
    assert r.status_code == 200
    return cliente


=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
def enviar(cliente, ruta, archivo, **datos):
    with open(ESC / archivo, "rb") as f:
        return cliente.post(ruta, files={"archivo": (archivo, f, "text/csv")}, data=datos)


def niveles(r):
    return {(h["severidad"], h["nivel"], h["variable"]) for h in r.json()["diagnostico"]["hallazgos"]}


<<<<<<< HEAD
def test_1_compatible_genera_predicciones(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "01_compatible.csv")
=======
def test_1_compatible_genera_predicciones(cliente):
    r = enviar(cliente, "/api/predecir", "01_compatible.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 200
    j = r.json()
    assert j["diagnostico"]["estado"] == "Compatible"
    assert j["resumen"]["registros"] == len(j["filas"]) > 0
    assert all(f["limite_inferior_80"] <= f["prediccion_kwh"] <= f["limite_superior_80"] for f in j["filas"])
<<<<<<< HEAD
    assert admin_cliente.get(j["reportes"]["predicciones_csv"]).status_code == 200


def test_2_falta_variable_bloquea(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "02_falta_variable.csv")
=======
    assert cliente.get(j["reportes"]["predicciones_csv"]).status_code == 200


def test_2_falta_variable_bloquea(cliente):
    r = enviar(cliente, "/api/predecir", "02_falta_variable.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 422
    assert ("error", "esquema", "energia_lag1_kwh") in niveles(r)
    assert "filas" not in r.json()


<<<<<<< HEAD
def test_3_tipo_incompatible(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "03_tipo_incompatible.csv")
=======
def test_3_tipo_incompatible(cliente):
    r = enviar(cliente, "/api/predecir", "03_tipo_incompatible.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 422
    assert {("error", "tipo", "mes_objetivo"), ("error", "tipo", "energia_lag1_kwh")} <= niveles(r)


<<<<<<< HEAD
def test_4_faltantes_en_variable_necesaria(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "04_faltantes.csv")
=======
def test_4_faltantes_en_variable_necesaria(cliente):
    r = enviar(cliente, "/api/predecir", "04_faltantes.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 422
    h = [h for h in r.json()["diagnostico"]["hallazgos"] if h["nivel"] == "contenido"][0]
    assert h["variable"] == "energia_lag1_kwh" and h["registros_afectados"] == 5


<<<<<<< HEAD
def test_5_categoria_nueva(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "05a_categoria_nueva_departamento.csv")
    assert r.status_code == 200 and r.json()["diagnostico"]["estado"] == "Compatible con advertencias"
    assert sum(1 for f in r.json()["filas"] if f["aviso"]) == 3
    r = enviar(admin_cliente, "/api/predecir", "05b_categoria_fuera_de_escala.csv")
    assert r.status_code == 422 and ("error", "contenido", "tamano") in niveles(r)


def test_6_columnas_adicionales(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "06_columnas_adicionales.csv")
=======
def test_5_categoria_nueva(cliente):
    r = enviar(cliente, "/api/predecir", "05a_categoria_nueva_departamento.csv")
    assert r.status_code == 200 and r.json()["diagnostico"]["estado"] == "Compatible con advertencias"
    assert sum(1 for f in r.json()["filas"] if f["aviso"]) == 3
    r = enviar(cliente, "/api/predecir", "05b_categoria_fuera_de_escala.csv")
    assert r.status_code == 422 and ("error", "contenido", "tamano") in niveles(r)


def test_6_columnas_adicionales(cliente):
    r = enviar(cliente, "/api/predecir", "06_columnas_adicionales.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 200
    assert r.json()["diagnostico"]["columnas_adicionales"] == ["operador", "observaciones"]


<<<<<<< HEAD
def test_7_no_predice_pero_si_eda(admin_cliente):
    r = enviar(admin_cliente, "/api/predecir", "07_solo_eda_portal_crudo.csv")
    assert r.status_code == 422 and "sugerencia" in r.json()["diagnostico"]
    r = enviar(admin_cliente, "/api/eda", "07_solo_eda_portal_crudo.csv")
=======
def test_7_no_predice_pero_si_eda(cliente):
    r = enviar(cliente, "/api/predecir", "07_solo_eda_portal_crudo.csv")
    assert r.status_code == 422 and "sugerencia" in r.json()["diagnostico"]
    r = enviar(cliente, "/api/eda", "07_solo_eda_portal_crudo.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert r.status_code == 200
    tipos = {v["variable"]: v["tipo"] for v in r.json()["eda"]["variables"]}
    assert tipos["ENERGÍA ACTIVA"] == "numérica" and tipos["FECHA DE DEMANDA MÁXIMA"] == "temporal"
    assert len(r.json()["graficos"]) >= 5
<<<<<<< HEAD
    r = enviar(admin_cliente, "/api/predecir", "07b_reglas_de_dominio.csv")
=======
    r = enviar(cliente, "/api/predecir", "07b_reglas_de_dominio.csv")
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert {h["variable"] for h in r.json()["diagnostico"]["hallazgos"] if h["nivel"] == "dominio"} == {
        "horas_dia_lag1", "factor_carga_lag1", "sin_servicio_lag1 / energia_lag1_kwh"}


def test_8_actualizacion_genera_candidata_sin_reemplazar(cliente):
<<<<<<< HEAD
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    r = enviar(anon, "/api/modelo/actualizar", "08_nuevos_etiquetados.csv")
    assert r.status_code == 401  # sin sesión nadie puede reentrenar
    r = anon.post("/api/auth/ingresar", data={"usuario": "admin", "contrasena": "clave1234"})
    assert r.status_code == 200
    r = enviar(anon, "/api/modelo/actualizar", "08_nuevos_etiquetados.csv")
    assert r.status_code == 200
    j = r.json()
    estados = {v["version"]: v["estado"] for v in anon.get("/api/modelo/versiones").json()["versiones"]}
    assert estados["v1"] == "activo" and estados[j["version_candidata"]] == "candidato"
    assert anon.get("/api/modelo").json()["version"] == "v1"  # no se sustituye sola
    r = anon.post(f"/api/modelo/versiones/{j['version_candidata']}/decision",
                     data={"accion": "activar", "justificacion": "prueba automática del flujo", "proceso": j["proceso"]})
    assert r.status_code == 200
    assert anon.get("/api/modelo").json()["version"] == j["version_candidata"]
    estados = {v["version"]: v["estado"] for v in anon.get("/api/modelo/versiones").json()["versiones"]}
=======
    r = enviar(cliente, "/api/modelo/actualizar", "08_nuevos_etiquetados.csv")
    assert r.status_code == 200
    j = r.json()
    estados = {v["version"]: v["estado"] for v in cliente.get("/api/modelo/versiones").json()["versiones"]}
    assert estados["v1"] == "activo" and estados[j["version_candidata"]] == "candidato"
    assert cliente.get("/api/modelo").json()["version"] == "v1"  # no se sustituye sola
    r = cliente.post(f"/api/modelo/versiones/{j['version_candidata']}/decision",
                     data={"accion": "activar", "justificacion": "prueba automática del flujo", "proceso": j["proceso"]})
    assert r.status_code == 200
    assert cliente.get("/api/modelo").json()["version"] == j["version_candidata"]
    estados = {v["version"]: v["estado"] for v in cliente.get("/api/modelo/versiones").json()["versiones"]}
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
    assert estados["v1"] == "historico"


def test_archivo_ilegible_sin_traza(cliente):
    r = cliente.post("/api/eda", files={"archivo": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400 and "Traceback" not in r.text
<<<<<<< HEAD


def test_sitio_y_recursos(admin_cliente):
    for pagina in ("/", "/sistema.html", "/ingresar.html", "/js/inicio.js", "/js/ingresar.js", "/js/mapa.js",
                   "/css/mapa.css", "/datos/mapa_colombia.json"):
        assert admin_cliente.get(pagina).status_code == 200
    assert admin_cliente.get("/js/app.js").status_code == 200
    esc = admin_cliente.get("/api/escenarios").json()["escenarios"]
    assert len(esc) >= 10 and admin_cliente.get(esc[0]["url"]).status_code == 200
    assert admin_cliente.get("/api/escenarios/../config/esquema.json").status_code == 404
    procesos = admin_cliente.get("/api/procesos").json()["procesos"]
    assert procesos and all("reportes" in p for p in procesos)


def test_acceso_de_administradores(cliente):
    datos = {"usuario": "otro", "nombre": "Otro", "contrasena": "clave1234"}
    assert cliente.post("/api/auth/registro", data={**datos, "codigo": "MAL"}).status_code == 403
    assert cliente.post("/api/auth/registro", data={**datos, "contrasena": "corta", "codigo": "CODIGO-PRUEBA"}).status_code == 400
    assert cliente.post("/api/auth/registro", data={**datos, "codigo": "CODIGO-PRUEBA"}).status_code == 200
    assert cliente.post("/api/auth/registro", data={**datos, "codigo": "CODIGO-PRUEBA"}).status_code == 409
    assert cliente.get("/api/auth/yo").json()["usuario"]["usuario"] == "otro"
    cliente.post("/api/auth/salir")
    assert cliente.get("/api/auth/yo").json()["usuario"] is None
    r = cliente.post("/api/modelo/versiones/v9/decision", data={"accion": "activar", "justificacion": "intento sin sesión"})
    assert r.status_code == 401
    cliente.cookies.set("zni_sesion", "token-falso")
    assert cliente.get("/api/auth/yo").json()["usuario"] is None
    cliente.cookies.clear()
    assert cliente.post("/api/auth/ingresar", data={"usuario": "otro", "contrasena": "clave1234"}).status_code == 200
    cliente.post("/api/auth/salir")
    for _ in range(5):
        assert cliente.post("/api/auth/ingresar", data={"usuario": "otro", "contrasena": "mala-clave1"}).status_code == 401
    assert cliente.post("/api/auth/ingresar", data={"usuario": "otro", "contrasena": "clave1234"}).status_code == 429
    base = (Path(os.environ["ZNI_DIR_SEGURIDAD"]) / "zni.db").read_bytes()
    assert b"clave1234" not in base and b"otro" in base  # nunca se guarda la contraseña en claro


def test_mapa_y_busqueda_por_territorio(cliente):
    """Consulta pública: resumen para el mapa, detalle de un lugar y búsqueda de registros."""
    op = cliente.get("/api/territorio/opciones").json()
    assert len(op["departamentos"]) == 18 and op["anios"][0] == 2020

    dep = cliente.get("/api/territorio/resumen").json()
    assert dep["total"]["localidades"] > 100 and len(dep["lugares"]) == 18
    assert any(l["registros"] == 0 and l["energia_mwh"] is None for l in dep["lugares"])  # sin datos en el periodo
    mun = cliente.get("/api/territorio/resumen?nivel=municipio&anio=2023").json()
    mapa = cliente.get("/datos/mapa_colombia.json").json()
    codigos_mapa = {m["codigo"] for m in mapa["municipios"]}
    assert all(l["codigo"] in codigos_mapa for l in mun["lugares"])  # todo municipio con datos se puede tocar en el mapa
    assert cliente.get("/api/territorio/resumen?nivel=vereda").status_code == 422

    choco = cliente.get("/api/territorio/detalle?nivel=departamento&codigo=27").json()
    assert choco["nombre"] == "CHOCÓ" and choco["serie"] and choco["localidades"]
    assert cliente.get("/api/territorio/detalle?codigo=11").status_code == 404  # Bogotá no es ZNI

    # el texto se busca sin importar tildes ni mayúsculas, en departamento, municipio y localidad
    r = cliente.get("/api/territorio/registros?q=bahia solano&por_pagina=10").json()
    assert r["total"] > 0 and len(r["registros"]) == 10
    assert all(x["municipio"].startswith("BAHÍA SOLANO") for x in r["registros"])
    todos = cliente.get("/api/territorio/registros?departamento=91").json()
    assert todos["resumen"]["departamentos"] == 1
    assert {x["departamento"] for x in todos["registros"]} == {"AMAZONAS"}
    nada = cliente.get("/api/territorio/registros?q=zzzz").json()
    assert nada["total"] == 0 and nada["registros"] == []

    csv = cliente.get("/api/territorio/registros.csv?municipio=91001")
    assert csv.status_code == 200 and csv.text.lstrip("﻿").startswith("departamento,municipio,localidad")


def test_crud_de_administradores_e_historial(cliente):
    """Crear, listar, editar y eliminar cuentas; historial de registros e inicios de sesión."""
    from app import seguridad
    seguridad._fallos.clear()  # la prueba anterior dejó bloqueada la dirección de prueba
    cliente.cookies.clear()
    assert cliente.get("/api/admin/usuarios").status_code == 401  # sin sesión no se ve nada
    assert cliente.post("/api/auth/ingresar", data={"usuario": "admin", "contrasena": "clave1234"}).status_code == 200

    lista = cliente.get("/api/admin/usuarios").json()
    assert lista["yo"] == "admin" and {"admin", "otro"} <= {u["usuario"] for u in lista["usuarios"]}
    assert all("hash" not in u and "sal" not in u for u in lista["usuarios"])

    r = cliente.post("/api/admin/usuarios", data={"usuario": "Stiwar", "nombre": "Carlos Stiwar", "contrasena": "docente2026"})
    assert r.status_code == 200 and r.json()["usuario"]["creado_por"] == "admin"
    assert cliente.post("/api/admin/usuarios", data={"usuario": "stiwar", "contrasena": "docente2026"}).status_code == 409

    assert cliente.put("/api/admin/usuarios/stiwar", data={"nombre": "Prof. Stiwar"}).json()["usuario"]["nombre"] == "Prof. Stiwar"
    assert cliente.put("/api/admin/usuarios/stiwar", data={"contrasena": "123"}).status_code == 400
    assert cliente.put("/api/admin/usuarios/admin", data={"activo": "false"}).status_code == 400  # no a sí mismo
    assert cliente.delete("/api/admin/usuarios/admin").status_code == 400
    assert cliente.put("/api/admin/usuarios/nadie", data={"nombre": "x"}).status_code == 404

    # una cuenta desactivada no puede ingresar; al reactivarla sí
    assert cliente.put("/api/admin/usuarios/stiwar", data={"activo": "false"}).json()["usuario"]["activo"] is False
    sesion = cliente.cookies.get("zni_sesion")
    cliente.cookies.clear()
    assert cliente.post("/api/auth/ingresar", data={"usuario": "stiwar", "contrasena": "docente2026"}).status_code == 401
    cliente.cookies.set("zni_sesion", sesion)
    cliente.put("/api/admin/usuarios/stiwar", data={"activo": "true"})

    # cambiar la contraseña invalida las sesiones abiertas de esa cuenta
    cliente.cookies.clear()
    assert cliente.post("/api/auth/ingresar", data={"usuario": "stiwar", "contrasena": "docente2026"}).status_code == 200
    sesion_stiwar = cliente.cookies.get("zni_sesion")
    cliente.cookies.set("zni_sesion", sesion)
    cliente.put("/api/admin/usuarios/stiwar", data={"contrasena": "nueva2026x"})
    cliente.cookies.set("zni_sesion", sesion_stiwar)
    assert cliente.get("/api/auth/yo").json()["usuario"] is None
    cliente.cookies.set("zni_sesion", sesion)

    h = cliente.get("/api/admin/sesiones?usuario=stiwar").json()
    eventos = [e["evento"] for e in h["eventos"]]
    assert "ingreso" in eventos and "fallo" in eventos
    assert cliente.get("/api/admin/sesiones?evento=registro").json()["total"] >= 2
    assert cliente.get("/api/admin/sesiones?evento=otro").status_code == 422

    assert cliente.delete("/api/admin/usuarios/stiwar").status_code == 200
    assert "stiwar" not in {u["usuario"] for u in cliente.get("/api/admin/usuarios").json()["usuarios"]}
=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
