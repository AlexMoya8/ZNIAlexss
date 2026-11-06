"""Cuentas de administrador, sesiones, historial de inicios de sesión y control de acceso.

Solo los administradores pueden reentrenar el modelo, decidir qué versión queda activa y administrar las
cuentas. El mapa y el análisis exploratorio de documentos son públicos. La validación, las predicciones y las herramientas del modelo requieren una sesión administrativa.

- Base de datos: SQLite en datos/seguridad/zni.db (viene con Python, no hay que instalar nada).
  Tablas «usuarios» e «inicios_sesion». Si existe un usuarios.json de la versión anterior, se importa solo.
- Contraseñas: PBKDF2-HMAC-SHA256 con sal aleatoria.
- Sesión: token firmado con HMAC en una cookie HttpOnly y SameSite=Lax, válido 8 horas. La firma incluye
  parte del hash de la contraseña, así que cambiar la contraseña o desactivar la cuenta cierra sus sesiones.
- Registro público: exige un código que se genera la primera vez y se muestra en la consola (o se fija con
  la variable de entorno ZNI_CODIGO_REGISTRO). Un administrador con sesión puede crear cuentas sin código.
- Fuerza bruta: tras 5 intentos fallidos en 10 minutos desde una misma dirección, se bloquea temporalmente.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from fastapi import HTTPException, Request

from .config import DIR_SEGURIDAD

COOKIE = "zni_sesion"
DURACION_SESION = 8 * 3600
ITERACIONES = 200_000
MAX_FALLOS, VENTANA_FALLOS = 5, 600
PATRON_USUARIO = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")
EVENTOS = ("registro", "ingreso", "fallo", "bloqueo", "salida")

_candado = threading.Lock()
_fallos: dict[str, list[float]] = {}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'administrador',
    sal TEXT NOT NULL,
    hash TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL,
    creado_por TEXT,
    actualizado TEXT,
    ultimo_ingreso TEXT
);
CREATE TABLE IF NOT EXISTS inicios_sesion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    usuario TEXT NOT NULL,
    evento TEXT NOT NULL,
    ip TEXT,
    navegador TEXT,
    detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_inicios_fecha ON inicios_sesion(fecha);
"""


def _archivo(nombre):
    DIR_SEGURIDAD.mkdir(parents=True, exist_ok=True)
    return DIR_SEGURIDAD / nombre


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def _bd():
    """Conexión a la base de datos; confirma los cambios al salir sin errores."""
    con = sqlite3.connect(_archivo("zni.db"), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(ESQUEMA)
        _importar_json(con)
        yield con
        con.commit()
    finally:
        con.close()


def _importar_json(con):
    """Pasa a la base de datos las cuentas guardadas en usuarios.json por la versión anterior."""
    ruta = DIR_SEGURIDAD / "usuarios.json"
    if not ruta.exists():
        return
    for u in json.loads(ruta.read_text(encoding="utf-8")).get("usuarios", []):
        con.execute("INSERT OR IGNORE INTO usuarios (usuario, nombre, rol, sal, hash, activo, creado) VALUES (?,?,?,?,?,?,?)",
                    (u["usuario"], u["nombre"], u.get("rol", "administrador"), u["sal"], u["hash"],
                     int(u.get("activo", True)), u.get("creado", _ahora())))
    con.commit()
    ruta.rename(ruta.with_suffix(".json.importado"))


def _secreto() -> bytes:
    ruta = _archivo("secreto.key")
    if not ruta.exists():
        ruta.write_text(secrets.token_hex(32), encoding="utf-8")
    return bytes.fromhex(ruta.read_text(encoding="utf-8").strip())


def codigo_registro() -> str:
    if os.environ.get("ZNI_CODIGO_REGISTRO"):
        return os.environ["ZNI_CODIGO_REGISTRO"]
    ruta = _archivo("codigo_registro.txt")
    if not ruta.exists():
        ruta.write_text("ZNI-" + secrets.token_hex(3).upper(), encoding="utf-8")
    return ruta.read_text(encoding="utf-8").strip()


def _hash(contrasena: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal, ITERACIONES).hex()


def _validar_usuario(usuario):
    if not PATRON_USUARIO.match(usuario):
        raise HTTPException(400, "El usuario debe tener de 3 a 30 caracteres: letras, números, punto, guion o guion bajo.")


def _validar_contrasena(contrasena):
    if len(contrasena) < 8 or not re.search(r"[A-Za-z]", contrasena) or not re.search(r"\d", contrasena):
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres, con letras y números.")


def anotar(usuario, evento, ip="", navegador="", detalle=""):
    """Guarda un evento en el historial de inicios de sesión."""
    with _bd() as con:
        con.execute("INSERT INTO inicios_sesion (fecha, usuario, evento, ip, navegador, detalle) VALUES (?,?,?,?,?,?)",
                    (_ahora(), (usuario or "")[:60], evento, ip, (navegador or "")[:200], detalle))


def _buscar(con, usuario):
    return con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()


def publico(u):
    return {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"]}


def ficha(u):
    """Datos de una cuenta para la pantalla de administración (nunca la sal ni el hash)."""
    return {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"], "activo": bool(u["activo"]),
            "creado": u["creado"], "creado_por": u["creado_por"], "actualizado": u["actualizado"],
            "ultimo_ingreso": u["ultimo_ingreso"]}


def hay_administradores() -> bool:
    with _bd() as con:
        return con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0


# ---------------------------------------------------------------- crear (registro público o por un administrador)

def crear_usuario(usuario: str, nombre: str, contrasena: str, creado_por: str | None = None) -> dict:
    usuario = usuario.strip().lower()
    _validar_usuario(usuario)
    _validar_contrasena(contrasena)
    sal = secrets.token_bytes(16)
    with _candado, _bd() as con:
        if _buscar(con, usuario):
            raise HTTPException(409, "Ese usuario ya existe.")
        con.execute("INSERT INTO usuarios (usuario, nombre, rol, sal, hash, activo, creado, creado_por) "
                    "VALUES (?,?,?,?,?,1,?,?)",
                    (usuario, nombre.strip()[:80] or usuario, "administrador", sal.hex(), _hash(contrasena, sal),
                     _ahora(), creado_por))
        return ficha(_buscar(con, usuario))


def registrar(usuario: str, nombre: str, contrasena: str, codigo: str, ip="", navegador="") -> dict:
    if not hmac.compare_digest(codigo.strip().upper(), codigo_registro().upper()):
        anotar(usuario.strip().lower(), "fallo", ip, navegador, "Código de registro inválido")
        raise HTTPException(403, "El código de registro no es válido. Pídalo a un administrador del proyecto.")
    u = crear_usuario(usuario, nombre, contrasena)
    anotar(u["usuario"], "registro", ip, navegador, "Cuenta creada con el código de registro")
    with _bd() as con:
        con.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE usuario = ?", (_ahora(), u["usuario"]))
    return publico(u)


# ---------------------------------------------------------------- leer

def listar_usuarios() -> list[dict]:
    with _bd() as con:
        return [ficha(u) for u in con.execute("SELECT * FROM usuarios ORDER BY creado")]


def historial(usuario: str = "", evento: str = "", limite: int = 100) -> dict:
    sql, args = "SELECT * FROM inicios_sesion WHERE 1=1", []
    if usuario:
        sql += " AND usuario = ?"
        args.append(usuario.strip().lower())
    if evento:
        sql += " AND evento = ?"
        args.append(evento)
    with _bd() as con:
        total = con.execute(sql.replace("SELECT *", "SELECT COUNT(*)"), args).fetchone()[0]
        filas = con.execute(sql + " ORDER BY id DESC LIMIT ?", args + [max(1, min(int(limite), 500))]).fetchall()
    return {"total": total, "eventos": [dict(f) for f in filas]}


# ---------------------------------------------------------------- actualizar y eliminar

def _activos(con, sin=None):
    return con.execute("SELECT COUNT(*) FROM usuarios WHERE activo = 1 AND usuario != ?", (sin or "",)).fetchone()[0]


def actualizar_usuario(usuario: str, quien: str, nombre: str | None = None, contrasena: str | None = None,
                       activo: bool | None = None) -> dict:
    usuario = usuario.strip().lower()
    with _candado, _bd() as con:
        u = _buscar(con, usuario)
        if not u:
            raise HTTPException(404, "Esa cuenta no existe.")
        cambios, args = [], []
        if nombre is not None and nombre.strip():
            cambios.append("nombre = ?"); args.append(nombre.strip()[:80])
        if contrasena:
            _validar_contrasena(contrasena)
            sal = secrets.token_bytes(16)
            cambios += ["sal = ?", "hash = ?"]; args += [sal.hex(), _hash(contrasena, sal)]
        if activo is not None and bool(activo) != bool(u["activo"]):
            if not activo and usuario == quien:
                raise HTTPException(400, "No puede desactivar su propia cuenta.")
            if not activo and _activos(con, usuario) == 0:
                raise HTTPException(400, "Debe quedar al menos un administrador activo.")
            cambios.append("activo = ?"); args.append(int(bool(activo)))
        if not cambios:
            raise HTTPException(400, "No hay cambios para guardar.")
        cambios.append("actualizado = ?"); args.append(_ahora())
        con.execute(f"UPDATE usuarios SET {', '.join(cambios)} WHERE usuario = ?", args + [usuario])
        return ficha(_buscar(con, usuario))


def eliminar_usuario(usuario: str, quien: str):
    usuario = usuario.strip().lower()
    with _candado, _bd() as con:
        if not _buscar(con, usuario):
            raise HTTPException(404, "Esa cuenta no existe.")
        if usuario == quien:
            raise HTTPException(400, "No puede eliminar su propia cuenta.")
        if _activos(con, usuario) == 0:
            raise HTTPException(400, "Debe quedar al menos un administrador activo.")
        con.execute("DELETE FROM usuarios WHERE usuario = ?", (usuario,))


# ---------------------------------------------------------------- ingreso y sesión

def _registrar_fallo(ip):
    ahora = time.time()
    with _candado:
        _fallos[ip] = [t for t in _fallos.get(ip, []) if ahora - t < VENTANA_FALLOS] + [ahora]


def _bloqueado(ip):
    ahora = time.time()
    with _candado:
        recientes = [t for t in _fallos.get(ip, []) if ahora - t < VENTANA_FALLOS]
        _fallos[ip] = recientes
        return len(recientes) >= MAX_FALLOS


def autenticar(usuario: str, contrasena: str, ip: str, navegador: str = "") -> dict:
    usuario = usuario.strip().lower()
    if _bloqueado(ip):
        anotar(usuario, "bloqueo", ip, navegador, "Demasiados intentos fallidos")
        raise HTTPException(429, "Demasiados intentos fallidos. Espere 10 minutos e intente de nuevo.")
    with _bd() as con:
        u = _buscar(con, usuario)
    u = u if u and u["activo"] else None
    esperado = u["hash"] if u else _hash("x", b"0" * 16)  # mismo costo exista o no el usuario
    calculado = _hash(contrasena, bytes.fromhex(u["sal"])) if u else _hash(contrasena, b"1" * 16)
    if not u or not hmac.compare_digest(esperado, calculado):
        _registrar_fallo(ip)
        anotar(usuario, "fallo", ip, navegador, "Usuario o contraseña incorrectos")
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    with _candado:
        _fallos.pop(ip, None)
    with _bd() as con:
        con.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE usuario = ?", (_ahora(), usuario))
    anotar(usuario, "ingreso", ip, navegador)
    return publico(u)


def _firma(usuario, vence, sello):
    return hmac.new(_secreto(), f"{usuario}|{vence}|{sello}".encode(), hashlib.sha256).hexdigest()


def crear_token(usuario: str) -> str:
    with _bd() as con:
        u = _buscar(con, usuario)
    vence = int(time.time()) + DURACION_SESION
    firma = _firma(usuario, vence, u["hash"][:16])
    return base64.urlsafe_b64encode(f"{usuario}|{vence}|{firma}".encode()).decode()


def usuario_de_token(token: str | None):
    if not token:
        return None
    try:
        usuario, vence, firma = base64.urlsafe_b64decode(token.encode()).decode().split("|")
        vence = int(vence)
    except Exception:
        return None
    if vence < time.time():
        return None
    with _bd() as con:
        u = _buscar(con, usuario)
    if not u or not u["activo"] or not hmac.compare_digest(firma, _firma(usuario, vence, u["hash"][:16])):
        return None
    return publico(u)


def usuario_actual(request: Request):
    return usuario_de_token(request.cookies.get(COOKIE))


def requiere_admin(request: Request) -> dict:
    """Dependencia de FastAPI para las operaciones que solo pueden hacer los administradores."""
    u = usuario_actual(request)
    if u is None:
        raise HTTPException(401, "Debe ingresar como administrador para hacer esta operación.")
    if u["rol"] != "administrador":
        raise HTTPException(403, "Su cuenta no tiene permiso para hacer esta operación.")
    return u
