"""Diagnóstico de error por localidad para la auditoría temporal reservada (ventana 4).

Ejecutar desde la raíz:
    python -m scripts.diagnostico_localidades

No modifica ni reemplaza modelos registrados. Entrena HistGradientBoosting con los
datos anteriores a 2025-01 y evalúa enero-junio de 2025, conservando la ventana
como auditoría temporal.
"""
import numpy as np
import pandas as pd

from app import modelo
from scripts import experimento_modelos as exp


def ejecutar():
    datos = exp.cargar_datos()
    inicio = exp.INICIOS_VENTANAS[3]  # 2025-01
    fin = inicio + 5

    periodos = exp.periodo(datos)
    entrenamiento = datos[periodos < inicio].copy()
    prueba = datos[(periodos >= inicio) & (periodos <= fin)].copy()

    if entrenamiento.empty or prueba.empty:
        raise ValueError("No hay datos suficientes para la ventana de auditoría 2025-01 a 2025-06.")

    estimador = exp.crear_pipeline("HistGradientBoosting")
    estimador.fit(entrenamiento[modelo.PREDICTORAS], entrenamiento[modelo.OBJETIVO])
    pred = np.clip(estimador.predict(prueba[modelo.PREDICTORAS]), 0, None)

    detalle = prueba[[
        "id_localidad", "localidad", "departamento", "tamano",
        "anio_objetivo", "mes_objetivo", modelo.OBJETIVO
    ]].copy()
    detalle = detalle.rename(columns={modelo.OBJETIVO: "energia_real_kwh"})
    detalle["energia_predicha_kwh"] = pred
    detalle["error_kwh_pred_menos_real"] = detalle["energia_predicha_kwh"] - detalle["energia_real_kwh"]
    detalle["error_absoluto_kwh"] = detalle["error_kwh_pred_menos_real"].abs()
    detalle["error_absoluto_log"] = np.abs(
        np.log1p(detalle["energia_predicha_kwh"]) - np.log1p(detalle["energia_real_kwh"])
    )
    detalle["error_porcentual_abs"] = (
        detalle["error_absoluto_kwh"] / detalle["energia_real_kwh"].clip(lower=1) * 100
    )

    def resumir(g):
        real = g["energia_real_kwh"].to_numpy(dtype=float)
        estimada = g["energia_predicha_kwh"].to_numpy(dtype=float)
        return pd.Series({
            "periodos_evaluados": len(g),
            "mae_log": np.mean(np.abs(np.log1p(estimada) - np.log1p(real))),
            "wape_pct": np.abs(estimada - real).sum() / max(real.sum(), 1) * 100,
            "mae_kwh": np.mean(np.abs(estimada - real)),
            "sesgo_kwh_pred_menos_real": np.mean(estimada - real),
            "energia_real_total_kwh": real.sum(),
            "energia_predicha_total_kwh": estimada.sum(),
            "energia_real_media_kwh": real.mean(),
            "energia_predicha_media_kwh": estimada.mean(),
        })

    columnas = ["id_localidad", "localidad", "departamento", "tamano"]
    filas_resumen = []
    for claves, grupo in detalle.groupby(columnas, dropna=False):
        fila = dict(zip(columnas, claves if isinstance(claves, tuple) else (claves,)))
        fila.update(resumir(grupo).to_dict())
        filas_resumen.append(fila)
    por_localidad = pd.DataFrame(filas_resumen).sort_values(
        ["mae_log", "wape_pct"], ascending=False
    )

    salida = exp.BASE / "docs" / "evaluacion_modelos"
    salida.mkdir(parents=True, exist_ok=True)
    detalle.to_csv(salida / "predicciones_detalladas_ventana4.csv", index=False, encoding="utf-8-sig")
    por_localidad.to_csv(salida / "errores_por_localidad_ventana4.csv", index=False, encoding="utf-8-sig")

    print("Diagnóstico guardado en:", salida)
    print("\nResumen por tamaño:")
    print(por_localidad.groupby("tamano").agg(
        localidades=("id_localidad", "nunique"),
        observaciones=("periodos_evaluados", "sum"),
        mae_log_promedio=("mae_log", "mean"),
        wape_promedio_pct=("wape_pct", "mean"),
    ).round(4).to_string())
    print("\n15 localidades con mayor MAE log:")
    print(por_localidad[[
        "id_localidad", "localidad", "departamento", "tamano",
        "periodos_evaluados", "mae_log", "wape_pct", "sesgo_kwh_pred_menos_real"
    ]].head(15).round(4).to_string(index=False))


if __name__ == "__main__":
    ejecutar()
