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
IGNORADAS_FILE = Path("ignoradas.json")
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

def cargar_ignoradas():
    """Carga la lista de URLs ignoradas desde ignoradas.json"""
    if IGNORADAS_FILE.exists():
        try:
            with open(IGNORADAS_FILE, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return json.loads(contenido)
        except (json.JSONDecodeError, ValueError):
            log("⚠️ ignoradas.json corrupto, iniciando desde cero")
    return []

def guardar_ignoradas(ignoradas):
    with open(IGNORADAS_FILE, "w", encoding="utf-8") as f:
        json.dump(ignoradas, f, ensure_ascii=False, indent=2)

def cargar_urls_publicadas():
    """Extrae URLs de fuente original de noticias ya publicadas desde los archivos HTML"""
    urls = []
    for html_file in NOTICIAS_DIR.glob("*.html"):
        if html_file.name == "index.html":
            continue
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html = f.read()
                # Extraer URL del disclaimer (fuente original)
                match = re.search(r'<a href="([^"]+)"[^>]*>fuente original', html)
                if match:
                    url = match.group(1).strip()
                    if url and url != "#":
                        urls.append(url)
        except Exception:
            pass
    return urls

def cargar_titulos_publicados():
    """Extrae títulos de noticias ya publicadas desde los archivos HTML en noticias/"""
    titulos = []
    for html_file in NOTICIAS_DIR.glob("*.html"):
        if html_file.name == "index.html":
            continue
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html = f.read()
                # Extraer título del <title> tag
                match = re.search(r"<title>(.+?)\s*\|", html)
                if match:
                    titulos.append(match.group(1).strip())
        except Exception:
            pass
    return titulos

def cargar_titulos_ignoradas():
    """Carga títulos de noticias ignoradas desde ignoradas.json"""
    titulos = []
    ignoradas = cargar_ignoradas()
    for item in ignoradas:
        if "titulo" in item and item["titulo"]:
            titulos.append(item["titulo"])
    return titulos

def cargar_titulos_borradas():
    """Carga títulos de noticias borradas desde borradas.txt si existe"""
    titulos = []
    borradas_file = Path("panel/borradas.txt")
    if borradas_file.exists():
        try:
            with open(borradas_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and line.endswith(".html"):
                        # El archivo borrado es un slug, no tenemos el título
                        # Pero podemos intentar leerlo del estado si existe
                        pass
        except Exception:
            pass
    return titulos

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def es_noticia_duplicada(nuevo_titulo, titulos_existentes):
    """Usa OpenAI para determinar si una noticia nueva es conceptualmente un duplicado de alguna existente."""
    if not titulos_existentes:
        return False
    
    # Primero: comparación rápida por similitud de texto (Jaccard)
    nuevo_norm = normalizar_texto(nuevo_titulo)
    nuevo_palabras = set(nuevo_norm.split())
    
    for titulo in titulos_existentes:
        existente_norm = normalizar_texto(titulo)
        existente_palabras = set(existente_norm.split())
        
        if len(nuevo_palabras) > 0 and len(existente_palabras) > 0:
            interseccion = nuevo_palabras & existente_palabras
            union = nuevo_palabras | existente_palabras
            similitud = len(interseccion) / len(union)
            
            # Si comparten más del 30% de palabras, es duplicado
            if similitud >= 0.3:
                return True
            
            # Si uno contiene al otro (título muy similar)
            if nuevo_norm in existente_norm or existente_norm in nuevo_norm:
                return True
    
    # Si no hay coincidencia por Jaccard, usar OpenAI si está disponible
    if not OPENAI_API_KEY or not client:
        return False
    
    # Con OpenAI: comparar solo con los últimos 30 títulos para no gastar tokens
    titulos_recientes = titulos_existentes[-30:]
    contexto = "\n".join([f"- {t}" for t in titulos_recientes])
    
    prompt = (
        "Eres un editor de noticias. Determina si la siguiente noticia NUEVA trata sobre "
        "EL MISMO TEMA o HECHO que alguna de las YA PUBLICADAS, aunque esté redactada con palabras diferentes.\n\n"
        "NOTICIAS YA PUBLICADAS (últimas 30):\n"
        f"{contexto}\n\n"
        f"NUEVA NOTICIA: {nuevo_titulo}\n\n"
        "Responde ÚNICAMENTE con 'DUPLICADO' si trata del mismo tema/hecho, "
        "o 'NUEVO' si es un tema completamente diferente.\n"
        "Respuesta:"
    )
    
    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Solo respondes 'DUPLICADO' o 'NUEVO'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=5
        )
        veredicto = respuesta.choices[0].message.content.strip().upper()
        return "DUPLICADO" in veredicto
    except Exception as e:
        log("   ⚠️ Error en deduplicación por IA: " + str(e))
        return False

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
    
    # Cargar ignoradas (URLs que el usuario descartó)
    ignoradas = cargar_ignoradas()
    urls_ignoradas = {i["url_google"] for i in ignoradas}
    log("  " + str(len(ignoradas)) + " URLs ignoradas (descartadas por el usuario)")
    
    # Cargar URLs de noticias ya publicadas para deduplicación por URL
    log("Cargando URLs de noticias publicadas...")
    urls_publicadas = cargar_urls_publicadas()
    log("  " + str(len(urls_publicadas)) + " URLs de fuente encontradas")
    
    # Combinar todas las URLs conocidas (ignoradas + publicadas)
    urls_conocidas = urls_ignoradas | set(urls_publicadas)
    
    # Cargar títulos de noticias ya publicadas para deduplicación semántica
    log("Cargando títulos de noticias publicadas...")
    titulos_publicados = cargar_titulos_publicados()
    log("  " + str(len(titulos_publicados)) + " noticias publicadas encontradas")
    
    # Cargar títulos de noticias ignoradas para deduplicación
    log("Cargando títulos de noticias ignoradas...")
    titulos_ignoradas = cargar_titulos_ignoradas()
    log("  " + str(len(titulos_ignoradas)) + " noticias ignoradas encontradas")
    
    # Combinar todos los títulos conocidos para deduplicación
    todos_titulos_conocidos = titulos_publicados + titulos_ignoradas
    log("  Total títulos conocidos para deduplicación: " + str(len(todos_titulos_conocidos)))
    
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
            # Saltar si ya está en pendientes
            if item["url_google"] in urls_existentes:
                continue
            # Saltar si fue ignorada (descartada por el usuario)
            if item["url_google"] in urls_ignoradas:
                log("  ⏭ Ignorada (descartada anteriormente): " + item["titulo"][:80])
                continue
            # Saltar si es muy vieja
            item_fecha = datetime.strptime(item["fecha"], "%Y-%m-%d %H:%M:%S") if item["fecha"] else None
            if item_fecha and item_fecha < limite:
                continue
            
            # Deduplicación semántica: no añadir si es el mismo tema que una ya publicada o ignorada
            if es_noticia_duplicada(item["titulo"], todos_titulos_conocidos):
                log("  ⏭ Duplicado semántico (ya publicado/ignorado): " + item["titulo"][:80])
                continue
            
            # También verificar contra pendientes existentes (por si acaso)
            titulos_pendientes = [p["titulo"] for p in pendientes]
            if es_noticia_duplicada(item["titulo"], titulos_pendientes):
                log("  ⏭ Duplicado semántico (ya en pendientes): " + item["titulo"][:80])
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
