#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikPanel - Recolector de Noticias Pendientes desde Google News RSS"""

import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

# Configuración de APIs
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Inicializar cliente de IA
client = None
if OPENAI_API_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("[OK] Usando OpenAI como motor de IA")
else:
    print("[ERROR] No hay OPENAI_API_KEY configurada.")

PENDIENTES_FILE = Path("pendientes.json")
NOTICIAS_DIR = Path("noticias")
NOTICIAS_DIR.mkdir(exist_ok=True)

# Resumen de ejecución para email
RESUMEN_EJECUCION = {"estado": "iniciado", "urls_encontradas": 0, "errores": [], "mensajes": []}

def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg)
    RESUMEN_EJECUCION["mensajes"].append(msg)

def log_error(msg):
    log("ERROR: " + msg)
    RESUMEN_EJECUCION["errores"].append(msg)
    RESUMEN_EJECUCION["estado"] = "error"

def guardar_resumen():
    """Guarda el resumen de ejecución en un archivo JSON para que el workflow lo lea"""
    with open("resumen_ejecucion.json", "w", encoding="utf-8") as f:
        json.dump(RESUMEN_EJECUCION, f, ensure_ascii=False, indent=2)

def cargar_pendientes():
    """Carga la lista de noticias pendientes desde pendientes.json"""
    if PENDIENTES_FILE.exists():
        try:
            with open(PENDIENTES_FILE, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return json.loads(contenido)
        except (json.JSONDecodeError, ValueError):
            log("⚠️ pendientes.json corrupto, iniciando desde cero")
    return []

def guardar_pendientes(pendientes):
    with open(PENDIENTES_FILE, "w", encoding="utf-8") as f:
        json.dump(pendientes, f, ensure_ascii=False, indent=2)

def parsear_fecha(fecha_str):
    formatos = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formatos:
        try:
            dt = datetime.strptime(fecha_str.strip(), fmt)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None

def obtener_feed_google_news(url):
    """Obtiene noticias de un feed RSS de Google News. Devuelve items con url_google (la encoded) y titulo."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            titulo = item.findtext("title", default="")
            link = item.findtext("link", default="")
            desc = item.findtext("description", default="")
            fecha_str = item.findtext("pubDate", default="")
            fecha = parsear_fecha(fecha_str) if fecha_str else None
            
            url_google = link.strip()
            
            # Solo noticias que mencionen TikTok en el título o descripción
            texto_completo = (titulo + " " + desc).lower()
            if "tiktok" not in texto_completo and "tik tok" not in texto_completo and "byte dance" not in texto_completo:
                continue
            
            if titulo and url_google:
                items.append({
                    "titulo": titulo.strip(),
                    "url_google": url_google,
                    "descripcion": desc.strip(),
                    "fecha": fecha.strftime("%Y-%m-%d %H:%M:%S") if fecha else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fecha_str": fecha_str,
                    "fuente": url,
                })
        return items
    except Exception as e:
        log("Error leyendo feed " + url + ": " + str(e))
        return []

def main():
    log("Iniciando recolección de noticias desde Google News RSS...")
    
    # Cargar pendientes existentes
    pendientes = cargar_pendientes()
    urls_existentes = {p["url_google"] for p in pendientes}
    
    # Feeds de Google News
    feeds = [
        "https://news.google.com/rss/search?q=TikTok&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+algoritmo&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+monetizacion&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+creadores&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+prohibicion&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+actualizacion&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+Shop&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+Live&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=ByteDance&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+ban&hl=es&gl=ES&ceid=ES:es",
    ]
    
    limite = datetime.now() - timedelta(days=7)
    nuevas = 0
    
    for feed_url in feeds:
        log("Leyendo feed: " + feed_url)
        items = obtener_feed_google_news(feed_url)
        for item in items:
            # Saltar si ya existe
            if item["url_google"] in urls_existentes:
                continue
            # Saltar si es muy vieja
            item_fecha = datetime.strptime(item["fecha"], "%Y-%m-%d %H:%M:%S") if item["fecha"] else None
            if item_fecha and item_fecha < limite:
                continue
            
            pendientes.append(item)
            urls_existentes.add(item["url_google"])
            nuevas += 1
            log("  + Nueva: " + item["titulo"][:80])
    
    # Guardar pendientes
    guardar_pendientes(pendientes)
    
    log("=" * 50)
    log("Total pendientes: " + str(len(pendientes)))
    log("Nuevas hoy: " + str(nuevas))
    
    RESUMEN_EJECUCION["urls_encontradas"] = nuevas
    RESUMEN_EJECUCION["estado"] = "ok" if nuevas > 0 else "sin_nuevas"
    guardar_resumen()
    
    log("Listo! Las noticias están en pendientes.json para revisión manual.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(str(e))
        guardar_resumen()
        raise
