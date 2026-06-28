# TikPanel News - Panel de Control

Panel web simple para gestionar noticias generadas automáticamente. **Sin base de datos**, funciona directamente con archivos HTML.

## ¿Cómo funciona?

```
┌─────────────────┐     FTP      ┌─────────────────┐
│  GitHub Actions │─────────────▶│  Servidor       │
│  (genera noticias)│            │  (noticias/)    │
└─────────────────┘              └─────────────────┘
         │                              │
         │  Descarga borradas.txt       │  Panel PHP
         │◄────────────────────────────│  (edita/borra)
         │                              │
         │  Respeta las borradas        │
         └──────────────────────────────┘
```

## Instalación

### 1. Subir el panel al servidor

Sube la carpeta `panel/` a tu hosting vía FTP:
```
/public_html/panel/
    ├── index.php          ← Panel de control
    ├── .htaccess          ← Redirecciones
    └── config.php         ← Credenciales (crear manualmente)
```

### 2. Crear config.php

Copia `config.example.php` a `config.php` y configura:

```php
<?php
// Contraseña del panel (generar hash SHA256)
define('PANEL_PASSWORD_HASH', '...');

// API Key de OpenAI (opcional, para reescribir con IA)
define('OPENAI_API_KEY', 'sk-...');
```

**Generar hash de contraseña:**
```php
<?php echo hash('sha256', 'tu_password'); ?>
```

### 3. Acceder al panel

Abre en tu navegador: `https://tikpanel.app/panel/`

## Funcionalidades

| Acción | Descripción |
|--------|-------------|
| 👁 Ver | Abre la noticia en el sitio público |
| ✏️ Editar | Modifica título y contenido HTML manualmente |
| 🤖 Reescribir IA | Pide a GPT-4o-mini que reescriba la noticia (misma URL) |
| 🗑 Borrar | Elimina la noticia y la registra en `borradas.txt` |

## Sincronización con GitHub

Cuando borras una noticia desde el panel:
1. Se elimina el archivo HTML del servidor
2. Se añade el slug a `borradas.txt`
3. GitHub Actions descarga `borradas.txt` antes de generar nuevas noticias
4. El script Python elimina esas noticias del repo y no las vuelve a generar

## Notas

- El panel trabaja **directamente en el servidor**, no necesita sincronización FTP
- Las noticias reescritas con IA mantienen la misma URL (mismo archivo)
- `borradas.txt` se crea automáticamente la primera vez que borras una noticia
- No necesitas base de datos ni configuración compleja
