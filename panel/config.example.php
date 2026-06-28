<?php
/**
 * Configuración sensible del panel
 * NO subir este archivo a GitHub. Colocar manualmente en el servidor.
 */

// API Key de OpenAI (opcional, para reescribir noticias con IA)
define('OPENAI_API_KEY', 'sk-...');

// Contraseña del panel (hash SHA256 de "tu_contraseña")
// Generar: <?php echo hash('sha256', 'tu_password'); ?>
define('PANEL_PASSWORD_HASH', 'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3'); // "123"
