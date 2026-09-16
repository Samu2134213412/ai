/* CodePilot Remote — desktop dashboard.
 * Runs on the PC itself, so it uses the loopback-only admin endpoints and needs
 * no device token. Every value rendered here comes from the backend; nothing is
 * placeholder data. */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'content-type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }
  if (!res.ok) throw new Error((body && body.detail) || `HTTP ${res.status}`);
  return body;
}

const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleString() : '—';
const fmtAgo = (ts) => {
  if (!ts) return 'never';
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};
const fmtDuration = (a, b) => {
  if (!a) return '—';
  const s = Math.round(((b || Date.now() / 1000) - a));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
};

function notice(kind, ...content) {
  return el('div', { class: `notice ${kind}` }, ...content);
}

function dot(state) { return el('span', { class: `dot ${state}` }); }

// --------------------------------------------------------------- status strip
let lastStatus = null;

async function refreshStatus() {
  const strip = $('#statusStrip');
  try {
    const s = await api('/api/status/local');
    lastStatus = s;
    strip.replaceChildren(
      statusRow('Ollama', s.ollama.available, s.ollama.version || 'offline'),
      statusRow('Claude Code', s.claude.available, s.claude.version || 'missing'),
      statusRow('Git', s.git.available, s.git.version || 'missing'),
      statusRow('Model', s.model.available, s.settings.ollama_model),
      statusRow('Tailscale', s.tailscale.available,
                s.tailscale.available ? (s.tailscale.extra.ips || [])[0] || 'up' : 'off'),
    );
  } catch (err) {
    lastStatus = null;
    strip.replaceChildren(el('div', { class: 'row' }, dot('err'),
      el('span', { class: 'label' }, 'Server unreachable')));
  }
}

function statusRow(label, ok, value) {
  return el('div', { class: 'row' }, dot(ok ? 'ok' : 'err'),
    el('span', { class: 'label' }, label),
    el('span', { class: 'value', title: value }, value || ''));
}

// -------------------------------------------------------------------- routes
const routes = {};

routes.dashboard = async (main) => {
  main.replaceChildren(el('div', { class: 'loading' }, 'Checking environment…'));
  let s;
  try { s = await api('/api/status/local'); }
  catch (err) { main.replaceChildren(notice('err', `Cannot reach the backend: ${err.message}`)); return; }

  const [{ projects }, { sessions }] = await Promise.all([
    api('/api/projects/local'), api('/api/sessions/local?limit=8'),
  ]);
  const active = sessions.filter((x) => x.status === 'running');

  const problems = [];
  for (const key of ['claude', 'git', 'ollama', 'model']) {
    const c = s[key];
    if (!c.available) {
      problems.push(notice('err',
        el('strong', {}, `${c.name}: not available. `),
        c.detail ? `${c.detail}. ` : '',
        c.remedy ? el('span', {}, 'Fix: ', el('code', {}, c.remedy)) : ''));
    } else if (c.detail) {
      problems.push(notice('warn', el('strong', {}, `${c.name}: `), c.detail,
        c.remedy ? el('span', {}, ' — ', el('code', {}, c.remedy)) : ''));
    }
  }

  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Dashboard')),
    el('p', { class: 'subtitle' }, 'Live state of this machine. Nothing here is cached or simulated.'),
    ...problems,
    el('div', { class: 'grid two' },
      card('Environment', el('dl', { class: 'kv' },
        ...kv('Claude Code', s.claude.available ? s.claude.version : 'missing'),
        ...kv('Ollama', s.ollama.available ? `${s.ollama.version} @ ${s.settings.ollama_url}` : 'offline'),
        ...kv('Anthropic API', s.ollama.available ?
          (s.ollama.extra.anthropic_api ? 'supported (v0.14+)' : 'NOT supported — update Ollama') : '—'),
        ...kv('Git', s.git.available ? s.git.version : 'missing'),
        ...kv('Model', `${s.settings.ollama_model} — ${s.model.available ? 'Available' : 'Missing'}`),
        ...kv('Context', `${s.settings.context_length} tokens`),
        ...kv('Model timeout', `${s.settings.model_timeout}s`),
        ...kv('Gateway', s.settings.compat_proxy_enabled ?
          `http://127.0.0.1:${s.settings.port}/llm (compat proxy)` : s.settings.ollama_url))),
      card('Reachable addresses', s.addresses.length
        ? el('table', {}, el('tbody', {}, ...s.addresses.map((a) => el('tr', {},
            el('td', { class: 'mono' }, a.url),
            el('td', {}, el('span', { class: 'badge' }, a.kind)),
            el('td', { class: 'hint' }, a.note)))))
        : el('div', { class: 'empty' }, 'none')),
    ),
    el('h2', {}, `Active sessions (${active.length})`),
    active.length ? sessionTable(active, projects) : el('div', { class: 'card empty' }, 'No session is running.'),
    el('h2', {}, 'Recent sessions'),
    sessions.length ? sessionTable(sessions.slice(0, 8), projects)
      : el('div', { class: 'card empty' }, 'No sessions yet. Start one from the mobile app.'),
    el('h2', {}, `Projects (${projects.length})`),
    projects.length ? projectTable(projects, false)
      : el('div', { class: 'card empty' }, 'No projects yet — add one on the Projects page.'),
  );
};

function card(title, ...body) {
  return el('div', { class: 'card' },
    el('div', { class: 'card-pad' }, el('h2', { style: 'margin:0 0 10px' }, title), ...body));
}
function kv(k, v) { return [el('dt', {}, k), el('dd', {}, v ?? '—')]; }

function projectTable(projects, withActions = true) {
  return el('div', { class: 'card' }, el('table', {},
    el('thead', {}, el('tr', {},
      el('th', {}, 'Name'), el('th', {}, 'Path'), el('th', {}, 'Branch'),
      el('th', {}, 'Changes'), el('th', {}, 'Last used'), withActions ? el('th', {}, '') : null)),
    el('tbody', {}, ...projects.map((p) => {
      const git = p.git;
      let changes = '—';
      if (p.error) changes = p.error;
      else if (git && git.is_repo) {
        changes = git.clean ? 'clean'
          : Object.entries(git.counts).map(([k, v]) => `${v} ${k}`).join(', ');
      } else if (git) changes = 'not a git repo';
      return el('tr', {},
        el('td', {}, p.exists ? p.name : el('span', {},
          p.name, ' ', el('span', { class: 'badge failed' }, 'missing'))),
        el('td', { class: 'mono' }, p.path),
        el('td', { class: 'mono' }, (git && git.branch) || '—'),
        el('td', { class: p.error ? 'hint' : '' }, changes),
        el('td', { class: 'hint' }, fmtAgo(p.last_used || p.created_at)),
        withActions ? el('td', {}, el('button', {
          class: 'small danger',
          onclick: async () => {
            if (!confirm(`Remove "${p.name}" from the allowlist?\n\nThe folder on disk is not touched.`)) return;
            await api(`/api/projects/${p.id}`, { method: 'DELETE' });
            render();
          },
        }, 'Remove')) : null);
    }))));
}

function sessionTable(sessions, projects) {
  const byId = Object.fromEntries((projects || []).map((p) => [p.id, p]));
  return el('div', { class: 'card' }, el('table', {},
    el('thead', {}, el('tr', {},
      el('th', {}, 'Status'), el('th', {}, 'Prompt'), el('th', {}, 'Project'),
      el('th', {}, 'Model'), el('th', {}, 'Started'), el('th', {}, 'Duration'))),
    el('tbody', {}, ...sessions.map((s) => el('tr', {
      style: 'cursor:pointer', onclick: () => { location.hash = `#/session/${s.id}`; },
    },
      el('td', {}, el('span', { class: `badge ${s.status}` }, s.status)),
      el('td', {}, (s.prompt || '').slice(0, 90) + ((s.prompt || '').length > 90 ? '…' : '')),
      el('td', {}, (byId[s.project_id] || {}).name || '—'),
      el('td', { class: 'mono' }, s.model || '—'),
      el('td', { class: 'hint' }, fmtAgo(s.started_at)),
      el('td', { class: 'hint' }, fmtDuration(s.started_at, s.ended_at)))))));
}

routes.projects = async (main) => {
  const { projects } = await api('/api/projects/local');
  const nameInput = el('input', { placeholder: 'Agent Factory' });
  const pathInput = el('input', { placeholder: 'C:\\Users\\you\\code\\agent-factory', class: 'mono' });
  const msg = el('div');

  const submit = async () => {
    msg.replaceChildren();
    try {
      await api('/api/projects', {
        method: 'POST',
        body: JSON.stringify({ name: nameInput.value, path: pathInput.value }),
      });
      nameInput.value = ''; pathInput.value = '';
      render();
    } catch (err) { msg.replaceChildren(notice('err', err.message)); }
  };

  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Projects')),
    el('p', { class: 'subtitle' },
      'Claude Code sessions may only run inside these directories. This allowlist can only be edited here, on the PC — a paired phone cannot add or change it.'),
    el('div', { class: 'card card-pad' },
      el('div', { class: 'row-inline' },
        el('div', { class: 'field' }, el('label', {}, 'Name'), nameInput),
        el('div', { class: 'field' }, el('label', {}, 'Absolute path'), pathInput),
        el('button', { class: 'primary', onclick: submit }, 'Add project')),
      el('div', { class: 'hint' }, 'The path must already exist. Symlinks are resolved, and file access is confined to the resolved directory.'),
      msg),
    el('h2', {}, `Allowed projects (${projects.length})`),
    projects.length ? projectTable(projects, true) : el('div', { class: 'card empty' }, 'None yet.'),
  );
};

routes.sessions = async (main) => {
  const [{ sessions }, { projects }] = await Promise.all([
    api('/api/sessions/local?limit=100'), api('/api/projects/local'),
  ]);
  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Sessions')),
    el('p', { class: 'subtitle' }, 'Full history. Click a row to open the transcript.'),
    sessions.length ? sessionTable(sessions, projects)
      : el('div', { class: 'card empty' }, 'No sessions recorded yet.'),
  );
};

routes.models = async (main) => {
  main.replaceChildren(el('div', { class: 'loading' }, 'Querying Ollama…'));
  let m;
  try { m = await api('/api/models/local'); }
  catch (err) { main.replaceChildren(notice('err', err.message)); return; }

  const detailsByName = Object.fromEntries(
    (m.installed_details || []).map((d) => [d.name, d]));

  const isTight = (name) => (detailsByName[name]?.fits_hint || '').startsWith('likely exceeds');

  const rows = m.installed.length
    ? el('div', { class: 'card' }, el('table', {},
        el('thead', {}, el('tr', {}, el('th', {}, 'Model'), el('th', {}, 'Size'),
          el('th', {}, 'Parameters'), el('th', {}, 'Quantization'), el('th', {}, ''))),
        el('tbody', {}, ...m.installed.map((name) => {
          const d = detailsByName[name] || {};
          return el('tr', {},
            el('td', { class: 'mono' }, name, isTight(name)
              ? el('span', { class: 'badge failed', style: 'margin-left:6px' }, 'tight VRAM') : null),
            el('td', {}, d.size_gb != null ? `${d.size_gb} GB` : '—'),
            el('td', { class: 'mono' }, d.parameter_size || '—'),
            el('td', { class: 'mono' }, d.quantization || '—'),
            el('td', {}, name === m.configured
              ? el('span', { class: 'badge completed' }, 'in use')
              : el('button', {
                  class: 'small',
                  onclick: async () => {
                    await api('/api/settings', {
                      method: 'PUT', body: JSON.stringify({ ollama_model: name }),
                    });
                    render(); refreshStatus();
                  },
                }, 'Use this model')),
          );
        }))))
    : el('div', { class: 'card empty' },
        m.online ? 'Ollama has no models pulled yet.' : 'Ollama is offline.');

  const anyTight = m.installed.some(isTight);

  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Models')),
    el('p', { class: 'subtitle' }, 'Discovered from your Ollama server. CodePilot never starts a download on its own.'),
    !m.model_available ? notice('err',
      el('strong', {}, `${m.configured} is not available. `),
      m.detail ? `${m.detail}. ` : '',
      m.install_command ? el('span', {}, 'Pull it with ', el('code', {}, m.install_command),
        ' — that is roughly 18 GB, so it is left for you to run.') : '') : null,
    el('div', { class: 'card card-pad' }, el('dl', { class: 'kv' },
      ...kv('Provider', m.provider),
      ...kv('Configured model', m.configured),
      ...kv('Ollama', m.online ? 'online' : 'offline'),
      ...kv('Context length', `${m.context_length} tokens`))),
    el('h2', {}, `Installed models (${m.installed.length})`),
    el('p', { class: 'subtitle', style: 'margin:-4px 0 10px' },
      'Pick any of these as the default here, or per task from the phone. Bigger is not ',
      'automatically better for an agent loop — a model that spills out of VRAM gets much slower, ',
      'not just a little slower.'),
    rows,
    anyTight ? notice('warn',
      el('strong', {}, 'Models marked "tight VRAM" are larger than this machine likely has free ',
        'video memory for. '),
      'Ollama will still run them by offloading part of the model to the CPU, but expect generation to ',
      'slow down a lot rather than gracefully. This is a caution based on typical overhead on a 24 GB ',
      'card, not a guarantee — try it if you want to trade speed for a bigger model.') : null,
    notice('info',
      el('strong', {}, 'About context size. '),
      'A 30B model quantised to 4-bit uses roughly 18 GB of your 24 GB card, so the KV cache has a few GB to work with. ',
      '32K is the default and fits comfortably; 64K is selectable but will be tight alongside a long tool transcript. ',
      'Ollama reads the window from its own server process, so also set ',
      el('code', {}, 'OLLAMA_CONTEXT_LENGTH'), ' before starting ', el('code', {}, 'ollama serve'), '.'),
  );
};

routes.settings = async (main) => {
  const { settings, context_choices, providers } = await api('/api/settings');
  const msg = el('div');
  const fields = {};

  const field = (key, label, input, hint) => {
    fields[key] = input;
    return el('div', { class: 'field' }, el('label', {}, label), input,
      hint ? el('div', { class: 'hint' }, hint) : null);
  };
  const select = (value, options) => {
    const s = el('select', {});
    for (const opt of options) {
      const o = el('option', { value: String(opt.value) }, opt.label);
      if (String(opt.value) === String(value)) o.selected = true;
      s.append(o);
    }
    return s;
  };

  const save = async () => {
    msg.replaceChildren();
    const payload = {
      bind_mode: fields.bind_mode.value,
      port: Number(fields.port.value),
      ollama_url: fields.ollama_url.value.trim(),
      ollama_model: fields.ollama_model.value.trim(),
      context_length: Number(fields.context_length.value),
      model_timeout: Number(fields.model_timeout.value),
      compat_proxy_enabled: fields.compat_proxy_enabled.value === 'true',
      claude_binary: fields.claude_binary.value.trim(),
      default_permission_mode: fields.default_permission_mode.value,
      approval_timeout: Number(fields.approval_timeout.value),
    };
    try {
      const out = await api('/api/settings', { method: 'PUT', body: JSON.stringify(payload) });
      msg.replaceChildren(notice(out.restart_required ? 'warn' : 'info',
        out.restart_required
          ? 'Saved. Restart the server for the new address or port to take effect.'
          : 'Saved. Changes apply to the next session you start.'));
      refreshStatus();
    } catch (err) { msg.replaceChildren(notice('err', err.message)); }
  };

  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Settings')),
    el('p', { class: 'subtitle' },
      'Stored outside the repository, in the CodePilot config directory. Secrets are never written to the project.'),
    el('div', { class: 'grid two' },
      card('Network',
        field('bind_mode', 'Network access', select(settings.bind_mode, [
          { value: 'local', label: 'This PC only (127.0.0.1)' },
          { value: 'private', label: 'LAN + Tailscale (0.0.0.0)' },
        ]), 'Your phone needs "LAN + Tailscale". The server is never exposed to the public internet; for access from outside your home, use Tailscale, not port forwarding.'),
        field('port', 'Port', el('input', { type: 'number', value: settings.port, min: 1, max: 65535 }))),
      card('Model',
        field('ollama_url', 'Ollama URL', el('input', { value: settings.ollama_url, class: 'mono' })),
        field('ollama_model', 'Model', el('input', { value: settings.ollama_model, class: 'mono' })),
        field('context_length', 'Context size',
          select(settings.context_length, context_choices.map((c) => ({ value: c, label: `${c} tokens` }))),
          '32K is the safe default on a 24 GB card. Also set OLLAMA_CONTEXT_LENGTH for the ollama serve process.'),
        field('model_timeout', 'Model timeout (s)', el('input', { type: 'number', value: settings.model_timeout, min: 10 })),
        field('compat_proxy_enabled', 'Compatibility proxy', select(String(settings.compat_proxy_enabled), [
          { value: 'true', label: 'On (recommended)' }, { value: 'false', label: 'Off — talk to Ollama directly' },
        ]), 'Answers /v1/messages/count_tokens locally, which Ollama does not implement. Works around ollama/ollama#13949.')),
      card('Claude Code',
        field('claude_binary', 'Binary', el('input', { value: settings.claude_binary, class: 'mono' })),
        field('default_permission_mode', 'Default approval mode', select(settings.default_permission_mode, [
          { value: 'manual', label: 'manual — ask my phone (recommended)' },
          { value: 'acceptEdits', label: 'acceptEdits — auto-accept file edits' },
          { value: 'plan', label: 'plan — plan only, no changes' },
        ]), 'This selects which of Claude Code\'s own permission modes to run in. CodePilot never bypasses permissions; there is deliberately no option here for that.'),
        field('approval_timeout', 'Approval timeout (s)', el('input', { type: 'number', value: settings.approval_timeout, min: 10 }),
          'If nobody answers on the phone within this time, the operation is denied.')),
      card('Provider', el('dl', { class: 'kv' },
        ...kv('Active', settings.provider), ...kv('Implemented', providers.join(', '))),
        el('div', { class: 'hint', style: 'margin-top:8px' },
          'Other backends (Claude API, OpenAI-compatible gateways, Agent Factory, other local runtimes) plug in through the same provider interface. None are implemented yet.')),
    ),
    el('div', { style: 'margin-top:14px' }, el('button', { class: 'primary', onclick: save }, 'Save settings')),
    msg,
  );
};

routes.pair = async (main) => {
  main.replaceChildren(el('div', { class: 'loading' }, 'Generating pairing token…'));
  let data;
  try { data = await api('/api/pairing/token', { method: 'POST' }); }
  catch (err) { main.replaceChildren(notice('err', err.message)); return; }

  const { devices } = await api('/api/devices');
  const qrBox = el('div', { class: 'qr' }, 'loading…');
  fetch(`/api/pairing/qr.svg?payload=${encodeURIComponent(data.qr_payload)}`)
    .then((r) => (r.ok ? r.text() : Promise.reject(new Error('QR rendering failed'))))
    .then((svg) => { qrBox.innerHTML = svg; })
    .catch(() => { qrBox.replaceChildren(el('div', { class: 'hint', style: 'color:#000' },
      'QR rendering needs the "qrcode" package. Type the token into the app instead.')); });

  const countdown = el('span', {});
  const tick = () => {
    const left = Math.max(0, Math.round(data.expires_at - Date.now() / 1000));
    countdown.textContent = left ? `expires in ${left}s` : 'expired — reload this page for a new one';
  };
  tick(); const timer = setInterval(tick, 1000);
  main.addEventListener('codepilot:leave', () => clearInterval(timer), { once: true });

  main.replaceChildren(
    el('div', { class: 'page-head' }, el('h1', {}, 'Pair Device')),
    el('p', { class: 'subtitle' },
      'Scan this with the CodePilot app. The token is single-use and expires after five minutes.'),
    data.warning ? notice('warn', data.warning) : null,
    el('div', { class: 'grid two' },
      el('div', { class: 'card card-pad' }, qrBox,
        el('div', { class: 'hint', style: 'margin-top:10px' }, countdown)),
      card('If the camera will not cooperate',
        el('p', { class: 'hint' }, 'Enter these in the app manually:'),
        el('dl', { class: 'kv' },
          ...kv('Token', data.token),
          ...kv('Addresses', data.addresses.map((a) => a.url).join('\n'))),
        el('p', { class: 'hint', style: 'margin-top:10px' },
          'The app stores only the long-lived credential it gets back, in the Android keystore. ',
          'This pairing token itself is destroyed the moment it is used.')),
    ),
    el('h2', {}, `Paired devices (${devices.length})`),
    devices.length ? el('div', { class: 'card' }, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}, 'Device'), el('th', {}, 'Paired'),
        el('th', {}, 'Last seen'), el('th', {}, 'State'), el('th', {}, ''))),
      el('tbody', {}, ...devices.map((d) => el('tr', {},
        el('td', {}, d.name),
        el('td', { class: 'hint' }, fmtTime(d.created_at)),
        el('td', { class: 'hint' }, fmtAgo(d.last_seen)),
        el('td', {}, el('span', { class: `badge ${d.revoked ? 'failed' : 'completed'}` },
          d.revoked ? 'revoked' : 'active')),
        el('td', {}, d.revoked ? null : el('button', {
          class: 'small danger',
          onclick: async () => {
            if (!confirm(`Revoke "${d.name}"? It will have to pair again.`)) return;
            await api(`/api/devices/${d.id}`, { method: 'DELETE' });
            render();
          },
        }, 'Revoke')))))))
      : el('div', { class: 'card empty' }, 'No devices paired yet.'),
  );
};

// ------------------------------------------------------------ session detail
routes.session = async (main, sessionId) => {
  main.replaceChildren(el('div', { class: 'loading' }, 'Loading session…'));
  const [{ sessions }, { projects }] = await Promise.all([
    api('/api/sessions/local?limit=200'), api('/api/projects/local'),
  ]);
  const session = sessions.find((s) => s.id === sessionId);
  if (!session) { main.replaceChildren(notice('err', 'Unknown session.')); return; }
  const project = projects.find((p) => p.id === session.project_id);

  // The dashboard has no device token, so it polls the local session list and
  // reads the persisted event log rather than opening the authenticated socket.
  const transcript = el('div', { class: 'card' });
  const changesBox = el('div');

  const renderEvents = (events) => {
    if (!events.length) { transcript.replaceChildren(el('div', { class: 'empty' }, 'No events.')); return; }
    transcript.replaceChildren(...events.map(eventRow).filter(Boolean));
  };

  let lastSeq = 0;
  const poll = async () => {
    try {
      const { events, last_seq } = await api(
        `/api/sessions/${sessionId}/events?after=0&limit=3000`);
      if (last_seq !== lastSeq) { lastSeq = last_seq; renderEvents(events); }
      const { files, total_added, total_removed } = await api(`/api/sessions/${sessionId}/changes`)
        .catch(() => ({ files: [], total_added: 0, total_removed: 0 }));
      changesBox.replaceChildren(changeList(project, files, total_added, total_removed, session.base_commit));
    } catch { /* keep the last render */ }
  };
  await poll();
  const timer = setInterval(poll, session.status === 'running' ? 2000 : 15000);
  main.addEventListener('codepilot:leave', () => clearInterval(timer), { once: true });

  main.replaceChildren(
    el('div', { class: 'page-head' },
      el('h1', {}, 'Session'),
      el('span', { class: `badge ${session.status}` }, session.status)),
    el('p', { class: 'subtitle' }, session.prompt),
    el('div', { class: 'card card-pad' }, el('dl', { class: 'kv' },
      ...kv('Project', project ? `${project.name} (${project.path})` : '(deleted)'),
      ...kv('Model', session.model),
      ...kv('Context', session.context_length ? `${session.context_length} tokens` : '—'),
      ...kv('Approval mode', session.permission_mode),
      ...kv('Started', fmtTime(session.started_at)),
      ...kv('Duration', fmtDuration(session.started_at, session.ended_at)),
      ...kv('Claude session id', session.claude_session_id || '—'),
      ...(session.error ? kv('Error', session.error) : []))),
    el('h2', {}, 'Changed files'), changesBox,
    el('h2', {}, 'Transcript'), transcript,
  );
};

function eventRow(event) {
  const p = event.payload || {};
  const wrap = (cls, who, ...body) => el('div', { class: `evt ${cls}` },
    el('div', { class: 'who' }, who), ...body);
  switch (event.type) {
    case 'assistant.message': return wrap('assistant', 'Claude', el('div', { class: 'body' }, p.text));
    case 'user.message': return wrap('user', 'You', el('div', { class: 'body' }, p.text));
    case 'tool.started':
      return wrap('tool', `Tool · ${p.tool_name}`,
        el('div', { class: 'body mono' }, summarizeToolInput(p.tool_name, p.input)));
    case 'tool.finished':
      return wrap(p.is_error ? 'error' : 'result', `${p.tool_name} · ${p.is_error ? 'error' : 'result'}`,
        el('details', {}, el('summary', {}, `${(p.output || '').split('\n').length} lines`),
          el('pre', { class: 'code' }, (p.output || '').slice(0, 6000))));
    case 'test.result':
      return wrap(p.passed ? 'result' : 'error', 'Tests',
        el('div', { class: 'body mono' }, p.summary));
    case 'tool.approval_required':
      return wrap('tool', 'Approval requested', el('div', { class: 'body mono' }, p.summary));
    case 'tool.approval_resolved':
      return wrap('tool', 'Approval', el('div', { class: 'body' },
        `${p.decision}${p.reason ? ` — ${p.reason}` : ''}`));
    case 'file.changed':
      return wrap('result', 'Files changed', el('div', { class: 'body mono' },
        `${(p.files || []).length} file(s), +${p.total_added} / -${p.total_removed}`));
    case 'session.started':
      return wrap('result', 'Session started', el('div', { class: 'body mono' },
        `${p.model} in ${p.cwd}`));
    case 'session.completed':
      return wrap('result', 'Completed', el('div', { class: 'body' }, p.result || 'done'));
    case 'session.failed':
      return wrap('error', 'Failed', el('div', { class: 'body' }, p.result || 'failed'));
    case 'session.cancelled':
      return wrap('error', 'Cancelled', el('div', { class: 'body' }, p.reason || ''));
    case 'session.error':
      return wrap('error', 'Error', el('div', { class: 'body' }, p.message));
    default: return null;  // status noise and raw frames stay out of the transcript
  }
}

function summarizeToolInput(name, input = {}) {
  if (name === 'Bash') return input.command || '';
  if (input.file_path) return input.file_path;
  if (input.pattern) return `${input.pattern}${input.path ? ` in ${input.path}` : ''}`;
  if (input.url) return input.url;
  const keys = Object.keys(input);
  return keys.length ? JSON.stringify(input).slice(0, 300) : '(no arguments)';
}

function changeList(project, files, added, removed, base) {
  if (!files.length) return el('div', { class: 'card empty' }, 'No file changes recorded.');
  const body = el('div');
  return el('div', {},
    el('div', { class: 'card' }, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}, 'File'),
        el('th', {}, el('span', { class: 'stat-add' }, `+${added}`), ' ',
          el('span', { class: 'stat-del' }, `-${removed}`)), el('th', {}, ''))),
      el('tbody', {}, ...files.map((f) => el('tr', {},
        el('td', { class: 'mono' }, f.path),
        el('td', { class: 'mono' },
          el('span', { class: 'stat-add' }, `+${f.added}`), ' ',
          el('span', { class: 'stat-del' }, `-${f.removed}`),
          f.binary ? ' (binary)' : ''),
        el('td', {}, project ? el('button', {
          class: 'small',
          onclick: async () => {
            body.replaceChildren(el('div', { class: 'loading' }, 'Loading diff…'));
            try {
              const { diff } = await api(
                `/api/projects/${project.id}/diff?path=${encodeURIComponent(f.path)}` +
                (base ? `&base=${encodeURIComponent(base)}` : ''));
              body.replaceChildren(el('h2', {}, f.path), renderDiff(diff));
            } catch (err) { body.replaceChildren(notice('err', err.message)); }
          },
        }, 'View diff') : null)))))),
    body);
}

function renderDiff(text) {
  const box = el('div', { class: 'diff' });
  if (!text || !text.trim()) { box.append(el('div', { class: 'meta' }, '(no textual diff)')); return box; }
  for (const line of text.split('\n')) {
    let cls = '';
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') ||
        line.startsWith('index ') || line.startsWith('new file') || line.startsWith('deleted file')) cls = 'meta';
    else if (line.startsWith('@@')) cls = 'hunk';
    else if (line.startsWith('+')) cls = 'add';
    else if (line.startsWith('-')) cls = 'del';
    box.append(el('div', { class: cls }, line || ' '));
  }
  return box;
}

// ------------------------------------------------------------------- router
async function render() {
  const main = $('#main');
  main.dispatchEvent(new CustomEvent('codepilot:leave'));
  const hash = (location.hash || '#/dashboard').slice(2);
  const [name, arg] = hash.split('/');
  const route = routes[name] || routes.dashboard;
  for (const link of document.querySelectorAll('#nav a')) {
    link.classList.toggle('active', link.dataset.route === (routes[name] ? name : 'dashboard'));
  }
  try { await route(main, arg); }
  catch (err) { main.replaceChildren(notice('err', `Failed to render: ${err.message}`)); }
}

window.addEventListener('hashchange', render);
render();
refreshStatus();
setInterval(refreshStatus, 10000);
