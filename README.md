# Sistema web ZNI: análisis automático y predicción de energía

Aplicativo web que convierte el análisis de la **prestación del servicio de energía en las Zonas No Interconectadas (ZNI) de Colombia** en un sistema que recibe datos nuevos, verifica si el modelo puede procesarlos, genera el análisis exploratorio, produce predicciones, exporta reportes y permite reentrenar el modelo con control de versiones.

**Qué predice:** la energía activa (kWh) que entregará cada localidad **el mes siguiente**, a partir de lo que pasó en los meses anteriores. Sirve para anticipar la demanda y planear el combustible y la logística, que en zonas remotas son muy costosos.

Proyecto de la Fundación Universitaria Uniclaretiana · Integrantes: Alex David Moya Bejarano y Alex David Garcia Chala · Docente: Carlos Stiwar Asprilla Mosquera.

<<<<<<< HEAD
## Inicio rápido en Windows

Descomprima el zip, entre a la carpeta `zni-app` (la que contiene `app`, `modelos` y este README) y haga **doble clic en `iniciar.bat`**. La primera vez instala las librerías; luego abre el sitio en el navegador. Para apagarlo, cierre la ventana negra.

=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
## Requisitos e instalación

Python 3.10 o superior.

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

El repositorio ya trae el modelo activo (`modelos/v1`). Para volver a generarlo desde el CSV del portal:

```bash
python -m scripts.entrenar_inicial      # entrena la v1 y la deja como activa
python -m scripts.generar_escenarios    # regenera los archivos de prueba
```

## Iniciar la API y la interfaz

```bash
uvicorn app.main:app --reload
```

<<<<<<< HEAD
- Página de presentación: <http://localhost:8000/> (explica el problema, cómo funciona el sistema, el modelo y el equipo)
- Sistema: <http://localhost:8000/sistema.html> (botón «Entrar al sistema»)
- Ingreso y registro de administradores: <http://localhost:8000/ingresar.html>
- Documentación interactiva de la API (para probar cada operación): <http://localhost:8000/docs>

El sitio lo sirve la misma API, así que no hay un segundo proceso que iniciar. Todo se usa desde ahí:

| Sección del sitio | Qué hace |
|---|---|
| Panel | Indicadores del modelo activo y los pasos de uso |
| Mapa y búsqueda | Mapa de calor de Colombia por departamento o municipio (energía, horas de servicio, localidades, % con menos de 12 h); al tocar un lugar muestra sus indicadores, su energía mensual y sus localidades. Buscador por departamento, municipio o comunidad con todos los registros y descarga en CSV |
| Analizar datos | EDA automático de cualquier CSV o Excel |
| Validar y predecir | Validación en 4 niveles y predicciones con intervalo del 80%, gráfico y tabla |
| Preparar datos del portal | Convierte el CSV del portal en la tabla del modelo; puede predecir en el mismo paso |
| Modelo y versiones | Métricas, comparación de algoritmos, variables, reentrenamiento y decisión sobre candidatas |
| Reportes | Historial de todas las cargas con sus reportes descargables |
| Archivos de prueba | Los escenarios obligatorios: «Probar» los ejecuta directamente, «Descargar» los guarda |
| Acerca del proyecto | Equipo, datos, metodología y diagrama de arquitectura |

## Mapa y búsqueda por territorio

La sección **Mapa y búsqueda** es pública. Lee el archivo del portal que está en `datos/crudos/` y lo limpia con las mismas reglas del modelo; si se reemplaza ese archivo por uno más reciente, el mapa se actualiza solo. Operaciones de la API: `/api/territorio/opciones`, `/api/territorio/resumen`, `/api/territorio/detalle`, `/api/territorio/registros` y `/api/territorio/registros.csv`.

Los contornos vienen del Marco Geoestadístico Nacional 2018 del DANE (versión simplificada de github.com/caticoa3/colombia_mapa) y están ya convertidos en `app/static/datos/mapa_colombia.json`. Para regenerarlos: `python -m scripts.generar_mapa departamentos.geojson municipios.geojson`.

## Administradores y base de datos

Consultar, analizar, validar, predecir y usar el mapa no requiere cuenta. **Reentrenar el modelo, decidir qué versión queda activa y administrar las cuentas solo lo pueden hacer los administradores.**

- **Base de datos:** SQLite en `datos/seguridad/zni.db`. Viene incluida con Python, no hay que instalar ningún servidor. Tiene dos tablas: `usuarios` (cuentas, con la contraseña cifrada) e `inicios_sesion` (cada registro, ingreso, salida, intento fallido y bloqueo, con fecha, dirección y navegador). Se puede abrir con [DB Browser for SQLite](https://sqlitebrowser.org/). Si existe un `usuarios.json` de la versión anterior, se importa solo la primera vez.
- **Primera cuenta:** vaya a **Ingresar → Crear cuenta**. Se pide un **código de registro**, que se muestra en la ventana del servidor al iniciarlo y queda guardado en `datos/seguridad/codigo_registro.txt`. También se puede fijar con la variable de entorno `ZNI_CODIGO_REGISTRO`.
- **Sección Administradores** (aparece en el menú al ingresar): crear cuentas sin código, editar el nombre o la contraseña, desactivar, activar o eliminar cuentas, y consultar el historial de inicios de sesión con filtros. No se puede desactivar ni eliminar la propia cuenta, y siempre queda al menos un administrador activo.
- **Seguridad:** contraseñas con PBKDF2-SHA256 y sal; la sesión vence a las 8 horas; cambiar la contraseña o desactivar una cuenta cierra sus sesiones abiertas; tras 5 intentos fallidos en 10 minutos el ingreso se bloquea temporalmente.
- API: `/api/admin/usuarios` (GET, POST), `/api/admin/usuarios/{usuario}` (PUT, DELETE) y `/api/admin/sesiones`.
- La carpeta `datos/seguridad/` no se sube al repositorio.

## Prueba completa (demostración)

La forma más rápida es la sección **Archivos de prueba**: cada botón «Probar» carga el archivo y lo ejecuta en la sección correcta. Paso a paso:

1. **Analizar datos:** cargue `pruebas/escenarios/07_solo_eda_portal_crudo.csv`. El sistema detecta los tipos (incluye números en formato español y fechas), muestra faltantes, atípicos, frecuencias, correlaciones y gráficos, y deja descargar el reporte EDA.
2. **Validar y predecir con un archivo incompatible:** cargue `03_tipo_incompatible.csv`. El estado sale *Incompatible*, se explica qué variable falla, qué se esperaba, qué se encontró y en qué filas. No se genera ninguna predicción.
3. **Validar y predecir con un archivo compatible:** cargue `01_compatible.csv`. Se generan las predicciones con su intervalo del 80% y se descargan en CSV, Excel y HTML.
4. **Modelo y versiones:** ingrese como administrador y cargue `08_nuevos_etiquetados.csv`. Se valida, se integra, se reentrena y aparece una versión **candidata** comparada con la activa. Escriba una justificación y elija activarla o conservar la activa.
=======
- Interfaz web: <http://localhost:8000/>
- Documentación interactiva de la API (para probar cada operación): <http://localhost:8000/docs>

La interfaz la sirve la misma API, así que no hay un segundo proceso que iniciar.

## Prueba completa (demostración)

1. **Analizar datos:** cargue `pruebas/escenarios/07_solo_eda_portal_crudo.csv`. El sistema detecta los tipos (incluye números en formato español y fechas), muestra faltantes, atípicos, frecuencias, correlaciones y gráficos, y deja descargar el reporte EDA.
2. **Validar y predecir con un archivo incompatible:** cargue `03_tipo_incompatible.csv`. El estado sale *Incompatible*, se explica qué variable falla, qué se esperaba, qué se encontró y en qué filas. No se genera ninguna predicción.
3. **Validar y predecir con un archivo compatible:** cargue `01_compatible.csv`. Se generan las predicciones con su intervalo del 80% y se descargan en CSV, Excel y HTML.
4. **Modelo y versiones:** cargue `08_nuevos_etiquetados.csv`. Se valida, se integra, se reentrena y aparece una versión **candidata** comparada con la activa. Escriba una justificación y elija activarla o conservar la activa.
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
5. **Preparar archivo del portal:** cargue el CSV original del portal de datos abiertos y descargue la tabla lista para predecir el mes siguiente.

## Pruebas automáticas

```bash
pytest -q
```

<<<<<<< HEAD
Cubren los 8 escenarios obligatorios el acceso de administradores (registro, ingreso, bloqueo por intentos) la consulta por territorio y la administración de cuentas. Trabajan sobre una copia temporal de `modelos/`, así que no cambian el modelo real.
=======
Cubren los 8 escenarios obligatorios. Trabajan sobre una copia temporal de `modelos/`, así que no cambian el modelo real.
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3

| # | Archivo | Resultado esperado |
|---|---|---|
| 1 | `01_compatible.csv` | Compatible, predicciones generadas |
| 2 | `02_falta_variable.csv` | Incompatible: falta `energia_lag1_kwh` |
| 3 | `03_tipo_incompatible.csv` | Incompatible: texto en `mes_objetivo` y números con formato español en `energia_lag1_kwh` |
| 4 | `04_faltantes.csv` | Incompatible: 5 faltantes en `energia_lag1_kwh` |
| 5 | `05a_categoria_nueva_departamento.csv` | Compatible con advertencias: departamento no visto (se predice y se marca) |
| 5 | `05b_categoria_fuera_de_escala.csv` | Incompatible: `tamano` fuera de la escala definida |
| 6 | `06_columnas_adicionales.csv` | Compatible con advertencias: columnas que el modelo no usa |
| 7 | `07_solo_eda_portal_crudo.csv` | Incompatible para predecir, pero el EDA funciona (y sugiere usar «Preparar») |
| 7 | `07b_reglas_de_dominio.csv` | Incompatible: horas > 24, factor de carga > 1, `sin_servicio_lag1` incoherente |
| 8 | `08_nuevos_etiquetados.csv` | Versión candidata creada sin reemplazar la activa |
| extra | `09_pronostico_2026_02.csv` | Pronóstico real de febrero de 2026 (compatible con advertencias: faltan horas por el cambio de formato de la fuente) |

## API

| Operación | Método y ruta |
|---|---|
| Analizar dataset (EDA) | `POST /api/eda` |
| Validar compatibilidad | `POST /api/validar` (`modo` = `prediccion` o `actualizacion`) |
| Generar predicciones | `POST /api/predecir` (responde 422 con el diagnóstico si el archivo es incompatible) |
| Consultar modelo activo | `GET /api/modelo` |
| Listar versiones | `GET /api/modelo/versiones` |
| Actualizar y reentrenar | `POST /api/modelo/actualizar` |
| Registrar decisión sobre una candidata | `POST /api/modelo/versiones/{version}/decision` |
| Descargar reporte | `GET /api/reportes/{proceso}/{tipo}` |
<<<<<<< HEAD
| Historial de cargas | `GET /api/procesos` |
| Archivos de prueba | `GET /api/escenarios` y `GET /api/escenarios/{archivo}` |
=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
| Preparar CSV del portal | `POST /api/preparar` |

## Estructura

```
app/
  main.py          API FastAPI (orquesta todo)
  validacion.py    validación en 4 niveles contra el esquema del modelo
  eda.py           EDA automático según los tipos de variable
  modelo.py        pipeline, validación temporal, predicción y versiones
  limpieza.py      limpieza del CSV del portal (la de la Actividad 3) y variables rezagadas
  reportes.py      reportes HTML
<<<<<<< HEAD
  static/          sitio web (index.html, css/, js/, img/)
=======
  static/          interfaz web
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
config/esquema.json  variables, tipos, faltantes, categorías, rangos y exclusiones
modelos/
  registro.json    versiones: activo, candidato, histórico
  v1/              pipeline.joblib, metadatos.json, datos_entrenamiento.csv
datos/crudos/      CSV original del portal
pruebas/escenarios/  archivos de los escenarios de prueba
tests/             pruebas automáticas
docs/              diagrama de arquitectura, documento técnico y evidencia de reportes
```

## El modelo en una línea

`HistGradientBoostingRegressor` sobre log(1 + kWh), con validación temporal (entrena hasta 2024-06, prueba de 2024-07 a 2025-06). Métrica principal: MAE en escala log = **0,266**, un **26,5% menos error** que repetir el valor del mes anterior. Detalle en `docs/documento_tecnico.md`.

![Arquitectura](docs/arquitectura.png)
<<<<<<< HEAD

## Experiencia pública y acceso administrativo

- La entrada principal (`/`) lleva directamente al mapa territorial (`/sistema.html#mapa`).
- Los usuarios sin sesión pueden consultar el mapa, buscar territorios y analizar documentos tabulares CSV/Excel desde **Analizar documento**.
- Las funciones técnicas (validación para predicción, predicción, preparación de datos, consulta del modelo, versiones, reportes técnicos, archivos de prueba y administración) requieren una sesión de administrador.
- La API mantiene públicas las consultas territoriales y el análisis exploratorio `/api/eda`; las rutas técnicas están protegidas en el backend, no solamente ocultas en la interfaz.
- Para administrar, ingrese desde el enlace **Ingresar como administrador** del menú lateral.
=======
>>>>>>> da2da0a704b9b9be8e8c1e1cbcb185e49874d2e3
