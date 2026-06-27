#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikPanel - Generador de Noticias Automáticas"""

import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-REEMPLAZA-ESTO-CON-TU-API-KEY")

FEEDS = [
    "https://news.google.com/rss/search?q=TikTok&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+algoritmo&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+monetizacion&hl=es&gl=ES&ceid=ES:es",
    "https://news.google.com/rss/search?q=TikTok+creadores&hl=es&gl=ES&ceid=ES:es",
    "https://www.20minutos.es/rss/tecnologia/",
    "https://feeds.feedburner.com/tubefilterNews",
    "https://www.socialmediatoday.com/rss.xml",
    "https://techcrunch.com/category/social/feed/",
    "https://www.theguardian.com/technology/tiktok/rss",
]

KEYWORDS = [
    "tiktok", "tik tok", "bytedance", "algorithm", "algoritmo",
    "creator", "creador", "monetization", "monetizacion", "shop",
    "live", "en directo", "ban", "prohibicion", "regulation", "regulacion",
    "update", "actualizacion", "feature", "funcion", "trend", "tendencia",
    "shorts", "reels", "viral", "viralizar", "influencer", "streamer",
    "contenido", "video", "plataforma", "red social", "social media",
    "youtube", "instagram", "meta", "byte dance"
]

MAX_NOTICIAS_POR_DIA = 2

client = OpenAI(api_key=OPENAI_API_KEY)
NOTICIAS_DIR = Path("noticias")
ESTADO_FILE = Path("estado_noticias.json")
NOTICIAS_DIR.mkdir(exist_ok=True)

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
    return {"procesados": [], "ultima_ejecucion": None, "extractos": {}}

def guardar_estado(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def generar_slug(titulo):
    slug = normalizar_texto(titulo)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:60].strip("-")
    return slug + ".html"

def limpiar_contenido_ia(contenido):
    """Convierte markdown a HTML y limpia URLs largas."""
    # Convertir **texto** a <strong>texto</strong>
    contenido = re.sub(r"\*\*(.+?)\*\*", r"<strong></strong>", contenido)
    # Convertir *texto* a <em>texto</em>
    contenido = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<em></em>", contenido)
    # Convertir URLs sueltas en texto a links limpios
    def link_replacer(match):
        url = match.group(1)
        if len(url) > 60:
            return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">Ver fuente</a>'
        return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>'
    contenido = re.sub(r'(https?://[^\s<>"]+)', link_replacer, contenido)
    # Eliminar líneas que empiecen con "--- Fuente original:" o similares
    contenido = re.sub(r"<p>\s*---+\s*Fuente original:.*?</p>", "", contenido, flags=re.DOTALL)
    contenido = re.sub(r"---+\s*Fuente original:.*", "", contenido, flags=re.DOTALL)
    return contenido.strip()

def generar_extracto(contenido_html, max_chars=140):
    texto = re.sub(r"<[^>]+>", "", contenido_html)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > max_chars:
        texto = texto[:max_chars].rsplit(" ", 1)[0] + "..."
    return texto

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
        "5. NO incluyas la fuente original ni URLs en el contenido. Eso se añade automaticamente despues.\n\n"
        "REGLAS IMPORTANTES:\n"
        "- Usa SOLO HTML para negritas: <strong>texto</strong> (NO uses ** ni markdown)\n"
        "- Usa <p> para cada parrafo\n"
        "- NO incluyas URLs largas en el texto\n"
        "- NO escribas "Fuente original" al final\n"
        "- Tono profesional, directo y util para creadores de TikTok\n"
        "- Si la noticia esta en ingles, traduce y adapta al espanol\n\n"
        "Responde UNICAMENTE en este formato exacto:\n"
        "TITULO: <titulo aqui>\n"
        "CONTENIDO: <contenido HTML aqui (solo <p> y <strong>)>"
    )
    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un editor de noticias especializado en TikTok y redes sociales. Escribes en espanol perfecto. Usas SOLO HTML, nunca markdown."},
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
        # Limpiar markdown residual
        contenido = limpiar_contenido_ia(contenido)
        return nuevo_titulo, contenido
    except Exception as e:
        log("Error con OpenAI: " + str(e))
        contenido_fallback = "<p>" + descripcion + "</p>"
        return titulo, contenido_fallback

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
        "\n"
        "    <div id=\"navbar-container\"></div>\n"
        "\n"
        "    <div class=\"blog-breadcrumb\">\n"
        "        <div class=\"container\">\n"
        "            <nav aria-label=\"Breadcrumb\">\n"
        "                <ol class=\"breadcrumb-list\">\n"
        "                    <li><a href=\"../index.html\">Inicio</a></li>\n"
        "                    <li><a href=\"./\">Noticias</a></li>\n"
        "                    <li aria-current=\"page\">" + titulo[:50] + "...</li>\n"
        "                </ol>\n"
        "            </nav>\n"
        "        </div>\n"
        "    </div>\n"
        "\n"
        "    <main class=\"content-wrapper blog-article-layout\">\n"
        "        <div class=\"container blog-article-container\">\n"
        "            <article class=\"blog-post\">\n"
        "\n"
        "                <header class=\"post-header\">\n"
        "                    <span class=\"badge badge-primary article-category\">📰 Noticias TikTok</span>\n"
        "                    <h1 class=\"article-title\">" + titulo + "</h1>\n"
        "                    <div class=\"post-meta\">\n"
        "                        <span class=\"post-meta-item\">\n"
        "                            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"3\" y=\"4\" width=\"18\" height=\"18\" rx=\"2\" ry=\"2\"/><line x1=\"16\" x2=\"16\" y1=\"2\" y2=\"6\"/><line x1=\"8\" x2=\"8\" y1=\"2\" y2=\"6\"/><line x1=\"3\" x2=\"21\" y1=\"10\" y2=\"10\"/></svg>\n"
        "                            <time datetime=\"" + fecha.strftime("%Y-%m-%d") + "\">" + fecha_formateada + "</time>\n"
        "                        </span>\n"
        "                        <span class=\"post-meta-separator\">|</span>\n"
        "                        <span class=\"post-meta-item\">\n"
        "                            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"12\" r=\"10\"/><polyline points=\"12 6 12 12 16 14\"/></svg>\n"
        "                            3 min lectura\n"
        "                        </span>\n"
        "                    </div>\n"
        "                </header>\n"
        "\n"
        "                <section class=\"post-intro\">\n"
        "                    <p>Resumen generado automaticamente por inteligencia artificial a partir de fuentes publicas.</p>\n"
        "                </section>\n"
        "\n"
        "                <hr class=\"section-divider\">\n"
        "\n"
        "                <section>\n"
        "                    " + contenido + "\n"
        "                    <div class=\"info-box warning\" style=\"margin-top: 2rem;\">\n"
        "                        <span class=\"box-title\">⚠️ Aviso importante</span>\n"
        "                        <p>Este articulo es un <strong>resumen generado automaticamente por IA</strong> a partir de noticias publicas. La informacion original proviene de: <a href=\"" + url_fuente + "\" target=\"_blank\" rel=\"noopener noreferrer\">Ver fuente original</a></p>\n"
        "                    </div>\n"
        "                </section>\n"
        "\n"
        "                <footer class=\"post-footer\">\n"
        "                    <div class=\"post-footer-card\">\n"
        "                        <h3>Mantente al dia con TikPanel</h3>\n"
        "                        <p>Descubre las ultimas novedades sobre TikTok, el algoritmo y las mejores herramientas para creadores. Visita nuestra seccion de <a href=\"index.html\">noticias</a> o descarga TikPanel para llevar tus directos al siguiente nivel.</p>\n"
        "                    </div>\n"
        "                </footer>\n"
        "\n"
        "                <nav class=\"article-nav\" aria-label=\"Navegacion de articulos\">\n"
        "                    <a href=\"index.html\" class=\"article-nav-back\">\n"
        "                        <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m15 18-6-6 6-6\"/></svg>\n"
        "                        Volver a Noticias\n"
        "                    </a>\n"
        "                </nav>\n"
        "\n"
        "            </article>\n"
        "        </div>\n"
        "    </main>\n"
        "\n"
        "    <div id=\"footer-container\"></div>\n"
        "\n"
        "    <script src=\"../shared-components.js\"></script>\n"
        "</body>\n"
        "</html>"
    )
    
    archivo = NOTICIAS_DIR / slug
    with open(archivo, "w", encoding="utf-8") as f:
        f.write(html)
    return archivo.name

def actualizar_index(extractos):
    entradas = []
    for f in sorted(NOTICIAS_DIR.glob("*.html")):
        if f.name == "index.html":
            continue
        fecha_obj = datetime.fromtimestamp(f.stat().st_mtime)
        titulo = "Noticia"
        extracto = extractos.get(f.name, "Resumen de la noticia sobre TikTok. Haz clic para leer el articulo completo.")
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
            "fecha_str": fecha_obj.strftime("%d %b %Y"),
            "extracto": extracto,
        })
    entradas.sort(key=lambda x: x["fecha"], reverse=True)
    
    items_html = ""
    for e in entradas[:30]:
        items_html += (
            "<article class=\"blog-card\">\n"
            "    <div class=\"blog-card-body\">\n"
            "        <div class=\"blog-card-meta\">\n"
            "            <time datetime=\"\">📅 " + e["fecha_str"] + "</time>\n"
            "            <span class=\"blog-card-readtime\">3 min lectura</span>\n"
            "        </div>\n"
            "        <h2 class=\"blog-card-title\">\n"
            "            <a href=\"" + e["archivo"] + "\">" + e["titulo"] + "</a>\n"
            "        </h2>\n"
            "        <p class=\"blog-card-excerpt\">" + e["extracto"] + "</p>\n"
            "        <a href=\"" + e["archivo"] + "\" class=\"blog-card-cta\">\n"
            "            Leer mas\n"
            "            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M5 12h14\"/><path d=\"m12 5 7 7-7 7\"/></svg>\n"
            "        </a>\n"
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
        "\n"
        "    <div id=\"navbar-container\"></div>\n"
        "\n"
        "    <section class=\"blog-hero\">\n"
        "        <div class=\"blog-hero-bg\">\n"
        "            <div class=\"hero-orb-1\"></div>\n"
        "            <div class=\"hero-orb-2\"></div>\n"
        "        </div>\n"
        "        <div class=\"container blog-hero-content\">\n"
        "            <span class=\"badge badge-primary blog-badge\">\n"
        "                <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z\"/><path d=\"M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z\"/></svg>\n"
        "                Noticias Automáticas\n"
        "            </span>\n"
        "            <h1 class=\"text-gradient\">Noticias sobre TikTok</h1>\n"
        "            <p>Resumen diario automatico de las noticias mas relevantes sobre TikTok, el algoritmo, monetizacion y tendencias para creadores.</p>\n"
        "            <p class=\"noticias-disclaimer\" style=\"color: var(--text3); font-size: 0.9rem; margin-top: 1.5rem;\">\n"
        "                <small>⚠️ Los articulos son generados automaticamente por IA a partir de fuentes publicas. Siempre se incluye el enlace a la noticia original.</small>\n"
        "            </p>\n"
        "        </div>\n"
        "    </section>\n"
        "\n"
        "    <main class=\"blog-section\">\n"
        "        <div class=\"container\">\n"
        "            <div class=\"blog-grid\">\n"
        "                " + items_html + "\n"
        "            </div>\n"
        "        </div>\n"
        "    </main>\n"
        "\n"
        "    <section class=\"blog-cta-section\">\n"
        "        <div class=\"container\">\n"
        "            <div class=\"blog-cta-card\">\n"
        "                <div class=\"blog-cta-content\">\n"
        "                    <h2>Mantente informado cada dia</h2>\n"
        "                    <p>Esta seccion se actualiza automaticamente con las ultimas noticias sobre TikTok. Vuelve mañana para mas contenido.</p>\n"
        "                    <div class=\"blog-cta-buttons\">\n"
        "                        <a href=\"https://free.tikpanel.app\" class=\"btn btn-primary\" target=\"_blank\">\n"
        "                            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"/><polyline points=\"7 10 12 15 17 10\"/><line x1=\"12\" x2=\"12\" y1=\"15\" y2=\"3\"/></svg>\n"
        "                            Descargar TikPanel\n"
        "                        </a>\n"
        "                        <a href=\"../documentacion.html\" class=\"btn btn-secondary\">Ver Documentacion</a>\n"
        "                    </div>\n"
        "                </div>\n"
        "            </div>\n"
        "        </div>\n"
        "    </section>\n"
        "\n"
        "    <div id=\"footer-container\"></div>\n"
        "\n"
        "    <script src=\"../shared-components.js\"></script>\n"
        "</body>\n"
        "</html>"
    )
    
    with open(NOTICIAS_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)

def main():
    log("Iniciando generacion de noticias automaticas...")
    log("Fecha: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    estado = cargar_estado()
    procesados = set(estado.get("procesados", []))
    extractos = estado.get("extractos", {})
    
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
        extracto = generar_extracto(contenido_ia)
        extractos[slug] = extracto
        nuevas_slugs.append(slug)
        log("Guardado: noticias/" + slug)
    
    log("Actualizando indice de noticias...")
    actualizar_index(extractos)
    
    estado["procesados"] = list(procesados)
    estado["extractos"] = extractos
    estado["ultima_ejecucion"] = ahora.isoformat()
    guardar_estado(estado)
    
    log("Listo! Se generaron " + str(len(nuevas_slugs)) + " noticia(s) nueva(s).")
    for s in nuevas_slugs:
        log("   → noticias/" + s)

if __name__ == "__main__":
    main()

    main()
