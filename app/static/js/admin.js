// Administración de cuentas (crear, ver, editar, desactivar, eliminar) e historial de inicios de sesión.
// Usa las funciones comunes de app.js ($, esc, tabla, cargando, error) y la API /api/admin/...
const NOMBRE_EVENTO = {ingreso: ['Ingreso', 'ok'], salida: ['Salida', ''], fallo: ['Intento fallido', 'err'],
  bloqueo: ['Bloqueo', 'err'], registro: ['Registro', 'adv']};
const A = {usuarios: [], yo: null, editando: null, confirmando: null};
const fecha = s => s ? new Date(s).toLocaleString('es-CO', {dateStyle: 'medium', timeStyle: 'short'}) : '—';
const avisoAdmin = (texto, tipo = 'ok') => { $('#adm-msg').innerHTML = texto ? `<div class="msg ${tipo}">${esc(texto)}</div>` : ''; };

async function pedirAdmin(url, opciones = {}) {
  const r = await fetch(url, opciones);
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { mostrarBloqueoAdmin(); throw new Error('sin sesión'); }
  if (!r.ok) throw new Error(j.detail || j.detalle || 'No se pudo completar la operación.');
  return j;
}

function mostrarBloqueoAdmin() {
  $('#admin-bloqueado').hidden = false;
  $('#admin-libre').hidden = true;
}

async function cargarAdmin() {
  let j;
  try { j = await pedirAdmin('/api/admin/usuarios'); } catch { return; }
  $('#admin-bloqueado').hidden = true;
  $('#admin-libre').hidden = false;
  A.usuarios = j.usuarios; A.yo = j.yo;
  pintarUsuarios();
  const sel = $('#adm-f-usuario'), actual = sel.value;
  sel.innerHTML = '<option value="">Todas</option>' + A.usuarios.map(u => `<option value="${esc(u.usuario)}">${esc(u.nombre)} (${esc(u.usuario)})</option>`).join('');
  sel.value = A.usuarios.some(u => u.usuario === actual) ? actual : '';
  cargarSesiones();
}

function pintarUsuarios() {
  const filas = A.usuarios.map(u => {
    const yo = u.usuario === A.yo;
    const acciones = A.confirmando === u.usuario
      ? `<span class="nota">¿Eliminar esta cuenta?</span><button class="btn peligro chico" data-acc="eliminar-si" data-u="${esc(u.usuario)}">Sí, eliminar</button>
         <button class="btn sec chico" data-acc="eliminar-no">No</button>`
      : `<button class="btn sec chico" data-acc="editar" data-u="${esc(u.usuario)}">Editar</button>
         ${yo ? '' : `<button class="btn sec chico" data-acc="activo" data-u="${esc(u.usuario)}">${u.activo ? 'Desactivar' : 'Activar'}</button>
         <button class="btn sec peligro chico" data-acc="eliminar" data-u="${esc(u.usuario)}">Eliminar</button>`}`;
    let html = `<tr><td><b>${esc(u.nombre)}</b>${yo ? ' <span class="etiqueta-admin">Usted</span>' : ''}<br><span class="nota">${esc(u.usuario)}</span></td>
      <td><span class="estado ${u.activo ? 'ok' : 'err'}">${u.activo ? 'Activa' : 'Desactivada'}</span></td>
      <td>${fecha(u.creado)}${u.creado_por ? `<br><span class="nota">por ${esc(u.creado_por)}</span>` : ''}</td>
      <td>${fecha(u.ultimo_ingreso)}</td>
      <td><div class="acciones-fila">${acciones}</div></td></tr>`;
    if (A.editando === u.usuario) html += `<tr class="fila-edicion"><td colspan="5"><form data-u="${esc(u.usuario)}" autocomplete="off">
      <label>Nombre<input name="nombre" value="${esc(u.nombre)}" maxlength="80"></label>
      <label>Nueva contraseña (opcional)<input name="contrasena" type="password" minlength="8" autocomplete="new-password" placeholder="Dejar vacío para no cambiarla"></label>
      <div class="acciones" style="margin:0"><button class="btn chico" type="submit">Guardar</button><button class="btn sec chico" type="button" data-acc="cancelar">Cancelar</button></div>
    </form></td></tr>`;
    return html;
  }).join('');
  $('#adm-usuarios').innerHTML = `<div class="tabla"><table><thead><tr><th>Cuenta</th><th>Estado</th><th>Creada</th><th>Último ingreso</th><th></th></tr></thead>
    <tbody>${filas}</tbody></table></div>`;
  const form = $('#adm-usuarios form');
  if (form) { form.onsubmit = guardarEdicion; form.querySelector('input').focus(); }
}

async function guardarEdicion(e) {
  e.preventDefault();
  const datos = new FormData(e.target), usuario = e.target.dataset.u;
  if (!datos.get('contrasena')) datos.delete('contrasena');
  try {
    await pedirAdmin(`/api/admin/usuarios/${encodeURIComponent(usuario)}`, {method: 'PUT', body: datos});
    A.editando = null;
    avisoAdmin(datos.has('contrasena') && usuario !== A.yo ? `Cuenta «${usuario}» actualizada. Sus sesiones abiertas se cerraron por el cambio de contraseña.` : `Cuenta «${usuario}» actualizada.`);
    await cargarAdmin();
  } catch (err) { if (err.message !== 'sin sesión') avisoAdmin(err.message, 'err'); }
}

$('#adm-usuarios').addEventListener('click', async e => {
  const b = e.target.closest('button[data-acc]');
  if (!b) return;
  const u = b.dataset.u, acc = b.dataset.acc;
  avisoAdmin('');
  try {
    if (acc === 'editar') { A.editando = A.editando === u ? null : u; A.confirmando = null; pintarUsuarios(); }
    else if (acc === 'cancelar') { A.editando = null; pintarUsuarios(); }
    else if (acc === 'eliminar') { A.confirmando = u; A.editando = null; pintarUsuarios(); }
    else if (acc === 'eliminar-no') { A.confirmando = null; pintarUsuarios(); }
    else if (acc === 'eliminar-si') {
      await pedirAdmin(`/api/admin/usuarios/${encodeURIComponent(u)}`, {method: 'DELETE'});
      A.confirmando = null; avisoAdmin(`Cuenta «${u}» eliminada.`); await cargarAdmin();
    } else if (acc === 'activo') {
      const actual = A.usuarios.find(x => x.usuario === u);
      const datos = new FormData(); datos.set('activo', actual.activo ? 'false' : 'true');
      await pedirAdmin(`/api/admin/usuarios/${encodeURIComponent(u)}`, {method: 'PUT', body: datos});
      avisoAdmin(actual.activo ? `Cuenta «${u}» desactivada: ya no puede ingresar.` : `Cuenta «${u}» activada.`);
      await cargarAdmin();
    }
  } catch (err) { if (err.message !== 'sin sesión') avisoAdmin(err.message, 'err'); }
});

$('#adm-nueva-btn').onclick = () => { $('#adm-nueva').hidden = false; $('#adm-nueva input').focus(); };
$('#adm-nueva-cancelar').onclick = () => { $('#adm-nueva').reset(); $('#adm-nueva').hidden = true; };
$('#adm-nueva').onsubmit = async e => {
  e.preventDefault();
  const boton = e.target.querySelector('button[type=submit]');
  boton.disabled = true;
  try {
    const j = await pedirAdmin('/api/admin/usuarios', {method: 'POST', body: new FormData(e.target)});
    e.target.reset(); e.target.hidden = true;
    avisoAdmin(`Cuenta «${j.usuario.usuario}» creada. Ya puede ingresar con la contraseña que usted definió.`);
    await cargarAdmin();
  } catch (err) { if (err.message !== 'sin sesión') avisoAdmin(err.message, 'err'); }
  boton.disabled = false;
};

async function cargarSesiones() {
  const caja = $('#adm-sesiones');
  const q = new URLSearchParams({limite: 200});
  if ($('#adm-f-usuario').value) q.set('usuario', $('#adm-f-usuario').value);
  if ($('#adm-f-evento').value) q.set('evento', $('#adm-f-evento').value);
  caja.innerHTML = cargando('Cargando el historial…');
  let h;
  try { h = await pedirAdmin(`/api/admin/sesiones?${q}`); } catch (err) { caja.innerHTML = err.message === 'sin sesión' ? '' : error(err.message); return; }
  const navegador = ua => {
    if (!ua) return '—';
    const n = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Otro';
    const so = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : '';
    return `<span title="${esc(ua)}">${n}${so ? ' · ' + so : ''}</span>`;
  };
  caja.innerHTML = `<p class="nota">${h.total > h.eventos.length ? `Mostrando los ${h.eventos.length} más recientes de ${h.total}.` : `${h.total} ${h.total === 1 ? "evento" : "eventos"}.`}</p>` +
    tabla(h.eventos, [['fecha', 'Fecha', v => fecha(v)], ['usuario', 'Cuenta', v => esc(v)],
      ['evento', 'Evento', v => { const [t, c] = NOMBRE_EVENTO[v] || [v, '']; return `<span class="chip-evento ${c}">${esc(t)}</span>`; }],
      ['ip', 'Dirección', v => esc(v || '—')], ['navegador', 'Navegador', navegador], ['detalle', 'Detalle', v => esc(v || '')]]);
}
$('#adm-f-usuario').onchange = cargarSesiones;
$('#adm-f-evento').onchange = cargarSesiones;

// Si la página se abrió directamente en #admin (app.js ya navegó antes de cargar este archivo)
if (location.hash === '#admin') cargarAdmin();
