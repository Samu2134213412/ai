<?php
/**
 * Plugin Name: Website-Schutz
 * Description: Vom Website-Installer. Sperrt die Anmeldung nach 5 falschen Passwörtern für 15 Minuten (pro IP-Adresse) und schaltet XML-RPC ab, das oft für Angriffe genutzt wird.
 * Version: 1.0
 */

defined( 'ABSPATH' ) || exit;

const WEBSITE_SCHUTZ_MAX_VERSUCHE = 5;
const WEBSITE_SCHUTZ_SPERRE       = 15 * MINUTE_IN_SECONDS;

add_filter( 'xmlrpc_enabled', '__return_false' );
add_filter( 'xmlrpc_methods', '__return_empty_array' );

function website_schutz_key() {
	$ip = isset( $_SERVER['REMOTE_ADDR'] ) ? $_SERVER['REMOTE_ADDR'] : '';
	return 'website_schutz_' . md5( $ip );
}

// Gesperrt? Dann gar nicht erst pruefen, ob das Passwort stimmt.
add_filter(
	'authenticate',
	function ( $user ) {
		$versuche = (int) get_transient( website_schutz_key() );
		if ( $versuche >= WEBSITE_SCHUTZ_MAX_VERSUCHE ) {
			return new WP_Error(
				'website_schutz_gesperrt',
				'<strong>Gesperrt:</strong> Zu viele falsche Versuche. Bitte in 15 Minuten nochmal probieren.'
			);
		}
		return $user;
	},
	30
);

add_action(
	'wp_login_failed',
	function () {
		$key = website_schutz_key();
		set_transient( $key, (int) get_transient( $key ) + 1, WEBSITE_SCHUTZ_SPERRE );
	}
);

add_action(
	'wp_login',
	function () {
		delete_transient( website_schutz_key() );
	}
);
