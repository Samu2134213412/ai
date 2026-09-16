/* New Task: prompt, project, model, context size and approval mode. */

import { router, useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from 'react-native';

import { api } from '../src/api';
import { Button, Card, Loading, Notice } from '../src/components/ui';
import { theme } from '../src/theme';

const APPROVAL_MODES = [
  { value: 'manual', label: 'Ask me', hint: 'Claude Code asks this phone before anything it considers risky.' },
  { value: 'acceptEdits', label: 'Auto-accept edits', hint: 'File edits go through; commands still ask.' },
  { value: 'plan', label: 'Plan only', hint: 'Claude Code investigates and proposes, but changes nothing.' },
];

/** A short, honest line about a model option — real size/quant data from
 * Ollama, plus a caution (never a promise) when it looks too big for the
 * card's VRAM. Bigger is not automatically better for an agent loop: once a
 * model spills into system RAM, generation slows down a lot, not gracefully. */
function modelHint(name, models) {
  if (name === models.configured && !models.model_available) return 'not pulled yet';
  const detail = (models.installed_details || []).find((d) => d.name === name);
  if (!detail) return undefined;
  const parts = [];
  if (detail.size_gb != null) parts.push(`${detail.size_gb} GB`);
  if (detail.parameter_size) parts.push(detail.parameter_size);
  if (detail.quantization) parts.push(detail.quantization);
  const tight = (detail.fits_hint || '').startsWith('likely exceeds');
  if (tight) parts.push('tight VRAM — slower');
  return parts.join(' · ') || undefined;
}

export default function NewTaskScreen() {
  const params = useLocalSearchParams();
  const [projects, setProjects] = useState(null);
  const [models, setModels] = useState(null);
  const [projectId, setProjectId] = useState(params.projectId || null);
  const [model, setModel] = useState(null);
  const [contextLength, setContextLength] = useState(null);
  const [mode, setMode] = useState('manual');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [{ projects: list }, modelInfo] = await Promise.all([api.projects(), api.models()]);
        setProjects(list);
        setModels(modelInfo);
        setModel(modelInfo.configured);
        setContextLength(modelInfo.context_length);
        if (!projectId && list.length) setProjectId(list[0].id);
      } catch (err) { setError(err.message); }
    })();
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !projects) {
    return <ScrollView contentContainerStyle={s.page}><Notice kind="err">{error}</Notice></ScrollView>;
  }
  if (!projects || !models) return <Loading />;

  if (!projects.length) {
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Notice kind="warn">
          There are no projects yet. Add one on the CodePilot dashboard on your PC
          before starting a task.
        </Notice>
      </ScrollView>
    );
  }

  const modelOptions = Array.from(new Set([models.configured, ...models.installed]));
  const blocked = !models.online || !models.model_available;

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const { session } = await api.createSession({
        project_id: projectId,
        prompt: prompt.trim(),
        model,
        permission_mode: mode,
        context_length: contextLength,
      });
      router.replace(`/session/${session.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
        {error ? <Notice kind="err">{error}</Notice> : null}
        {blocked ? (
          <Notice kind="err">
            {`${models.detail || 'The model is not ready.'}` +
             `${models.remedy ? `\n\nOn your PC run:  ${models.remedy}` : ''}` +
             '\n\nYou can still start a task, but Claude Code will fail until this is fixed.'}
          </Notice>
        ) : null}

        <Text style={s.label}>Task</Text>
        <TextInput
          style={s.prompt}
          value={prompt}
          onChangeText={setPrompt}
          multiline
          placeholder="Find why the coder stage is failing and fix it."
          placeholderTextColor={theme.fgFaint}
          textAlignVertical="top"
        />

        <Text style={s.label}>Project</Text>
        <Chooser
          options={projects.map((p) => ({ value: p.id, label: p.name, hint: p.path }))}
          value={projectId}
          onChange={setProjectId}
        />

        <Text style={s.label}>Model</Text>
        <Chooser
          options={modelOptions.map((m) => ({
            value: m, label: m, hint: modelHint(m, models),
          }))}
          value={model}
          onChange={setModel}
        />

        <Text style={s.label}>Context size</Text>
        <Chooser
          options={models.context_choices.map((c) => ({
            value: c,
            label: `${Math.round(c / 1024)}K`,
            hint: c === 32768 ? 'safe on 24 GB' : c >= 65536 ? 'tight on 24 GB' : undefined,
          }))}
          value={contextLength}
          onChange={setContextLength}
          horizontal
        />

        <Text style={s.label}>Approval mode</Text>
        <Chooser
          options={APPROVAL_MODES.map((m) => ({ value: m.value, label: m.label, hint: m.hint }))}
          value={mode}
          onChange={setMode}
        />

        <Button
          title={busy ? 'Starting…' : 'Start Claude Code'}
          kind="primary"
          disabled={busy || !prompt.trim() || !projectId}
          style={{ marginTop: 22 }}
          onPress={start}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Chooser({ options, value, onChange, horizontal }) {
  return (
    <View style={horizontal ? s.chooserRow : undefined}>
      {options.map((option) => {
        const selected = String(option.value) === String(value);
        return (
          <Pressable key={String(option.value)} onPress={() => onChange(option.value)}
                     style={horizontal ? { flex: 1 } : undefined}>
            <Card style={[s.option, selected && s.optionSelected,
                          horizontal && { marginRight: 6 }]}>
              <Text style={[s.optionLabel, selected && { color: theme.accent }]}>
                {option.label}
              </Text>
              {option.hint
                ? <Text style={s.optionHint} numberOfLines={2}>{option.hint}</Text>
                : null}
            </Card>
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  page: { padding: 16, paddingBottom: 56 },
  label: { color: theme.fgMuted, fontSize: 12, marginTop: 20, marginBottom: 7 },
  prompt: {
    backgroundColor: theme.inset, borderWidth: 1, borderColor: theme.border,
    borderRadius: theme.radius, color: theme.fg, padding: 12,
    minHeight: 110, fontSize: 15, lineHeight: 21,
  },
  chooserRow: { flexDirection: 'row' },
  option: { padding: 12, marginBottom: 7 },
  optionSelected: { borderColor: theme.accent },
  optionLabel: { color: theme.fg, fontSize: 14 },
  optionHint: { color: theme.fgFaint, fontSize: 11, marginTop: 3, fontFamily: theme.mono },
});
