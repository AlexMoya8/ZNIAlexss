(() => {
// Mapa independiente del portal: evita colisiones con las funciones de portal.js.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (v, d = 0) => typeof v === 'number' ? v.toLocaleString('es-CO', {maximumFractionDigits:d}) : esc(v);
const cargando = t => `<div class="mapa-cargando">${esc(t)}</div>`;
const error = m => `<div class="mapa-error">${esc(m)}</div>`;

function tabla(filas, cols, nums = [], dec = 2) {
  if (!filas || !filas.length) return '<p class="mapa-nota">Sin datos.</p>';
  return `<div class="mapa-tabla"><table><thead><tr>${cols.map(c => `<th>${esc(c[1])}</th>`).join('')}</tr></thead><tbody>${filas.map(f => `<tr>${cols.map(c => { const v=f[c[0]]; return `<td class="${nums.includes(c[0])?'n':''}">${Array.isArray(v)?esc(v.join(', ')):c[2]?c[2](v,f):fmt(v,dec)}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>`;
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const per = p => p ? `${MESES[p % 100 - 1]} ${Math.floor(p / 100)}` : '';

const INDICADORES = {
  energia_mwh: {
    nombre: 'Energía entregada',
    unidad: 'MWh',
    dec: 0,
    ayuda: 'Suma de la energía activa de todas las localidades del lugar en el periodo.'
  },
  horas_promedio: {
    nombre: 'Horas de servicio al día',
    unidad: 'h/día',
    dec: 1,
    ayuda: 'Promedio de horas diarias con servicio.'
  },
  localidades: {
    nombre: 'Localidades atendidas',
    unidad: 'localidades',
    dec: 0,
    ayuda: 'Número de localidades con registros en el periodo.'
  },
  pct_menos_12h: {
    nombre: 'Localidades con menos de 12 h',
    unidad: '%',
    dec: 0,
    ayuda: 'Porcentaje de localidades cuyo servicio promedio fue menor a 12 horas al día.'
  }
};

const M = {
  geo: null,
  opciones: null,
  resumen: null,
  nivel: 'departamento',
  indicador: 'energia_mwh',
  anio: '',
  sel: null,
  cortes: [],
  pagina: 1,
  iniciado: false
};

async function cargarMapa() {
  if (M.iniciado) return;
  M.iniciado = true;

  $('#mapa-svg').innerHTML =
    `<foreignObject width="100%" height="100%">${cargando('Cargando el mapa…')}</foreignObject>`;

  const pedir = async (url, que) => {
    let r;

    try {
      r = await fetch(url);
    } catch {
      throw new Error(`No hubo respuesta del servidor al pedir ${que}.`);
    }

    const j = await r.json().catch(() => ({}));

    if (!r.ok) {
      throw new Error(`${que}: ${j.detalle || j.detail || 'error ' + r.status}`);
    }

    return j;
  };

  try {
    [M.geo, M.opciones] = await Promise.all([
      pedir('datos/mapa_colombia.json', 'Contornos del mapa'),
      pedir('/api/territorio/opciones', 'Datos territoriales')
    ]);
  } catch (e) {
    M.iniciado = false;
    $('#mapa-svg').innerHTML = '';
    $('#mapa-detalle').innerHTML =
      error(`No se pudo cargar el mapa. ${e.message}`);
    return;
  }

  $('#mapa-anio').innerHTML =
    '<option value="">Últimos 12 meses</option>' +
    M.opciones.anios.slice().reverse().map(a =>
      `<option>${a}</option>`
    ).join('');

  $('#mapa-fuente').textContent =
    `Datos del portal: ${per(M.opciones.primer_periodo)} a ${per(M.opciones.ultimo_periodo)}. ` +
    'Contornos: DANE, Marco Geoestadístico Nacional 2018.';

  prepararBuscador();
  await pintarResumen();
  buscar(1);
}

// ------------------------------------------------------------
// Resumen territorial
// ------------------------------------------------------------

async function pintarResumen() {
  const q = new URLSearchParams({nivel: M.nivel});

  if (M.anio) q.set('anio', M.anio);

  const r = await fetch(`/api/territorio/resumen?${q}`);

  if (!r.ok) {
    $('#mapa-detalle').innerHTML = error('No se pudo consultar el resumen territorial.');
    return;
  }

  M.resumen = await r.json();

  dibujar();

  if (M.sel && M.sel.nivel === M.nivel) {
    await mostrarDetalle(M.sel.codigo);
  } else {
    pintarTotal();
  }
}

function cortes(valores) {
  const v = valores.filter(x => x != null).sort((a, b) => a - b);

  if (!v.length) return [];

  const q = [0.2, 0.4, 0.6, 0.8].map(p =>
    v[Math.min(v.length - 1, Math.floor(p * v.length))]
  );

  return [...new Set(q)];
}

const claseColor = v =>
  v == null ? 'sd' : `c${M.cortes.filter(c => v >= c).length}`;

function dibujar() {
  const svg = $('#mapa-svg');
  const g = M.geo;
  const ind = INDICADORES[M.indicador];

  const datos = Object.fromEntries(
    M.resumen.lugares.map(l => [l.codigo, l])
  );

  M.cortes = cortes(
    M.resumen.lugares.map(l => l[M.indicador])
  );

  svg.setAttribute('viewBox', g.viewBox);

  const [rx, ry, rw, rh] = g.recuadro_islas;

  const tipDe = (nombre, l, extra = '') => l
    ? `<b>${esc(nombre)}</b>${extra}<br>${esc(ind.nombre)}: ${
        l[M.indicador] == null
          ? 'sin dato'
          : fmt(l[M.indicador], ind.dec) + ' ' + ind.unidad
      }<br>${l.registros
        ? `${l.localidades} ${l.localidades === 1 ? 'localidad' : 'localidades'}`
        : 'Sin registros en este periodo'
      } · toque para ver más`
    : `<b>${esc(nombre)}</b><br>Sin registros de ZNI`;

  const islas = c =>
    M.nivel === 'departamento'
      ? c === 88
      : Math.floor(c / 1000) === 88;

  const camino = (o, cls, l, nombre, extra) =>
    `<path class="${cls}" d="${o.d}" data-codigo="${o.codigo}"${
      l ? ' tabindex="0" role="button"' : ''
    } aria-label="${esc(nombre)}" data-tip="${esc(tipDe(nombre, l, extra))}"/>`;

  let h = `
    <rect class="mapa-recuadro" x="${rx}" y="${ry}" width="${rw}" height="${rh}" rx="6"/>
    <text class="mapa-rotulo" x="${rx + 8}" y="${ry + 14}">
      Archipiélago de San Andrés
    </text>
    <text class="mapa-rotulo chico" x="${rx + rw / 4}" y="${ry + rh - 4}" text-anchor="middle">
      San Andrés
    </text>
    <text class="mapa-rotulo chico" x="${rx + rw * 3 / 4}" y="${ry + rh - 4}" text-anchor="middle">
      Providencia
    </text>
  `;

  if (M.nivel === 'departamento') {
    h += g.departamentos.map(o => {
      const l = datos[o.codigo];

      return camino(
        o,
        `lugar ${l ? claseColor(l[M.indicador]) + ' con-datos' : 'fuera'}`,
        l,
        l ? l.nombre : o.nombre
      );
    }).join('');
  } else {
    h += g.departamentos.map(o =>
      `<path class="lugar fuera" d="${o.d}" data-tip="${esc(`<b>${esc(o.nombre)}</b>`)}"/>`
    ).join('');

    h += g.municipios.map(o => {
      const l = datos[o.codigo];
      const dep = M.opciones.departamentos.find(
        d => d.codigo === o.departamento
      );

      return camino(
        o,
        `lugar ${l ? claseColor(l[M.indicador]) + ' con-datos' : 'sd con-datos'}`,
        l,
        l ? l.nombre : o.nombre,
        dep ? ` · ${esc(dep.nombre)}` : ''
      );
    }).join('');

    h += g.departamentos.map(o =>
      `<path class="borde-dep" d="${o.d}"/>`
    ).join('');
  }

  const objIslas = (
    M.nivel === 'departamento' ? g.departamentos : g.municipios
  ).filter(o => islas(o.codigo) && datos[o.codigo]);

  h += objIslas.map(o =>
    `<path class="toque" d="${o.d}" data-codigo="${o.codigo}" data-tip="${
      esc(tipDe(datos[o.codigo].nombre, datos[o.codigo]))
    }"/>`
  ).join('');

  svg.innerHTML = h;

  marcarSeleccion();
  pintarLeyenda();
}

function pintarLeyenda() {
  const ind = INDICADORES[M.indicador];
  const c = M.cortes;
  const f = v => fmt(v, ind.dec);

  const rangos = c.length
    ? [
        `menos de ${f(c[0])}`,
        ...c.slice(0, -1).map((x, i) => `${f(x)} a ${f(c[i + 1])}`),
        `${f(c[c.length - 1])} o más`
      ]
    : [];

  $('#mapa-leyenda').innerHTML = `
    <b>${esc(ind.nombre)} (${esc(ind.unidad)})</b>
    <div class="escala">
      ${rangos.map((r, i) =>
        `<span><i class="c${i}"></i>${r}</span>`
      ).join('')}
      <span><i class="sd"></i>Sin dato</span>
      <span><i class="fuera"></i>Sin registros ZNI</span>
    </div>
    <p class="nota">${esc(ind.ayuda)} ${esc(M.resumen.periodo)}.</p>
  `;
}

function marcarSeleccion() {
  document.querySelectorAll('#mapa-svg .sel').forEach(p =>
    p.classList.remove('sel')
  );

  if (!M.sel || M.sel.nivel !== M.nivel) return;

  const p = document.querySelector(
    `#mapa-svg path.lugar[data-codigo="${M.sel.codigo}"]`
  );

  if (p) {
    p.classList.add('sel');

    const borde = p.parentNode.querySelector('.borde-dep');

    if (borde) p.parentNode.insertBefore(p, borde);
  }
}

// ------------------------------------------------------------
// Selección en el mapa: actualiza los filtros del portal
// ------------------------------------------------------------

function elegir(codigo) {
  $('#tip').style.display = 'none';

  const l = M.resumen.lugares.find(x => x.codigo === +codigo);

  if (!l) return;

  M.sel = {
    nivel: M.nivel,
    codigo: +codigo
  };

  marcarSeleccion();

  mostrarDetalle(+codigo);

  const departamento =
    M.nivel === 'departamento'
      ? +codigo
      : Math.floor(+codigo / 1000);

  const municipio =
    M.nivel === 'municipio'
      ? +codigo
      : null;

  if (window.ZNIPortal?.actualizarDesdeMapa) {
    window.ZNIPortal.actualizarDesdeMapa({
      nivel: M.nivel,
      codigo: +codigo,
      departamento,
      municipio
    });
  }

  if (innerWidth < 900) {
    $('#mapa-detalle').scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
  }
}

function kpis(i) {
  return `
    <div class="kpis">
      <div class="kpi">
        <b>${fmt(i.energia_mwh)}</b>
        <span>MWh entregados</span>
      </div>
      <div class="kpi">
        <b>${i.horas_promedio == null ? '—' : fmt(i.horas_promedio, 1)}</b>
        <span>horas de servicio al día</span>
      </div>
      <div class="kpi">
        <b>${fmt(i.localidades)}</b>
        <span>${i.localidades === 1 ? 'localidad' : 'localidades'}</span>
      </div>
      <div class="kpi">
        <b>${i.pct_menos_12h == null ? '—' : fmt(i.pct_menos_12h) + '%'}</b>
        <span>con menos de 12 h al día</span>
      </div>
    </div>
  `;
}

function pintarTotal() {
  const t = M.resumen.total;

  $('#mapa-detalle').innerHTML = `
    <p class="sobre">Todas las ZNI</p>
    <h2>Colombia</h2>
    <p class="nota">${esc(M.resumen.periodo)}</p>
    ${kpis(t)}
    <p class="ayuda">
      Selecciona un ${M.nivel === 'departamento' ? 'departamento' : 'municipio'}
      del mapa para ver su información.
      Los lugares en gris no tienen registros en la base de Zonas No Interconectadas.
    </p>
  `;
}

async function mostrarDetalle(codigo) {
  const caja = $('#mapa-detalle');

  caja.innerHTML = cargando('Cargando la información del lugar…');

  const q = new URLSearchParams({
    nivel: M.nivel,
    codigo
  });

  if (M.anio) q.set('anio', M.anio);

  const r = await fetch(`/api/territorio/detalle?${q}`);

  if (!r.ok) {
    caja.innerHTML = error('No hay información para ese lugar.');
    return;
  }

  const d = await r.json();
  const hist = d.historico;

  caja.innerHTML = `
    <p class="sobre">
      ${d.nivel === 'departamento'
        ? 'Departamento'
        : `Municipio · ${esc(d.departamento)}`}
    </p>
    <h2>${esc(d.nombre)}</h2>
    <p class="nota">${esc(d.periodo)}</p>

    ${d.indicadores
      ? kpis(d.indicadores)
      : '<div class="msg adv">Sin registros en este periodo.</div>'}

    <h3>Energía mensual (MWh)</h3>
    ${serie(d.serie)}

    <p class="nota">
      Con registros desde ${per(hist.desde)} hasta ${per(hist.hasta)}:
      ${fmt(hist.registros)} registros de ${fmt(hist.localidades)} localidades.
    </p>

    <h3>Localidades en el periodo</h3>

    ${tabla(
      d.localidades,
      [
        ['localidad', 'Localidad'],
        ...(d.nivel === 'departamento'
          ? [['municipio', 'Municipio']]
          : []),
        ['energia_mwh', 'MWh'],
        ['horas_promedio', 'h/día', v => v == null ? '—' : fmt(v, 1)]
      ],
      ['energia_mwh', 'horas_promedio'],
      1
    )}

    <div class="acciones">
      <button class="btn" id="ver-registros">Ver todos sus registros</button>
      <button class="btn sec" id="quitar-sel">Ver todo el país</button>
    </div>
  `;

  $('#ver-registros').onclick = () => {
    limpiarFiltros(false);

    if (d.nivel === 'departamento') {
      $('#b-dep').value = d.codigo;
      llenarMunicipios();
    } else {
      $('#b-dep').value = Math.floor(d.codigo / 1000);
      llenarMunicipios();
      $('#b-mun').value = d.codigo;
      llenarLocalidades();
    }

    if (M.anio) $('#b-anio').value = M.anio;

    buscar(1);

    $('#buscador').scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
  };

  $('#quitar-sel').onclick = () => {
    M.sel = null;
    marcarSeleccion();
    pintarTotal();

    if (window.ZNIPortal?.limpiarFiltrosDesdeMapa) {
      window.ZNIPortal.limpiarFiltrosDesdeMapa();
    }
  };
}

function serie(s) {
  if (!s.length) return '<p class="nota">Sin datos.</p>';

  const W = 460;
  const H = 130;
  const pi = 50;
  const pd = 6;
  const ps = 8;
  const pb = 20;

  const max = Math.max(...s.map(x => x.energia_mwh), 1);

  const x = i =>
    pi + (W - pi - pd) * (
      s.length === 1 ? .5 : i / (s.length - 1)
    );

  const y = v =>
    ps + (H - ps - pb) * (1 - v / max);

  const pts = s.map((p, i) =>
    `${x(i).toFixed(1)},${y(p.energia_mwh).toFixed(1)}`
  );

  const anios = s.map((p, i) => [p.periodo, i])
    .filter(([p]) => p % 100 === 1);

  return `
    <svg class="svg-graf serie" viewBox="0 0 ${W} ${H}" role="img" aria-label="Energía mensual">
      <line class="eje" x1="${pi}" x2="${W - pd}" y1="${y(0)}" y2="${y(0)}"/>
      <text x="${pi - 4}" y="${y(max) + 4}" text-anchor="end">
        ${fmt(max, max < 10 ? 1 : 0)}
      </text>
      <text x="${pi - 4}" y="${y(0) + 4}" text-anchor="end">0</text>
      <path class="area" d="M${x(0)},${y(0)}L${pts.join('L')}L${x(s.length - 1)},${y(0)}Z"/>
      <polyline class="linea" points="${pts.join(' ')}"/>

      ${anios.map(([p, i]) =>
        `<text x="${Math.min(x(i), W - pd - 12)}" y="${H - 5}" text-anchor="middle">${Math.floor(p / 100)}</text>`
      ).join('')}

      ${s.map((p, i) =>
        `<rect x="${x(i) - (W - pi) / s.length / 2}"
          y="${ps}"
          width="${(W - pi) / s.length}"
          height="${H - ps - pb}"
          fill="transparent"
          data-tip="${esc(`<b>${per(p.periodo)}</b><br>${fmt(p.energia_mwh, 1)} MWh`)}"/>`
      ).join('')}
    </svg>
  `;
}

// ------------------------------------------------------------
// Buscador de registros territoriales
// ------------------------------------------------------------

function prepararBuscador() {
  const deps = M.opciones.departamentos;

  $('#b-dep').innerHTML =
    '<option value="">Todos los departamentos</option>' +
    deps.map(d =>
      `<option value="${d.codigo}">${esc(d.nombre)}</option>`
    ).join('');

  $('#b-anio').innerHTML =
    '<option value="">Todos los años</option>' +
    M.opciones.anios.slice().reverse().map(a =>
      `<option>${a}</option>`
    ).join('');

  $('#b-mes').innerHTML =
    '<option value="">Todos los meses</option>' +
    MESES.map((m, i) =>
      `<option value="${i + 1}">${m[0].toUpperCase() + m.slice(1)}</option>`
    ).join('');

  const sug = new Set();

  deps.forEach(d => {
    sug.add(d.nombre);

    d.municipios.forEach(m => {
      sug.add(m.nombre);
      m.localidades.forEach(l => sug.add(l));
    });
  });

  $('#b-sugerencias').innerHTML =
    [...sug].sort((a, b) => a.localeCompare(b, 'es'))
      .map(s => `<option value="${esc(s)}">`)
      .join('');

  llenarMunicipios();

  $('#b-dep').onchange = () => {
    llenarMunicipios();
    buscar(1);
  };

  $('#b-mun').onchange = () => {
    llenarLocalidades();
    buscar(1);
  };

  ['#b-loc', '#b-anio', '#b-mes', '#b-orden'].forEach(s => {
    $(s).onchange = () => buscar(1);
  });

  $('#b-form').onsubmit = e => {
    e.preventDefault();
    buscar(1);
  };

  $('#b-limpiar').onclick = () => {
    limpiarFiltros(true);
    buscar(1);
  };
}

function llenarMunicipios() {
  const d = M.opciones.departamentos.find(
    x => x.codigo === +$('#b-dep').value
  );

  const mpios = d
    ? d.municipios
    : M.opciones.departamentos.flatMap(x => x.municipios);

  $('#b-mun').innerHTML =
    '<option value="">Todos los municipios</option>' +
    mpios.slice()
      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
      .map(m => `<option value="${m.codigo}">${esc(m.nombre)}</option>`)
      .join('');

  llenarLocalidades();
}

function llenarLocalidades() {
  const dep = +$('#b-dep').value;
  const mun = +$('#b-mun').value;

  const mpios = M.opciones.departamentos
    .filter(d => !dep || d.codigo === dep)
    .flatMap(d => d.municipios)
    .filter(m => !mun || m.codigo === mun);

  const locs = [...new Set(
    mpios.flatMap(m => m.localidades)
  )].sort((a, b) => a.localeCompare(b, 'es'));

  $('#b-loc').innerHTML =
    '<option value="">Todas las localidades</option>' +
    locs.map(l => `<option>${esc(l)}</option>`).join('');
}

function limpiarFiltros(todo) {
  $('#b-q').value = '';
  $('#b-dep').value = '';

  llenarMunicipios();

  $('#b-anio').value = '';
  $('#b-mes').value = '';

  if (todo) $('#b-orden').value = 'reciente';
}

function filtros() {
  const q = new URLSearchParams();

  [
    ['q', '#b-q'],
    ['departamento', '#b-dep'],
    ['municipio', '#b-mun'],
    ['localidad', '#b-loc'],
    ['anio', '#b-anio'],
    ['mes', '#b-mes']
  ].forEach(([k, s]) => {
    const v = $(s).value.trim();
    if (v) q.set(k, v);
  });

  return q;
}

async function buscar(pagina) {
  const caja = $('#b-resultados');
  const q = filtros();

  $('#b-csv').href = `/api/territorio/registros.csv?${q}`;

  q.set('pagina', pagina);
  q.set('orden', $('#b-orden').value);
  q.set('por_pagina', 50);

  caja.innerHTML = cargando('Buscando registros…');

  let r;

  try {
    r = await fetch(`/api/territorio/registros?${q}`).then(x => x.json());
  } catch {
    caja.innerHTML = error('No se pudo hacer la búsqueda.');
    return;
  }

  if (!r.total) {
    caja.innerHTML =
      '<div class="msg adv">No hay registros con esos filtros. Pruebe con menos palabras o quite algún filtro.</div>';

    $('#b-csv').hidden = true;
    return;
  }

  $('#b-csv').hidden = false;

  const s = r.resumen;

  const lugar = r.departamentos_encontrados.length <= 3
    ? r.departamentos_encontrados.join(', ')
    : `${s.departamentos} departamentos`;

  caja.innerHTML = `
    <p class="resumen-busqueda">
      <b>${fmt(r.total)} registros</b> de ${fmt(s.localidades)} localidades en ${esc(lugar)},
      de ${per(s.desde)} a ${per(s.hasta)}.
    </p>

    <div class="kpis">
      <div class="kpi">
        <b>${fmt(s.energia_mwh)}</b>
        <span>MWh en total</span>
      </div>
      <div class="kpi">
        <b>${s.horas_promedio == null ? '—' : fmt(s.horas_promedio, 1)}</b>
        <span>horas de servicio al día (promedio)</span>
      </div>
      <div class="kpi">
        <b>${fmt(s.municipios)}</b>
        <span>${s.municipios === 1 ? 'municipio' : 'municipios'}</span>
      </div>
      <div class="kpi">
        <b>${fmt(s.meses_sin_energia)}</b>
        <span>${s.meses_sin_energia === 1 ? 'mes reportado' : 'meses reportados'} sin energía</span>
      </div>
    </div>

    ${tabla(
      r.registros,
      [
        ['departamento', 'Departamento'],
        ['municipio', 'Municipio'],
        ['localidad', 'Localidad'],
        ['anio', 'Periodo', (v, f) => `${MESES[f.mes - 1]} ${v}`],
        ['energia_kwh', 'Energía (kWh)', v => v == null ? '—' : fmt(v)],
        ['horas_dia', 'Horas/día', v => v == null ? '—' : fmt(v, 1)],
        ['factor_carga', 'Factor de carga', v => v == null ? '—' : fmt(v, 2)]
      ],
      ['energia_kwh', 'horas_dia', 'factor_carga']
    )}

    <div class="paginador">
      <button class="btn sec chico" id="b-ant" ${r.pagina <= 1 ? 'disabled' : ''}>
        ← Anterior
      </button>
      <span>Página ${r.pagina} de ${r.paginas}</span>
      <button class="btn sec chico" id="b-sig" ${r.pagina >= r.paginas ? 'disabled' : ''}>
        Siguiente →
      </button>
    </div>
  `;

  $('#b-ant').onclick = () => buscar(r.pagina - 1);
  $('#b-sig').onclick = () => buscar(r.pagina + 1);
}

// ------------------------------------------------------------
// Controles del mapa
// ------------------------------------------------------------

$('#mapa-svg').addEventListener('click', e => {
  const p = e.target.closest('[data-codigo]');
  if (p) elegir(p.dataset.codigo);
});

$('#mapa-svg').addEventListener('keydown', e => {
  const p = e.target.closest('[data-codigo]');

  if (p && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    elegir(p.dataset.codigo);
  }
});

$('#mapa-indicador').onchange = e => {
  M.indicador = e.target.value;
  dibujar();
};

$('#mapa-anio').onchange = e => {
  M.anio = e.target.value;
  pintarResumen();
};

document.querySelectorAll('#mapa-nivel button').forEach(b => {
  b.onclick = () => {
    if (M.nivel === b.dataset.nivel) return;

    M.nivel = b.dataset.nivel;

    document.querySelectorAll('#mapa-nivel button').forEach(x =>
      x.setAttribute('aria-pressed', x === b)
    );

    M.sel = null;
    pintarResumen();
  };
});

window.addEventListener('scroll', () => {
  $('#tip').style.display = 'none';
}, {passive: true});

// ------------------------------------------------------------
// API pública para sincronizar los filtros del portal con el mapa
// ------------------------------------------------------------

window.ZNIMapa = {
  async sincronizar(departamento = '', municipio = '') {
    if (!M.iniciado || !M.geo || !M.resumen) return;

    if (municipio) {
      M.nivel = 'municipio';
      M.sel = {
        nivel: 'municipio',
        codigo: Number(municipio)
      };
    } else if (departamento) {
      M.nivel = 'departamento';
      M.sel = {
        nivel: 'departamento',
        codigo: Number(departamento)
      };
    } else {
      M.nivel = 'departamento';
      M.sel = null;
    }

    document.querySelectorAll('#mapa-nivel button').forEach(b => {
      b.setAttribute(
        'aria-pressed',
        String(b.dataset.nivel === M.nivel)
      );
    });

    await pintarResumen();
  },

  limpiar() {
    return this.sincronizar('', '');
  }
};

// Iniciar mapa y sincronizar selección inicial del portal.
cargarMapa().then(() => {
  const dep = document.querySelector('#departamento')?.value || '';
  const mun = document.querySelector('#municipio')?.value || '';

  if (dep || mun) {
    window.ZNIMapa.sincronizar(dep, mun);
  }
});

})();