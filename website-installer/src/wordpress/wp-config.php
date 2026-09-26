<?php
/**
 * WordPress-Konfiguration, angelegt vom Website-Installer.
 *
 * Die Datenbank ist eine SQLite-Datei in wp-content/database/ - es wird
 * kein MySQL gebraucht. Das Plugin "SQLite Database Integration" (offiziell
 * vom WordPress-Team) sorgt dafuer, dass WordPress damit arbeitet.
 */

define( 'DB_NAME', 'wordpress' );
define( 'DB_USER', '' );
define( 'DB_PASSWORD', '' );
define( 'DB_HOST', 'localhost' );
define( 'DB_CHARSET', 'utf8mb4' );
define( 'DB_COLLATE', '' );
define( 'DB_DIR', __DIR__ . '/wp-content/database/' );
define( 'DB_FILE', '.ht.sqlite' );

/* Geheime Schluessel - beim Installieren zufaellig erzeugt. */
__SALTS__

$table_prefix = 'wp_';

// Hinter dem Cloudflare Tunnel kommt HTTPS nur als Header an.
if ( isset( $_SERVER['HTTP_X_FORWARDED_PROTO'] ) && 'https' === $_SERVER['HTTP_X_FORWARDED_PROTO'] ) {
	$_SERVER['HTTPS'] = 'on';
}
// Die echte IP-Adresse der Besucher (wichtig fuer den Login-Schutz).
if ( ! empty( $_SERVER['HTTP_CF_CONNECTING_IP'] ) ) {
	$_SERVER['REMOTE_ADDR'] = $_SERVER['HTTP_CF_CONNECTING_IP'];
}

// Adresse der Website. Der Installer passt sie an, wenn du den Modus wechselst.
define( 'WP_HOME', '__URL__' );
define( 'WP_SITEURL', '__URL__' );

// Updates, Plugins und Themes direkt installieren (ohne FTP-Abfrage).
define( 'FS_METHOD', 'direct' );
define( 'WP_DEBUG', false );

if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', __DIR__ . '/' );
}
require_once ABSPATH . 'wp-settings.php';
