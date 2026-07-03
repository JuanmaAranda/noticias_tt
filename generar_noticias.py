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
    """Extrae URLs de fuente original de noticias ya publicadas desde los archivos HTML
    locales y también del listado del servidor si está disponible."""
    urls = []
    # 1. Leer desde archivos HTML locales
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
    
    # 2. Leer desde noticias_servidor.html descargado del workflow
    servidor_file = Path("noticias_servidor.html")
    if servidor_file.exists():
        try:
            with open(servidor_file, "r", encoding="utf-8") as f:
                html = f.read()
                # Extraer URLs de fuente original de las noticias del servidor
                matches = re.findall(r'<a href="([^"]+)"[^>]*>fuente original', html)
                for url in matches:
                    url = url.strip()
                    if url and url != "#" and url not in urls:
                        urls.append(url)
        except Exception:
            pass
    
    return urls

def cargar_titulos_publicados():
    """Extrae títulos de noticias ya publicadas desde archivos HTML locales
    y también del listado del servidor si está disponible."""
    titulos = []
    # 1. Leer desde archivos HTML locales
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
    
    # 2. Leer desde noticias_servidor.html descargado del workflow
    servidor_file = Path("noticias_servidor.html")
    if servidor_file.exists():
        try:
            with open(servidor_file, "r", encoding="utf-8") as f:
                html = f.read()
                # Extraer títulos del <title> tag
                matches = re.findall(r"<title>(.+?)\s*\|", html)
                for titulo in matches:
                    titulo = titulo.strip()
                    if titulo and titulo not in titulos:
                        titulos.append(titulo)
                # También extraer de h2/h3 que contienen títulos de noticias
                matches_h2 = re.findall(r'<h[23][^>]*>(.+?)</h[23]>', html, re.DOTALL)
                for match in matches_h2:
                    titulo = re.sub(r'<[^>]+>', '', match).strip()
                    if titulo and titulo not in titulos and len(titulo) > 10:
                        titulos.append(titulo)
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
    """Carga títulos de noticias borradas desde panel/borradas.json (títulos completos)
    y panel/borradas.txt (slugs) como fallback."""
    titulos = set()
    
    # 1. Cargar desde borradas.json (títulos completos guardados por el panel)
    borradas_json_file = Path("panel/borradas.json")
    if borradas_json_file.exists():
        try:
            with open(borradas_json_file, "r", encoding="utf-8") as f:
                borradas = json.load(f)
                for item in borradas:
                    if "titulo" in item and item["titulo"]:
                        titulos.add(item["titulo"])
        except Exception:
            pass
    
    # 2. Cargar desde borradas.txt (slugs de noticias eliminadas por el usuario)
    borradas_file = Path("panel/borradas.txt")
    if borradas_file.exists():
        try:
            with open(borradas_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and line.endswith(".html"):
                        # El slug está en formato: slug-de-la-noticia.html
                        # Convertir a título aproximado para deduplicación
                        slug = line.replace(".html", "")
                        # Convertir guiones a espacios para comparación
                        titulo_aprox = slug.replace("-", " ").replace("_", " ")
                        titulos.add(titulo_aprox)
        except Exception:
            pass
    
    # 3. IMPORTANTE: También cargar títulos de noticias ya publicadas en noticias/
    # Esto previene que noticias ya publicadas (subidas por FTP) vuelvan a aparecer
    for html_file in NOTICIAS_DIR.glob("*.html"):
        if html_file.name == "index.html":
            continue
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html = f.read()
                # Extraer título del <title> tag
                match = re.search(r"<title>(.+?)\s*\|", html)
                if match:
                    titulos.add(match.group(1).strip())
                # También extraer del h1 si existe
                match_h1 = re.search(r'<h1[^>]*>(.+?)</h1>', html, re.DOTALL)
                if match_h1:
                    titulos.add(re.sub(r'<[^>]+>', '', match_h1.group(1)).strip())
        except Exception:
            pass
    
    return list(titulos)

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def es_noticia_duplicada(nuevo_titulo, titulos_existentes):
    """Usa comparación por similitud de texto para determinar si una noticia nueva es conceptualmente un duplicado."""
    if not titulos_existentes:
        return False
    
    # Stopwords para filtrar palabras no significativas
    stopwords = {"el", "la", "los", "las", "un", "una", "de", "del", "al", "y", "o", "en", "con", "por", "para", "que", "es", "son", "se", "lo", "le", "como", "pero", "mas", "más", "sin", "sobre", "entre", "hasta", "desde", "a", "ante", "bajo", "segun", "según", "tras", "durante", "mediante", "excepto", "salvo", "contra", "hacia", "hasta", "desde", "durante", "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by", "for", "with", "about", "into", "through", "during", "before", "after", "above", "below", "from", "up", "down", "out", "off", "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just", "should", "now"}
    
    nuevo_norm = normalizar_texto(nuevo_titulo)
    nuevo_palabras = set(nuevo_norm.split())
    
    # Si el título normalizado es muy corto, no podemos comparar bien
    if len(nuevo_palabras) < 3:
        return False
    
    for titulo in titulos_existentes:
        existente_norm = normalizar_texto(titulo)
        existente_palabras = set(existente_norm.split())
        
        if len(existente_palabras) < 3:
            continue
        
        if len(nuevo_palabras) > 0 and len(existente_palabras) > 0:
            interseccion = nuevo_palabras & existente_palabras
            union = nuevo_palabras | existente_palabras
            similitud = len(interseccion) / len(union)
            
            # Si comparten más del 35% de palabras, es muy probable que sea duplicado
            # Bajado de 0.50 a 0.35 para capturar más duplicados semánticos
            if similitud >= 0.35:
                log(f"  ⏭ Duplicado por similitud de palabras ({similitud:.0%}): '{nuevo_titulo[:60]}' vs '{titulo[:60]}'")
                return True
            
            # Detección de palabras clave compartidas: nombres propios, números, términos técnicos
            # Si comparten 3+ palabras clave específicas, es muy probable que sea el mismo tema
            palabras_clave_nuevo = {p for p in nuevo_palabras if len(p) > 4 and p not in stopwords and not p.isdigit()}
            palabras_clave_existente = {p for p in existente_palabras if len(p) > 4 and p not in stopwords and not p.isdigit()}
            interseccion_clave = palabras_clave_nuevo & palabras_clave_existente
            if len(interseccion_clave) >= 3:
                log(f"  ⏭ Duplicado por palabras clave compartidas ({len(interseccion_clave)}): '{nuevo_titulo[:60]}' vs '{titulo[:60]}'")
                return True
            
            # Si uno contiene al otro (título muy similar)
            if nuevo_norm in existente_norm or existente_norm in nuevo_norm:
                log(f"  ⏭ Duplicado por contención: '{nuevo_titulo[:60]}' vs '{titulo[:60]}'")
                return True
            
            # Si comparten más de 5 palabras significativas (palabras de contenido, no stopwords)
            palabras_significativas_nuevo = {p for p in nuevo_palabras if len(p) > 3 and p not in stopwords}
            palabras_significativas_existente = {p for p in existente_palabras if len(p) > 3 and p not in stopwords}
            
            if len(palabras_significativas_nuevo) > 0 and len(palabras_significativas_existente) > 0:
                interseccion_signif = palabras_significativas_nuevo & palabras_significativas_existente
                union_signif = palabras_significativas_nuevo | palabras_significativas_existente
                similitud_signif = len(interseccion_signif) / len(union_signif)
                
                # Si comparten más del 45% de palabras significativas
                if similitud_signif >= 0.45:
                    log(f"  ⏭ Duplicado por similitud de palabras clave ({similitud_signif:.0%}): '{nuevo_titulo[:60]}' vs '{titulo[:60]}'")
                    return True
    
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
    
    # Cargar títulos de noticias borradas para deduplicación
    log("Cargando títulos de noticias borradas...")
    titulos_borradas = cargar_titulos_borradas()
    log("  " + str(len(titulos_borradas)) + " títulos de borradas/publicadas encontrados")
    
    # Combinar todos los títulos conocidos para deduplicación (publicadas + ignoradas + borradas)
    todos_titulos_conocidos = list(set(titulos_publicados + titulos_ignoradas + titulos_borradas))
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
