"""Abre el navegador cuando el servidor ya responde (lo usa iniciar.bat). Espera hasta 2 minutos."""
import time
import urllib.request
import webbrowser

URL = "http://127.0.0.1:8000"
for _ in range(120):
    try:
        urllib.request.urlopen(URL + "/api/auth/yo", timeout=2)
        webbrowser.open(URL)
        break
    except Exception:
        time.sleep(1)
