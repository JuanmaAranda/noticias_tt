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
$FEEDS_FILE = dirname(__DIR__) . '/feeds.json';

// ============================================================
// GESTIÓN DE FEEDS RSS
// ============================================================

function cargar_feeds() {
    global $FEEDS_FILE;
    $feeds_default = [
        "https://news.google.com/rss/search?q=TikTok&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+algoritmo&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+monetizacion&hl=es&gl=ES&ceid=ES:es",
        "https://news.google.com/rss/search?q=TikTok+creadores&hl=es&gl=ES&ceid=ES:es",
        "https://www.20minutos.es/rss/tecnologia/",
        "https://feeds.feedburner.com/tubefilterNews",
        "https://www.socialmediatoday.com/rss.xml",
        "https://techcrunch.com/category/social/feed/",
        "https://www.theguardian.com/technology/tiktok/rss"
    ];
    
    if (file_exists($FEEDS_FILE)) {
        try {
            $contenido = file_get_contents($FEEDS_FILE);
            $feeds = json_decode($contenido, true);
            if (is_array($feeds) && count($feeds) > 0) {
                return $feeds;
            }
        } catch (Exception $e) {
            // Si hay error, usar defaults
        }
    }
    return $feeds_default;
}

function guardar_feeds($feeds) {
    global $FEEDS_FILE;
    file_put_contents($FEEDS_FILE, json_encode(array_values($feeds), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
}

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
        'contenido_plano' => '',
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
        // Quitar el párrafo de resumen si existe
        $contenido = preg_replace('/<p>Resumen informativo de actualidad.*?<\/p>/i', '', $contenido);
        // Quitar párrafos vacíos al inicio y final
        $contenido = preg_replace('/^(\s*<p>\s*<\/p>\s*)+/i', '', $contenido);
        $contenido = preg_replace('/(\s*<p>\s*<\/p>\s*)+$/i', '', $contenido);
        $info['contenido'] = trim($contenido);
        $info['contenido_plano'] = strip_tags(trim($contenido));
        $info['extracto'] = generar_extracto($contenido);
    } else {
        // Fallback: intentar capturar todo el body si no encuentra la sección específica
        if (preg_match('/<body[^>]*>(.*?)<\/body>/s', $html, $m)) {
            $body = $m[1];
            // Quitar scripts, nav, footer, etc.
            $body = preg_replace('/<script.*?<\/script>/s', '', $body);
            $body = preg_replace('/<nav.*?<\/nav>/s', '', $body);
            $body = preg_replace('/<footer.*?<\/footer>/s', '', $body);
            $body = preg_replace('/<div[^>]*id="navbar-container".*?<\/div>/s', '', $body);
            $body = preg_replace('/<div[^>]*id="footer-container".*?<\/div>/s', '', $body);
            $body = preg_replace('/<div class="blog-breadcrumb".*?<\/div>/s', '', $body);
            $body = strip_tags($body, '<p><strong><em><h3><ul><ol><li><a><br>');
            $info['contenido'] = trim($body);
            $info['contenido_plano'] = strip_tags(trim($body));
            $info['extracto'] = generar_extracto($body);
        }
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
        if (isset($borradas[basename($f)])) continue;
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
    // No-op: El index.php dinámico en /noticias/ se encarga de listar las noticias.
    // No generamos index.html estático para evitar conflictos con el índice dinámico.
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

        // Convertir el contenido del editor visual a HTML
        // El editor ya envía HTML, pero aseguramos que sea válido
        $contenido_html = $contenido;

        $info = parsear_info_noticia($NOTICIAS_DIR . $archivo);
        $url_fuente = $info['url_fuente'] ?? '';
        $fecha = $info['fecha'] ?? date('Y-m-d');

        crear_html_noticia($titulo, $contenido_html, $url_fuente, $fecha, $archivo);
        actualizar_index();
        echo json_encode(['ok' => true, 'mensaje' => 'Noticia actualizada']);
        exit;
    }

    if ($action === 'reescribir' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
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

    // Acciones para gestionar feeds RSS
    if ($action === 'listar_feeds') {
        require_auth();
        $feeds = cargar_feeds();
        echo json_encode(['ok' => true, 'feeds' => $feeds]);
        exit;
    }

    if ($action === 'agregar_feed' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
        $data = json_decode(file_get_contents('php://input'), true);
        $nueva_url = trim($data['url'] ?? '');
        
        if (!$nueva_url || !filter_var($nueva_url, FILTER_VALIDATE_URL)) {
            echo json_encode(['error' => 'URL no válida']);
            exit;
        }
        
        $feeds = cargar_feeds();
        if (in_array($nueva_url, $feeds)) {
            echo json_encode(['error' => 'Esta fuente ya existe']);
            exit;
        }
        
        $feeds[] = $nueva_url;
        guardar_feeds($feeds);
        echo json_encode(['ok' => true, 'mensaje' => 'Fuente añadida', 'feeds' => $feeds]);
        exit;
    }

    if ($action === 'eliminar_feed' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        require_auth();
        $data = json_decode(file_get_contents('php://input'), true);
        $url = trim($data['url'] ?? '');
        
        $feeds = cargar_feeds();
        $feeds = array_values(array_filter($feeds, function($f) use ($url) {
            return $f !== $url;
        }));
        
        guardar_feeds($feeds);
        echo json_encode(['ok' => true, 'mensaje' => 'Fuente eliminada', 'feeds' => $feeds]);
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

        /* Modal de estado centrada */
        .status-modal-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(15px);
            display: none; align-items: center; justify-content: center; z-index: 400;
        }
        .status-modal-overlay.active { display: flex; }
        .status-modal {
            background: var(--bg2); border: 1px solid var(--border); border-radius: 20px;
            padding: 2.5rem; max-width: 400px; width: 90%; text-align: center;
            box-shadow: 0 25px 60px rgba(0,0,0,0.5);
        }
        .status-modal .spinner-large {
            width: 50px; height: 50px; border: 3px solid rgba(255,255,255,0.1);
            border-top-color: var(--accent); border-radius: 50%;
            animation: spin 1s linear infinite; margin: 0 auto 1.5rem;
        }
        .status-modal h3 { font-size: 1.2rem; margin-bottom: 0.5rem; }
        .status-modal p { color: var(--text2); font-size: 0.95rem; }
        .status-modal.success { border-color: var(--success); }
        .status-modal.success h3 { color: var(--success); }
        .status-modal.error { border-color: var(--danger); }
        .status-modal.error h3 { color: var(--danger); }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Modales generales */
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
        .modal-body input { width: 100%; padding: 0.8rem 1rem; border: 1px solid var(--border); border-radius: 10px; background: var(--card); color: var(--text); font-size: 0.95rem; margin-bottom: 1rem; font-family: inherit; }
        .modal-footer { padding: 1rem 1.5rem; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 0.8rem; }
        
        /* Editor visual */
        .editor-toolbar {
            display: flex; gap: 0.3rem; padding: 0.5rem;
            background: var(--card); border: 1px solid var(--border);
            border-radius: 10px 10px 0 0; border-bottom: none;
            flex-wrap: wrap;
        }
        .editor-toolbar button {
            padding: 0.4rem 0.7rem; border: 1px solid var(--border); border-radius: 6px;
            background: var(--bg2); color: var(--text); font-size: 0.85rem;
            cursor: pointer; transition: all 0.15s;
        }
        .editor-toolbar button:hover { background: rgba(255,255,255,0.1); border-color: var(--accent); }
        .editor-toolbar button.active { background: rgba(255,0,80,0.2); border-color: var(--accent); }
        .editor-toolbar .separator { width: 1px; background: var(--border); margin: 0 0.3rem; }
        #editor {
            min-height: 350px; padding: 1rem;
            border: 1px solid var(--border); border-radius: 0 0 10px 10px;
            background: var(--card); color: var(--text); font-size: 0.95rem;
            line-height: 1.7; overflow-y: auto;
        }
        #editor:focus { outline: none; border-color: var(--accent); }
        #editor p { margin-bottom: 0.8rem; }
        #editor strong { color: #fff; }
        #editor h3 { color: var(--accent2); margin: 1.2rem 0 0.6rem; font-size: 1.15rem; }
        #editor ul, #editor ol { margin-left: 1.5rem; margin-bottom: 0.8rem; }
        #editor li { margin-bottom: 0.3rem; }
        #editor a { color: var(--accent2); }
        #editor blockquote {
            border-left: 3px solid var(--accent); padding-left: 1rem;
            margin: 1rem 0; color: var(--text2); font-style: italic;
        }

        .empty-state { text-align: center; padding: 4rem 2rem; color: var(--text2); }
        .empty-state .icon { font-size: 4rem; margin-bottom: 1rem; opacity: 0.5; }
        .confirm-dialog { background: var(--bg2); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; max-width: 400px; text-align: center; }
        .confirm-dialog h3 { margin-bottom: 1rem; color: var(--danger); }
        .confirm-dialog p { color: var(--text2); margin-bottom: 1.5rem; font-size: 0.95rem; }
        .confirm-dialog .btn-group { display: flex; gap: 0.8rem; justify-content: center; }

        /* Sección de Fuentes RSS */
        .feeds-section {
            background: var(--card); border: 1px solid var(--border); border-radius: 16px;
            padding: 1.5rem; margin-top: 2rem;
        }
        .feeds-section h2 {
            font-size: 1.2rem; margin-bottom: 1rem;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .feeds-list {
            display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem;
        }
        .feed-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 0.7rem 1rem; background: var(--bg2); border: 1px solid var(--border);
            border-radius: 10px; font-size: 0.9rem;
        }
        .feed-item span { color: var(--text2); word-break: break-all; flex: 1; margin-right: 1rem; }
        .feed-item .btn { padding: 0.3rem 0.6rem; font-size: 0.75rem; }
        .feed-add-form {
            display: flex; gap: 0.8rem; flex-wrap: wrap;
        }
        .feed-add-form input {
            flex: 1; min-width: 250px; padding: 0.7rem 1rem;
            border: 1px solid var(--border); border-radius: 10px;
            background: var(--card); color: var(--text); font-size: 0.9rem;
        }
        .feed-add-form input:focus { outline: none; border-color: var(--accent); }
        .feed-empty { color: var(--text2); text-align: center; padding: 1rem; font-style: italic; }
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
                    <button class="btn btn-rewrite" onclick="confirmRewrite('<?php echo addslashes($noticia['archivo']); ?>', '<?php echo addslashes($noticia['titulo']); ?>')">🤖 Reescribir IA</button>
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

        <!-- Sección de Fuentes RSS -->
        <div class="feeds-section" id="feedsSection">
            <h2>📡 Fuentes RSS</h2>
            <div class="feeds-list" id="feedsList">
                <div class="feed-empty">Cargando fuentes...</div>
            </div>
            <div class="feed-add-form">
                <input type="url" id="newFeedUrl" placeholder="https://ejemplo.com/rss.xml">
                <button class="btn btn-primary" onclick="addFeed()">➕ Añadir fuente</button>
            </div>
        </div>
    </div>

    <!-- Modal de Estado/Progreso Centrado -->
    <div class="status-modal-overlay" id="statusModal">
        <div class="status-modal" id="statusModalContent">
            <div class="spinner-large" id="statusSpinner"></div>
            <h3 id="statusTitle">Procesando...</h3>
            <p id="statusMessage">Por favor espera</p>
        </div>
    </div>

    <!-- Modal de Editar con Editor Visual -->
    <div class="modal-overlay" id="editModal">
        <div class="modal">
            <div class="modal-header">
                <h2>✏️ Editar Noticia</h2>
                <button class="modal-close" onclick="closeModal('editModal')">&times;</button>
            </div>
            <div class="modal-body">
                <label for="editTitle">Título</label>
                <input type="text" id="editTitle">
                <label>Contenido</label>
                <div class="editor-toolbar">
                    <button type="button" onclick="editorFormat('bold')" title="Negrita"><b>B</b></button>
                    <button type="button" onclick="editorFormat('italic')" title="Cursiva"><i>I</i></button>
                    <button type="button" onclick="editorFormat('underline')" title="Subrayado"><u>U</u></button>
                    <div class="separator"></div>
                    <button type="button" onclick="editorFormat('h3')" title="Subtítulo">H3</button>
                    <div class="separator"></div>
                    <button type="button" onclick="editorFormat('insertUnorderedList')" title="Lista">• Lista</button>
                    <button type="button" onclick="editorFormat('insertOrderedList')" title="Lista numerada">1. Lista</button>
                    <div class="separator"></div>
                    <button type="button" onclick="editorFormat('removeFormat')" title="Quitar formato">🧹</button>
                </div>
                <div id="editor" contenteditable="true"></div>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="closeModal('editModal')">Cancelar</button>
                <button class="btn btn-primary" onclick="saveEdit()">💾 Guardar cambios</button>
            </div>
        </div>
    </div>

    <!-- Modal de Confirmar Borrar -->
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

    <!-- Modal de Confirmar Reescribir IA -->
    <div class="modal-overlay" id="rewriteModal">
        <div class="confirm-dialog">
            <h3>🤖 ¿Reescribir con IA?</h3>
            <p id="rewriteText">La IA reescribirá esta noticia completamente. Se mantendrá la misma URL.</p>
            <div class="btn-group">
                <button class="btn" onclick="closeModal('rewriteModal')">Cancelar</button>
                <button class="btn btn-rewrite" onclick="executeRewrite()" style="background: rgba(138,43,226,0.2); color: #c084fc; border-color: rgba(138,43,226,0.4);">Sí, reescribir</button>
            </div>
        </div>
    </div>

    <script>
        let currentFile = null;
        let deleteFile = null;
        let rewriteFile = null;

        // Modal de estado centrado
        function showStatus(title, message, type='loading') {
            const modal = document.getElementById('statusModal');
            const content = document.getElementById('statusModalContent');
            const spinner = document.getElementById('statusSpinner');
            const titleEl = document.getElementById('statusTitle');
            const msgEl = document.getElementById('statusMessage');
            
            titleEl.textContent = title;
            msgEl.textContent = message;
            content.className = 'status-modal ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : '');
            spinner.style.display = type === 'loading' ? 'block' : 'none';
            
            modal.classList.add('active');
            
            if (type !== 'loading') {
                setTimeout(() => modal.classList.remove('active'), 3000);
            }
        }

        function hideStatus() {
            document.getElementById('statusModal').classList.remove('active');
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

        // Editor visual
        function editorFormat(command) {
            document.execCommand(command, false, null);
            document.getElementById('editor').focus();
        }

        async function editNews(archivo) {
            currentFile = archivo;
            showStatus('Cargando noticia...', 'Por favor espera');
            try {
                const res = await fetch('?format=json&action=noticia&archivo=' + encodeURIComponent(archivo));
                const data = await res.json();
                document.getElementById('editTitle').value = data.titulo || '';
                
                // Cargar contenido en el editor visual
                const editor = document.getElementById('editor');
                let contenido = data.contenido || '';
                
                // Si el contenido está vacío, intentar con contenido_plano
                if (!contenido && data.contenido_plano) {
                    contenido = '<p>' + data.contenido_plano.replace(/\n\n/g, '</p><p>') + '</p>';
                }
                
                if (contenido && contenido.trim() !== '') {
                    editor.innerHTML = contenido;
                } else {
                    editor.innerHTML = '<p><br></p>';
                }
                
                hideStatus();
                openModal('editModal');
            } catch (e) {
                hideStatus();
                showStatus('Error', 'No se pudo cargar la noticia: ' + e.message, 'error');
            }
        }

        async function saveEdit() {
            if (!currentFile) return;
            const titulo = document.getElementById('editTitle').value.trim();
            const contenido = document.getElementById('editor').innerHTML.trim();
            
            if (!titulo) {
                showStatus('Error', 'El título es obligatorio', 'error');
                return;
            }
            if (!contenido || contenido === '<p>Escribe el contenido de la noticia aquí...</p>') {
                showStatus('Error', 'El contenido es obligatorio', 'error');
                return;
            }
            
            showStatus('Guardando...', 'Por favor espera');
            try {
                const res = await fetch('?format=json&action=editar&archivo=' + encodeURIComponent(currentFile), {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({titulo, contenido})
                });
                const data = await res.json();
                if (data.ok) {
                    hideStatus();
                    closeModal('editModal');
                    showStatus('¡Guardado!', 'La noticia se actualizó correctamente', 'success');
                    setTimeout(() => location.reload(), 1500);
                } else {
                    hideStatus();
                    showStatus('Error', data.error || 'Error al guardar', 'error');
                }
            } catch (e) {
                hideStatus();
                showStatus('Error', e.message, 'error');
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
            showStatus('Borrando...', 'Por favor espera');
            try {
                const res = await fetch('?format=json&action=borrar&archivo=' + encodeURIComponent(deleteFile), {method: 'POST'});
                const data = await res.json();
                if (data.ok) {
                    hideStatus();
                    showStatus('¡Borrado!', 'La noticia se eliminó correctamente', 'success');
                    const card = document.querySelector(`[data-file="${deleteFile}"]`);
                    if (card) card.remove();
                } else {
                    hideStatus();
                    showStatus('Error', data.error || 'Error al borrar', 'error');
                }
            } catch (e) {
                hideStatus();
                showStatus('Error', e.message, 'error');
            }
            deleteFile = null;
        }

        function confirmRewrite(archivo, titulo) {
            rewriteFile = archivo;
            document.getElementById('rewriteText').textContent = `La IA reescribirá "${titulo}" completamente. Se mantendrá la misma URL.`;
            openModal('rewriteModal');
        }

        async function executeRewrite() {
            if (!rewriteFile) return;
            closeModal('rewriteModal');
            showStatus('Reescribiendo...', 'La IA está generando el nuevo contenido. Esto puede tardar unos segundos.');
            try {
                const res = await fetch('?format=json&action=reescribir&archivo=' + encodeURIComponent(rewriteFile), {method: 'POST'});
                const data = await res.json();
                if (data.ok) {
                    hideStatus();
                    showStatus('¡Reescrita!', 'La noticia se reescribió correctamente: ' + data.titulo, 'success');
                    setTimeout(() => location.reload(), 2000);
                } else {
                    hideStatus();
                    showStatus('Error', data.error || 'Error al reescribir', 'error');
                }
            } catch (e) {
                hideStatus();
                showStatus('Error', e.message, 'error');
            }
            rewriteFile = null;
        }
        // Cargar feeds al iniciar
        async function loadFeeds() {
            try {
                const res = await fetch('?format=json&action=listar_feeds');
                const data = await res.json();
                if (data.ok) {
                    renderFeeds(data.feeds);
                }
            } catch (e) {
                console.error('Error cargando feeds:', e);
            }
        }

        function renderFeeds(feeds) {
            const container = document.getElementById('feedsList');
            if (!feeds || feeds.length === 0) {
                container.innerHTML = '<div class="feed-empty">No hay fuentes configuradas</div>';
                return;
            }
            container.innerHTML = feeds.map(url => `
                <div class="feed-item">
                    <span>${escapeHtml(url)}</span>
                    <button class="btn btn-danger" onclick="removeFeed('${escapeJs(url)}')">🗑 Eliminar</button>
                </div>
            `).join('');
        }

        async function addFeed() {
            const input = document.getElementById('newFeedUrl');
            const url = input.value.trim();
            
            if (!url) {
                showStatus('Error', 'Introduce una URL válida', 'error');
                return;
            }
            
            showStatus('Añadiendo fuente...', 'Por favor espera');
            try {
                const res = await fetch('?format=json&action=agregar_feed', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                if (data.ok) {
                    input.value = '';
                    hideStatus();
                    renderFeeds(data.feeds);
                    showStatus('¡Añadida!', 'La fuente RSS se añadió correctamente', 'success');
                } else {
                    hideStatus();
                    showStatus('Error', data.error || 'Error al añadir', 'error');
                }
            } catch (e) {
                hideStatus();
                showStatus('Error', e.message, 'error');
            }
        }

        async function removeFeed(url) {
            if (!confirm('¿Eliminar esta fuente RSS?')) return;
            
            showStatus('Eliminando fuente...', 'Por favor espera');
            try {
                const res = await fetch('?format=json&action=eliminar_feed', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                if (data.ok) {
                    hideStatus();
                    renderFeeds(data.feeds);
                    showStatus('¡Eliminada!', 'La fuente se eliminó correctamente', 'success');
                } else {
                    hideStatus();
                    showStatus('Error', data.error || 'Error al eliminar', 'error');
                }
            } catch (e) {
                hideStatus();
                showStatus('Error', e.message, 'error');
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function escapeJs(str) {
            return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
        }

        // Cargar feeds al iniciar la página
        loadFeeds();
    </script>
</body>
</html>
