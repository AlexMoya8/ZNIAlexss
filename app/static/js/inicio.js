// Página de presentación: muestra las métricas reales del modelo activo y el estado de la sesión.
const $ = s => document.querySelector(s);
const fmt = (v, d = 0) => v.toLocaleString('es-CO', {maximumFractionDigits: d});
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

// Pronóstico de febrero de 2026 generado por el modelo v1 con pruebas/escenarios/09_pronostico_2026_02.csv (MWh).
const PRONOSTICO = [
  ['San Andrés', 15593.7, 14307.3, 17244.1], ['Leticia', 3849.1, 3531.6, 4256.5], ['Puerto Carreño', 3330.4, 3055.7, 3682.9],
  ['Inírida', 2282.0, 2093.8, 2523.5], ['Mitú', 1328.3, 1218.7, 1468.8],
];
const max = Math.max(...PRONOSTICO.map(p => p[3]));
$('#vp-barras').innerHTML = PRONOSTICO.map(([n, v, lo, hi]) => `
  <div class="vp-fila" title="${n}: ${fmt(v, 1)} MWh (80%: ${fmt(lo)} a ${fmt(hi)})">
    <span class="nombre">${n}</span>
    <span class="vp-pista"><span class="vp-barra" style="width:${v / max * 100}%"></span>
      <span class="vp-int" style="left:${lo / max * 100}%;width:${(hi - lo) / max * 100}%"></span></span>
    <span class="valor">${fmt(v)}</span></div>`).join('');

fetch('/api/modelo').then(r => r.ok ? r.json() : null).then(m => {
  if (!m) return;
  const v = m.metricas_validacion;
  $('#h-error').textContent = `${fmt(v.mediana_error_relativo_pct)}%`;
  $('#h-mejora').textContent = `${fmt(v.mejora_vs_ingenuo_pct)}%`;
  $('#m-version').textContent = m.version;
  $('#m-prueba').textContent = m.estrategia_validacion.prueba;
  $('#m-err').textContent = `${fmt(v.mediana_error_relativo_pct, 1)}%`;
  $('#m-mej').textContent = `${fmt(v.mejora_vs_ingenuo_pct, 1)}%`;
  $('#m-wape').textContent = `${fmt(v.wape_pct, 1)}%`;
  $('#m-reg').textContent = fmt(m.registros);
  $('#m-algoritmo').textContent = m.algoritmo === 'HistGradientBoostingRegressor' ? 'Gradient Boosting por histogramas' : m.algoritmo;
}).catch(() => {});

fetch('/api/auth/yo').then(r => r.json()).then(j => {
  if (j.usuario) $('#cab-cuenta').innerHTML = `<span class="nota">Hola, ${esc(j.usuario.nombre)}</span>`;
}).catch(() => {});

$('#abrir-menu').onclick = () => {
  const abierto = $('#menu').classList.toggle('abierto');
  $('#abrir-menu').setAttribute('aria-expanded', abierto);
};
document.querySelectorAll('#menu a').forEach(a => a.onclick = () => $('#menu').classList.remove('abierto'));
