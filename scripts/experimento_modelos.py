"""Comparación reproducible de modelos mediante validación temporal de origen móvil.

Uso desde la raíz del proyecto:
    python -m scripts.experimento_modelos

El experimento reproduce el conjunto histórico de la v1 (objetivos hasta 2025-06),
usa cuatro ventanas de prueba consecutivas de seis meses y reserva la última ventana
como auditoría temporal. La selección preliminar se realiza únicamente con las tres
primeras ventanas. No modifica ni reemplaza ningún modelo registrado.
"""
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, OrdinalEncoder, StandardScaler

from app import limpieza, modelo
from app.config import BASE

# Se conserva el mismo corte histórico que la versión v1 para que la comparación
# sea reproducible y no mezcle observaciones posteriores en este primer estudio.
CORTE_MAXIMO = 2025 * 12 + 5  # 2025-06
INICIOS_VENTANAS = [2023 * 12 + 6, 2024 * 12, 2024 * 12 + 6, 2025 * 12]
NOMBRES = ["HistGradientBoosting", "RandomForest", "ExtraTrees", "Ridge"]


def periodo(df):
    return df["anio_objetivo"].astype(int) * 12 + df["mes_objetivo"].astype(int) - 1


def mes_texto(indice):
    return f"{indice // 12}-{indice % 12 + 1:02d}"


def crear_pipeline(nombre):
    """Preprocesamiento común; solo cambia el estimador."""
    tamanos = limpieza.TAMANOS
    energia = Pipeline([
        ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
        ("imputar", SimpleImputer(strategy="median", add_indicator=True)),
    ])
    prep = ColumnTransformer([
        ("energia", energia, modelo.VAR_ENERGIA),
        ("otras", SimpleImputer(strategy="median", add_indicator=True), modelo.VAR_OTRAS),
        ("departamento", OneHotEncoder(handle_unknown="ignore", sparse_output=False), modelo.VAR_CAT),
        ("tamano", OrdinalEncoder(categories=[tamanos]), modelo.VAR_ORD),
        ("mes", FunctionTransformer(modelo.mes_ciclico), modelo.VAR_MES),
        ("binaria", "passthrough", modelo.VAR_BIN),
    ])

    if nombre == "HistGradientBoosting":
        estimador = HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=0.03, max_iter=300,
            max_leaf_nodes=31, min_samples_leaf=20,
            l2_regularization=1.0, random_state=42,
        )
        pasos = [("preprocesamiento", prep), ("regresor", estimador)]
    elif nombre == "RandomForest":
        estimador = RandomForestRegressor(
            n_estimators=300, min_samples_leaf=2, max_features=0.8,
            n_jobs=-1, random_state=42,
        )
        pasos = [("preprocesamiento", prep), ("regresor", estimador)]
    elif nombre == "ExtraTrees":
        estimador = ExtraTreesRegressor(
            n_estimators=300, min_samples_leaf=2, max_features=0.8,
            n_jobs=-1, random_state=42,
        )
        pasos = [("preprocesamiento", prep), ("regresor", estimador)]
    elif nombre == "Ridge":
        estimador = Ridge(alpha=1.0)
        pasos = [("preprocesamiento", prep), ("escalar", StandardScaler()), ("regresor", estimador)]
    else:
        raise ValueError(f"Algoritmo no reconocido: {nombre}")

    return TransformedTargetRegressor(
        regressor=Pipeline(pasos), func=np.log1p, inverse_func=np.expm1
    )


def calcular_metricas(real, predicho):
    real = np.asarray(real, dtype=float)
    predicho = np.clip(np.asarray(predicho, dtype=float), 0, None)
    return {
        "mae_log": float(np.mean(np.abs(np.log1p(predicho) - np.log1p(real)))),
        "wape_pct": float(np.abs(predicho - real).sum() / max(real.sum(), 1) * 100),
        "mae_kwh": float(np.mean(np.abs(predicho - real))),
        "sesgo_kwh": float(np.mean(predicho - real)),
        "n": int(len(real)),
    }


def cargar_datos():
    archivos = sorted((BASE / "datos" / "crudos").glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not archivos:
        raise FileNotFoundError("No se encontró el CSV fuente en datos/crudos.")
    raw = pd.read_csv(archivos[-1], dtype=str, encoding="utf-8-sig")
    limpio = limpieza.limpiar(raw)
    datos = limpieza.construir_variables(limpio)
    datos = datos[datos[modelo.OBJETIVO] > 0].copy()
    datos = datos[periodo(datos) <= CORTE_MAXIMO].copy()
    return datos.sort_values(["anio_objetivo", "mes_objetivo", "id_localidad"]).reset_index(drop=True)


def ejecutar():
    datos = cargar_datos()
    p = periodo(datos)
    folds = []
    for inicio in INICIOS_VENTANAS:
        fin = inicio + 5
        entrenamiento = datos[p < inicio].copy()
        prueba = datos[(p >= inicio) & (p <= fin)].copy()
        if entrenamiento.empty or prueba.empty:
            raise ValueError(f"Ventana sin datos suficientes: {mes_texto(inicio)} a {mes_texto(fin)}")
        folds.append((inicio, fin, entrenamiento, prueba))

    resultados, por_tamano = [], []
    for nombre in NOMBRES:
        for numero, (inicio, fin, entrenamiento, prueba) in enumerate(folds, start=1):
            inicio_t = time.perf_counter()
            estimador = crear_pipeline(nombre)
            estimador.fit(entrenamiento[modelo.PREDICTORAS], entrenamiento[modelo.OBJETIVO])
            pred = np.clip(estimador.predict(prueba[modelo.PREDICTORAS]), 0, None)
            metricas = calcular_metricas(prueba[modelo.OBJETIVO], pred)
            resultados.append({
                "algoritmo": nombre, "ventana": numero,
                "desde": mes_texto(inicio), "hasta": mes_texto(fin),
                "registros_entrenamiento": len(entrenamiento),
                "registros_prueba": len(prueba), **metricas,
                "tiempo_segundos": time.perf_counter() - inicio_t,
            })
            detalle = prueba[["tamano"]].copy()
            detalle["real"] = prueba[modelo.OBJETIVO].to_numpy()
            detalle["predicho"] = pred
            for tamano, grupo in detalle.groupby("tamano", dropna=False):
                m = calcular_metricas(grupo["real"], grupo["predicho"])
                por_tamano.append({
                    "algoritmo": nombre, "ventana": numero,
                    "desde": mes_texto(inicio), "hasta": mes_texto(fin),
                    "tamano": str(tamano), **m,
                })

    # Referencia de persistencia: repetir el último mes conocido.
    for numero, (inicio, fin, entrenamiento, prueba) in enumerate(folds, start=1):
        metricas = calcular_metricas(prueba[modelo.OBJETIVO], prueba["energia_lag1_kwh"])
        resultados.append({
            "algoritmo": "Ingenuo_lag1", "ventana": numero,
            "desde": mes_texto(inicio), "hasta": mes_texto(fin),
            "registros_entrenamiento": len(entrenamiento),
            "registros_prueba": len(prueba), **metricas, "tiempo_segundos": 0.0,
        })

    df_resultados = pd.DataFrame(resultados)
    df_tamano = pd.DataFrame(por_tamano)
    carpeta = BASE / "docs" / "evaluacion_modelos"
    carpeta.mkdir(parents=True, exist_ok=True)
    df_resultados.to_csv(carpeta / "resultados_por_ventana.csv", index=False, encoding="utf-8-sig")
    df_tamano.to_csv(carpeta / "resultados_por_tamano.csv", index=False, encoding="utf-8-sig")

    desarrollo = df_resultados[df_resultados["ventana"] <= 3]
    resumen_desarrollo = (desarrollo.groupby("algoritmo")
                          .agg(mae_log_promedio=("mae_log", "mean"),
                               mae_log_desviacion=("mae_log", "std"),
                               wape_promedio_pct=("wape_pct", "mean"),
                               mae_kwh_promedio=("mae_kwh", "mean"),
                               sesgo_kwh_promedio=("sesgo_kwh", "mean"))
                          .sort_values("mae_log_promedio"))
    auditoria = df_resultados[df_resultados["ventana"] == 4].sort_values("mae_log")
    resumen = {
        "proposito": "Comparación preliminar con validación temporal de origen móvil; no modifica modelos registrados.",
        "periodo_maximo_objetivo": "2025-06",
        "registros": int(len(datos)),
        "localidades": int(datos["id_localidad"].nunique()),
        "ventanas": [
            {"ventana": i, "desde": mes_texto(a), "hasta": mes_texto(b),
             "n_entrenamiento": int(len(tr)), "n_prueba": int(len(te)),
             "uso": "desarrollo" if i <= 3 else "auditoria_temporal_reservada"}
            for i, (a, b, tr, te) in enumerate(folds, start=1)
        ],
        "seleccion_preliminar_solo_desarrollo": resumen_desarrollo.reset_index().to_dict("records"),
        "auditoria_ventana_4_no_usar_para_seleccion": auditoria.to_dict("records"),
        "advertencias": [
            "Los objetivos iguales a cero se excluyen porque la fuente no permite distinguir de forma fiable cero real, interrupción y ausencia de reporte.",
            "La selección se basa principalmente en MAE log; WAPE y MAE en kWh se reportan como métricas complementarias.",
            "La última ventana se reserva como auditoría temporal y no debe usarse para ajustar hiperparámetros.",
            "Este experimento compara configuraciones iniciales; después se debe optimizar hiperparámetros solo dentro del periodo de desarrollo.",
        ],
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evaluación guardada en:", carpeta)
    print("\nSelección preliminar (ventanas 1-3):")
    print(resumen_desarrollo.round(4).to_string())
    print("\nAuditoría temporal (ventana 4; no usar para selección):")
    print(auditoria[["algoritmo", "mae_log", "wape_pct", "mae_kwh", "n"]].round(4).to_string(index=False))


if __name__ == "__main__":
    ejecutar()
