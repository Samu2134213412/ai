/* Small shared presentational pieces. */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../theme';

export function Card({ children, style }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Section({ title, children, right }) {
  return (
    <View style={{ marginTop: 22 }}>
      <View style={styles.sectionHead}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {right}
      </View>
      {children}
    </View>
  );
}

export function StatusDot({ ok, unknown }) {
  const color = unknown ? theme.fgFaint : ok ? theme.ok : theme.err;
  return <View style={[styles.dot, { backgroundColor: color }]} />;
}

export function StatusRow({ label, ok, value, unknown }) {
  return (
    <View style={styles.statusRow}>
      <StatusDot ok={ok} unknown={unknown} />
      <Text style={styles.statusLabel}>{label}</Text>
      <Text style={styles.statusValue} numberOfLines={1}>{value}</Text>
    </View>
  );
}

export function Button({ title, onPress, kind = 'default', disabled, style }) {
  const palette = {
    default: { bg: theme.inset, border: theme.border, fg: theme.fg },
    primary: { bg: '#1f6feb', border: '#388bfd', fg: '#ffffff' },
    danger: { bg: theme.inset, border: theme.err, fg: theme.err },
    ok: { bg: theme.inset, border: theme.ok, fg: theme.ok },
  }[kind];
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: palette.bg, borderColor: palette.border,
          opacity: disabled ? 0.45 : pressed ? 0.75 : 1 },
        style,
      ]}
    >
      <Text style={[styles.buttonText, { color: palette.fg }]}>{title}</Text>
    </Pressable>
  );
}

export function Badge({ text, color = theme.fgMuted }) {
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[styles.badgeText, { color }]}>{text}</Text>
    </View>
  );
}

export function Notice({ kind = 'info', children }) {
  const color = { info: theme.accent, warn: theme.warn, err: theme.err }[kind];
  return (
    <View style={[styles.notice, { borderLeftColor: color }]}>
      <Text style={styles.noticeText}>{children}</Text>
    </View>
  );
}

export function Loading({ label = 'Loading…' }) {
  return (
    <View style={styles.loading}>
      <ActivityIndicator color={theme.accent} />
      <Text style={styles.loadingText}>{label}</Text>
    </View>
  );
}

export function Empty({ text }) {
  return <Card style={{ padding: 20 }}><Text style={styles.empty}>{text}</Text></Card>;
}

export const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.elevated,
    borderWidth: 1, borderColor: theme.border,
    borderRadius: theme.radius,
  },
  sectionHead: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 8,
  },
  sectionTitle: { color: theme.fg, fontSize: 14, fontWeight: '600' },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusRow: {
    flexDirection: 'row', alignItems: 'center', gap: 9,
    paddingVertical: 7, paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.borderMuted,
  },
  statusLabel: { color: theme.fgMuted, fontSize: 13, flex: 1 },
  statusValue: { color: theme.fgFaint, fontSize: 12, fontFamily: theme.mono, maxWidth: '55%' },
  button: {
    borderWidth: 1, borderRadius: theme.radius,
    paddingVertical: 11, paddingHorizontal: 16, alignItems: 'center',
  },
  buttonText: { fontSize: 14, fontWeight: '600' },
  badge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 1 },
  badgeText: { fontSize: 11, fontFamily: theme.mono },
  notice: {
    backgroundColor: theme.elevated, borderWidth: 1, borderColor: theme.border,
    borderLeftWidth: 3, borderRadius: theme.radius, padding: 12, marginBottom: 12,
  },
  noticeText: { color: theme.fg, fontSize: 13, lineHeight: 19 },
  loading: { alignItems: 'center', paddingVertical: 40, gap: 10 },
  loadingText: { color: theme.fgMuted, fontSize: 13 },
  empty: { color: theme.fgFaint, fontSize: 13, textAlign: 'center' },
});
