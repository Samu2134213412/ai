/* Home: connection health, PC/Ollama/Claude Code status, live and recent work. */

import { router, useFocusEffect } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api, credentials, currentBase, forgetBase } from '../src/api';
import {
  Badge, Button, Card, Empty, Loading, Notice, Section, StatusRow,
} from '../src/components/ui';
import { SessionCard } from '../src/components/SessionCard';
import { statusColor, theme } from '../src/theme';

export default function HomeScreen() {
  const [state, setState] = useState({ phase: 'loading' });

  const load = useCallback(async () => {
    const token = await credentials.load();
    if (!token) { setState({ phase: 'unpaired' }); return; }
    try {
      const [status, projects, sessions] = await Promise.all([
        api.status(), api.projects(), api.sessions(),
      ]);
      setState({ phase: 'ready', status, projects: projects.projects,
                 sessions: sessions.sessions, base: currentBase() });
    } catch (err) {
      if (err.kind === 'unpaired') { setState({ phase: 'unpaired' }); return; }
      setState({ phase: 'error', message: err.message });
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (state.phase === 'loading') return <Loading label="Contacting your PC…" />;

  if (state.phase === 'unpaired') {
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Notice kind="info">
          This phone is not paired with a PC yet. Open the CodePilot dashboard on
          your PC, go to Pair Device, and scan the QR code.
        </Notice>
        <Button title="Pair with my PC" kind="primary" onPress={() => router.push('/pair')} />
      </ScrollView>
    );
  }

  if (state.phase === 'error') {
    return (
      <ScrollView
        contentContainerStyle={s.page}
        refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={theme.accent} />}
      >
        <Notice kind="err">{state.message}</Notice>
        <Button title="Try again" kind="primary" onPress={() => { forgetBase(); load(); }} />
        <Button title="Pair again" style={{ marginTop: 10 }} onPress={() => router.push('/pair')} />
      </ScrollView>
    );
  }

  const { status, projects, sessions, base } = state;
  const active = sessions.filter((x) => x.status === 'running');
  const recent = sessions.slice(0, 6);
  const problems = ['claude', 'git', 'ollama', 'model']
    .map((key) => status[key])
    .filter((c) => !c.available);

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={theme.accent} />}
    >
      <Pressable onPress={() => router.push('/connection')}>
        <Card>
          <View style={s.connHead}>
            <Text style={s.connTitle}>Connected</Text>
            <Text style={s.connUrl} numberOfLines={1}>{base}</Text>
          </View>
          <StatusRow label="Ollama" ok={status.ollama.available}
                     value={status.ollama.available ? status.ollama.version : 'offline'} />
          <StatusRow label="Claude Code" ok={status.claude.available}
                     value={status.claude.available ? status.claude.version : 'missing'} />
          <StatusRow label="Git" ok={status.git.available}
                     value={status.git.available ? status.git.version : 'missing'} />
          <StatusRow label="Model" ok={status.model.available}
                     value={status.settings.ollama_model} />
          <StatusRow label="Context" ok unknown
                     value={`${status.settings.context_length} tokens`} />
          <StatusRow label="Tailscale" ok={status.tailscale.available}
                     value={status.tailscale.available
                       ? (status.tailscale.extra.ips || ['up'])[0] : 'not set up'} />
        </Card>
      </Pressable>

      {problems.map((c) => (
        <View key={c.name} style={{ marginTop: 12 }}>
          <Notice kind="err">
            {`${c.name} is not available${c.detail ? `: ${c.detail}` : ''}.` +
             `${c.remedy ? `\n\nOn your PC run:  ${c.remedy}` : ''}`}
          </Notice>
        </View>
      ))}

      <Section
        title={`Active session${active.length === 1 ? '' : 's'} (${active.length})`}
      >
        {active.length
          ? active.map((session) => (
              <SessionCard key={session.id} session={session} projects={projects} />))
          : <Empty text="Nothing is running right now." />}
      </Section>

      <Section title="Projects" right={
        <Pressable onPress={() => router.push('/projects')}>
          <Text style={s.link}>See all</Text>
        </Pressable>}>
        {projects.length
          ? projects.slice(0, 4).map((project) => (
              <Pressable key={project.id} onPress={() => router.push(`/project/${project.id}`)}>
                <Card style={s.rowCard}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.rowTitle}>{project.name}</Text>
                    <Text style={s.rowSub} numberOfLines={1}>{project.path}</Text>
                  </View>
                  {project.git?.branch
                    ? <Badge text={project.git.branch} color={theme.fgMuted} />
                    : <Badge text="no git" color={theme.fgFaint} />}
                </Card>
              </Pressable>))
          : <Empty text="No projects yet. Add one from the dashboard on your PC." />}
      </Section>

      <Section title="Recent sessions">
        {recent.length
          ? recent.map((session) => (
              <SessionCard key={session.id} session={session} projects={projects} />))
          : <Empty text="No sessions yet." />}
      </Section>

      <Button title="New task" kind="primary" style={{ marginTop: 22 }}
              onPress={() => router.push('/new-task')} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 56 },
  connHead: {
    padding: 14, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.borderMuted,
  },
  connTitle: { color: theme.ok, fontSize: 13, fontWeight: '600' },
  connUrl: { color: theme.fgFaint, fontSize: 12, fontFamily: theme.mono, marginTop: 3 },
  rowCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 13, marginBottom: 8,
  },
  rowTitle: { color: theme.fg, fontSize: 14 },
  rowSub: { color: theme.fgFaint, fontSize: 12, marginTop: 3 },
  link: { color: theme.accent, fontSize: 13 },
});
