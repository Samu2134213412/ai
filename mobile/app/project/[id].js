import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../../src/api';
import { Badge, Button, Card, Empty, Loading, Notice, Section } from '../../src/components/ui';
import { SessionCard } from '../../src/components/SessionCard';
import { theme } from '../../src/theme';

export default function ProjectScreen() {
  const { id } = useLocalSearchParams();
  const [state, setState] = useState({ phase: 'loading' });

  const load = useCallback(async () => {
    try {
      const [{ projects }, { sessions }] = await Promise.all([
        api.projects(), api.sessions(id),
      ]);
      const project = projects.find((p) => p.id === id);
      if (!project) { setState({ phase: 'error', message: 'This project no longer exists.' }); return; }
      let changes = { files: [], total_added: 0, total_removed: 0 };
      try { changes = await api.projectChanges(id); } catch { /* not a repo, or git missing */ }
      setState({ phase: 'ready', project, sessions, changes, projects });
    } catch (err) {
      setState({ phase: 'error', message: err.message });
    }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (state.phase === 'loading') return <Loading />;
  if (state.phase === 'error') {
    return <ScrollView contentContainerStyle={s.page}><Notice kind="err">{state.message}</Notice></ScrollView>;
  }

  const { project, sessions, changes, projects } = state;
  const git = project.git;

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={theme.accent} />}
    >
      <Card style={{ padding: 14 }}>
        <Text style={s.name}>{project.name}</Text>
        <Text style={s.path}>{project.path}</Text>
        <View style={s.badges}>
          {git?.branch ? <Badge text={git.branch} color={theme.accent} /> : null}
          <Badge
            text={project.exists === false ? 'folder missing'
                  : git?.is_repo ? (git.clean ? 'clean' : 'has changes') : 'no git'}
            color={project.exists === false ? theme.err
                   : git?.clean ? theme.ok : theme.warn}
          />
        </View>
        {project.error ? <Text style={s.err}>{project.error}</Text> : null}
      </Card>

      {git?.is_repo && !git.clean ? (
        <Section title="Git status">
          <Card>
            {git.files.slice(0, 40).map((file) => (
              <View key={file.path} style={s.fileRow}>
                <Text style={s.fileName} numberOfLines={1}>{file.path}</Text>
                <Badge text={file.status} color={
                  { modified: theme.warn, untracked: theme.accent,
                    added: theme.ok, deleted: theme.err }[file.status] || theme.fgMuted} />
              </View>
            ))}
            {git.files.length > 40
              ? <Text style={s.more}>{`+${git.files.length - 40} more`}</Text> : null}
          </Card>
        </Section>
      ) : null}

      <Button title="New task" kind="primary" style={{ marginTop: 20 }}
              onPress={() => router.push({ pathname: '/new-task', params: { projectId: id } })} />
      <Button
        title={`View changes (${changes.files.length} file${changes.files.length === 1 ? '' : 's'})`}
        style={{ marginTop: 10 }}
        disabled={!changes.files.length}
        onPress={() => router.push({ pathname: '/diff', params: { projectId: id } })}
      />

      <Section title={`Sessions (${sessions.length})`}>
        {sessions.length
          ? sessions.slice(0, 20).map((session) => (
              <SessionCard key={session.id} session={session} projects={projects} />))
          : <Empty text="No tasks have been run in this project yet." />}
      </Section>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 56 },
  name: { color: theme.fg, fontSize: 17, fontWeight: '600' },
  path: { color: theme.fgFaint, fontSize: 12, fontFamily: theme.mono, marginTop: 5 },
  badges: { flexDirection: 'row', gap: 8, marginTop: 12 },
  err: { color: theme.err, fontSize: 12, marginTop: 10 },
  fileRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 11,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.borderMuted,
  },
  fileName: { color: theme.fg, fontSize: 12, fontFamily: theme.mono, flex: 1 },
  more: { color: theme.fgFaint, fontSize: 12, padding: 11 },
});
