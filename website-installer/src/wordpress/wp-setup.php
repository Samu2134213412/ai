<?php
/**
 * Richtet WordPress einmalig ein (wird vom Installer per PHP aufgerufen).
 *
 * Die Angaben kommen als Umgebungsvariablen, damit das Passwort nicht in
 * der Prozessliste auftaucht:
 *   MW_WP_DIR   Ordner der WordPress-Installation
 *   MW_URL      Adresse der Website (http://localhost:8080 oder https://domain)
 *   MW_OLD_URL  vorherige Adresse (beim Wechsel lokal -> online), optional
 *   MW_TITLE, MW_USER, MW_EMAIL, MW_PASS   nur fuer die Erstinstallation
 */

error_reporting( E_ALL & ~E_DEPRECATED & ~E_NOTICE & ~E_WARNING );

$wp_dir = getenv( 'MW_WP_DIR' );
$url    = rtrim( getenv( 'MW_URL' ), '/' );
$parts  = parse_url( $url );

// WordPress erwartet eine Web-Anfrage - so tun als ob.
$_SERVER['HTTP_HOST']      = $parts['host'] . ( isset( $parts['port'] ) ? ':' . $parts['port'] : '' );
$_SERVER['SERVER_NAME']    = $parts['host'];
$_SERVER['SERVER_PORT']    = isset( $parts['port'] ) ? $parts['port'] : ( 'https' === $parts['scheme'] ? 443 : 80 );
$_SERVER['REQUEST_URI']    = '/';
$_SERVER['REQUEST_METHOD'] = 'GET';
if ( 'https' === $parts['scheme'] ) {
	$_SERVER['HTTPS'] = 'on';
}

define( 'WP_INSTALLING', true );
require $wp_dir . '/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';

if ( ! is_blog_installed() ) {
	$result = wp_install(
		getenv( 'MW_TITLE' ),
		getenv( 'MW_USER' ),
		getenv( 'MW_EMAIL' ),
		true,
		'',
		wp_slash( getenv( 'MW_PASS' ) ),
		'de_DE'
	);
	if ( is_wp_error( $result ) ) {
		fwrite( STDERR, 'WordPress-Einrichtung fehlgeschlagen: ' . $result->get_error_message() . "\n" );
		exit( 1 );
	}
	update_option( 'permalink_structure', '/%postname%/' );
	update_option( 'timezone_string', 'Europe/Berlin' );
	update_option( 'date_format', 'j. F Y' );
	update_option( 'time_format', 'H:i' );
	update_option( 'start_of_week', 1 );
	echo "installiert\n";
} else {
	// Adresse hat sich geaendert (z. B. von lokal auf die eigene Domain):
	// Links und Bilder in Beitraegen und Seiten mitziehen.
	$old = rtrim( (string) getenv( 'MW_OLD_URL' ), '/' );
	if ( $old && $old !== $url ) {
		global $wpdb;
		$wpdb->query( $wpdb->prepare( "UPDATE {$wpdb->posts} SET post_content = REPLACE(post_content, %s, %s)", $old, $url ) );
		$wpdb->query( $wpdb->prepare( "UPDATE {$wpdb->posts} SET guid = REPLACE(guid, %s, %s)", $old, $url ) );
		echo "adresse geaendert\n";
	}
	echo "vorhanden\n";
}

// Direkt in die Datenbank: update_option() wuerde die Aenderung ueberspringen,
// weil WP_HOME/WP_SITEURL in wp-config.php den gespeicherten Wert ueberdecken.
global $wpdb;
foreach ( array( 'home', 'siteurl' ) as $name ) {
	$wpdb->update( $wpdb->options, array( 'option_value' => $url ), array( 'option_name' => $name ) );
}
wp_cache_flush();
flush_rewrite_rules( false );
