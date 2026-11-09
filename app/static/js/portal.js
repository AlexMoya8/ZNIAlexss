const $ = s => document.querySelector(s);

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[c]));

const fmt = (v, d = 0) =>
  Number(v ?? 0).toLocaleString('es-CO', {
    maximumFractionDigits: d
  });

let opciones = null;
let archivo = null;
let archivoValidado = false;

const toast = m => {
  const t = $('#toast');
  t.textContent = m;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4500);
};

// ------------------------------------------------------------
// Navegación y pestañas
// ------------------------------------------------------------

$('#menu-toggle').onclick = () =>
  $('#nav').classList.toggle('open');

document.querySelectorAll('#nav a').forEach(a => {
  a.onclick = () => $('#nav').classList.remove('open');
});

document.querySelectorAll('.tab').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('.tab').forEach(x =>
      x.classList.toggle('active', x === b)
    );

    ['prediccion', 'historico', 'ayuda'].forEach(k => {
      $('#tab-' + k).hidden = k !== b.dataset.tab;
    });
  };
});

// ------------------------------------------------------------
// Catálogo territorial
// ------------------------------------------------------------

async function cargarOpciones() {
  try {
    const r = await fetch('/api/territorio/opciones');

    if (!r.ok) {
      throw new Error('No fue posible consultar el catálogo territorial.');
    }

    opciones = await r.json();

    $('#source-status').textContent =
      `Datos: ${opciones.primer_periodo} – ${opciones.ultimo_periodo}`;

    $('#departamento').innerHTML =
      '<option value="">Selecciona un departamento</option>' +
      opciones.departamentos.map(d =>
        `<option value="${d.codigo}">${esc(d.nombre)}</option>`
      ).join('');

    if (window.ZNIMapa) {
      window.ZNIMapa.sincronizar(
        $('#departamento').value,
        $('#municipio').value
      );
    }

  } catch (e) {
    $('#source-status').textContent = 'Datos no disponibles';
    toast(e.message);
  }
}

// ------------------------------------------------------------
// Filtros del portal
// ------------------------------------------------------------

function cargarMunicipios() {
  const d = opciones.departamentos.find(
    x => x.codigo === Number($('#departamento').value)
  );

  $('#municipio').disabled = !d;

  $('#municipio').innerHTML =
    '<option value="">Todos los municipios</option>' +
    (d?.municipios || []).map(m =>
      `<option value="${m.codigo}">${esc(m.nombre)}</option>`
    ).join('');

  cargarLocalidades();
}

function cargarLocalidades() {
  const d = opciones.departamentos.find(
    x => x.codigo === Number($('#departamento').value)
  );

  const m = d?.municipios.find(
    x => x.codigo === Number($('#municipio').value)
  );

  $('#localidad').disabled = !m;

  $('#localidad').innerHTML =
    '<option value="">Todas las localidades</option>' +
    (m?.localidades || []).map(l =>
      `<option>${esc(l)}</option>`
    ).join('');

  sincronizarMapaDesdeFiltros();
  consultarHistorico();
}

// ------------------------------------------------------------
// Sincronización de filtros hacia el mapa
// ------------------------------------------------------------

function sincronizarMapaDesdeFiltros() {
  if (window.ZNIMapa) {
    window.ZNIMapa.sincronizar(
      $('#departamento').value,
      $('#municipio').value
    ).catch(e => {
      console.error('No se pudo sincronizar el mapa:', e);
    });
  }
}

$('#departamento').onchange = cargarMunicipios;
$('#municipio').onchange = cargarLocalidades;

$('#localidad').onchange = () => {
  consultarHistorico();
  sincronizarMapaDesdeFiltros();
};

// ------------------------------------------------------------
// Sincronización del mapa hacia los filtros del portal
// ------------------------------------------------------------

window.ZNIPortal = {
  actualizarDesdeMapa({departamento, municipio}) {
    const dep = String(departamento || '');
    const mun = municipio ? String(municipio) : '';

    $('#departamento').value = dep;

    cargarMunicipios();

    $('#municipio').value = mun;

    cargarLocalidades();
  },

  limpiarFiltrosDesdeMapa() {
    $('#departamento').value = '';

    cargarMunicipios();

    $('#municipio').value = '';
    $('#localidad').value = '';

    consultarHistorico();
  }
};

// ------------------------------------------------------------
// Consulta de datos históricos
// ------------------------------------------------------------

async function consultarHistorico() {
  const dep = $('#departamento').value;
  const mun = $('#municipio').value;
  const loc = $('#localidad').value;

  if (!dep) {
    $('#territory-stats').innerHTML = `
      <div><b>—</b><small>Registros</small></div>
      <div><b>—</b><small>Localidades</small></div>
      <div><b>—</b><small>Energía (MWh)</small></div>
    `;

    $('#history-label').textContent = 'Selecciona un territorio';

    $('#history-results').textContent =
      'Los indicadores aparecerán al seleccionar un territorio.';

    return;
  }

  try {
    let i;
    let periodo;
    let desde;
    let hasta;
    let nombre;

    if (loc) {
      const q = new URLSearchParams({
        departamento: dep,
        localidad: loc,
        por_pagina: '1'
      });

      if (mun) q.set('municipio', mun);

      const r = await fetch('/api/territorio/registros?' + q);

      if (!r.ok) {
        throw new Error('No hay registros para la localidad seleccionada.');
      }

      const d = await r.json();

      if (!d.total) {
        throw new Error('No hay registros para la localidad seleccionada.');
      }

      i = d.resumen;
      periodo = 'Registros de la localidad seleccionada';
      desde = i.desde;
      hasta = i.hasta;
      nombre = loc;

    } else {
      const nivel = mun ? 'municipio' : 'departamento';
      const codigo = mun || dep;

      const q = new URLSearchParams({
        nivel,
        codigo
      });

      const r = await fetch('/api/territorio/detalle?' + q);

      if (!r.ok) {
        throw new Error('No hay registros para la selección.');
      }

      const d = await r.json();

      i = d.historico;
      periodo = d.periodo;
      desde = i.desde;
      hasta = i.hasta;
      nombre = d.nombre;
    }

    $('#territory-stats').innerHTML = `
      <div>
        <b>${fmt(i.registros)}</b>
        <small>Registros</small>
      </div>
      <div>
        <b>${fmt(i.localidades)}</b>
        <small>Localidades</small>
      </div>
      <div>
        <b>${fmt(i.energia_mwh, 1)}</b>
        <small>Energía (MWh)</small>
      </div>
    `;

    $('#history-label').textContent =
      `${nombre} · ${periodo}`;

    $('#history-results').innerHTML = `
      <div class="history-kpis">
        <div>
          <b>${fmt(i.energia_mwh, 1)} MWh</b>
          <small>Energía consultada</small>
        </div>
        <div>
          <b>${fmt(i.localidades)}</b>
          <small>Localidades</small>
        </div>
        <div>
          <b>${i.horas_promedio == null
            ? '—'
            : fmt(i.horas_promedio, 1) + ' h'}
          </b>
          <small>Promedio de servicio al día</small>
        </div>
        <div>
          <b>${fmt(i.registros)}</b>
          <small>Registros disponibles</small>
        </div>
      </div>

      <p class="fineprint">
        Periodo disponible: ${desde} a ${hasta}.
        Los indicadores corresponden a la selección actual.
      </p>
    `;

  } catch (e) {
    $('#history-results').textContent = e.message;
  }
}

// ------------------------------------------------------------
// Carga y validación de archivos
// ------------------------------------------------------------

$('#prediction-file').onchange = e => {
  archivo = e.target.files[0] || null;
  archivoValidado = false;

  $('#run-prediction').disabled = true;

  $('#file-name').textContent = archivo
    ? archivo.name
    : 'Selecciona tu archivo CSV o Excel';

  $('#validation-results').className = 'validation-results';

  $('#validation-results').innerHTML = `
    <b>Documento pendiente de validación</b>
    <span>
      Comprueba la estructura y compatibilidad antes de ejecutar el modelo.
    </span>
  `;
};

$('#validate-file').onclick = async () => {
  if (!archivo) {
    toast('Selecciona primero un archivo CSV o Excel.');
    return;
  }

  const b = $('#validate-file');

  b.disabled = true;
  b.textContent = 'Validando…';

  archivoValidado = false;
  $('#run-prediction').disabled = true;

  try {
    const fd = new FormData();

    fd.append('archivo', archivo);
    fd.append('modo', 'prediccion');

    const r = await fetch('/api/validar', {
      method: 'POST',
      body: fd
    });

    const j = await r.json();

    if (!r.ok) {
      throw new Error(
        j.detalle || j.detail || 'No se pudo validar el documento.'
      );
    }

    const d = j.diagnostico;
    const ok = Boolean(d.puede_predecir);

    archivoValidado = ok;

    const hallazgos = (d.hallazgos || []).slice(0, 8);

    $('#validation-results').className =
      'validation-results ' + (ok ? 'ok' : 'bad');

    $('#validation-results').innerHTML = `
      <b>${ok
        ? '✓ Archivo compatible con el modelo'
        : '✕ Archivo incompatible'}
      </b>

      <span>
        ${fmt(d.filas)} filas ·
        ${fmt(d.columnas)} columnas ·
        ${fmt(d.errores)} errores ·
        ${fmt(d.advertencias)} advertencias
      </span>

      ${hallazgos.length
        ? `<ul>${hallazgos.map(h =>
            `<li><strong>${esc(h.variable)}:</strong> ${esc(h.mensaje)}</li>`
          ).join('')}</ul>`
        : '<span>La estructura, los tipos y las reglas de validación están correctos.</span>'
      }
    `;

    $('#run-prediction').disabled = !ok;

    toast(
      ok
        ? 'Documento validado. Ya puedes ejecutar la predicción.'
        : 'Corrige los errores indicados para poder predecir.'
    );

  } catch (e) {
    $('#validation-results').className = 'validation-results bad';

    $('#validation-results').innerHTML = `
      <b>No fue posible validar el archivo</b>
      <span>${esc(e.message)}</span>
    `;

    toast(e.message);

  } finally {
    b.disabled = false;
    b.innerHTML = '✓ &nbsp;Validar documento';
  }
};

// ------------------------------------------------------------
// Gráfica de predicciones
// ------------------------------------------------------------

function chart(rows) {
  const vals = rows.map(x => Number(x.prediccion_kwh) || 0);

  const max = Math.max(...vals, 1);
  const w = 640;
  const h = 210;
  const p = 38;

  const pts = vals.map((v, i) =>
    `${p + i * (w - 2 * p) / Math.max(vals.length - 1, 1)},${h - p - v / max * (h - 2 * p)}`
  ).join(' ');

  return `
    <svg viewBox="0 0 ${w} ${h}"
      role="img"
      aria-label="Gráfica de valores predichos"
      style="width:100%;height:auto">

      <defs>
        <linearGradient id="area" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#16b96b" stop-opacity=".25"/>
          <stop offset="1" stop-color="#16b96b" stop-opacity="0"/>
        </linearGradient>
      </defs>

      ${[0, 1, 2, 3].map(i =>
        `<line
          x1="${p}"
          y1="${p + i * (h - 2 * p) / 3}"
          x2="${w - p}"
          y2="${p + i * (h - 2 * p) / 3}"
          stroke="#e5eeea"/>`
      ).join('')}

      <polygon
        points="${p},${h - p} ${pts} ${w - p},${h - p}"
        fill="url(#area)"/>

      <polyline
        points="${pts}"
        fill="none"
        stroke="#12ad60"
        stroke-width="3"
        stroke-linecap="round"
        stroke-linejoin="round"/>

      ${rows.map((x, i) => {
        const xx = p + i * (w - 2 * p) / Math.max(rows.length - 1, 1);
        const yy = h - p - vals[i] / max * (h - 2 * p);

        return `
          <circle cx="${xx}" cy="${yy}" r="4" fill="#12ad60">
            <title>${esc(x.localidad)}: ${fmt(vals[i])} kWh</title>
          </circle>
        `;
      }).join('')}
    </svg>
  `;
}

// ------------------------------------------------------------
// Ejecutar predicción
// ------------------------------------------------------------

$('#run-prediction').onclick = async () => {
  if (!archivo) {
    toast('Primero selecciona un archivo CSV o Excel.');
    return;
  }

  if (!archivoValidado) {
    toast('Valida el documento antes de ejecutar la predicción.');
    return;
  }

  const b = $('#run-prediction');

  b.disabled = true;
  b.textContent = 'Procesando…';

  try {
    const fd = new FormData();

    fd.append('archivo', archivo);

    const r = await fetch('/api/predecir', {
      method: 'POST',
      body: fd
    });

    const j = await r.json();

    if (!r.ok) {
      throw new Error(
        j.detalle || j.detail || 'No se pudo generar la predicción.'
      );
    }

    const rows = j.filas || [];

    $('#chart-subtitle').textContent =
      `Modelo ${j.version_modelo} · ${j.resumen.registros} registros procesados`;

    $('#prediction-results').classList.remove('empty-chart');

    $('#prediction-results').innerHTML = `
      <div class="result-kpis">
        <div>
          <b>${fmt(j.resumen.total_kwh)} kWh</b>
          <small>Demanda estimada total</small>
        </div>
        <div>
          <b>${fmt(j.resumen.mediana_kwh)} kWh</b>
          <small>Mediana por registro</small>
        </div>
        <div>
          <b>${fmt(rows.length)}</b>
          <small>Registros predichos</small>
        </div>
      </div>

      ${chart(rows.slice(0, 40))}

      <div class="result-table">
        <table>
          <thead>
            <tr>
              <th>Localidad</th>
              <th>Periodo</th>
              <th>Predicción (kWh)</th>
            </tr>
          </thead>
          <tbody>
            ${rows.slice(0, 50).map(x => `
              <tr>
                <td>${esc(x.localidad)}</td>
                <td>${esc(x.periodo_objetivo)}</td>
                <td>${fmt(x.prediccion_kwh)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <div class="result-links">
        ${Object.entries(j.reportes || {}).map(([k, u]) =>
          `<a href="${u}" target="_blank" rel="noopener">
            ↓ Descargar ${k.replaceAll('_', ' ')}
          </a>`
        ).join('')}
      </div>
    `;

    toast('Predicción generada correctamente.');

  } catch (e) {
    $('#prediction-results').innerHTML = `
      <div class="empty-chart">
        <b>No se pudo generar la predicción</b>
        <span>${esc(e.message)}</span>
      </div>
    `;

    toast(e.message);

  } finally {
    b.disabled = false;
    b.innerHTML = '▶ &nbsp;Ejecutar predicción';
  }
};

// ------------------------------------------------------------
// Inicialización
// ------------------------------------------------------------

cargarOpciones();