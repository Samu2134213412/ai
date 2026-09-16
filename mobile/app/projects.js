import { router, useFocusEffect } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../src/api';
import { Badge, Card, Empty, Loading, Notice } from '../src/components/ui';
import { theme } from '../src/theme';

export default function ProjectsScreen() {
  const [state, setState] = useState({ phase: 'loading' });

  const load = useCallback(async () => {
    try {
      const { projects } = await api.projects();
      setState({ phase: 'ready', projects });
    } catch (err) {
      setState({ phase: 'error', message: err.message });
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (state.phase === 'loading') return <Loading />;
  if (state.phase === 'error') {
    return <ScrollView contentContainerStyle={s.page}><Notice kind="err">{state.message}</Notice></ScrollView>;
  }

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={theme.accent} />}
    >
      <Notice kind="info">
        Claude Code can only work inside these folders. Add or remove them on the
        PC dashboard — a phone deliberately cannot change the list.
      </Notice>
      {state.projects.length ? state.projects.map((project) => (
        <Pressable key={project.id} onPress={() => router.push(`/project/${project.id}`)}>
          <Card style={s.card}>
            <View style={s.cardHead}>
              <Text style={s.name}>{project.name}</Text>
              {project.exists === false
                ? <Badge text="missing" color={theme.err} />
                : project.git?.branch
                  ? <Badge text={project.git.branch} />
                  : <Badge text="no git" color={theme.fgFaint} />}
            </View>
            <Text style={s.path} numberOfLines={1}>{project.path}</Text>
            <Text style={s.meta}>
              {project.error
                ? project.error
                : project.git?.is_repo
                  ? (project.git.clean
                      ? 'working tree clean'
                      : Object.entries(project.git.counts)
                          .map(([k, v]) => `${v} ${k}`).join(' · '))
                  : 'not a git repository'}
            </Text>
          </Card>
        </Pressable>
      )) : <Empty text="No projects configured yet." />}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 48 },
  card: { padding: 14, marginBottom: 10 },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { color: theme.fg, fontSize: 15, fontWeight: '600', flex: 1 },
  path: { color: theme.fgFaint, fontSize: 12, fontFamily: theme.mono, marginTop: 5 },
  meta: { color: theme.fgMuted, fontSize: 12, marginTop: 7 },
});
