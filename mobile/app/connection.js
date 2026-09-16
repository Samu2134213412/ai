/* Connection detail: which address is in use, what else is known, unpair. */

import { router } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { addresses, api, credentials, currentBase, forgetBase, probe } from '../src/api';
import { Badge, Button, Card, Loading, Notice, Section } from '../src/components/ui';
import { theme } from '../src/theme';

export default function ConnectionScreen() {
  const [known, setKnown] = useState([]);
  const [results, setResults] = useState({});
  const [serverAddresses, setServerAddresses] = useState([]);
  const [busy, setBusy] = useState(true);

  const test = useCallback(async () => {
    setBusy(true);
    const list = await addresses.load();
    setKnown(list);
    const outcome = {};
    await Promise.all(list.map(async (url) => {
      try { await probe(url); outcome[url] = 'reachable'; }
      catch (err) { outcome[url] = err.message; }
    }));
    setResults(outcome);
    try {
      const status = await api.status();
      // The PC may have gained a Tailscale address since pairing; adopt it.
      const discovered = status.addresses.filter((a) => a.kind !== 'local').map((a) => a.url);
      const merged = Array.from(new Set([...list, ...discovered]));
      if (merged.length !== list.length) {
        await addresses.save(merged);
        setKnown(merged);
      }
      setServerAddresses(status.addresses);
    } catch { /* offline is already visible above */ }
    setBusy(false);
  }, []);

  useEffect(() => { test(); }, [test]);

  if (busy && !known.length) return <Loading label="Testing addresses…" />;

  return (
    <ScrollView contentContainerStyle={s.page}>
      <Notice kind="info">
        CodePilot tries every address it knows and sticks with whichever answers.
        On your home Wi-Fi that is the LAN address; anywhere else it is the
        Tailscale address, as long as Tailscale is connected on both devices.
      </Notice>

      <Section title="In use">
        <Card style={{ padding: 14 }}>
          <Text style={s.mono}>{currentBase() || 'not connected'}</Text>
        </Card>
      </Section>

      <Section title="Known addresses" right={<Button title="Re-test" onPress={test} />}>
        {known.map((url) => (
          <Card key={url} style={s.row}>
            <Text style={[s.mono, { flex: 1 }]} numberOfLines={1}>{url}</Text>
            <Badge
              text={results[url] === 'reachable' ? 'reachable' : 'no answer'}
              color={results[url] === 'reachable' ? theme.ok : theme.err}
            />
          </Card>
        ))}
      </Section>

      {serverAddresses.length ? (
        <Section title="Reported by the PC">
          {serverAddresses.map((a) => (
            <Card key={a.url} style={s.row}>
              <View style={{ flex: 1 }}>
                <Text style={s.mono} numberOfLines={1}>{a.url}</Text>
                <Text style={s.hint}>{a.note}</Text>
              </View>
              <Badge text={a.kind} />
            </Card>
          ))}
        </Section>
      ) : null}

      <Button
        title="Reconnect" style={{ marginTop: 22 }}
        onPress={() => { forgetBase(); test(); }}
      />
      <Button
        title="Unpair this phone" kind="danger" style={{ marginTop: 10 }}
        onPress={async () => {
          await credentials.clear();
          forgetBase();
          router.replace('/');
        }}
      />
      <Text style={s.footnote}>
        Unpairing only forgets the credential on this phone. To stop it being
        accepted at all, revoke the device on the PC dashboard.
      </Text>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 56 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 13, marginBottom: 8 },
  mono: { color: theme.fg, fontFamily: theme.mono, fontSize: 12 },
  hint: { color: theme.fgFaint, fontSize: 11, marginTop: 3 },
  footnote: { color: theme.fgFaint, fontSize: 12, marginTop: 12, lineHeight: 18 },
});
