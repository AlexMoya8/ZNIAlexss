# Primera evaluación temporal de algoritmos — ZNI-APP

## Objetivo

Comparar algoritmos de regresión para estimar la energía activa del mes siguiente por localidad ZNI, sin modificar ni reemplazar la versión activa del modelo.

## Ejecución

Desde la raíz del proyecto:

```bash
python -m scripts.experimento_modelos
```

El script genera:

- `resultados_por_ventana.csv`: métricas por algoritmo y ventana temporal.
- `resultados_por_tamano.csv`: métricas desglosadas por tamaño de localidad.
- `resumen.json`: metodología, periodos y resultados agregados.

## Datos y diseño experimental

- 4.708 observaciones positivas.
- 207 localidades.
- Periodo objetivo utilizado: 2020-02 a 2025-06.
- Se excluyen objetivos iguales a cero porque la fuente no permite distinguir de forma fiable entre cero real, interrupción y ausencia de reporte.
- Se utiliza validación temporal de origen móvil con cuatro ventanas consecutivas de seis meses.
- Las ventanas 1 a 3 son de desarrollo. La ventana 4 (2025-01 a 2025-06) queda reservada como auditoría temporal y no debe utilizarse para seleccionar hiperparámetros.
- Todos los algoritmos comparten el mismo preprocesamiento y las mismas particiones.

## Resultados de desarrollo

Promedios de las ventanas 1 a 3. La métrica prioritaria es MAE logarítmico; menor es mejor.

| Algoritmo | MAE log promedio | WAPE promedio | MAE promedio (kWh) |
|---|---:|---:|---:|
| HistGradientBoosting | 0,2058 | 9,56 % | 34.323,6 |
| Random Forest | 0,2076 | 9,25 % | 32.735,2 |
| Extra Trees | 0,2100 | 8,49 % | 30.278,0 |
| Ridge | 0,2446 | 16,08 % | 56.137,4 |
| Persistencia (lag 1) | 0,2721 | 5,42 % | 19.572,0 |

HistGradientBoosting queda como candidato preliminar por MAE log. Random Forest y Extra Trees son cercanos y muestran WAPE y MAE en kWh inferiores. La persistencia obtiene menor WAPE, lo que evidencia que ninguna decisión debe basarse en una sola métrica.

## Auditoría temporal reservada

Ventana 4: 2025-01 a 2025-06, 680 observaciones.

| Algoritmo | MAE log | WAPE | MAE (kWh) |
|---|---:|---:|---:|
| HistGradientBoosting | 0,3003 | 8,92 % | 27.976,7 |
| Extra Trees | 0,3064 | 8,08 % | 25.339,0 |
| Random Forest | 0,3075 | 6,44 % | 20.198,6 |
| Ridge | 0,3333 | 17,23 % | 54.033,8 |
| Persistencia (lag 1) | 0,4248 | 7,92 % | 24.834,4 |

Esta ventana no se usa para elegir el algoritmo ni para ajustar hiperparámetros. Los resultados muestran una degradación de todos los modelos frente a las ventanas anteriores, por lo que el siguiente paso debe investigar cambios temporales, cobertura de localidades y calidad de las variables.

## Próximos pasos

1. Revisar los resultados por tamaño y por localidad para detectar dónde se concentra el error.
2. Investigar la cobertura cambiante de localidades y los datos faltantes.
3. Analizar el sesgo negativo de los modelos de regresión.
4. Optimizar hiperparámetros usando exclusivamente las ventanas de desarrollo.
5. Mantener una evaluación final independiente antes de crear una nueva versión productiva.
6. Investigar por separado los registros con energía objetivo cero; no asumir que todo cero equivale a interrupción.

## Precauciones

- Esta es una comparación inicial de configuraciones razonables, no una búsqueda exhaustiva de hiperparámetros.
- Los intervalos de incertidumbre actuales deben reevaluarse con predicciones fuera de muestra y cobertura empírica.
- El archivo `pipeline.joblib` de v1 fue serializado con scikit-learn 1.9.1. En un entorno con scikit-learn 1.8.0 aparecen advertencias de incompatibilidad al cargarlo. No se debe ignorar esa diferencia en despliegue.
- El script es experimental y no modifica `modelos/`, el registro de versiones ni el modelo activo.
