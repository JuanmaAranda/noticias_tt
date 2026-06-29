def extraer_contenido_web(url):
    """Extrae el texto relevante de una página web para usar como contexto."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
        
        # Eliminar scripts y estilos
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        
        # Extraer texto de párrafos
        parrafos = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL)
        texto = ' '.join(parrafos)
        
        # Limpiar HTML residual
        texto = re.sub(r'<[^>]+>', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        
        # Limitar a 3000 caracteres para no saturar la API
        if len(texto) > 3000:
            texto = texto[:3000] + "..."
        
        return texto
    except Exception as e:
        log("   ⚠️ No se pudo extraer contenido de " + url + ": " + str(e))
        return ""

def publicar_linkedin(titulo, url_noticia):
    """Publica un post en LinkedIn usando cookies de sesión."""
    LINKEDIN_COOKIES = os.environ.get("LINKEDIN_COOKIES", "")
    LINKEDIN_CSRF = os.environ.get("LINKEDIN_CSRF", "")
    
    if not LINKEDIN_COOKIES or not LINKEDIN_CSRF:
        log("   ⚠️ LinkedIn: No hay cookies configuradas, saltando publicación")
        return False
    
    headers = {
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "content-type": "application/json",
        "cookie": LINKEDIN_COOKIES,
        "csrf-token": LINKEDIN_CSRF,
        "x-restli-protocol-version": "2.0.0",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    payload = {
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": f"📰 {titulo}\n\nLee el artículo completo en:\n{url_noticia}"
                },
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "description": {
                            "text": "Noticias diarias sobre TikTok, algoritmo y creadores de contenido."
                        },
                        "originalUrl": url_noticia,
                        "title": {
                            "text": titulo
                        }
                    }
                ]
            }
        }
    }
    
    try:
        resp = requests.post(
            "https://www.linkedin.com/voyager/api/ugcPosts",
            headers=headers,
            json=payload,
            timeout=20
        )
        if resp.status_code in (200, 201):
            log("   ✅ LinkedIn: Publicado correctamente")
            return True
        elif resp.status_code == 401 or resp.status_code == 403:
            log("   ⚠️ LinkedIn: Cookies expiradas o inválidas (revisa LINKEDIN_COOKIES)")
            return False
        else:
            log("   ⚠️ LinkedIn: Error " + str(resp.status_code) + " - " + resp.text[:200])
            return False
    except Exception as e:
        log("   ⚠️ LinkedIn: Error de conexión - " + str(e))
        return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikPanel - Generador de Noticias Automáticas"""

import os
import json
import re
import hashlib
import difflib
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from openai import OpenAI

# Configuración de APIs
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Inicializar cliente de IA
client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    USAR_GEMINI = False
    print("[OK] Usando OpenAI como motor de IA")
elif GEMINI_API_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    USAR_GEMINI = True
    print("[OK] Usando Gemini como motor de IA")
else:
    print("[ERROR] No hay API key configurada. Configura OPENAI_API_KEY o GEMINI_API_KEY.")
    USAR_GEMINI = False
    USAR_GEMINI = False

FEEDS_FILE = Path("feeds.json")

def cargar_feeds():
    """Carga la lista de feeds RSS desde feeds.json (ahora obsoleto, usamos NewsAPI)"""
    return []

def obtener_noticias_newsapi():
    """Obtiene noticias sobre TikTok usando NewsAPI."""
    NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
    if not NEWSAPI_KEY:
        log("[ERROR] No hay NEWSAPI_KEY configurada")
        return []
    
    try:
        fecha_hace_7_dias = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "TikTok",
            "from": fecha_hace_7_dias,
            "to": datetime.now().strftime('%Y-%m-%d'),
            "language": "es",
            "sortBy": "relevancy",
            "pageSize": 20,
            "apiKey": NEWSAPI_KEY
        }
        
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") != "ok":
            log("[ERROR] NewsAPI error: " + data.get("message", "Unknown error"))
            return []
        
        items = []
        for article in data.get("articles", []):
            titulo = article.get("title", "")
            url_articulo = article.get("url", "")
            desc = article.get("description", "") or ""
            fecha_str = article.get("publishedAt", "")
            
            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%SZ") if fecha_str else None
            except ValueError:
                fecha = None
            
            if titulo and url_articulo and "tiktok" in titulo.lower():
                items.append({
                    "titulo": titulo.strip(),
                    "url": url_articulo.strip(),
                    "descripcion": desc.strip(),
                    "fecha": fecha,
                    "fecha_str": fecha_str,
                    "fuente": "newsapi",
                })
        
        log("[OK] NewsAPI: " + str(len(items)) + " noticias sobre TikTok encontradas")
        return items
        
    except Exception as e:
        log("[ERROR] NewsAPI: " + str(e))
        return []

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

# Resumen de ejecución para email
RESUMEN_EJECUCION = {"estado": "iniciado", "noticias_generadas": 0, "errores": [], "mensajes": []}

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

def noticia_ya_existe_ia(nuevo_titulo, nueva_desc, titulos_existentes):
    """Utiliza la IA para saber si conceptualmente la noticia ya se ha publicado."""
    if not titulos_existentes:
        return False
        
    # Pasamos solo los últimos 20 títulos para optimizar el contexto
    contexto_existente = "\n".join([f"- {t}" for t in titulos_existentes[-20:]])
    
    prompt = (
        "Se te proporciona una lista de noticias que ya han sido publicadas en un blog, "
        "y los datos de una nueva noticia entrante.\n\n"
        "NOTICIAS YA PUBLICADAS:\n"
        f"{contexto_existente}\n\n"
        "NUEVA NOTICIA CANDIDATA:\n"
        f"- Titulo: {nuevo_titulo}\n"
        f"- Descripción: {nueva_desc}\n\n"
        "Tu tarea es determinar si la nueva noticia candidata describe exactamente EL MISMO HECHO O EVENTO REAL "
        "que alguna de las ya publicadas, aunque esté redactada con palabras totalmente distintas.\n\n"
        "Responde ÚNICAMENTE con la palabra 'DUPLICADO' si el hecho central ya existe, "
        "o 'NUEVO' si es un hecho o actualización completamente diferente.\n"
        "Respuesta:"
    )
    
    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un asistente editorial estricto. Solo respondes 'DUPLICADO' o 'NUEVO'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=5
        )
        veredicto = respuesta.choices[0].message.content.strip().upper()
        return "DUPLICADO" in veredicto
    except Exception as e:
        log(f"Error en validación de duplicados por IA: {e}")
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

def obtener_feed(url):
    """Obtiene noticias de una fuente RSS (ahora obsoleto, usamos NewsAPI)."""
    return []

def cargar_estado():
    if ESTADO_FILE.exists():
        try:
            with open(ESTADO_FILE, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return json.loads(contenido)
        except (json.JSONDecodeError, ValueError):
            log("⚠️ estado_noticias.json corrupto, iniciando desde cero")
    return {"procesados": [], "ultima_ejecucion": None, "extractos": {}, "titulos": []}

def guardar_estado(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def limpiar_estado(estado):
    archivos_existentes = {f.name for f in NOTICIAS_DIR.glob("*.html") if f.name != "index.html"}
    extractos = estado.get("extractos", {})
    extractos_limpio = {k: v for k, v in extractos.items() if k in archivos_existentes}
    if len(extractos_limpio) != len(extractos):
        log("🧹 Eliminados " + str(len(extractos) - len(extractos_limpio)) + " extractos de artículos borrados")

    titulos_limpio = []
    for f in sorted(NOTICIAS_DIR.glob("*.html")):
        if f.name == "index.html":
            continue
        try:
            with open(f, "r", encoding="utf-8") as file:
                html = file.read()
                t_match = re.search(r"<title>(.+?)\s*\|", html)
                if t_match:
                    titulos_limpio.append(t_match.group(1).strip())
        except:
            pass

    estado["extractos"] = extractos_limpio
    estado["titulos"] = titulos_limpio
    return estado

def generar_slug(titulo):
    slug = normalizar_texto(titulo)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:60].strip("-")
    return slug + ".html"

def limpiar_markdown(contenido):
    contenido = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", contenido)
    contenido = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<em>\1</em>", contenido)
    return contenido

def limpiar_urls(contenido):
    patron = re.compile(r"(https?://[^\s<>]+)")
    def link_replacer(match):
        url = match.group(1)
        if len(url) > 60:
            return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">Ver fuente</a>'
        return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>'
    return patron.sub(link_replacer, contenido)

def limpiar_fuentes(contenido):
    # Eliminar fuentes originales en varios formatos
    contenido = re.sub(r"\n?---\n?\s*Fuente original:\s*.*?\n?", "", contenido, flags=re.DOTALL)
    contenido = re.sub(r"<p>\s*---+\s*Fuente original:.*?</p>", "", contenido, flags=re.DOTALL)
    contenido = re.sub(r"---+\s*Fuente original:.*", "", contenido, flags=re.DOTALL)
    contenido = re.sub(r"\n?\[.*?\]\(https?://.*?\)\n?", "", contenido)
    return contenido.strip()

def generar_extracto(contenido_html, max_chars=140):
    texto = re.sub(r"<[^>]+>", "", contenido_html)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > max_chars:
        texto = texto[:max_chars].rsplit(" ", 1)[0] + "..."
    return texto

def generar_articulo_ia(titulo, descripcion, url_fuente):
    # Extraer contenido real de la web si es posible
    contenido_web = extraer_contenido_web(url_fuente)
    
    prompt = (
        "INSTRUCCIÓN ABSOLUTA: Eres un PERIODISTA DE AGENCIA. Tu trabajo es LEER el texto fuente, EXTRAER los hechos reales que contiene, y REDACTAR un artículo periodístico completo con esos hechos.\n\n"
        "REGLAS CRÍTICAS (INCUMPLIR = RESPUESTA INVÁLIDA):\n"
        "1. NO hagas un resumen. NO condenses la información. REDACTA un artículo completo con TODOS los hechos del texto.\n"
        "2. NO interpretes, NO añadas tu opinión, NO infieras nada que no esté explícito en el texto.\n"
        "3. NO inventes nombres, empresas, cifras, fechas, lugares o datos que no aparezcan en el texto fuente.\n"
        "4. Si el texto no menciona un protagonista, NO inventes uno genérico como 'la plataforma' o 'los expertos'.\n"
        "5. Si el texto no menciona una fecha concreta, NO inventes 'recientemente' o 'en los últimos días'.\n"
        "6. PROHIBIDO: 'en el dinámico mundo', 'revolucionario', 'crucial', 'es fundamental', 'un hito', 'fascinante', 'cada vez más', 'en la era digital'.\n"
        "7. PROHIBIDO usar frases genéricas que no aporten información específica del texto fuente.\n"
        "8. NO incluyas fuentes, enlaces, ni referencias al final del artículo.\n\n"
        "REGLAS DE REDACCIÓN:\n"
        "9. Escribe entre 300-500 palabras (NO menos de 300).\n"
        "10. Usa 4-6 párrafos con información sustancial en cada uno.\n"
        "11. Cada párrafo debe contener datos concretos extraídos del texto.\n"
        "12. Usa <strong> solo para nombres propios, empresas, cifras y datos concretos.\n\n"
        "TEXTO FUENTE (del que debes extraer los hechos):\n"
        "---\n"
        + (contenido_web if contenido_web else descripcion) + "\n"
        "---\n\n"
        "FORMATO DE RESPUESTA (EXACTO):\n"
        "TITULO: <titular con datos concretos, máx 70 caracteres>\n"
        "CONTENIDO: <cuerpo en HTML con <p> y <strong> solo para datos reales>"
    )
    
    try:
        if USAR_GEMINI and GEMINI_API_KEY:
            # Intentar con Gemini primero
            try:
                model = genai.GenerativeModel('gemini-2.0-flash')
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=1500,
                    )
                )
                texto = response.text.strip()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                    log("   ⚠️ Gemini cuota excedida (429), intentando con OpenAI...")
                    if client:
                        respuesta = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": "Eres un periodista de agencia. Extraes hechos reales de textos fuente sin inventar nada. Si no hay dato concreto, no lo menciones."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.1,
                            max_tokens=1500,
                        )
                        texto = respuesta.choices[0].message.content.strip()
                    else:
                        raise Exception("No hay API de OpenAI configurada para fallback")
                else:
                    raise
        elif client:
            # Usar OpenAI directamente
            respuesta = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un periodista de agencia. Extraes hechos reales de textos fuente sin inventar nada. Si no hay dato concreto, no lo menciones."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            texto = respuesta.choices[0].message.content.strip()
        else:
            # Sin API disponible
            log("   ❌ No hay API de IA configurada")
            return titulo, "<p>" + descripcion + "</p>"
            log("⚠️ No hay API de IA disponible, usando descripción como contenido")
            return titulo, "<p>" + descripcion + "</p>"
        
        # Extraer título y contenido
        titulo_match = re.search(r"TITULO:\s*(.+?)(?=\n|CONTENIDO:)", texto, re.DOTALL)
        contenido_match = re.search(r"CONTENIDO:\s*(.+)", texto, re.DOTALL)
        nuevo_titulo = titulo_match.group(1).strip() if titulo_match else titulo
        contenido = contenido_match.group(1).strip() if contenido_match else texto
        contenido = limpiar_markdown(contenido)
        contenido = limpiar_urls(contenido)
        contenido = limpiar_fuentes(contenido)
        return nuevo_titulo, contenido
    except Exception as e:
        log("Error con la IA: " + str(e))
        contenido_fallback = "<p>" + descripcion + "</p>"
        return titulo, contenido_fallback

def crear_html_noticia(titulo, contenido, url_fuente, fecha, slug):
    fecha_formateada = fecha.strftime("%d de %B de %Y") if fecha else datetime.now().strftime("%d de %B de %Y")
    meta_desc = generar_extracto(contenido, 150)

    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"es\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "    <title>" + titulo + " | Noticias TikPanel</title>\n"
        "    <meta name=\"description\" content=\"" + meta_desc + "\">\n"
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
        "                    <p>Resumen informativo de actualidad redactado en base a reportes del sector.</p>\n"
        "                </section>\n"
        "\n"
        "                <hr class=\"section-divider\">\n"
        "\n"
        "                <section class=\"article-body-content\">\n"
        "                    " + contenido + "\n"
        "                    <div class=\"info-box warning\" style=\"margin-top: 1rem;\">\n"
        "                        <span class=\"box-title\">⚠️ Referencia externa</span>\n"
        "                        <p>Este contenido ha sido estructurado de forma informativa. Puedes consultar los detalles adicionales en la <a href=\"" + url_fuente + "\" target=\"_blank\" rel=\"noopener noreferrer\">fuente original de la noticia</a>.</p>\n"
        "                    </div>\n"
        "                </section>\n"
        "\n"
        "                <footer class=\"post-footer\">\n"
        "                    <div class=\"post-footer-card\">\n"
        "                        <h3>Mantente al día con TikPanel</h3>\n"
        "                        <p>Descubre las últimas novedades sobre TikTok, el algoritmo y las mejores herramientas para creadores. Visita nuestra sección de <a href=\"index.html\">noticias</a> o descarga TikPanel para llevar tus directos al siguiente nivel.</p>\n"
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
        extracto = extractos.get(f.name, "Resumen de la noticia sobre TikTok. Haz clic para leer el artículo completo.")
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
            "            <time datetime=\"\"><svg xmlns=\"http://www.w3.org/2000/svg\" width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"3\" y=\"4\" width=\"18\" height=\"18\" rx=\"2\" ry=\"2\"/><line x1=\"16\" x2=\"16\" y1=\"2\" y2=\"6\"/><line x1=\"8\" x2=\"8\" y1=\"2\" y2=\"6\"/><line x1=\"3\" x2=\"21\" y1=\"10\" y2=\"10\"/></svg> " + e["fecha_str"] + "</time>\n"
            "            <span class=\"blog-card-readtime\">3 min lectura</span>\n"
            "        </div>\n"
            "        <h2 class=\"blog-card-title\">\n"
            "            <a href=\"" + e["archivo"] + "\">" + e["titulo"] + "</a>\n"
            "        </h2>\n"
            "        <p class=\"blog-card-excerpt\">" + e["extracto"] + "</p>\n"
            "        <a href=\"" + e["archivo"] + "\" class=\"blog-card-cta\">\n"
            "            Leer más\n"
            "            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M5 12h14\"/><path d=\"m12 5 7 7-7 7\"/></svg>\n"
            "        </a>\n"
            "    </div>\n"
            "</article>\n"
        )

    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"es\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "    <title>Noticias sobre TikTok | TikPanel</title>\n"
        "    <meta name=\"description\" content=\"Noticias diarias automáticas sobre TikTok, algoritmo, creadores y tendencias.\">\n"
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
        "            <p>Resumen diario automático de las noticias más relevantes sobre TikTok, el algoritmo, monetización y tendencias para creadores.</p>\n"
        "            <p class=\"noticias-disclaimer\" style=\"color: var(--text3); font-size: 0.9rem; margin-top: 1.5rem;\">\n"
        "                <small>⚠️ Los artículos son generados automáticamente por IA a partir de fuentes públicas. Siempre se incluye el enlace a la noticia original.</small>\n"
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
        "                    <h2>Mantente informado cada día</h2>\n"
        "                    <p>Esta sección se actualización automáticamente con las últimas noticias sobre TikTok. Vuelve mañana para más contenido.</p>\n"
        "                    <div class=\"blog-cta-buttons\">\n"
        "                        <a href=\"https://free.tikpanel.app\" class=\"btn btn-primary\" target=\"_blank\">\n"
        "                            <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"/><polyline points=\"7 10 12 15 17 10\"/><line x1=\"12\" x2=\"12\" y1=\"15\" y2=\"3\"/></svg>\n"
        "                            Descargar TikPanel\n"
        "                        </a>\n"
        "                        <a href=\"../documentacion.html\" class=\"btn btn-secondary\">Ver Documentación</a>\n"
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
    log("Iniciando generación de noticias automáticas...")
    estado = cargar_estado()
    estado = limpiar_estado(estado)

    procesados = set(estado.get("procesados", []))
    extractos = estado.get("extractos", {})
    titulos_procesados = estado.get("titulos", [])

    # Cargar noticias borradas desde el panel (si existe)
    borradas_file = Path("panel/borradas.txt")
    borradas = set()
    if borradas_file.exists():
        with open(borradas_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    borradas.add(line)
        log("🗑 " + str(len(borradas)) + " noticia(s) marcada(s) como borrada(s) en el panel")

    # Eliminar archivos de noticias borradas del repo local
    for slug in borradas:
        path = NOTICIAS_DIR / slug
        if path.exists():
            path.unlink()
            log("   Eliminado del repo: " + slug)
        # También eliminar del estado si existe
        if slug in extractos:
            del extractos[slug]

    # Cargar feeds desde NewsAPI (en lugar de RSS)
    log("📡 Consultando NewsAPI para noticias sobre TikTok...")
    todas_noticias = obtener_noticias_newsapi()
    
    if not todas_noticias:
        log("No se encontraron noticias en NewsAPI. Saliendo.")
        guardar_estado(estado)
        return

    ahora = datetime.now()
    limite = ahora - timedelta(days=7)
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

    log(str(len(candidatas)) + " noticias candidatas tras filtrar relevancia básica")

    if not candidatas:
        log("No hay noticias nuevas relevantes hoy. Saliendo.")
        guardar_estado(estado)
        return

    publicadas_hoy = 0
    nuevas_slugs = []

    for noticia in candidatas:
        if publicadas_hoy >= MAX_NOTICIAS_POR_DIA:
            break

        # Filtro semántico dinámico por IA justo antes de procesar
        if noticia_ya_existe_ia(noticia["titulo"], noticia["descripcion"], titulos_procesados):
            log("   ⏭ Saltado de forma dinámica (Duplicado conceptual detectado): " + noticia["titulo"][:60])
            continue

        log("Procesando: " + noticia["titulo"][:80] + "...")
        titulo_ia, contenido_ia = generar_articulo_ia(
            noticia["titulo"],
            noticia["descripcion"],
            noticia["url"]
        )
        
        slug = generar_slug(titulo_ia)
        
        # Verificar que el slug no esté en la lista de borradas
        if slug in borradas:
            log("   ⏭ Saltado (noticia previamente borrada desde el panel): " + slug)
            continue
        
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
        
        # Agregamos inmediatamente al listado en memoria para que el siguiente elemento del bucle lo herede
        titulos_procesados.append(titulo_ia)
        nuevas_slugs.append(slug)
        publicadas_hoy += 1
        log("Guardado: noticias/" + slug)
        
        # Publicar en LinkedIn
        url_noticia = "https://tikpanel.app/noticias/" + slug
        publicar_linkedin(titulo_ia, url_noticia)

    log("Actualizando índice de noticias...")
    actualizar_index(extractos)

    estado["procesados"] = list(procesados)
    estado["extractos"] = extractos
    estado["titulos"] = titulos_procesados
    estado["ultima_ejecucion"] = ahora.isoformat()
    guardar_estado(estado)

    RESUMEN_EJECUCION["noticias_generadas"] = len(nuevas_slugs)
    if len(nuevas_slugs) > 0:
        RESUMEN_EJECUCION["estado"] = "ok"
    else:
        RESUMEN_EJECUCION["estado"] = "sin_noticias"
    guardar_resumen()

    log("Listo! Se generaron " + str(len(nuevas_slugs)) + " noticia(s) nueva(s).")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(str(e))
        guardar_resumen()
        raise
