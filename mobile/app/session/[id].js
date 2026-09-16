/* Session screen — the centre of the app.
 *
 * A chat-like transcript of a real Claude Code session, streaming over the
 * WebSocket. The task runs on the PC, so closing the app does not stop it; on
 * return the socket replays everything that happened while we were gone. */

import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from 'react-native';

import { api } from '../../src/api';
import { Badge, Button, Card, Loading, Notice } from '../../src/components/ui';
import { SessionStream } from '../../src/ws';
import { statusColor, theme } from '../../src/theme';

const CONNECTION_LABEL = {
  open: null,
  connecting: 'Connecting to your PC…',
  reconnecting: 'Reconnecting… the task keeps running on your PC.',
  offline: 'This phone is offline. The task keeps running on your PC.',
  unreachable: 'Cannot reach your PC. The task keeps running there; this view will catch up.',
  unpaired: 'This phone is no longer authorised. Pair it again from the PC.',
};

export default function SessionScreen() {
  const { id } = useLocalSearchParams();
  const navigation = useNavigation();
  const [events, setEvents] = useState([]);
  const [session, setSession] = useState(null);
  const [project, setProject] = useState(null);
  const [connection, setConnection] = useState('connecting');
  const [connectionDetail, setConnectionDetail] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);
  const streamRef = useRef(null);
  const seen = useRef(new Set());

  const refreshSession = useCallback(async () => {
    try {
      const body = await api.session(id);
      setSession(body.session);
      setProject(body.project);
      navigation.setOptions({ title: body.project?.name || 'Session' });
    } catch (err) { setError(err.message); }
  }, [id, navigation]);

  useEffect(() => {
    refreshSession();
    const stream = new SessionStream(id, {
      onEvent: (event) => {
        if (seen.current.has(event.seq)) return;
        seen.current.add(event.seq);
        setEvents((prev) => [...prev, event].sort((a, b) => a.seq - b.seq));
        if (['session.completed', 'session.failed', 'session.cancelled',
             'session.started'].includes(event.event_type)) {
          refreshSession();
        }
      },
      onStatus: (state, detail) => { setConnection(state); setConnectionDetail(detail); },
      onReplayComplete: () => refreshSession(),
    });
    streamRef.current = stream;
    stream.start(0);
    return () => stream.stop();
  }, [id, refreshSession]);

  const pendingApproval = useMemo(() => {
    const resolved = new Set(events
      .filter((e) => e.event_type === 'tool.approval_resolved')
      .map((e) => e.payload.approval_id));
    return events
      .filter((e) => e.event_type === 'tool.approval_required'
                     && !resolved.has(e.payload.approval_id))
      .map((e) => e.payload)
      .pop() || null;
  }, [events]);

  const decide = async (approve, reason) => {
    if (!pendingApproval) return;
    setBusy(true);
    try {
      await api.decideApproval(pendingApproval.approval_id, approve, reason);
    } catch (err) { setError(err.message); }
    setBusy(false);
  };

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (err) { setError(err.message); }
    setBusy(false);
  };

  const send = () => {
    const text = message.trim();
    if (!text) return;
    setMessage('');
    act(async () => {
      if (session?.status === 'running') {
        await api.sendMessage(id, text);
      } else {
        // Not running any more: continue the same Claude Code context in a new turn.
        const { session: next } = await api.continueSession(id, text);
        router.replace(`/session/${next.id}`);
      }
    });
  };

  if (!session && !events.length) return <Loading label="Loading session…" />;

  const running = session?.status === 'running';
  const connectionNote = CONNECTION_LABEL[connection];

  return (
    <KeyboardAvoidingView style={{ flex: 1 }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
                          keyboardVerticalOffset={90}>
      <View style={s.header}>
        <View style={{ flex: 1 }}>
          <Text style={s.prompt} numberOfLines={2}>{session?.prompt}</Text>
          <Text style={s.meta}>
            {session?.model}{session?.context_length ? ` · ${Math.round(session.context_length / 1024)}K` : ''}
            {session?.permission_mode ? ` · ${session.permission_mode}` : ''}
          </Text>
        </View>
        <Badge text={session?.status || '…'} color={statusColor(session?.status)} />
      </View>

      {connectionNote ? (
        <View style={s.banner}>
          <Text style={s.bannerText}>{connectionDetail || connectionNote}</Text>
        </View>
      ) : null}

      <ScrollView
        ref={scrollRef}
        contentContainerStyle={s.transcript}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {events.map((event) => <EventRow key={event.seq} event={event} />)}
        {!events.length ? <Text style={s.waiting}>Waiting for Claude Code…</Text> : null}
      </ScrollView>

      {error ? <View style={{ padding: 12 }}><Notice kind="err">{error}</Notice></View> : null}

      {pendingApproval ? (
        <ApprovalCard approval={pendingApproval} busy={busy} onDecide={decide} />
      ) : null}

      <View style={s.footer}>
        <View style={s.composer}>
          <TextInput
            style={s.input}
            value={message}
            onChangeText={setMessage}
            placeholder={running ? 'Send another message…' : 'Continue this session…'}
            placeholderTextColor={theme.fgFaint}
            multiline
          />
          <Button title="Send" kind="primary" disabled={busy || !message.trim()} onPress={send} />
        </View>
        <View style={s.controls}>
          {running ? (
            <Button title="Stop" kind="danger" style={{ flex: 1 }} disabled={busy}
                    onPress={() => act(() => api.stopSession(id))} />
          ) : null}
          <Button
            title="View changes" style={{ flex: 1 }}
            onPress={() => router.push({ pathname: '/diff', params: { sessionId: id } })}
          />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

function ApprovalCard({ approval, busy, onDecide }) {
  return (
    <Card style={s.approval}>
      <Text style={s.approvalTitle}>Claude Code wants to run</Text>
      <Text style={s.approvalTool}>{approval.tool_name}</Text>
      <View style={s.approvalBody}>
        <Text style={s.approvalCommand} selectable>{approval.summary}</Text>
      </View>
      <View style={s.approvalButtons}>
        <Button title="Approve Once" kind="ok" style={{ flex: 1 }} disabled={busy}
                onPress={() => onDecide(true)} />
        <Button title="Reject" kind="danger" style={{ flex: 1 }} disabled={busy}
                onPress={() => onDecide(false, 'Rejected from the CodePilot app.')} />
      </View>
      <Pressable
        onPress={() => onDecide(false,
          'Rejected from the CodePilot app — try a different approach instead.')}
        disabled={busy}
      >
        <Text style={s.approvalAlt}>Reject and ask for a different approach</Text>
      </Pressable>
      <Text style={s.approvalHint}>
        {`No answer within ${approval.timeout_seconds}s counts as a rejection.`}
      </Text>
    </Card>
  );
}

function EventRow({ event }) {
  const p = event.payload;
  switch (event.event_type) {
    case 'user.message':
      return <Row who="YOU" color={theme.fg} body={p.text} />;
    case 'assistant.message':
      return <Row who="CLAUDE" color={theme.accent} body={p.text} />;
    case 'tool.started':
      return <Row who={`TOOL · ${p.tool_name}`} color={theme.warn} mono
                  body={describeTool(p.tool_name, p.input)} />;
    case 'tool.finished':
      return (
        <Row
          who={`${p.tool_name} · ${p.is_error ? 'error' : 'result'}`}
          color={p.is_error ? theme.err : theme.ok}
          mono collapsible
          body={p.output || '(no output)'}
        />
      );
    case 'test.result':
      return <Row who="TESTS" color={p.passed ? theme.ok : theme.err} mono body={p.summary} />;
    case 'file.changed':
      return <Row who="FILES" color={theme.ok} mono
                  body={`${p.files.length} changed · +${p.total_added} / -${p.total_removed}`} />;
    case 'tool.approval_required':
      return <Row who="APPROVAL ASKED" color={theme.warn} mono body={p.summary} />;
    case 'tool.approval_resolved':
      return <Row who="APPROVAL" color={p.decision === 'approved' ? theme.ok : theme.err}
                  body={`${p.decision}${p.reason ? ` — ${p.reason}` : ''}`} />;
    case 'session.started':
      return <Row who="STARTED" color={theme.fgMuted} mono body={`${p.model} in ${p.cwd}`} />;
    case 'session.completed':
      return <Row who="COMPLETED" color={theme.ok} body={p.result || 'Task finished.'} />;
    case 'session.failed':
      return <Row who="FAILED" color={theme.err} body={p.result || 'The session failed.'} />;
    case 'session.cancelled':
      return <Row who="CANCELLED" color={theme.warn} body={p.reason || 'Stopped.'} />;
    case 'session.error':
      return <Row who="ERROR" color={theme.err} body={p.message} />;
    default:
      return null;  // status frames and raw stream chunks stay out of the transcript
  }
}

function Row({ who, color, body, mono, collapsible }) {
  const [open, setOpen] = useState(false);
  const text = String(body ?? '');
  const isLong = text.length > 400;
  const shown = collapsible && isLong && !open ? `${text.slice(0, 400)}…` : text;
  return (
    <View style={s.event}>
      <Text style={[s.who, { color }]}>{who}</Text>
      <Text style={[s.body, mono && s.bodyMono]} selectable>{shown}</Text>
      {collapsible && isLong ? (
        <Pressable onPress={() => setOpen(!open)}>
          <Text style={s.expand}>{open ? 'Show less' : `Show all ${text.length} characters`}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function describeTool(name, input = {}) {
  if (name === 'Bash') return input.command || '';
  if (input.file_path) return input.file_path;
  if (input.pattern) return `${input.pattern}${input.path ? ` in ${input.path}` : ''}`;
  if (input.url) return input.url;
  const keys = Object.keys(input);
  return keys.length ? JSON.stringify(input).slice(0, 300) : '(no arguments)';
}

const s = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14,
    backgroundColor: theme.elevated,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.border,
  },
  prompt: { color: theme.fg, fontSize: 14 },
  meta: { color: theme.fgFaint, fontSize: 11, fontFamily: theme.mono, marginTop: 3 },
  banner: { backgroundColor: '#3a2d00', paddingVertical: 8, paddingHorizontal: 14 },
  bannerText: { color: theme.warn, fontSize: 12 },
  transcript: { padding: 12, paddingBottom: 24 },
  waiting: { color: theme.fgFaint, fontSize: 13, textAlign: 'center', paddingVertical: 30 },
  event: {
    backgroundColor: theme.elevated, borderWidth: 1, borderColor: theme.borderMuted,
    borderRadius: theme.radius, padding: 12, marginBottom: 8,
  },
  who: { fontSize: 10, fontWeight: '700', letterSpacing: 0.6, marginBottom: 5,
         fontFamily: theme.mono },
  body: { color: theme.fg, fontSize: 14, lineHeight: 20 },
  bodyMono: { fontFamily: theme.mono, fontSize: 12, lineHeight: 17, color: theme.fgMuted },
  expand: { color: theme.accent, fontSize: 12, marginTop: 7 },
  approval: { margin: 12, padding: 14, borderColor: theme.warn },
  approvalTitle: { color: theme.warn, fontSize: 12, fontWeight: '700', letterSpacing: 0.5 },
  approvalTool: { color: theme.fg, fontSize: 15, fontWeight: '600', marginTop: 5 },
  approvalBody: {
    backgroundColor: theme.inset, borderRadius: 6, padding: 10, marginTop: 9,
  },
  approvalCommand: { color: theme.fg, fontFamily: theme.mono, fontSize: 12.5, lineHeight: 18 },
  approvalButtons: { flexDirection: 'row', gap: 10, marginTop: 12 },
  approvalAlt: { color: theme.accent, fontSize: 12, textAlign: 'center', marginTop: 11 },
  approvalHint: { color: theme.fgFaint, fontSize: 11, textAlign: 'center', marginTop: 8 },
  footer: {
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: theme.border,
    backgroundColor: theme.elevated, padding: 12, gap: 10,
  },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 9 },
  input: {
    flex: 1, backgroundColor: theme.inset, borderWidth: 1, borderColor: theme.border,
    borderRadius: theme.radius, color: theme.fg, paddingHorizontal: 11,
    paddingVertical: 9, fontSize: 14, maxHeight: 110,
  },
  controls: { flexDirection: 'row', gap: 10 },
});
