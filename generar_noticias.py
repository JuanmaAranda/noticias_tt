#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikPanel - Generador de Noticias Automáticas (PythonAnywhere)"""

import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET
import ftplib

import requests
from openai import OpenAI

# ════════════════════════════════════════════════════════════
# CONFIGURACIÓN - EDITAR ESTAS VARIABLES
# ════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-REEMPLAZA-ESTO-CON-TU-API-KEY")

FTP_HOST = "ftp.tikpanel.app"
FTP_USER = "u208113460.github"
FTP_PASS = "3Kk:~+eR;V*"

REMOTE_DIR = "/noticias"
LOCAL_DIR = Path(".")

# Nota: PythonAnywhere gratuito bloquea algunos dominios.
# Solo Google News RSS funciona seguro. Usamos varias queries.
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
NOTICIAS_DIR = LOCAL_DIR / "noticias"
ESTADO_FILE = LOCAL_DIR / "estado_noticias.json"
NOTICIAS_DIR.mkdir(parents=True, exist_ok=True)

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
            # Convertir a naive (sin timezone) para evitar errores de comparacion
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
        contenido_match = re.search(r"CONTENIDO:\s*(.+)" , texto, re.DOTALL)
        nuevo_titulo = titulo_match.group(1).strip() if titulo_match else titulo
        contenido = contenido_match.group(1).strip() if contenido_match else texto
        return nuevo_titulo, contenido
    except Exception as e:
        log("Error con OpenAI: " + str(e))
        contenido_fallback = "<p>" + descripcion + "</p><p><strong>Fuente original:</strong> <a href=\"" + url_fuente + "\" target=\"_blank\">" + url_fuente + "</a></p>"
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
        "<header class=\"site-header\">\n"
        "    <nav class=\"main-nav\">\n"
        "        <a href=\"../index.html\" class=\"logo\">TikPanel</a>\n"
        "        <ul class=\"nav-links\">\n"
        "            <li><a href=\"../index.html\">Inicio</a></li>\n"
        "            <li><a href=\"../precios.html\">Precios</a></li>\n"
        "            <li><a href=\"../blog/index.html\">Blog</a></li>\n"
        "            <li><a href=\"index.html\" class=\"active\">Noticias</a></li>\n"
        "            <li><a href=\"../soporte.html\">Soporte</a></li>\n"
        "        </ul>\n"
        "    </nav>\n"
        "</header>\n"
        "\n"
        "<main class=\"container\">\n"
        "    <article class=\"noticia-articulo\">\n"
        "        <header class=\"noticia-header\">\n"
        "            <div class=\"noticia-meta\">\n"
        "                <span class=\"noticia-fecha\">📅 " + fecha_formateada + "</span>\n"
        "                <span class=\"noticia-tag\">TikTok</span>\n"
        "            </div>\n"
        "            <h1>" + titulo + "</h1>\n"
        "        </header>\n"
        "        <div class=\"noticia-contenido\">\n"
        "            " + contenido + "\n"
        "            <hr>\n"
        "            <p class=\"noticia-disclaimer\">\n"
        "                <small>⚠️ Este articulo es un <strong>resumen generado automaticamente por IA</strong> "
        "                a partir de noticias publicas. La informacion original proviene de: "
        "                <a href=\"" + url_fuente + "\" target=\"_blank\" rel=\"noopener noreferrer\">" + url_fuente + "</a></small>\n"
        "            </p>\n"
        "        </div>\n"
        "        <footer class=\"noticia-footer\">\n"
        "            <a href=\"index.html\" class=\"btn btn-secondary\">← Volver a todas las noticias</a>\n"
        "        </footer>\n"
        "    </article>\n"
        "</main>\n"
        "\n"
        "<footer class=\"site-footer\">\n"
        "    <p>© " + str(anio) + " TikPanel. Todos los derechos reservados.</p>\n"
        "</footer>\n"
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
        if f.name in ["index.html", "plantilla.html"]:
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
            "    <div class=\"noticia-card-meta\">\n"
            "        <span class=\"noticia-card-fecha\">" + e["fecha_str"] + "</span>\n"
            "    </div>\n"
            "    <h3><a href=\"" + e["archivo"] + "\">" + e["titulo"] + "</a></h3>\n"
            "    <a href=\"" + e["archivo"] + "\" class=\"btn btn-small\">Leer mas →</a>\n"
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
        "    <meta name=\"description\" content=\"Noticias diarias automaticas sobre TikTok.\">\n"
        "    <link rel=\"stylesheet\" href=\"../css/style.css\">\n"
        "</head>\n"
        "<body>\n"
        "<header class=\"site-header\">\n"
        "    <nav class=\"main-nav\">\n"
        "        <a href=\"../index.html\" class=\"logo\">TikPanel</a>\n"
        "        <ul class=\"nav-links\">\n"
        "            <li><a href=\"../index.html\">Inicio</a></li>\n"
        "            <li><a href=\"../precios.html\">Precios</a></li>\n"
        "            <li><a href=\"../blog/index.html\">Blog</a></li>\n"
        "            <li><a href=\"index.html\" class=\"active\">Noticias</a></li>\n"
        "            <li><a href=\"../soporte.html\">Soporte</a></li>\n"
        "        </ul>\n"
        "    </nav>\n"
        "</header>\n"
        "\n"
        "<main class=\"container\">\n"
        "    <section class=\"noticias-hero\">\n"
        "        <h1>📰 Noticias sobre TikTok</h1>\n"
        "        <p>Resumen diario automatico de las noticias mas relevantes sobre TikTok, el algoritmo, monetizacion y tendencias.</p>\n"
        "        <p class=\"noticias-disclaimer\">\n"
        "            <small>⚠️ Los articulos son generados automaticamente por IA a partir de fuentes publicas. Siempre se incluye el enlace a la noticia original.</small>\n"
        "        </p>\n"
        "    </section>\n"
        "\n"
        "    <section class=\"noticias-grid\">\n"
        "        " + items_html + "\n"
        "    </section>\n"
        "</main>\n"
        "\n"
        "<footer class=\"site-footer\">\n"
        "    <p>© " + str(anio) + " TikPanel. Todos los derechos reservados.</p>\n"
        "</footer>\n"
        "</body>\n"
        "</html>"
    )
    
    with open(NOTICIAS_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)

def subir_por_ftp():
    try:
        log("Conectando por FTP...")
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        log("Conectado a " + FTP_HOST)
        
        try:
            ftp.cwd(REMOTE_DIR)
        except ftplib.error_perm:
            log("Creando directorio remoto " + REMOTE_DIR + "...")
            ftp.mkd(REMOTE_DIR)
            ftp.cwd(REMOTE_DIR)
        
        archivos_subidos = 0
        for archivo in NOTICIAS_DIR.glob("*.html"):
            nombre = archivo.name
            with open(archivo, "rb") as f:
                ftp.storbinary("STOR " + nombre, f)
            log("Subido: " + nombre)
            archivos_subidos += 1
        
        ftp.quit()
        log("FTP completado. " + str(archivos_subidos) + " archivo(s) subido(s).")
        return True
    except Exception as e:
        log("Error en FTP: " + str(e))
        return False

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
        log("Guardado localmente: noticias/" + slug)
    
    log("Actualizando indice de noticias...")
    actualizar_index()
    
    estado["procesados"] = list(procesados)
    estado["ultima_ejecucion"] = ahora.isoformat()
    guardar_estado(estado)
    
    log("Subiendo archivos al hosting por FTP...")
    exito = subir_por_ftp()
    
    if exito:
        log("Listo! Se publicaron " + str(len(nuevas_slugs)) + " noticia(s) nueva(s).")
        for s in nuevas_slugs:
            log("   → https://tikpanel.app/noticias/" + s)
    else:
        log("Las noticias se generaron pero no se pudieron subir por FTP.")
        log("Revisa los datos de FTP en la configuracion del script.")

if __name__ == "__main__":
    main()
