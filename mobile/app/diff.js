/* Changed files, and a readable per-file diff with add/remove highlighting. */

import { useLocalSearchParams } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../src/api';
import { Card, Empty, Loading, Notice } from '../src/components/ui';
import { theme } from '../src/theme';

export default function DiffScreen() {
  const { sessionId, projectId } = useLocalSearchParams();
  const [state, setState] = useState({ phase: 'loading' });
  const [selected, setSelected] = useState(null);
  const [diff, setDiff] = useState(null);

  const load = useCallback(async () => {
    try {
      if (sessionId) {
        const changes = await api.sessionChanges(sessionId);
        setState({ phase: 'ready', ...changes, projectId: changes.project_id });
      } else {
        const changes = await api.projectChanges(projectId);
        setState({ phase: 'ready', ...changes, projectId, base: null });
      }
    } catch (err) {
      setState({ phase: 'error', message: err.message });
    }
  }, [sessionId, projectId]);

  useEffect(() => { load(); }, [load]);

  const open = async (path) => {
    setSelected(path);
    setDiff(null);
    try {
      const body = await api.fileDiff(state.projectId, path, state.base);
      setDiff(body.diff);
    } catch (err) {
      setDiff(`Could not load this diff:\n${err.message}`);
    }
  };

  if (state.phase === 'loading') return <Loading />;
  if (state.phase === 'error') {
    return <ScrollView contentContainerStyle={s.page}><Notice kind="err">{state.message}</Notice></ScrollView>;
  }

  if (selected) {
    return (
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        <Pressable onPress={() => { setSelected(null); setDiff(null); }} style={s.back}>
          <Text style={s.backText}>‹ All changed files</Text>
        </Pressable>
        <Text style={s.fileHeading}>{selected}</Text>
        {diff === null ? <Loading label="Loading diff…" /> : <DiffBody text={diff} />}
      </ScrollView>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={theme.accent} />}
    >
      <Card style={s.summary}>
        <Text style={s.summaryText}>
          {state.files.length} file{state.files.length === 1 ? '' : 's'} changed
        </Text>
        <Text style={s.summaryStats}>
          <Text style={{ color: theme.add }}>+{state.total_added}</Text>
          {'  '}
          <Text style={{ color: theme.del }}>-{state.total_removed}</Text>
        </Text>
      </Card>
      {state.files.length ? state.files.map((file) => (
        <Pressable key={file.path} onPress={() => open(file.path)}>
          <Card style={s.fileRow}>
            <Text style={s.filePath} numberOfLines={2}>{file.path}</Text>
            <Text style={s.fileStats}>
              {file.binary ? (
                <Text style={{ color: theme.fgFaint }}>binary</Text>
              ) : (
                <>
                  <Text style={{ color: theme.add }}>+{file.added}</Text>
                  {'  '}
                  <Text style={{ color: theme.del }}>-{file.removed}</Text>
                </>
              )}
            </Text>
          </Card>
        </Pressable>
      )) : <Empty text="Nothing has changed in this project yet." />}
    </ScrollView>
  );
}

function DiffBody({ text }) {
  if (!text || !text.trim()) {
    return <View style={s.diff}><Text style={s.diffMeta}>(no textual diff)</Text></View>;
  }
  const lines = text.split('\n');
  return (
    <ScrollView horizontal contentContainerStyle={{ minWidth: '100%' }}>
      <View style={s.diff}>
        {lines.map((line, index) => {
          let style = s.diffContext;
          if (/^(\+\+\+|---|diff |index |new file|deleted file)/.test(line)) style = s.diffMeta;
          else if (line.startsWith('@@')) style = s.diffHunk;
          else if (line.startsWith('+')) style = s.diffAdd;
          else if (line.startsWith('-')) style = s.diffDel;
          return <Text key={index} style={[s.diffLine, style]} selectable>{line || ' '}</Text>;
        })}
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 48 },
  summary: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: 14, marginBottom: 12,
  },
  summaryText: { color: theme.fg, fontSize: 14 },
  summaryStats: { fontFamily: theme.mono, fontSize: 13 },
  fileRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    gap: 12, padding: 13, marginBottom: 8,
  },
  filePath: { color: theme.fg, fontFamily: theme.mono, fontSize: 12.5, flex: 1 },
  fileStats: { fontFamily: theme.mono, fontSize: 12 },
  back: { padding: 14 },
  backText: { color: theme.accent, fontSize: 14 },
  fileHeading: {
    color: theme.fg, fontFamily: theme.mono, fontSize: 13,
    paddingHorizontal: 14, paddingBottom: 10,
  },
  diff: { backgroundColor: theme.inset, paddingVertical: 8, minWidth: '100%' },
  diffLine: { fontFamily: theme.mono, fontSize: 11.5, lineHeight: 17, paddingHorizontal: 12 },
  diffContext: { color: theme.fgMuted },
  diffMeta: { color: theme.fgFaint },
  diffHunk: { color: theme.accent, backgroundColor: 'rgba(88,166,255,0.08)' },
  diffAdd: { color: '#7ee787', backgroundColor: 'rgba(46,160,67,0.15)' },
  diffDel: { color: '#ffa198', backgroundColor: 'rgba(248,81,73,0.13)' },
});
