/* One row in any session list. */
import { router } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, Card } from './ui';
import { statusColor, theme } from '../theme';

export function SessionCard({ session, projects }) {
  const project = (projects || []).find((p) => p.id === session.project_id);
  return (
    <Pressable onPress={() => router.push(`/session/${session.id}`)}>
      <Card style={s.card}>
        <View style={{ flex: 1 }}>
          <Text style={s.title} numberOfLines={2}>{session.prompt}</Text>
          <Text style={s.sub}>
            {(project?.name || 'unknown project')} · {session.model}
          </Text>
        </View>
        <Badge text={session.status} color={statusColor(session.status)} />
      </Card>
    </Pressable>
  );
}

const s = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 13, marginBottom: 8 },
  title: { color: theme.fg, fontSize: 14 },
  sub: { color: theme.fgFaint, fontSize: 12, marginTop: 3 },
});
