"""Consulta territorial de los registros de ZNI: resumen por departamento o municipio para el mapa de
calor, detalle de cada lugar y búsqueda de registros por departamento, municipio o localidad (comunidad).

Lee el archivo del portal de datos abiertos que está en datos/crudos y lo limpia con las mismas reglas
del modelo (limpieza.limpiar). El resultado se guarda en memoria hasta que el archivo cambie.
"""
import numpy as np
import pandas as pd

from . import config, limpieza

DIR_CRUDOS = config.BASE / "datos" / "crudos"
_cache = {"firma": None, "df": None}

NIVELES = {"departamento": ("ID_DEP", "DEPARTAMENTO_LIMPIO"), "municipio": ("ID_MUN", "MUNICIPIO_LIMPIO")}


def _archivo():
    archivos = sorted(DIR_CRUDOS.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not archivos:
        raise FileNotFoundError("No hay archivo del portal en datos/crudos.")
    return archivos[-1]


def datos():
    ruta = _archivo()
    firma = (str(ruta), ruta.stat().st_mtime)
    if _cache["firma"] != firma:
        raw = pd.read_csv(ruta, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
        d = limpieza.limpiar(raw)
        d["PERIODO"] = d.ANIO * 100 + d.MES
        d["T"] = d.ANIO * 12 + d.MES - 1
        d["_texto"] = (d.LOCALIDAD_LIMPIA + " " + d.MUNICIPIO_LIMPIO + " " + d.DEPARTAMENTO_LIMPIO).map(
            limpieza.limpiar_nombre)
        d = d.sort_values(["DEPARTAMENTO_LIMPIO", "MUNICIPIO_LIMPIO", "LOCALIDAD_LIMPIA", "PERIODO"])
        _cache.update(firma=firma, df=d.reset_index(drop=True))
    return _cache["df"]


def _num(v, d=1):
    return None if v is None or pd.isna(v) else round(float(v), d)


def _periodo(d, anio):
    """Filtra un año, o los últimos 12 meses con datos si no se indica año."""
    if anio:
        return d[d.ANIO == int(anio)], f"Año {int(anio)}"
    ult = d["T"].max()
    p = d[d["T"] > ult - 12]
    ini, fin = p.PERIODO.min(), p.PERIODO.max()
    return p, f"Últimos 12 meses ({ini % 100:02d}/{ini // 100} a {fin % 100:02d}/{fin // 100})"


def _indicadores(g):
    por_loc = g.groupby("LOC_KEY").HORAS_DIA.mean()
    con_horas = por_loc.dropna()
    return {
        "registros": int(len(g)),
        "localidades": int(g.LOC_KEY.nunique()),
        "municipios": int(g.ID_MUN.nunique()),
        "energia_mwh": _num(g.EA_KWH.sum() / 1000),
        "horas_promedio": _num(g.HORAS_DIA.mean()),
        "pct_menos_12h": _num((con_horas < 12).mean() * 100) if len(con_horas) else None,
        "meses_sin_energia": int((g.EA_KWH == 0).sum()),
    }


def opciones():
    d = datos()
    deps = []
    for (cod, nom), g in d.groupby(["ID_DEP", "DEPARTAMENTO_LIMPIO"]):
        mpios = [{"codigo": int(c), "nombre": n, "localidades": sorted(gm.LOCALIDAD_LIMPIA.unique().tolist())}
                 for (c, n), gm in g.groupby(["ID_MUN", "MUNICIPIO_LIMPIO"])]
        deps.append({"codigo": int(cod), "nombre": nom, "municipios": mpios})
    return {"departamentos": deps, "anios": sorted(int(a) for a in d.ANIO.unique()),
            "primer_periodo": int(d.PERIODO.min()), "ultimo_periodo": int(d.PERIODO.max()),
            "archivo": _archivo().name}


def resumen(nivel="departamento", anio=None):
    cod_col, nom_col = NIVELES[nivel]
    d = datos()
    p, etiqueta = _periodo(d, anio)
    grupos = dict(list(p.groupby(cod_col)))
    vacio = {"registros": 0, "localidades": 0, "municipios": 0, "energia_mwh": None, "horas_promedio": None,
             "pct_menos_12h": None, "meses_sin_energia": 0}
    # también los lugares que tienen registros en otros periodos, para mostrarlos como «sin dato»
    filas = [{"codigo": int(c), "nombre": n, **(_indicadores(grupos[c]) if c in grupos else vacio)}
             for (c, n), _ in d.groupby([cod_col, nom_col])]
    return {"nivel": nivel, "periodo": etiqueta, "lugares": filas, "total": _indicadores(p)}


def detalle(nivel, codigo, anio=None):
    cod_col, nom_col = NIVELES[nivel]
    d = datos()
    todo = d[d[cod_col] == int(codigo)]
    if todo.empty:
        return None
    p, etiqueta = _periodo(d, anio)
    g = p[p[cod_col] == int(codigo)]
    mensual = (todo.groupby("PERIODO").agg(energia=("EA_KWH", "sum"), horas=("HORAS_DIA", "mean")).reset_index())
    locs = (g.groupby(["LOC_KEY", "LOCALIDAD_LIMPIA", "MUNICIPIO_LIMPIO"])
            .agg(energia=("EA_KWH", "sum"), horas=("HORAS_DIA", "mean"), meses=("EA_KWH", "size"))
            .reset_index().sort_values("energia", ascending=False))
    return {
        "nivel": nivel, "codigo": int(codigo), "nombre": todo[nom_col].iloc[0],
        "departamento": todo.DEPARTAMENTO_LIMPIO.iloc[0], "periodo": etiqueta,
        "indicadores": _indicadores(g) if len(g) else None,
        "historico": {"desde": int(todo.PERIODO.min()), "hasta": int(todo.PERIODO.max()), **_indicadores(todo)},
        "serie": [{"periodo": int(r.PERIODO), "energia_mwh": _num(r.energia / 1000, 2), "horas": _num(r.horas)}
                  for r in mensual.itertuples()],
        "localidades": [{"localidad": r.LOCALIDAD_LIMPIA, "municipio": r.MUNICIPIO_LIMPIO,
                         "energia_mwh": _num(r.energia / 1000, 2), "horas_promedio": _num(r.horas),
                         "meses": int(r.meses)} for r in locs.itertuples()],
    }


def filtrar(q="", departamento=None, municipio=None, localidad="", anio=None, mes=None):
    d = datos()
    m = pd.Series(True, index=d.index)
    if departamento:
        m &= d.ID_DEP == int(departamento)
    if municipio:
        m &= d.ID_MUN == int(municipio)
    if localidad:
        m &= d.LOCALIDAD_LIMPIA.map(limpieza.limpiar_nombre) == limpieza.limpiar_nombre(localidad)
    if anio:
        m &= d.ANIO == int(anio)
    if mes:
        m &= d.MES == int(mes)
    for palabra in limpieza.limpiar_nombre(q or "").split():
        m &= d._texto.str.contains(palabra, regex=False)
    return d[m]


COLUMNAS_SALIDA = {"DEPARTAMENTO_LIMPIO": "departamento", "MUNICIPIO_LIMPIO": "municipio",
                   "LOCALIDAD_LIMPIA": "localidad", "ANIO": "anio", "MES": "mes", "EA_KWH": "energia_kwh",
                   "HORAS_DIA": "horas_dia", "FACTOR_CARGA": "factor_carga"}


def tabla(g):
    out = g[list(COLUMNAS_SALIDA)].rename(columns=COLUMNAS_SALIDA)
    out["factor_carga"] = out.factor_carga.round(3)
    out["horas_dia"] = out.horas_dia.round(2)
    return out


def buscar(pagina=1, por_pagina=50, orden="reciente", **filtros):
    g = filtrar(**filtros)
    if orden == "energia":
        g = g.sort_values("EA_KWH", ascending=False, na_position="last")
    elif orden == "lugar":
        pass  # ya viene ordenado por departamento, municipio, localidad y periodo
    else:
        g = g.sort_values(["PERIODO", "DEPARTAMENTO_LIMPIO", "MUNICIPIO_LIMPIO", "LOCALIDAD_LIMPIA"],
                          ascending=[False, True, True, True])
    por_pagina = max(1, min(int(por_pagina), 200))
    paginas = max(1, -(-len(g) // por_pagina))
    pagina = max(1, min(int(pagina), paginas))
    filas = tabla(g.iloc[(pagina - 1) * por_pagina: pagina * por_pagina])
    filas = filas.astype(object).where(filas.notna(), None)
    lugares = g.drop_duplicates("LOC_KEY")
    return {
        "total": int(len(g)), "pagina": pagina, "paginas": paginas, "por_pagina": por_pagina,
        "resumen": {**_indicadores(g), "departamentos": int(g.ID_DEP.nunique()),
                    "desde": int(g.PERIODO.min()) if len(g) else None,
                    "hasta": int(g.PERIODO.max()) if len(g) else None} if len(g) else None,
        "departamentos_encontrados": sorted(lugares.DEPARTAMENTO_LIMPIO.unique().tolist()),
        "registros": [{k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items()}
                      for r in filas.to_dict("records")],
    }
