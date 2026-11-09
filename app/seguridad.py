"""Autenticación de los tres administradores de ZNI-APP sin base de datos.

Las credenciales se leen exclusivamente desde variables de entorno:
  ZNI_ADMIN_ALEXM_PASSWORD
  ZNI_ADMIN_ALEXC_PASSWORD
  ZNI_ADMIN_CARLOSS_PASSWORD
  ZNI_SECRET_KEY

No existe registro público ni CRUD de cuentas. Las sesiones se firman con HMAC y
se validan contra las credenciales actuales del entorno.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime

from fastapi import HTTPException, Request

COOKIE = "zni_sesion"
DURACION_SESION = 8 * 3600
ITERACIONES = 200_000
MAX_FALLOS, VENTANA_FALLOS = 5, 600
EVENTOS = ("registro", "ingreso", "fallo", "bloqueo", "salida")

_ADMINISTRADORES = {
    "alexm": {"nombre": "Alex M", "variable": "ZNI_ADMIN_ALEXM_PASSWORD"},
    "alexc": {"nombre": "Alex C", "variable": "ZNI_ADMIN_ALEXC_PASSWORD"},
    "carloss": {"nombre": "Carlos S", "variable": "ZNI_ADMIN_CARLOSS_PASSWORD"},
}
_candado = threading.Lock()
_fallos: dict[str, list[float]] = {}
_eventos: list[dict] = []


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def _secreto() -> bytes:
    valor = os.environ.get("ZNI_SECRET_KEY", "").strip()
    if len(valor) < 32:
        raise HTTPException(503, "El administrador del sistema debe configurar ZNI_SECRET_KEY en el servidor.")
    return valor.encode("utf-8")


def _password(usuario: str) -> str | None:
    cuenta = _ADMINISTRADORES.get(usuario.lower())
    if not cuenta:
        return None
    valor = os.environ.get(cuenta["variable"], "")
    return valor if valor else None


def _hash(contrasena: str, usuario: str) -> str:
    sal = hashlib.sha256(("ZNI-APP:" + usuario.lower()).encode()).digest()[:16]
    return hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, ITERACIONES).hex()


def _validar_contrasena(contrasena):
    if len(contrasena) < 10:
        raise HTTPException(400, "La contraseña debe tener al menos 10 caracteres.")


def _datos_usuario(usuario):
    cuenta = _ADMINISTRADORES[usuario.lower()]
    return {"usuario": usuario.lower(), "nombre": cuenta["nombre"], "rol": "administrador"}


def publico(u):
    return {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"]}


def ficha(u):
    return {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"],
            "activo": True, "creado": "Configurado en Render", "creado_por": "Sistema",
            "actualizado": None, "ultimo_ingreso": None}


def anotar(usuario, evento, ip="", navegador="", detalle=""):
    """Mantiene un historial temporal en memoria (se reinicia al reiniciar el servidor)."""
    fila = {"id": len(_eventos) + 1, "fecha": _ahora(), "usuario": (usuario or "")[:60],
            "evento": evento, "ip": (ip or "")[:100], "navegador": (navegador or "")[:200],
            "detalle": detalle}
    with _candado:
        _eventos.append(fila)
        del _eventos[:-500]


def hay_administradores() -> bool:
    return all(_password(u) for u in _ADMINISTRADORES)


def codigo_registro() -> str:
    # Se conserva por compatibilidad con el arranque existente; el registro está deshabilitado.
    return "DESHABILITADO: cuentas definidas en variables de entorno"


def registrar(usuario: str, nombre: str, contrasena: str, codigo: str, ip="", navegador="") -> dict:
    raise HTTPException(403, "El registro está deshabilitado. Solo existen los tres administradores configurados.")


def crear_usuario(usuario: str, nombre: str, contrasena: str, creado_por: str | None = None) -> dict:
    raise HTTPException(403, "Las cuentas se administran mediante variables de entorno del servidor.")


def listar_usuarios() -> list[dict]:
    return [ficha(_datos_usuario(u)) for u in _ADMINISTRADORES]


def historial(usuario: str = "", evento: str = "", limite: int = 100) -> dict:
    with _candado:
        filas = list(reversed(_eventos))
    if usuario:
        filas = [f for f in filas if f["usuario"] == usuario.lower()]
    if evento:
        filas = [f for f in filas if f["evento"] == evento]
    return {"total": len(filas), "eventos": filas[:max(1, min(int(limite), 500))]}


def actualizar_usuario(usuario: str, quien: str, nombre=None, contrasena=None, activo=None) -> dict:
    raise HTTPException(403, "No se pueden modificar cuentas desde el panel. Cambie las variables de entorno en Render.")


def eliminar_usuario(usuario: str, quien: str):
    raise HTTPException(403, "No se pueden eliminar las cuentas fijas de administración.")


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
    usuario = (usuario or "").strip().lower()
    if _bloqueado(ip):
        anotar(usuario, "bloqueo", ip, navegador, "Demasiados intentos fallidos")
        raise HTTPException(429, "Demasiados intentos fallidos. Espere 10 minutos e intente de nuevo.")
    esperado = _password(usuario)
    correcto = bool(esperado) and hmac.compare_digest(_hash(contrasena, usuario), _hash(esperado, usuario))
    if not correcto:
        _registrar_fallo(ip)
        anotar(usuario, "fallo", ip, navegador, "Usuario o contraseña incorrectos")
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    with _candado:
        _fallos.pop(ip, None)
    anotar(usuario, "ingreso", ip, navegador)
    return _datos_usuario(usuario)


def _firma(usuario, vence, sello):
    return hmac.new(_secreto(), f"{usuario}|{vence}|{sello}".encode(), hashlib.sha256).hexdigest()


def crear_token(usuario: str) -> str:
    usuario = usuario.lower()
    contrasena = _password(usuario)
    if not contrasena:
        raise HTTPException(401, "La cuenta administrativa no está configurada.")
    vence = int(time.time()) + DURACION_SESION
    sello = _hash(contrasena, usuario)[:16]
    firma = _firma(usuario, vence, sello)
    return base64.urlsafe_b64encode(f"{usuario}|{vence}|{firma}".encode()).decode()


def usuario_de_token(token: str | None):
    if not token:
        return None
    try:
        usuario, vence, firma = base64.urlsafe_b64decode(token.encode()).decode().split("|")
        vence = int(vence)
    except Exception:
        return None
    if vence < time.time() or usuario not in _ADMINISTRADORES:
        return None
    contrasena = _password(usuario)
    if not contrasena:
        return None
    sello = _hash(contrasena, usuario)[:16]
    try:
        firma_esperada = _firma(usuario, vence, sello)
    except HTTPException:
        return None
    if not hmac.compare_digest(firma, firma_esperada):
        return None
    return _datos_usuario(usuario)


def usuario_actual(request: Request):
    return usuario_de_token(request.cookies.get(COOKIE))


def requiere_admin(request: Request) -> dict:
    u = usuario_actual(request)
    if u is None:
        raise HTTPException(401, "Debe ingresar como administrador para hacer esta operación.")
    return u
