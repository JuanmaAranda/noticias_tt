#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikPanel - Generador de Noticias Automáticas (GitHub Actions)"""

import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from openai import OpenAI

# ============================================================
# CONFIGURACIÓN
# ============================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-REEMPLAZA-ESTO-CON-TU-API-KEY")

FEEDS = [
    "https://news.google.com/rss/search?q=TikTok&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+algoritmo&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+monetizacion&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+creadores&hl=es&gl=ES&ceid=ES:es",
]

KEYWORDS = [
    "tiktok", "tik tok", "bytedance", "algorithm", "algoritmo",
    "creator", "creador", "monetization", "monetizacion", "shop",
    "live", "en directo", "ban", "prohibicion", "regulation", "regulacion",
    "update", "actualizacion", "feature", "funcion", "trend", "tendencia"
]

MAX_NOTICIAS_POR_DIA = 2

client = OpenAI(api_key=OPENAI_API_KEY)
NOTICIAS_DIR = Path("noticias")
ESTADO_FILE = Path("estado_noticias.json")
NOTICIAS_DIR.mkdir(exist_ok=True)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg)

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def es_relevante(titulo, descripcion=""):
    texto = normalizar_texto(titulo + " " + descripcion)
    for kw in KEYWORDS:
        if kw.lower() in texto:
            return True
    return False

def generar_id(url, titulo):
    return hashlib.md5((url + titulo).encode()).hexdigest()

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

def obtener_feed(url):
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
            if titulo and link:
                items.append({
                    "titulo": titulo.strip(),
                    "url": link.strip(),
                    "descripcion": desc.strip(),
                    "fecha": fecha,
                    "fecha_str": fecha_str,
                    "fuente": url,
                })
        return items
    except Exception as e:
        log("Error leyendo feed " + url + ": " + str(e))
        return []

def cargar_estado():
    if ESTADO_FILE.exists():
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"procesados": [], "ultima_ejecucion": None}

def guardar_estado(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def generar_slug(titulo):
    slug = normalizar_texto(titulo)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:60].strip("-")
    return slug + ".html"

# ============================================================
# GENERAR ARTÍCULO CON IA
# ============================================================

def generar_articulo_ia(titulo, descripcion, url_fuente):
    prompt = (
        "Eres un redactor experto en redes sociales para TikPanel (tikpanel.app).\n\n"
        "Tu tarea: escribir un articulo de noticias de 350-500 palabras en ESPANOL, "
        "basado en la siguiente noticia externa. NO copies texto literal. "
        "Reescribelo completamente con tu propio estilo, manteniendo los hechos clave.\n\n"
        "INFORMACION DE LA NOTICIA ORIGINAL:\n"
        "- Titulo: " + titulo + "\n"
        "- Descripcion: " + descripcion + "\n"
        "- URL fuente: " + url_fuente + "\n\n"
        "ESTRUCTURA REQUERIDA:\n"
        "1. Titulo atractivo y claro (max 70 caracteres)\n"
        "2. Subtitulo o entradilla (1-2 frases)\n"
        "3. 3-4 parrafos de desarrollo\n"
        "4. Conclusion con implicacion para creadores de contenido\n"
        "5. Separador --- y la linea: Fuente original: [URL]\n\n"
        "REGLAS:\n"
        "- Tono profesional, directo y util para creadores de TikTok\n"
        "- Usa negritas para palabras clave importantes\n"
        "- No inventes datos que no esten en la noticia original\n"
        "- Si la noticia esta en ingles, traduce y adapta al espanol\n"
        "- Incluye siempre la atribucion a la fuente original\n\n"
        "Responde UNICAMENTE en este formato exacto:\n"
        "TITULO: <titulo aqui>\n"
        "CONTENIDO: <contenido HTML aqui (parrafos con <p>, negritas con <strong>)>"
    )
    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un editor de noticias especializado en TikTok y redes sociales. Escribes en espanol perfecto."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        texto = respuesta.choices[0].message.content.strip()
        titulo_match = re.search(r"TITULO:\s*(.+?)(?=\n|CONTENIDO:)", texto, re.DOTALL)
        contenido_match = re.search(r"CONTENIDO:\s*(.+)", texto, re.DOTALL)
        nuevo_titulo = titulo_match.group(1).strip() if titulo_match else titulo
        contenido = contenido_match.group(1).strip() if contenido_match else texto
        return nuevo_titulo, contenido
    except Exception as e:
        log("Error con OpenAI: " + str(e))
        contenido_fallback = "<p>" + descripcion + "</p><p><strong>Fuente original:</strong> <a href=\"" + url_fuente + "\" target=\"_blank\">" + url_fuente + "</a></p>"
        return titulo, contenido_fallback

# ============================================================
# CREAR HTML CON TEMA OSCURO
# ============================================================

def crear_html_noticia(titulo, contenido, url_fuente, fecha, slug):
    fecha_formateada = fecha.strftime("%d de %B de %Y") if fecha else datetime.now().strftime("%d de %B de %Y")
    anio = datetime.now().year
    
    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"es\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "    <title>" + titulo + " | Noticias TikPanel</title>\n"
        "    <meta name=\"description\" content=\"Noticias sobre TikTok: " + titulo[:150] + "\">\n"
        "    <link rel=\"stylesheet\" href=\"../css/style.css\">\n"
        "</head>\n"
        "<body>\n"
        "<div id=\"navbar-container\"></div>\n"
        "\n"
        "<main class=\"noticia-article-layout\">\n"
        "    <div class=\"container noticia-article-container\">\n"
        "        <article>\n"
        "            <header class=\"noticia-header\">\n"
        "                <div class=\"noticia-meta\">\n"
        "                    <span class=\"noticia-tag\">📰 TikTok</span>\n"
        "                    <span>" + fecha_formateada + "</span>\n"
        "                </div>\n"
        "                <h1>" + titulo + "</h1>\n"
        "            </header>\n"
        "            <div class=\"noticia-contenido\">\n"
        "                " + contenido + "\n"
        "                <div class=\"noticia-disclaimer\">\n"
        "                    <strong>⚠️ Aviso:</strong> Este articulo es un <strong>resumen generado automaticamente por IA</strong> a partir de noticias publicas.\n"
        "                    La informacion original proviene de: <a href=\"" + url_fuente + "\" target=\"_blank\" rel=\"noopener noreferrer\">" + url_fuente + "</a>\n"
        "                </div>\n"
        "            </div>\n"
        "            <footer class=\"noticia-footer\">\n"
        "                <a href=\"index.html\" class=\"noticia-nav-back\">← Volver a todas las noticias</a>\n"
        "            </footer>\n"
        "        </article>\n"
        "    </div>\n"
        "</main>\n"
        "\n"
        "<div id=\"footer-container\"></div>\n"
        "<script src=\"../shared-components.js\"></script>\n"
        "</body>\n"
        "</html>"
    )
    
    archivo = NOTICIAS_DIR / slug
    with open(archivo, "w", encoding="utf-8") as f:
        f.write(html)
    return archivo.name

def actualizar_index():
    entradas = []
    for f in sorted(NOTICIAS_DIR.glob("*.html")):
        if f.name == "index.html":
            continue
        fecha_match = re.search(r"-(\d{4}-\d{2}-\d{2})\.html$", f.name)
        if fecha_match:
            fecha_obj = datetime.strptime(fecha_match.group(1), "%Y-%m-%d")
        else:
            fecha_obj = datetime.fromtimestamp(f.stat().st_mtime)
        titulo = "Noticia"
        try:
            with open(f, "r", encoding="utf-8") as file:
                html = file.read()
                t_match = re.search(r"<title>(.+?)\s*\|", html)
                if t_match:
                    titulo = t_match.group(1).strip()
        except:
            pass
        entradas.append({
            "archivo": f.name,
            "titulo": titulo,
            "fecha": fecha_obj,
            "fecha_str": fecha_obj.strftime("%d/%m/%Y"),
        })
    entradas.sort(key=lambda x: x["fecha"], reverse=True)
    
    items_html = ""
    for e in entradas[:30]:
        items_html += (
            "<article class=\"noticia-card\">\n"
            "    <div class=\"noticia-card-body\">\n"
            "        <div class=\"noticia-card-meta\">\n"
            "            <span class=\"noticia-card-fecha\">📅 " + e["fecha_str"] + "</span>\n"
            "        </div>\n"
            "        <h3><a href=\"" + e["archivo"] + "\">" + e["titulo"] + "</a></h3>\n"
            "        <p class=\"noticia-card-excerpt\">Resumen de la noticia sobre TikTok. Haz clic para leer el articulo completo.</p>\n"
            "        <a href=\"" + e["archivo"] + "\" class=\"noticia-card-cta\">Leer mas →</a>\n"
            "    </div>\n"
            "</article>\n"
        )
    
    anio = datetime.now().year
    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"es\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "    <title>Noticias sobre TikTok | TikPanel</title>\n"
        "    <meta name=\"description\" content=\"Noticias diarias automaticas sobre TikTok, algoritmo, creadores y tendencias.\">\n"
        "    <link rel=\"stylesheet\" href=\"../css/style.css\">\n"
        "</head>\n"
        "<body>\n"
        "<div id=\"navbar-container\"></div>\n"
        "\n"
        "<main>\n"
        "    <section class=\"noticias-hero\">\n"
        "        <div class=\"noticias-hero-bg\"></div>\n"
        "        <div class=\"noticias-hero-content\">\n"
        "            <h1>📰 Noticias sobre TikTok</h1>\n"
        "            <p>Resumen diario automatico de las noticias mas relevantes sobre TikTok, el algoritmo, monetizacion y tendencias para creadores.</p>\n"
        "            <p class=\"noticias-disclaimer\">\n"
        "                <small>⚠️ Los articulos son generados automaticamente por IA a partir de fuentes publicas. Siempre se incluye el enlace a la noticia original.</small>\n"
        "            </p>\n"
        "        </div>\n"
        "    </section>\n"
        "\n"
        "    <section class=\"noticias-section\">\n"
        "        <div class=\"container\">\n"
        "            <div class=\"noticias-grid\">\n"
        "                " + items_html + "\n"
        "            </div>\n"
        "        </div>\n"
        "    </section>\n"
        "</main>\n"
        "\n"
        "<div id=\"footer-container\"></div>\n"
        "<script src=\"../shared-components.js\"></script>\n"
        "</body>\n"
        "</html>"
    )
    
    with open(NOTICIAS_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)

# ============================================================
# MAIN
# ============================================================

def main():
    log("Iniciando generacion de noticias automaticas...")
    log("Fecha: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    estado = cargar_estado()
    procesados = set(estado.get("procesados", []))
    
    todas_noticias = []
    for feed_url in FEEDS:
        log("Leyendo feed: " + feed_url)
        items = obtener_feed(feed_url)
        log("   → " + str(len(items)) + " articulos encontrados")
        todas_noticias.extend(items)
    
    ahora = datetime.now()
    limite = ahora - timedelta(hours=48)
    candidatas = []
    for item in todas_noticias:
        noticia_id = generar_id(item["url"], item["titulo"])
        if noticia_id in procesados:
            continue
        if item["fecha"] and item["fecha"] < limite:
            continue
        if not es_relevante(item["titulo"], item["descripcion"]):
            continue
        candidatas.append({**item, "id": noticia_id})
    
    log(str(len(candidatas)) + " noticias candidatas tras filtrar")
    
    if not candidatas:
        log("No hay noticias nuevas relevantes hoy. Saliendo.")
        return
    
    a_procesar = candidatas[:MAX_NOTICIAS_POR_DIA]
    nuevas_slugs = []
    
    for noticia in a_procesar:
        log("Procesando: " + noticia["titulo"][:80] + "...")
        titulo_ia, contenido_ia = generar_articulo_ia(
            noticia["titulo"],
            noticia["descripcion"],
            noticia["url"]
        )
        slug = generar_slug(titulo_ia)
        crear_html_noticia(
            titulo_ia,
            contenido_ia,
            noticia["url"],
            noticia["fecha"] or datetime.now(),
            slug
        )
        procesados.add(noticia["id"])
        nuevas_slugs.append(slug)
        log("Guardado: noticias/" + slug)
    
    log("Actualizando indice de noticias...")
    actualizar_index()
    
    estado["procesados"] = list(procesados)
    estado["ultima_ejecucion"] = ahora.isoformat()
    guardar_estado(estado)
    
    log("Listo! Se generaron " + str(len(nuevas_slugs)) + " noticia(s) nueva(s).")
    for s in nuevas_slugs:
        log("   → noticias/" + s)

if __name__ == "__main__":
    main()

