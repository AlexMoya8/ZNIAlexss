// Ingreso y registro de administradores.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const mensaje = (id, texto, tipo = 'err') => { $(id).innerHTML = texto ? `<div class="msg ${tipo}">${esc(texto)}</div>` : ''; };

// Solo se vuelve a páginas del propio sitio
const pedido = new URLSearchParams(location.search).get('volver') || 'sistema.html#modelo';
const destino = /^[a-z]+\.html(#[a-z]+)?$/.test(pedido) ? pedido : 'sistema.html#modelo';

function mostrar(p) {
  document.querySelectorAll('.pestanas button').forEach(b => b.setAttribute('aria-selected', b.dataset.p === p));
  $('#f-ingresar').hidden = p !== 'ingresar';
  $('#f-registro').hidden = p !== 'registro';
}
document.querySelectorAll('.pestanas button').forEach(b => b.onclick = () => mostrar(b.dataset.p));

async function enviar(url, form, idMensaje) {
  const boton = form.querySelector('button[type=submit]');
  boton.disabled = true; mensaje(idMensaje, '');
  try {
    const r = await fetch(url, {method: 'POST', body: new FormData(form)});
    const j = await r.json().catch(() => ({}));
    if (r.ok) { mensaje(idMensaje, 'Listo, entrando…', 'ok'); location.href = destino; return; }
    mensaje(idMensaje, j.detail || j.detalle || 'No se pudo completar la operación.');
  } catch { mensaje(idMensaje, 'No se pudo conectar con el servidor.'); }
  boton.disabled = false;
}

$('#f-ingresar').onsubmit = e => { e.preventDefault(); enviar('/api/auth/ingresar', e.target, '#m-ingresar'); };
$('#f-registro').onsubmit = e => {
  e.preventDefault();
  if ($('#r-contrasena').value !== $('#r-confirmar').value) { mensaje('#m-registro', 'Las contraseñas no coinciden.'); return; }
  enviar('/api/auth/registro', e.target, '#m-registro');
};

// Si ya hay sesión, ir directo; si aún no existe ningún administrador, abrir el registro
fetch('/api/auth/yo').then(r => r.json()).then(j => {
  if (j.usuario) location.href = destino;
  else if (!j.hay_administradores) mostrar('registro');
}).catch(() => {});
