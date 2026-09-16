/* Pairing: scan the QR code shown by the desktop dashboard.
 *
 * The QR carries a one-time token plus every address the PC believes it is
 * reachable on (LAN and Tailscale). We keep all of them so the same pairing
 * works at home and away. */

import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import React, { useCallback, useRef, useState } from 'react';
import {
  Platform, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';

import { pair } from '../src/api';
import { Button, Card, Notice, Loading } from '../src/components/ui';
import { theme } from '../src/theme';

export default function PairScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [manual, setManual] = useState(false);
  const [token, setToken] = useState('');
  const [address, setAddress] = useState('');
  const handled = useRef(false);

  const deviceName = `${Platform.OS === 'android' ? 'Android' : 'iOS'} phone`;

  const finish = useCallback(async (payload) => {
    setBusy(true);
    setError(null);
    try {
      await pair(payload, deviceName);
      router.replace('/');
    } catch (err) {
      handled.current = false;
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [deviceName]);

  const onScan = useCallback(({ data }) => {
    if (handled.current) return;
    let parsed;
    try {
      parsed = JSON.parse(data);
    } catch {
      setError('That QR code is not a CodePilot pairing code.');
      return;
    }
    if (!parsed.token || !(parsed.addresses || parsed.address)) {
      setError('That QR code is missing a token or an address.');
      return;
    }
    handled.current = true;
    finish(parsed);
  }, [finish]);

  if (busy) return <Loading label="Pairing…" />;

  if (manual) {
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Notice kind="info">
          Open the Pair Device page in the CodePilot dashboard on your PC and copy
          the token and one address shown there.
        </Notice>
        {error ? <Notice kind="err">{error}</Notice> : null}
        <Card style={{ padding: 14 }}>
          <Text style={s.label}>Pairing token</Text>
          <TextInput
            style={s.input} value={token} onChangeText={setToken}
            autoCapitalize="none" autoCorrect={false} placeholder="paste the token"
            placeholderTextColor={theme.fgFaint}
          />
          <Text style={[s.label, { marginTop: 14 }]}>Server address</Text>
          <TextInput
            style={s.input} value={address} onChangeText={setAddress}
            autoCapitalize="none" autoCorrect={false} keyboardType="url"
            placeholder="http://192.168.178.50:8765"
            placeholderTextColor={theme.fgFaint}
          />
          <Text style={s.hint}>
            Use the LAN address at home, or the Tailscale address (100.x.y.z) from
            anywhere. Both get stored either way once you are connected.
          </Text>
        </Card>
        <Button
          title="Pair" kind="primary" style={{ marginTop: 14 }}
          disabled={!token.trim() || !address.trim()}
          onPress={() => finish({ token: token.trim(), addresses: [address.trim().replace(/\/$/, '')] })}
        />
        <Button title="Scan a QR code instead" style={{ marginTop: 10 }}
                onPress={() => { setManual(false); setError(null); }} />
      </ScrollView>
    );
  }

  if (!permission) return <Loading label="Checking camera…" />;

  if (!permission.granted) {
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Notice kind="info">
          CodePilot needs the camera to read the pairing QR code. It is not used
          for anything else.
        </Notice>
        <Button title="Allow camera" kind="primary" onPress={requestPermission} />
        <Button title="Type the token instead" style={{ marginTop: 10 }}
                onPress={() => setManual(true)} />
      </ScrollView>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <CameraView
        style={{ flex: 1 }}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={onScan}
      />
      <View style={s.overlay}>
        {error ? <Notice kind="err">{error}</Notice> : null}
        <Text style={s.overlayText}>
          Point the camera at the QR code on the CodePilot dashboard.
        </Text>
        <Button title="Type the token instead" onPress={() => setManual(true)} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 48 },
  overlay: { padding: 16, backgroundColor: theme.bg, gap: 10 },
  overlayText: { color: theme.fgMuted, fontSize: 13, textAlign: 'center' },
  label: { color: theme.fgMuted, fontSize: 12, marginBottom: 5 },
  input: {
    backgroundColor: theme.inset, borderWidth: 1, borderColor: theme.border,
    borderRadius: theme.radius, color: theme.fg, padding: 10,
    fontFamily: theme.mono, fontSize: 13,
  },
  hint: { color: theme.fgFaint, fontSize: 12, marginTop: 10, lineHeight: 18 },
});
