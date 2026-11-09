"""API del sistema de predicción de energía en ZNI (FastAPI).

Documentación interactiva en /docs. La interfaz web (/) consume estas mismas operaciones.
"""
import io
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import eda, limpieza, modelo, reportes, seguridad, territorio
from .config import BASE, DIR_PROCESOS, MAX_MB
from .validacion import INCOMPATIBLE, ArchivoIlegible, leer_archivo, validar

log = logging.getLogger("zni")


@asynccontextmanager
async def al_iniciar(_app):
    print("\n  Sistema ZNI listo. Registro público deshabilitado; administradores por variables de entorno.\n",
          flush=True)
    yield


app = FastAPI(lifespan=al_iniciar,
              title="Sistema ZNI: energía del mes siguiente por localidad",
              description="Análisis exploratorio automático, validación de compatibilidad, predicción, reportes y "
                          "actualización versionada del modelo de energía activa en las Zonas No Interconectadas.",
              version="1.0")

REPORTES = {"eda": "eda.html", "compatibilidad": "compatibilidad.html", "compatibilidad_json": "compatibilidad.json",
            "predicciones_html": "predicciones.html", "predicciones_csv": "predicciones.csv",
            "predicciones_xlsx": "predicciones.xlsx", "actualizacion": "actualizacion.html"}


@app.middleware("http")
async def sin_cache(request: Request, call_next):
    """Evita que el navegador muestre una versión vieja del sitio después de actualizarlo."""
    respuesta = await call_next(request)
    if not request.url.path.startswith("/api/"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@app.exception_handler(Exception)
async def error_general(request: Request, exc: Exception):
    log.exception("Error no controlado")
    return JSONResponse(status_code=500, content={"detalle": "Ocurrió un error interno al procesar la solicitud. "
                                                             "Revise el archivo e intente de nuevo."})


@app.exception_handler(ArchivoIlegible)
async def error_archivo(request: Request, exc: ArchivoIlegible):
    return JSONResponse(status_code=400, content={"detalle": str(exc)})


# ---------------------------------------------------------------- utilidades

async def _leer(archivo: UploadFile):
    contenido = await archivo.read()
    if len(contenido) > MAX_MB * 1024 * 1024:
        raise ArchivoIlegible(f"El archivo supera el límite de {MAX_MB} MB.")
    return leer_archivo(contenido, archivo.filename), archivo.filename


def _nuevo_proceso(tipo, archivo):
    pid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    carpeta = DIR_PROCESOS / pid
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "proceso.json").write_text(json.dumps({"tipo": tipo, "archivo": archivo,
                                                      "fecha": datetime.now().isoformat(timespec="seconds")},
                                                     ensure_ascii=False), encoding="utf-8")
    return pid, carpeta


def _urls(pid, tipos):
    return {t: f"/api/reportes/{pid}/{t}" for t in tipos}


def _activa():
    v = modelo.version_activa()
    if v is None:
        raise HTTPException(503, "No hay un modelo activo. Ejecute scripts/entrenar_inicial.py.")
    return v, modelo.cargar_metadatos(v)


def _sin_graficos(r):
    return {**r, "graficos": [t for t, _ in r["graficos"]]}


def _validar_y_guardar(df, archivo, meta, modo, carpeta):
    diag, tipado = validar(df, meta, modo)
    if not limpieza.faltan_columnas_crudas(df):
        diag["sugerencia"] = ("Este archivo tiene el formato del portal de datos abiertos, no el de la tabla del modelo. "
                              "Use 'Preparar archivo' para construir las variables del mes siguiente y valide el resultado.")
    (carpeta / "compatibilidad.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "compatibilidad.html").write_text(reportes.html_compatibilidad(diag, archivo), encoding="utf-8")
    return diag, tipado


# ---------------------------------------------------------------- operaciones

@app.post("/api/eda", tags=["Análisis"], summary="Analizar dataset (EDA automático)")
async def analizar_dataset(archivo: UploadFile = File(...)):
    """Genera el EDA de cualquier archivo, sea o no compatible con el modelo."""
    df, nombre = await _leer(archivo)
    pid, carpeta = _nuevo_proceso("eda", nombre)
    r = eda.analizar(df, nombre)
    (carpeta / "eda.html").write_text(reportes.html_eda(r), encoding="utf-8")
    return {"proceso": pid, "eda": _sin_graficos(r), "graficos": [{"titulo": t, "png": g} for t, g in r["graficos"]],
            "reportes": _urls(pid, ["eda"])}


@app.post("/api/validar", tags=["Validación"], summary="Validar compatibilidad con el modelo activo")
async def validar_compatibilidad(archivo: UploadFile = File(...), modo: str = Form("prediccion"),
                               admin: dict = Depends(seguridad.requiere_admin)):
    if modo not in ("prediccion", "actualizacion"):
        raise HTTPException(400, "modo debe ser 'prediccion' o 'actualizacion'.")
    _, meta = _activa()
    df, nombre = await _leer(archivo)
    pid, carpeta = _nuevo_proceso("validacion", nombre)
    diag, _ = _validar_y_guardar(df, nombre, meta, modo, carpeta)
    return {"proceso": pid, "diagnostico": diag, "reportes": _urls(pid, ["compatibilidad", "compatibilidad_json"])}


@app.post("/api/predecir", tags=["Predicción"], summary="Generar predicciones (solo con datos compatibles)")
async def generar_predicciones(archivo: UploadFile = File(...), admin: dict = Depends(seguridad.requiere_admin)):
    v, meta = _activa()
    df, nombre = await _leer(archivo)
    pid, carpeta = _nuevo_proceso("prediccion", nombre)
    diag, tipado = _validar_y_guardar(df, nombre, meta, "prediccion", carpeta)
    if diag["estado"] == INCOMPATIBLE:
        return JSONResponse(status_code=422, content={
            "proceso": pid, "detalle": "El archivo es incompatible con el modelo; no se generaron predicciones.",
            "diagnostico": diag, "reportes": _urls(pid, ["compatibilidad", "compatibilidad_json"])})

    pred, lo, hi = modelo.predecir(v, tipado)
    deps = next(x for x in meta["esquema"]["variables"] if x["nombre"] == "departamento")["categorias"]
    salida = pd.DataFrame({
        "fila": np.arange(len(tipado)) + 2,
        "id_localidad": tipado["id_localidad"] if "id_localidad" in tipado else (np.arange(len(tipado)) + 2).astype(str),
        "localidad": tipado["localidad"] if "localidad" in tipado else "",
        "departamento": tipado["departamento"], "tamano": tipado["tamano"],
        "periodo_objetivo": (tipado["anio_objetivo"].astype(str) + "-" if "anio_objetivo" in tipado else "mes ")
        + tipado["mes_objetivo"].astype(int).astype(str).str.zfill(2),
        "prediccion_kwh": np.round(pred, 0), "limite_inferior_80": np.round(lo, 0), "limite_superior_80": np.round(hi, 0),
        "aviso": np.where(tipado["departamento"].isin(deps), "", "departamento no visto en el entrenamiento"),
        "version_modelo": v["version"],
    })
    salida.to_csv(carpeta / "predicciones.csv", index=False, encoding="utf-8-sig")
    salida.to_excel(carpeta / "predicciones.xlsx", index=False)
    resumen = {"registros": int(len(salida)), "total_kwh": float(salida.prediccion_kwh.sum()),
               "mediana_kwh": float(salida.prediccion_kwh.median()), "min_kwh": float(salida.prediccion_kwh.min()),
               "max_kwh": float(salida.prediccion_kwh.max())}
    por_tam = (salida.groupby("tamano").agg(registros=("fila", "size"), total_kwh=("prediccion_kwh", "sum"))
               .reset_index().to_dict("records"))
    res = {"version_modelo": v["version"], "estado_validacion": diag["estado"], "resumen": resumen,
           "por_tamano": por_tam, "filas": salida.fillna("").to_dict("records")}
    (carpeta / "predicciones.html").write_text(reportes.html_predicciones(res, nombre), encoding="utf-8")
    return {"proceso": pid, "diagnostico": diag, **res,
            "reportes": _urls(pid, ["predicciones_csv", "predicciones_xlsx", "predicciones_html", "compatibilidad"])}


@app.get("/api/modelo", tags=["Modelo"], summary="Consultar modelo activo")
def modelo_activo(admin: dict = Depends(seguridad.requiere_admin)):
    _, meta = _activa()
    return meta


@app.get("/api/modelo/versiones", tags=["Modelo"], summary="Listar versiones (activo, candidato, histórico)")
def versiones(admin: dict = Depends(seguridad.requiere_admin)):
    return modelo.leer_registro()


@app.post("/api/modelo/actualizar", tags=["Modelo"], summary="Actualizar datos y reentrenar (genera una candidata)")
async def actualizar(archivo: UploadFile = File(...), admin: dict = Depends(seguridad.requiere_admin)):
    v_act, meta = _activa()
    df, nombre = await _leer(archivo)
    pid, carpeta = _nuevo_proceso("actualizacion", nombre)
    diag, tipado = _validar_y_guardar(df, nombre, meta, "actualizacion", carpeta)
    if diag["estado"] == INCOMPATIBLE:
        return JSONResponse(status_code=422, content={
            "proceso": pid, "detalle": "Los registros nuevos no cumplen el esquema de entrenamiento; no se integraron.",
            "diagnostico": diag, "reportes": _urls(pid, ["compatibilidad"])})

    cols = ["id_localidad", "localidad", "departamento", "anio_objetivo", "mes_objetivo", "tamano"] + \
        modelo.VAR_ENERGIA + modelo.VAR_OTRAS + modelo.VAR_BIN + [modelo.OBJETIVO]
    nuevos = tipado.reindex(columns=cols).copy()
    nuevos["id_localidad"] = nuevos["id_localidad"].astype(str)
    nuevos[["anio_objetivo", "mes_objetivo"]] = nuevos[["anio_objetivo", "mes_objetivo"]].astype(int)
    nuevos = nuevos.drop_duplicates(subset=["id_localidad", "anio_objetivo", "mes_objetivo"], keep="last")
    antes = modelo.cargar_datos(v_act)
    clave = ["id_localidad", "anio_objetivo", "mes_objetivo"]
    existentes = set(map(tuple, antes[clave].astype(str).to_numpy()))
    es_nuevo = ~nuevos[clave].astype(str).apply(tuple, axis=1).isin(existentes)
    integrar = nuevos[es_nuevo]
    if modelo.entrenables(integrar).empty:
        raise HTTPException(400, "El archivo no trae registros nuevos con energía mayor que 0: todos ya estaban en el "
                                 "conjunto de entrenamiento o tienen energía 0. No se generó una versión candidata.")
    despues = pd.concat([antes, integrar], ignore_index=True)

    version, meta_c = modelo.entrenar_version(despues, estado="candidato", nota=f"Actualización con {nombre} (por {admin['usuario']})")
    # Comparación justa adicional: registros nuevos que ninguna versión vio al estimar su error.
    _, prueba, _ = modelo.separar_temporal(modelo.entrenables(despues))
    eval_nuevos = modelo.entrenables(integrar).merge(prueba[clave], on=clave)
    fila_nuevos = None
    if len(eval_nuevos) >= 10:
        modelo_eval, _, _, _ = modelo.validar(modelo.entrenables(despues))
        p_act = np.clip(modelo.cargar_pipeline(v_act).predict(eval_nuevos[modelo.PREDICTORAS]), 0, None)
        p_cand = np.clip(modelo_eval.predict(eval_nuevos[modelo.PREDICTORAS]), 0, None)
        fila_nuevos = (modelo.metricas(eval_nuevos[modelo.OBJETIVO], p_act)["mae_log"],
                       modelo.metricas(eval_nuevos[modelo.OBJETIVO], p_cand)["mae_log"], len(eval_nuevos))

    ma, mc = meta["metricas_validacion"], meta_c["metricas_validacion"]

    def mejor(a, b, menor=True):
        if a is None or b is None or a == b:
            return "igual"
        return "candidata" if (b < a) == menor else "activa"

    tabla = [
        {"metrica": "MAE log en su validación temporal (principal)", "activa": ma["mae_log"], "candidata": mc["mae_log"],
         "mejor": mejor(ma["mae_log"], mc["mae_log"])},
        {"metrica": "WAPE % (secundaria)", "activa": ma["wape_pct"], "candidata": mc["wape_pct"],
         "mejor": mejor(ma["wape_pct"], mc["wape_pct"])},
        {"metrica": "Mediana del error relativo %", "activa": ma["mediana_error_relativo_pct"],
         "candidata": mc["mediana_error_relativo_pct"],
         "mejor": mejor(ma["mediana_error_relativo_pct"], mc["mediana_error_relativo_pct"])},
        {"metrica": "Mejora frente al pronóstico ingenuo %", "activa": ma.get("mejora_vs_ingenuo_pct"),
         "candidata": mc.get("mejora_vs_ingenuo_pct"),
         "mejor": mejor(ma.get("mejora_vs_ingenuo_pct"), mc.get("mejora_vs_ingenuo_pct"), menor=False)},
        {"metrica": "Registros de entrenamiento", "activa": meta["registros"], "candidata": meta_c["registros"], "mejor": "-"},
    ]
    nota = (f"Cada versión se valida con la misma estrategia temporal (últimos {modelo.MESES_PRUEBA} meses objetivo). "
            f"Activa: prueba {meta['estrategia_validacion']['prueba']}. Candidata: prueba "
            f"{meta_c['estrategia_validacion']['prueba']}. Como los periodos de prueba no son idénticos, "
            "se agrega una comparación sobre los registros nuevos, que ninguna de las dos usó para entrenar.")
    if fila_nuevos:
        tabla.append({"metrica": f"MAE log sobre {fila_nuevos[2]} registros nuevos (ninguna los vio)",
                      "activa": fila_nuevos[0], "candidata": fila_nuevos[1], "mejor": mejor(fila_nuevos[0], fila_nuevos[1])})
    gana = tabla[0]["mejor"]
    lectura = (f"En la métrica principal la candidata obtiene {mc['mae_log']} frente a {ma['mae_log']} de la activa "
               f"({'mejor' if gana == 'candidata' else 'peor' if gana == 'activa' else 'igual'}). "
               "La decisión de activarla o descartarla debe registrarse con una justificación; el sistema no la toma solo.")

    t_int = integrar["anio_objetivo"] * 12 + integrar["mes_objetivo"] - 1
    act = {
        "proceso": pid, "version_activa": v_act["version"], "version_candidata": version,
        "nuevos": {"archivo": nombre, "recibidos": int(len(df)), "integrados": int(len(integrar)),
                   "ya_existian": int((~es_nuevo).sum()),
                   "sin_energia": int((integrar[modelo.OBJETIVO] == 0).sum()),
                   "periodo": f"{int(t_int.min()) // 12}-{int(t_int.min()) % 12 + 1:02d} a "
                              f"{int(t_int.max()) // 12}-{int(t_int.max()) % 12 + 1:02d}"},
        "registros_antes": int(len(modelo.entrenables(antes))), "registros_despues": int(meta_c["registros"]),
        "comparacion": {"tabla": tabla, "nota": nota}, "lectura": lectura, "decision": None,
        "eda_nuevos": eda.analizar(integrar.astype(str).replace("nan", ""), nombre)["observaciones"],
        "eda_actualizado": eda.analizar(despues.astype(str).replace("nan", ""), "actualizado")["observaciones"],
    }
    (carpeta / "actualizacion.json").write_text(json.dumps(act, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (carpeta / "actualizacion.html").write_text(reportes.html_actualizacion(act), encoding="utf-8")
    return {**act, "diagnostico": diag, "reportes": _urls(pid, ["actualizacion", "compatibilidad"])}


@app.post("/api/modelo/versiones/{version}/decision", tags=["Modelo"],
          summary="Registrar la decisión sobre una versión candidata")
def decidir(version: str, accion: str = Form(...), justificacion: str = Form(...), proceso: str = Form(""),
            admin: dict = Depends(seguridad.requiere_admin)):
    if accion not in ("activar", "descartar"):
        raise HTTPException(400, "accion debe ser 'activar' o 'descartar'.")
    if len(justificacion.strip()) < 10:
        raise HTTPException(400, "Escriba una justificación de al menos 10 caracteres.")
    try:
        v = modelo.decidir(version, accion, justificacion.strip(), admin["usuario"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    carpeta = DIR_PROCESOS / proceso
    if proceso and (carpeta / "actualizacion.json").exists():  # deja la decisión escrita en el reporte
        act = json.loads((carpeta / "actualizacion.json").read_text(encoding="utf-8"))
        act["decision"] = (f"{v['decision']['fecha']}: {accion} {version} (por {admin['usuario']}). "
                           f"Justificación: {justificacion.strip()}")
        (carpeta / "actualizacion.json").write_text(json.dumps(act, ensure_ascii=False, indent=2), encoding="utf-8")
        (carpeta / "actualizacion.html").write_text(reportes.html_actualizacion(act), encoding="utf-8")
    return {"version": v, "registro": modelo.leer_registro()}


@app.post("/api/preparar", tags=["Utilidades"],
          summary="Convertir el CSV del portal de datos abiertos en la tabla de entrada del modelo")
async def preparar(archivo: UploadFile = File(...), tipo: str = Form("prediccion"),
                   admin: dict = Depends(seguridad.requiere_admin)):
    """tipo='prediccion': filas del mes siguiente al último del archivo. tipo='etiquetados': pares con objetivo real."""
    df, nombre = await _leer(archivo)
    faltan = limpieza.faltan_columnas_crudas(df)
    if faltan:
        raise HTTPException(400, f"El archivo no tiene el formato del portal de datos abiertos; faltan: {', '.join(faltan)}.")
    limpio = limpieza.limpiar(df)
    tabla = limpieza.construir_variables(limpio, con_objetivo=(tipo == "etiquetados"), siguiente_mes=(tipo != "etiquetados"))
    buf = io.StringIO()
    tabla.to_csv(buf, index=False)
    sufijo = "etiquetados" if tipo == "etiquetados" else "para_prediccion"
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="zni_{sufijo}.csv"'})


@app.get("/api/reportes/{proceso}/{tipo}", tags=["Reportes"], summary="Descargar un reporte generado")
def descargar_reporte(proceso: str, tipo: str, request: Request):
    if tipo not in REPORTES or not proceso.replace("-", "").isalnum():
        raise HTTPException(404, "Reporte no encontrado.")
    carpeta = DIR_PROCESOS / proceso
    meta_proceso = carpeta / "proceso.json"
    if meta_proceso.exists():
        info = json.loads(meta_proceso.read_text(encoding="utf-8"))
        if info.get("tipo") != "eda" and not seguridad.usuario_actual(request):
            raise HTTPException(401, "Esta operación requiere una cuenta de administrador.")
    ruta = carpeta / REPORTES[tipo]
    if not ruta.exists():
        raise HTTPException(404, "Ese reporte no existe para este proceso.")
    return FileResponse(ruta, filename=f"{tipo}_{proceso}{ruta.suffix}")


# ---------------------------------------------------------------- acceso de administradores

def _cliente(request: Request):
    return (request.client.host if request.client else "desconocida"), request.headers.get("user-agent", "")


def _cookie(respuesta: Response, request: Request, token: str):
    respuesta.set_cookie(seguridad.COOKIE, token, max_age=seguridad.DURACION_SESION, httponly=True, samesite="lax",
                         secure=request.url.scheme == "https", path="/")


@app.post("/api/auth/registro", tags=["Acceso"], summary="Crear una cuenta de administrador (requiere código)")
def registro(request: Request, respuesta: Response, usuario: str = Form(...), nombre: str = Form(""),
             contrasena: str = Form(...), codigo: str = Form(...)):
    u = seguridad.registrar(usuario, nombre, contrasena, codigo, *_cliente(request))
    _cookie(respuesta, request, seguridad.crear_token(u["usuario"]))
    return {"usuario": u}


@app.post("/api/auth/ingresar", tags=["Acceso"], summary="Iniciar sesión")
def ingresar(request: Request, respuesta: Response, usuario: str = Form(...), contrasena: str = Form(...)):
    u = seguridad.autenticar(usuario, contrasena, *_cliente(request))
    _cookie(respuesta, request, seguridad.crear_token(u["usuario"]))
    return {"usuario": u}


@app.post("/api/auth/salir", tags=["Acceso"], summary="Cerrar sesión")
def salir(request: Request, respuesta: Response):
    u = seguridad.usuario_actual(request)
    if u:
        seguridad.anotar(u["usuario"], "salida", *_cliente(request))
    respuesta.delete_cookie(seguridad.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/yo", tags=["Acceso"], summary="Usuario de la sesión actual")
def yo(request: Request):
    return {"usuario": seguridad.usuario_actual(request), "hay_administradores": seguridad.hay_administradores()}


# ---------- administración de cuentas (CRUD) e historial de inicios de sesión: solo administradores
@app.get("/api/admin/usuarios", tags=["Administración"], summary="Listar las cuentas de administrador")
def admin_listar(admin: dict = Depends(seguridad.requiere_admin)):
    return {"usuarios": seguridad.listar_usuarios(), "yo": admin["usuario"]}


@app.post("/api/admin/usuarios", tags=["Administración"], summary="Crear una cuenta de administrador")
def admin_crear(usuario: str = Form(...), nombre: str = Form(""), contrasena: str = Form(...),
                admin: dict = Depends(seguridad.requiere_admin)):
    return {"usuario": seguridad.crear_usuario(usuario, nombre, contrasena, creado_por=admin["usuario"])}


@app.put("/api/admin/usuarios/{usuario}", tags=["Administración"],
         summary="Editar una cuenta (nombre, contraseña o si está activa)")
def admin_editar(request: Request, respuesta: Response, usuario: str, nombre: str | None = Form(None),
                 contrasena: str | None = Form(None), activo: bool | None = Form(None),
                 admin: dict = Depends(seguridad.requiere_admin)):
    u = seguridad.actualizar_usuario(usuario, admin["usuario"], nombre, contrasena, activo)
    if contrasena and u["usuario"] == admin["usuario"]:  # quien cambia su propia contraseña sigue con sesión
        _cookie(respuesta, request, seguridad.crear_token(u["usuario"]))
    return {"usuario": u}


@app.delete("/api/admin/usuarios/{usuario}", tags=["Administración"], summary="Eliminar una cuenta")
def admin_eliminar(usuario: str, admin: dict = Depends(seguridad.requiere_admin)):
    seguridad.eliminar_usuario(usuario, admin["usuario"])
    return {"ok": True}


@app.get("/api/admin/sesiones", tags=["Administración"], summary="Historial de registros e inicios de sesión")
def admin_sesiones(usuario: str = "", evento: str = Query("", pattern="^(|registro|ingreso|fallo|bloqueo|salida)$"),
                   limite: int = Query(100, ge=1, le=500), admin: dict = Depends(seguridad.requiere_admin)):
    return seguridad.historial(usuario, evento, limite)


DIR_ESCENARIOS = BASE / "pruebas" / "escenarios"
ESCENARIOS = {
    "01_compatible.csv": ("1", "predecir", "Archivo completamente compatible", "Compatible: genera predicciones"),
    "02_falta_variable.csv": ("2", "predecir", "Falta una variable obligatoria", "Incompatible: falta energia_lag1_kwh"),
    "03_tipo_incompatible.csv": ("3", "predecir", "Tipos de dato incompatibles",
                                 "Incompatible: texto en mes_objetivo y formato español en energia_lag1_kwh"),
    "04_faltantes.csv": ("4", "predecir", "Faltantes en una variable necesaria", "Incompatible: 5 faltantes en energia_lag1_kwh"),
    "05a_categoria_nueva_departamento.csv": ("5", "predecir", "Departamento no visto en el entrenamiento",
                                             "Compatible con advertencias: predice y marca las filas"),
    "05b_categoria_fuera_de_escala.csv": ("5", "predecir", "Tamaño fuera de la escala definida", "Incompatible: categoría inválida"),
    "06_columnas_adicionales.csv": ("6", "predecir", "Columnas adicionales", "Compatible con advertencias: se ignoran"),
    "07_solo_eda_portal_crudo.csv": ("7", "eda", "CSV crudo del portal (2025)",
                                     "No sirve para predecir, pero sí para el análisis exploratorio"),
    "07b_reglas_de_dominio.csv": ("7", "predecir", "Reglas de dominio incumplidas",
                                  "Incompatible: horas > 24, factor de carga > 1, bandera incoherente"),
    "08_nuevos_etiquetados.csv": ("8", "actualizar", "Nuevos datos con la energía real (2025-07 a 2026-01)",
                                  "Crea una versión candidata sin reemplazar la activa"),
    "09_pronostico_2026_02.csv": ("extra", "predecir", "Pronóstico real de febrero de 2026",
                                  "Compatible con advertencias: faltan horas por el cambio de formato de la fuente"),
}


@app.get("/api/procesos", tags=["Reportes"], summary="Historial de cargas y reportes generados")
def procesos(limite: int = 50, admin: dict = Depends(seguridad.requiere_admin)):
    salida = []
    if DIR_PROCESOS.exists():
        for carpeta in sorted(DIR_PROCESOS.iterdir(), reverse=True)[:limite]:
            info_p = carpeta / "proceso.json"
            if not info_p.exists():
                continue
            info = json.loads(info_p.read_text(encoding="utf-8"))
            estado = None
            if (carpeta / "compatibilidad.json").exists():
                estado = json.loads((carpeta / "compatibilidad.json").read_text(encoding="utf-8"))["estado"]
            disponibles = [t for t, f in REPORTES.items() if (carpeta / f).exists()]
            salida.append({"proceso": carpeta.name, **info, "estado": estado, "reportes": _urls(carpeta.name, disponibles)})
    return {"procesos": salida}


@app.get("/api/escenarios", tags=["Utilidades"], summary="Archivos de prueba incluidos")
def escenarios(admin: dict = Depends(seguridad.requiere_admin)):
    return {"escenarios": [{"archivo": n, "escenario": e, "uso": u, "descripcion": d, "esperado": r,
                            "url": f"/api/escenarios/{n}"}
                           for n, (e, u, d, r) in ESCENARIOS.items() if (DIR_ESCENARIOS / n).exists()]}


@app.get("/api/escenarios/{nombre}", tags=["Utilidades"], summary="Descargar un archivo de prueba")
def descargar_escenario(nombre: str, admin: dict = Depends(seguridad.requiere_admin)):
    if nombre not in ESCENARIOS or not (DIR_ESCENARIOS / nombre).exists():
        raise HTTPException(404, "Archivo de prueba no encontrado.")
    return FileResponse(DIR_ESCENARIOS / nombre, filename=nombre, media_type="text/csv")


# ---------- Mapa y búsqueda por territorio (consulta pública) ----------
def _filtros(q: str = "", departamento: int | None = None, municipio: int | None = None,
             localidad: str = "", anio: int | None = None, mes: int | None = Query(None, ge=1, le=12)):
    return dict(q=q, departamento=departamento, municipio=municipio, localidad=localidad, anio=anio, mes=mes)


@app.get("/api/territorio/opciones", tags=["Territorio"], summary="Departamentos, municipios y localidades con datos")
def territorio_opciones():
    try:
        return territorio.opciones()
    except FileNotFoundError:
        raise HTTPException(503, "Falta el archivo del portal de datos abiertos en la carpeta datos/crudos (un CSV).")
    except Exception as e:
        log.exception("No se pudieron leer los datos del portal")
        raise HTTPException(500, f"No se pudo leer el archivo de datos/crudos: {type(e).__name__}: {e}")


@app.get("/api/territorio/resumen", tags=["Territorio"], summary="Indicadores por departamento o municipio (mapa)")
def territorio_resumen(nivel: str = Query("departamento", pattern="^(departamento|municipio)$"),
                       anio: int | None = None):
    return territorio.resumen(nivel, anio)


@app.get("/api/territorio/detalle", tags=["Territorio"], summary="Información de un departamento o municipio")
def territorio_detalle(codigo: int, nivel: str = Query("departamento", pattern="^(departamento|municipio)$"),
                       anio: int | None = None):
    r = territorio.detalle(nivel, codigo, anio)
    if r is None:
        raise HTTPException(404, "Ese lugar no tiene registros de prestación del servicio en ZNI.")
    return r


@app.get("/api/territorio/registros", tags=["Territorio"], summary="Buscar registros por lugar")
def territorio_registros(filtros: dict = Depends(_filtros), pagina: int = 1,
                         por_pagina: int = Query(50, ge=1, le=200),
                         orden: str = Query("reciente", pattern="^(reciente|energia|lugar)$")):
    return territorio.buscar(pagina=pagina, por_pagina=por_pagina, orden=orden, **filtros)


@app.get("/api/territorio/registros.csv", tags=["Territorio"], summary="Descargar en CSV los registros encontrados")
def territorio_csv(filtros: dict = Depends(_filtros)):
    buf = io.StringIO()
    territorio.tabla(territorio.filtrar(**filtros)).to_csv(buf, index=False)
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="registros_zni.csv"'})


app.mount("/", StaticFiles(directory=BASE / "app" / "static", html=True), name="interfaz")
