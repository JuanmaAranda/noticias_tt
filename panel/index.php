<?php
/**
 * TikPanel News - Panel de Control Simplificado
 * Subir a: /panel/index.php en el servidor
 * 
 * Funciona SIN base de datos. Usa archivos directamente.
 * Las noticias borradas se guardan en borradas.txt
 */

// ============================================================
// CONFIGURACIÓN
// ============================================================

// Cargar configuración sensible desde archivo local (no en GitHub)
$config_file = __DIR__ . '/config.php';
if (file_exists($config_file)) {
    require_once $config_file;
}

// Valores por defecto si no hay config.php
if (!defined('PANEL_PASSWORD_HASH')) {
    define('PANEL_PASSWORD_HASH', 'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3'); // "123"
}
if (!defined('OPENAI_API_KEY')) {
    define('OPENAI_API_KEY', '');
}

// Ruta a la carpeta de noticias (relativa a este archivo)
$NOTICIAS_DIR = dirname(__DIR__) . '/noticias/';
$BORRADAS_FILE = __DIR__ . '/borradas.txt';

// ============================================================
// AUTENTICACIÓN
// ============================================================

session_start();

function is_authenticated() {
    return isset($_SESSION['auth']) && $_SESSION['auth'] === true;
}

function require_auth() {
    if (!is_authenticated()) {
        header('Location: ?page=login');
        exit;
    }
}

function login($password) {
    $hash = hash('sha256', $password);
    return $hash === PANEL_PASSWORD_HASH;
}

// ============================================================
// UTILIDADES
// ============================================================

function generar_extracto($html, $max = 140) {
    $texto = strip_tags($html);
    $texto = preg_replace('/\s+/', ' ', $texto);
    $texto = trim($texto);
    if (strlen($texto) > $max) {
        $texto = substr($texto, 0, $max);
        $last_space = strrpos($texto, ' ');
        if ($last_space !== false) {
            $texto = substr($texto, 0, $last_space) . '...';
        }
    }
    return $texto;
}

function parsear_info_noticia($archivo_path) {
    if (!file_exists($archivo_path)) return null;
    $html = file_get_contents($archivo_path);
    if (!$html) return null;

    $info = [
        'archivo' => basename($archivo_path),
        'titulo' => 'Sin título',
        'fecha' => null,
        'fecha_str' => '',
        'extracto' => '',
        'contenido' => '',
        'url_fuente' => '',
    ];

    if (preg_match('/<title>(.+?)\s*\|/', $html, $m)) {
        $info['titulo'] = trim($m[1]);
    }
    if (preg_match('/<time datetime="([^"]+)">([^<]+)<\/time>/', $html, $m)) {
        $info['fecha_str'] = trim($m[2]);
        $info['fecha'] = $m[1];
    }
    if (preg_match('/<a href="([^"]+)"[^>]*>fuente original/i', $html, $m)) {
        $info['url_fuente'] = $m[1];
    } elseif (preg_match('/Referencia externa.*?<a href="([^"]+)"/si', $html, $m)) {
        $info['url_fuente'] = $m[1];
    }
    if (preg_match('/<section class="article-body-content">(.*?)<div class="info-box warning"/s', $html, $m)) {
        $contenido = trim($m[1]);
        $contenido = preg_replace('/<p>Resumen informativo de actualidad.*?<\/p>/i', '', $contenido);
        $info['contenido'] = trim($contenido);
        $info['extracto'] = generar_extracto($contenido);
    }

    return $info;
}

function listar_noticias() {
    global $NOTICIAS_DIR, $BORRADAS_FILE;
    $noticias = [];
    if (!is_dir($NOTICIAS_DIR)) return $noticias;

    // Cargar lista de borradas
    $borradas = [];
    if (file_exists($BORRADAS_FILE)) {
        $borradas = array_map('trim', file($BORRADAS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
    }
    $borradas = array_flip($borradas);

    foreach (glob($NOTICIAS_DIR . '*.html') as $f) {
        if (basename($f) === 'index.html') continue;
        if (isset($borradas[basename($f)])) continue; // Saltar borradas
        $info = parsear_info_noticia($f);
        if ($info) {
            $info['mtime'] = filemtime($f);
            $noticias[] = $info;
        }
    }

    usort($noticias, function($a, $b) {
        return $b['mtime'] - $a['mtime'];
    });

    return $noticias;
}

function crear_html_noticia($titulo, $contenido, $url_fuente, $fecha, $slug) {
    global $NOTICIAS_DIR;
    $fecha_formateada = date('d \d\e F \d\e Y', strtotime($fecha));
    $meta_desc = generar_extracto($contenido, 150);
    $fecha_iso = date('Y-m-d', strtotime($fecha));
    $titulo_corto = substr($titulo, 0, 50);

    $html = <<<HTML
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{$titulo} | Noticias TikPanel</title>
    <meta name="description" content="{$meta_desc}">
    <link rel="stylesheet" href="../css/style.css">
</head>
<body>

    <div id="navbar-container"></div>

    <div class="blog-breadcrumb">
        <div class="container">
            <nav aria-label="Breadcrumb">
                <ol class="breadcrumb-list">
                    <li><a href="../index.html">Inicio</a></li>
                    <li><a href="./">Noticias</a></li>
                    <li aria-current="page">{$titulo_corto}...</li>
                </ol>
            </nav>
        </div>
    </div>

    <main class="content-wrapper blog-article-layout">
        <div class="container blog-article-container">
            <article class="blog-post">

                <header class="post-header">
                    <span class="badge badge-primary article-category">📰 Noticias TikTok</span>
                    <h1 class="article-title">{$titulo}</h1>
                    <div class="post-meta">
                        <span class="post-meta-item">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                            <time datetime="{$fecha_iso}">{$fecha_formateada}</time>
                        </span>
                        <span class="post-meta-separator">|</span>
                        <span class="post-meta-item">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            3 min lectura
                        </span>
                    </div>
                </header>

                <section class="post-intro">
                    <p>Resumen informativo de actualidad redactado en base a reportes del sector.</p>
                </section>

                <hr class="section-divider">

                <section class="article-body-content">
                    {$contenido}
                    <div class="info-box warning" style="margin-top: 2rem;">
                        <span class="box-title">⚠️ Referencia externa</span>
                        <p>Este contenido ha sido estructurado de forma informativa. Puedes consultar los detalles adicionales en la <a href="{$url_fuente}" target="_blank" rel="noopener noreferrer">fuente original de la noticia</a>.</p>
                    </div>
                </section>

                <footer class="post-footer">
                    <div class="post-footer-card">
                        <h3>Mantente al día con TikPanel</h3>
                        <p>Descubre las últimas novedades sobre TikTok, el algoritmo y las mejores herramientas para creadores. Visita nuestra sección de <a href="index.html">noticias</a> o descarga TikPanel para llevar tus directos al siguiente nivel.</p>
                    </div>
                </footer>

                <nav class="article-nav" aria-label="Navegacion de articulos">
                    <a href="index.html" class="article-nav-back">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                        Volver a Noticias
                    </a>
                </nav>

            </article>
        </div>
    </main>

    <div id="footer-container"></div>

    <script src="../shared-components.js"></script>
</body>
</html>
HTML;

    file_put_contents($NOTICIAS_DIR . $slug, $html);
    return $slug;
}

function actualizar_index() {
    global $NOTICIAS_DIR, $BORRADAS_FILE;
    $entradas = [];

    // Cargar borradas
    $borradas = [];
    if (file_exists($BORRADAS_FILE)) {
        $borradas = array_map('trim', file($BORRADAS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
    }
    $borradas = array_flip($borradas);

    foreach (glob($NOTICIAS_DIR . '*.html') as $f) {
        if (basename($f) === 'index.html') continue;
        if (isset($borradas[basename($f)])) continue;

        $fecha_obj = filemtime($f);
        $titulo = 'Noticia';
        $extracto = 'Resumen de la noticia sobre TikTok. Haz clic para leer el artículo completo.';

        $html = file_get_contents($f);
        if (preg_match('/<title>(.+?)\s*\|/', $html, $m)) {
            $titulo = trim($m[1]);
        }
        if (preg_match('/<section class="article-body-content">(.*?)<div class="info-box warning"/s', $html, $m)) {
            $extracto = generar_extracto($m[1]);
        }

        $entradas[] = [
            'archivo' => basename($f),
            'titulo' => $titulo,
            'fecha' => $fecha_obj,
            'fecha_str' => date('d M Y', $fecha_obj),
            'extracto' => $extracto,
        ];
    }

    usort($entradas, function($a, $b) {
        return $b['fecha'] - $a['fecha'];
    });

    $items_html = '';
    foreach (array_slice($entradas, 0, 30) as $e) {
        $items_html .= <<<HTML
<article class="blog-card">
    <div class="blog-card-body">
        <div class="blog-card-meta">
            <time datetime="">📅 {$e['fecha_str']}</time>
            <span class="blog-card-readtime">3 min lectura</span>
        </div>
        <h2 class="blog-card-title">
            <a href="{$e['archivo']}">{$e['titulo']}</a>
        </h2>
        <p class="blog-card-excerpt">{$e['extracto']}</p>
        <a href="{$e['archivo']}" class="blog-card-cta">
            Leer más
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        </a>
    </div>
</article>
HTML;
    }

    $html = <<<HTML
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Noticias sobre TikTok | TikPanel</title>
    <meta name="description" content="Noticias diarias automáticas sobre TikTok, algoritmo, creadores y tendencias.">
    <link rel="stylesheet" href="../css/style.css">
</head>
<body>

    <div id="navbar-container"></div>

    <section class="blog-hero">
        <div class="blog-hero-bg">
            <div class="hero-orb-1"></div>
            <div class="hero-orb-2"></div>
        </div>
        <div class="container blog-hero-content">
            <span class="badge badge-primary blog-badge">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                Noticias Automáticas
            </span>
            <h1 class="text-gradient">Noticias sobre TikTok</h1>
            <p>Resumen diario automático de las noticias más relevantes sobre TikTok, el algoritmo, monetización y tendencias para creadores.</p>
            <p class="noticias-disclaimer" style="color: var(--text3); font-size: 0.9rem; margin-top: 1.5rem;">
                <small>⚠️ Los artículos son generados automáticamente por IA a partir de fuentes públicas. Siempre se incluye el enlace a la noticia original.</small>
            </p>
        </div>
    </section>

    <main class="blog-section">
        <div class="container">
            <div class="blog-grid">
                {$items_html}
            </div>
        </div>
    </main>

    <section class="blog-cta-section">
        <div class="container">
            <div class="blog-cta-card">
                <div class="blog-cta-content">
                    <h2>Mantente informado cada día</h2>
                    <p>Esta sección se actualiza automáticamente con las últimas noticias sobre TikTok. Vuelve mañana para más contenido.</p>
                    <div class="blog-cta-buttons">
                        <a href="https://free.tikpanel.app" class="btn btn-primary" target="_blank">
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                            Descargar TikPanel
                        </a>
                        <a href="../documentacion.html" class="btn btn-secondary">Ver Documentación</a>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <div id="footer-container"></div>

    <script src="../shared-components.js"></script>
</body>
</html>
HTML;

    file_put_contents($NOTICIAS_DIR . 'index.html', $html);
}

function reescribir_con_ia($titulo, $descripcion, $url_fuente, $api_key) {
    $prompt = "Eres un periodista tecnológico y redactor SEO experto para la plataforma TikPanel (tikpanel.app).\n\n"
        . "Tu objetivo es redactar una noticia original, informativa y de alto valor periodístico basada en datos externos. "
        . "Google penaliza el contenido genérico, así que debes enfocarte en HECHOS, DATOS, NOMBRES y PROTAGONISTAS reales. "
        . "No inventes cosas que no estén en el texto original, pero extrae y enfatiza cada detalle concreto que encuentres.\n\n"
        . "INFORMACIÓN ORIGINAL EXTRAÍDA DEL FEED:\n"
        . "- Titulo original: " . $titulo . "\n"
        . "- Descripción original: " . $descripcion . "\n\n"
        . "REGLAS DE REDACCIÓN Y SEO (ESTRICTAS):\n"
        . "1. Enfócate al 100% en los hechos ocurridos. ¿Qué pasó? ¿Quién lo hizo? ¿Cuándo? Evita generalidades.\n"
        . "2. PROHIBIDO usar lenguaje cliché de IA. No uses palabras como: 'en el dinámico mundo', 'revolucionario', 'crucial', 'es fundamental', 'un hito', 'fascinante'. Sé directo y periodístico.\n"
        . "3. Longitud: Entre 300 y 450 palabras organizadas de forma lógica.\n"
        . "4. El artículo debe ser útil para creadores de contenido, streamers y marketers que usan TikTok.\n\n"
        . "ESTRUCTURA DEL OUTPUT:\n"
        . "- TITULO: Un titular periodístico limpio, optimizado para SEO (máx. 70 caracteres), que incluya palabras clave naturales.\n"
        . "- CONTENIDO: El cuerpo de la noticia en formato HTML puro. Organízalo con etiquetas <p> para párrafos normales. Usa <strong>únicamente</strong> para destacar palabras clave importantes (máx 3-4 por párrafo). Puedes incluir un subtítulo intermedio usando <h3> si ayuda a estructurar el texto.\n\n"
        . "Responde ÚNICAMENTE en este formato estructural exacto:\n"
        . "TITULO: <titular aquí>\n"
        . "CONTENIDO: <cuerpo en HTML aquí>";

    $ch = curl_init('https://api.openai.com/v1/chat/completions');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json',
        'Authorization: Bearer ' . $api_key
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
        'model' => 'gpt-4o-mini',
        'messages' => [
            ['role' => 'system', 'content' => 'Eres un redactor SEO y periodista de tecnología. Escribes con un tono informativo, directo, sin introducciones vacías ni palabras cliché de IA. Usas exclusivamente etiquetas HTML (<p>, <strong>, <h3>).'],
            ['role' => 'user', 'content' => $prompt]
        ],
        'temperature' => 0.4,
        'max_tokens' => 1500
    ]));

    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($http_code !== 200 || !$response) {
        return [null, 'Error en la API de OpenAI: HTTP ' . $http_code];
    }

    $data = json_decode($response, true);
    $texto = $data['choices'][0]['message']['content'] ?? '';

    $nuevo_titulo = $titulo;
    $contenido = '';

    if (preg_match('/TITULO:\s*(.+?)(?=\n|CONTENIDO:)/s', $texto, $m)) {
        $nuevo_titulo = trim($m[1]);
    }
    if (preg_match('/CONTENIDO:\s*(.+)/s', $texto, $m)) {
        $contenido = trim($m[1]);
    }

    // Limpiar markdown
    $contenido = preg_replace('/\*\*(.+?)\*\*/', '<strong>$1</strong>', $contenido);
    $contenido = preg_replace('/(?<!\*)\*(.+?)\*(?!\*)/', '<em>$1</em>', $contenido);

    // Limpiar URLs
    $contenido = preg_replace_callback('/(https?:\/\/[^\s<>]+)/', function($m) {
        $url = $m[1];
        $texto = strlen($url) > 60 ? 'Ver fuente' : $url;
        return '<a href="' . $url . '" target="_blank" rel="noopener noreferrer">' . $texto . '</a>';
    }, $contenido);

    // Limpiar fuentes
    $contenido = preg_replace('/<p>\s*---+\s*Fuente original:.*?<\/p>/s', '', $contenido);
    $contenido = preg_replace('/---+\s*Fuente original:.*/s', '', $contenido);
    $contenido = trim($contenido);

    return [$nuevo_titulo, $contenido];
}

// ============================================================
// RUTAS / ACCIONES
// ============================================================

$page = $_GET['page'] ?? 'dashboard';
$action = $_GET['action'] ?? '';
$format = $_GET['format'] ?? 'html';

// API JSON
if ($format === 'json') {
    header('Content-Type: application/json');

    if ($action === 'noticia' && isset($_GET['archivo'])) {
        $info = parsear_info_noticia($NOTICIAS_DIR . basename($_GET['archivo']));
        echo json_encode($info ?: ['error' => 'No encontrado']);
        exit;
    }

    if ($action === 'borrar' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
        $archivo = basename($_GET['archivo'] ?? '');
        if (!$archivo || $archivo === 'index.html') {
            echo json_encode(['error' => 'Archivo no válido']);
            exit;
        }

        $path = $NOTICIAS_DIR . $archivo;
        if (file_exists($path)) {
            unlink($path);
        }

        // Registrar en borradas.txt
        $borradas = [];
        if (file_exists($BORRADAS_FILE)) {
            $borradas = array_map('trim', file($BORRADAS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
        }
        if (!in_array($archivo, $borradas)) {
            file_put_contents($BORRADAS_FILE, $archivo . "\n", FILE_APPEND | LOCK_EX);
        }

        actualizar_index();
        echo json_encode(['ok' => true, 'mensaje' => 'Noticia borrada']);
        exit;
    }

    if ($action === 'editar' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
        $archivo = basename($_GET['archivo'] ?? '');
        $data = json_decode(file_get_contents('php://input'), true);
        $titulo = trim($data['titulo'] ?? '');
        $contenido = trim($data['contenido'] ?? '');

        if (!$archivo || $archivo === 'index.html' || !$titulo || !$contenido) {
            echo json_encode(['error' => 'Datos incompletos']);
            exit;
        }

        $info = parsear_info_noticia($NOTICIAS_DIR . $archivo);
        $url_fuente = $info['url_fuente'] ?? '';
        $fecha = $info['fecha'] ?? date('Y-m-d');

        crear_html_noticia($titulo, $contenido, $url_fuente, $fecha, $archivo);
        actualizar_index();
        echo json_encode(['ok' => true, 'mensaje' => 'Noticia actualizada']);
        exit;
    }

    if ($action === 'reescribir' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
        global $OPENAI_API_KEY;
        $OPENAI_API_KEY = defined('OPENAI_API_KEY') ? OPENAI_API_KEY : '';

        if (!$OPENAI_API_KEY) {
            echo json_encode(['error' => 'OpenAI API key no configurada']);
            exit;
        }

        $archivo = basename($_GET['archivo'] ?? '');
        if (!$archivo || $archivo === 'index.html') {
            echo json_encode(['error' => 'Archivo no válido']);
            exit;
        }

        $info = parsear_info_noticia($NOTICIAS_DIR . $archivo);
        if (!$info) {
            echo json_encode(['error' => 'No se pudo leer la noticia']);
            exit;
        }

        $titulo_actual = $info['titulo'];
        $descripcion = substr(strip_tags($info['contenido']), 0, 500);
        $url_fuente = $info['url_fuente'] ?: 'https://news.google.com';
        $fecha = $info['fecha'] ?: date('Y-m-d');

        list($nuevo_titulo, $nuevo_contenido) = reescribir_con_ia($titulo_actual, $descripcion, $url_fuente, $OPENAI_API_KEY);

        if (!$nuevo_titulo || !$nuevo_contenido) {
            echo json_encode(['error' => 'Error al reescribir con IA']);
            exit;
        }

        crear_html_noticia($nuevo_titulo, $nuevo_contenido, $url_fuente, $fecha, $archivo);
        actualizar_index();
        echo json_encode(['ok' => true, 'titulo' => $nuevo_titulo, 'archivo' => $archivo]);
        exit;
    }

    echo json_encode(['error' => 'Acción no válida']);
    exit;
}

// Login
if ($page === 'login') {
    $error = '';
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (login($_POST['password'] ?? '')) {
            $_SESSION['auth'] = true;
            header('Location: ?page=dashboard');
            exit;
        } else {
            $error = 'Contraseña incorrecta';
        }
    }
    ?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | TikPanel Noticias</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e0e0e0;
        }
        .login-box {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 3rem 2.5rem;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.3);
        }
        .login-box h1 {
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #ff0050, #00f2ea);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
        }
        .login-box p.subtitle { text-align: center; color: #888; margin-bottom: 2rem; font-size: 0.95rem; }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: #aaa; }
        .form-group input {
            width: 100%; padding: 0.9rem 1rem;
            border: 1px solid rgba(255,255,255,0.15); border-radius: 12px;
            background: rgba(0,0,0,0.2); color: #fff; font-size: 1rem;
        }
        .form-group input:focus { outline: none; border-color: #ff0050; box-shadow: 0 0 0 3px rgba(255,0,80,0.15); }
        .btn-login {
            width: 100%; padding: 1rem; border: none; border-radius: 12px;
            background: linear-gradient(90deg, #ff0050, #ff4080); color: #fff;
            font-size: 1rem; font-weight: 600; cursor: pointer;
        }
        .btn-login:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(255,0,80,0.3); }
        .flash-error { background: rgba(255,0,80,0.1); border: 1px solid rgba(255,0,80,0.3); color: #ff6b8a; padding: 0.8rem 1rem; border-radius: 10px; margin-bottom: 1.5rem; text-align: center; }
        .logo-icon { text-align: center; font-size: 3rem; margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="logo-icon">📰</div>
        <h1>TikPanel Noticias</h1>
        <p class="subtitle">Panel de Control</p>
        <?php if ($error): ?><div class="flash-error"><?php echo htmlspecialchars($error); ?></div><?php endif; ?>
        <form method="POST">
            <div class="form-group">
                <label for="password">Contraseña</label>
                <input type="password" id="password" name="password" placeholder="Introduce tu contraseña" required autofocus>
            </div>
            <button type="submit" class="btn-login">Entrar</button>
        </form>
    </div>
</body>
</html>
    <?php
    exit;
}

// Logout
if ($page === 'logout') {
    session_destroy();
    header('Location: ?page=login');
    exit;
}

// Dashboard (protegido)
require_auth();

$noticias = listar_noticias();
$total = count($noticias);

?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Control | TikPanel Noticias</title>
    <style>
        :root {
            --bg: #0f0f1a; --bg2: #1a1a2e; --bg3: #16213e;
            --text: #e0e0e0; --text2: #888;
            --accent: #ff0050; --accent2: #00f2ea;
            --card: rgba(255,255,255,0.05); --border: rgba(255,255,255,0.1);
            --success: #00d084; --danger: #ff4757; --warning: #ffa502;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, var(--bg2) 50%, var(--bg3) 100%);
            min-height: 100vh; color: var(--text); padding-bottom: 3rem;
        }
        .header {
            background: rgba(0,0,0,0.2); backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border); padding: 1rem 2rem;
            display: flex; justify-content: space-between; align-items: center;
            position: sticky; top: 0; z-index: 100;
        }
        .header-left { display: flex; align-items: center; gap: 1rem; }
        .header-left h1 {
            font-size: 1.3rem;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .badge-count { background: var(--card); border: 1px solid var(--border); padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.85rem; color: var(--text2); }
        .header-right { display: flex; gap: 0.8rem; align-items: center; }
        .btn {
            padding: 0.6rem 1.2rem; border-radius: 10px; border: 1px solid var(--border);
            background: var(--card); color: var(--text); font-size: 0.9rem;
            cursor: pointer; transition: all 0.2s; text-decoration: none;
            display: inline-flex; align-items: center; gap: 0.4rem;
        }
        .btn:hover { background: rgba(255,255,255,0.1); transform: translateY(-1px); }
        .btn-primary { background: linear-gradient(90deg, var(--accent), #ff4080); border-color: transparent; color: #fff; font-weight: 600; }
        .btn-primary:hover { box-shadow: 0 5px 20px rgba(255,0,80,0.3); }
        .btn-danger { background: rgba(255,71,87,0.15); border-color: rgba(255,71,87,0.3); color: #ff6b8a; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
        .search-box { position: relative; flex: 1; max-width: 400px; }
        .search-box input {
            width: 100%; padding: 0.7rem 1rem 0.7rem 2.5rem;
            border: 1px solid var(--border); border-radius: 12px;
            background: var(--card); color: var(--text); font-size: 0.95rem;
        }
        .search-box input:focus { outline: none; border-color: var(--accent); }
        .search-box::before { content: "🔍"; position: absolute; left: 0.8rem; top: 50%; transform: translateY(-50%); font-size: 0.9rem; }
        .news-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
        .news-card {
            background: var(--card); border: 1px solid var(--border); border-radius: 16px;
            padding: 1.5rem; transition: all 0.2s; position: relative; overflow: hidden;
        }
        .news-card:hover { border-color: rgba(255,0,80,0.3); transform: translateY(-3px); box-shadow: 0 15px 40px rgba(0,0,0,0.2); }
        .news-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), var(--accent2)); opacity: 0; transition: opacity 0.2s; }
        .news-card:hover::before { opacity: 1; }
        .news-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.8rem; gap: 0.5rem; }
        .news-card-title { font-size: 1.05rem; font-weight: 600; line-height: 1.4; color: var(--text); flex: 1; }
        .news-card-date { font-size: 0.8rem; color: var(--text2); white-space: nowrap; }
        .news-card-excerpt { font-size: 0.9rem; color: var(--text2); line-height: 1.5; margin-bottom: 1.2rem; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        .news-card-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .news-card-actions .btn { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
        .btn-view { background: rgba(0,242,234,0.1); border-color: rgba(0,242,234,0.3); color: var(--accent2); }
        .btn-edit { background: rgba(255,165,2,0.1); border-color: rgba(255,165,2,0.3); color: var(--warning); }
        .btn-rewrite { background: rgba(138,43,226,0.1); border-color: rgba(138,43,226,0.3); color: #c084fc; }
        .status-bar {
            position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%) translateY(100px);
            background: var(--bg2); border: 1px solid var(--border); padding: 1rem 2rem;
            border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.4);
            display: flex; align-items: center; gap: 0.8rem; z-index: 200;
            transition: transform 0.3s ease;
        }
        .status-bar.show { transform: translateX(-50%) translateY(0); }
        .status-bar.success { border-color: var(--success); }
        .status-bar.error { border-color: var(--danger); }
        .spinner { width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.2); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .modal-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(10px);
            display: none; align-items: center; justify-content: center; z-index: 300; padding: 2rem;
        }
        .modal-overlay.active { display: flex; }
        .modal { background: var(--bg2); border: 1px solid var(--border); border-radius: 20px; width: 100%; max-width: 800px; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; }
        .modal-header { padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .modal-header h2 { font-size: 1.2rem; }
        .modal-close { background: none; border: none; color: var(--text2); font-size: 1.5rem; cursor: pointer; }
        .modal-body { padding: 1.5rem; overflow-y: auto; flex: 1; }
        .modal-body label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--text2); }
        .modal-body input, .modal-body textarea { width: 100%; padding: 0.8rem 1rem; border: 1px solid var(--border); border-radius: 10px; background: var(--card); color: var(--text); font-size: 0.95rem; margin-bottom: 1rem; font-family: inherit; }
        .modal-body textarea { min-height: 300px; resize: vertical; line-height: 1.6; }
        .modal-footer { padding: 1rem 1.5rem; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 0.8rem; }
        .empty-state { text-align: center; padding: 4rem 2rem; color: var(--text2); }
        .empty-state .icon { font-size: 4rem; margin-bottom: 1rem; opacity: 0.5; }
        .confirm-dialog { background: var(--bg2); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; max-width: 400px; text-align: center; }
        .confirm-dialog h3 { margin-bottom: 1rem; color: var(--danger); }
        .confirm-dialog p { color: var(--text2); margin-bottom: 1.5rem; font-size: 0.95rem; }
        .confirm-dialog .btn-group { display: flex; gap: 0.8rem; justify-content: center; }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-left">
            <h1>📰 TikPanel Noticias</h1>
            <span class="badge-count"><?php echo $total; ?> noticias</span>
        </div>
        <div class="header-right">
            <a href="?page=logout" class="btn">Cerrar sesión</a>
        </div>
    </header>

    <div class="container">
        <div class="toolbar">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Buscar noticias..." oninput="filterNews()">
            </div>
        </div>

        <?php if ($noticias): ?>
        <div class="news-grid" id="newsGrid">
            <?php foreach ($noticias as $noticia): ?>
            <div class="news-card" data-title="<?php echo strtolower(htmlspecialchars($noticia['titulo'])); ?>" data-file="<?php echo htmlspecialchars($noticia['archivo']); ?>">
                <div class="news-card-header">
                    <div class="news-card-title"><?php echo htmlspecialchars($noticia['titulo']); ?></div>
                    <div class="news-card-date"><?php echo htmlspecialchars($noticia['fecha_str']); ?></div>
                </div>
                <div class="news-card-excerpt"><?php echo htmlspecialchars($noticia['extracto']); ?></div>
                <div class="news-card-actions">
                    <a href="../noticias/<?php echo urlencode($noticia['archivo']); ?>" target="_blank" class="btn btn-view">👁 Ver</a>
                    <button class="btn btn-edit" onclick="editNews('<?php echo addslashes($noticia['archivo']); ?>')">✏️ Editar</button>
                    <button class="btn btn-rewrite" onclick="rewriteNews('<?php echo addslashes($noticia['archivo']); ?>')">🤖 Reescribir IA</button>
                    <button class="btn btn-danger" onclick="confirmDelete('<?php echo addslashes($noticia['archivo']); ?>', '<?php echo addslashes($noticia['titulo']); ?>')">🗑 Borrar</button>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
        <?php else: ?>
        <div class="empty-state">
            <div class="icon">📭</div>
            <h2>No hay noticias publicadas</h2>
            <p>Ejecuta el script generar_noticias.py para crear nuevas noticias.</p>
        </div>
        <?php endif; ?>
    </div>

    <div class="status-bar" id="statusBar">
        <div class="spinner" id="statusSpinner" style="display:none;"></div>
        <span id="statusText">Listo</span>
    </div>

    <div class="modal-overlay" id="editModal">
        <div class="modal">
            <div class="modal-header">
                <h2>✏️ Editar Noticia</h2>
                <button class="modal-close" onclick="closeModal('editModal')">&times;</button>
            </div>
            <div class="modal-body">
                <label for="editTitle">Título</label>
                <input type="text" id="editTitle">
                <label for="editContent">Contenido HTML</label>
                <textarea id="editContent"></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="closeModal('editModal')">Cancelar</button>
                <button class="btn btn-primary" onclick="saveEdit()">💾 Guardar cambios</button>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="confirmModal">
        <div class="confirm-dialog">
            <h3>🗑 ¿Borrar noticia?</h3>
            <p id="confirmText">Esta acción no se puede deshacer.</p>
            <div class="btn-group">
                <button class="btn" onclick="closeModal('confirmModal')">Cancelar</button>
                <button class="btn btn-danger" onclick="executeDelete()">Sí, borrar</button>
            </div>
        </div>
    </div>

    <script>
        let currentFile = null;
        let deleteFile = null;

        function showStatus(msg, type='success', loading=false) {
            const bar = document.getElementById('statusBar');
            const text = document.getElementById('statusText');
            const spinner = document.getElementById('statusSpinner');
            text.textContent = msg;
            bar.className = 'status-bar show ' + type;
            spinner.style.display = loading ? 'block' : 'none';
            setTimeout(() => bar.classList.remove('show'), 4000);
        }

        function filterNews() {
            const q = document.getElementById('searchInput').value.toLowerCase();
            document.querySelectorAll('.news-card').forEach(card => {
                const title = card.dataset.title;
                card.style.display = title.includes(q) ? '' : 'none';
            });
        }

        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }

        async function editNews(archivo) {
            currentFile = archivo;
            showStatus('Cargando noticia...', 'success', true);
            try {
                const res = await fetch('?format=json&action=noticia&archivo=' + encodeURIComponent(archivo));
                const data = await res.json();
                document.getElementById('editTitle').value = data.titulo || '';
                document.getElementById('editContent').value = data.contenido || '';
                openModal('editModal');
                showStatus('Noticia cargada');
            } catch (e) {
                showStatus('Error al cargar: ' + e.message, 'error');
            }
        }

        async function saveEdit() {
            if (!currentFile) return;
            const titulo = document.getElementById('editTitle').value.trim();
            const contenido = document.getElementById('editContent').value.trim();
            if (!titulo || !contenido) {
                showStatus('Título y contenido son obligatorios', 'error');
                return;
            }
            showStatus('Guardando...', 'success', true);
            try {
                const res = await fetch('?format=json&action=editar&archivo=' + encodeURIComponent(currentFile), {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({titulo, contenido})
                });
                const data = await res.json();
                if (data.ok) {
                    showStatus('Guardado correctamente');
                    closeModal('editModal');
                    setTimeout(() => location.reload(), 800);
                } else {
                    showStatus(data.error || 'Error al guardar', 'error');
                }
            } catch (e) {
                showStatus('Error: ' + e.message, 'error');
            }
        }

        function confirmDelete(archivo, titulo) {
            deleteFile = archivo;
            document.getElementById('confirmText').textContent = `¿Borrar permanentemente "${titulo}"? Esta acción no se puede deshacer.`;
            openModal('confirmModal');
        }

        async function executeDelete() {
            if (!deleteFile) return;
            closeModal('confirmModal');
            showStatus('Borrando...', 'success', true);
            try {
                const res = await fetch('?format=json&action=borrar&archivo=' + encodeURIComponent(deleteFile), {method: 'POST'});
                const data = await res.json();
                if (data.ok) {
                    showStatus('Borrado correctamente');
                    const card = document.querySelector(`[data-file="${deleteFile}"]`);
                    if (card) card.remove();
                } else {
                    showStatus(data.error || 'Error al borrar', 'error');
                }
            } catch (e) {
                showStatus('Error: ' + e.message, 'error');
            }
            deleteFile = null;
        }

        async function rewriteNews(archivo) {
            if (!confirm('¿Quieres que la IA reescriba esta noticia completamente? Se mantendrá la misma URL.')) return;
            showStatus('La IA está reescribiendo la noticia...', 'success', true);
            try {
                const res = await fetch('?format=json&action=reescribir&archivo=' + encodeURIComponent(archivo), {method: 'POST'});
                const data = await res.json();
                if (data.ok) {
                    showStatus('Reescrita: ' + data.titulo);
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showStatus(data.error || 'Error al reescribir', 'error');
                }
            } catch (e) {
                showStatus('Error: ' + e.message, 'error');
            }
        }
    </script>
</body>
</html>
