/* Shared dark palette — same tokens as the desktop dashboard. */
export const theme = {
  bg: '#0d1117',
  elevated: '#161b22',
  inset: '#010409',
  border: '#30363d',
  borderMuted: '#21262d',
  fg: '#e6edf3',
  fgMuted: '#8b949e',
  fgFaint: '#6e7681',
  accent: '#58a6ff',
  ok: '#3fb950',
  warn: '#d29922',
  err: '#f85149',
  add: '#3fb950',
  del: '#f85149',
  radius: 8,
  mono: 'monospace',
};

export const statusColor = (status) => ({
  running: theme.accent,
  completed: theme.ok,
  failed: theme.err,
  cancelled: theme.warn,
}[status] || theme.fgMuted);
