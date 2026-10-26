#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { createServer } from './lib/app.js';

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || '127.0.0.1';
const url = `http://localhost:${PORT}`;

function openBrowser(target) {
  const [cmd, args] = process.platform === 'win32' ? ['cmd', ['/c', 'start', '', target]]
    : process.platform === 'darwin' ? ['open', [target]]
      : ['xdg-open', [target]];
  try {
    spawn(cmd, args, { stdio: 'ignore', detached: true }).on('error', () => {}).unref();
  } catch {
    // No browser available – the URL is printed anyway.
  }
}

const server = createServer({ allowAnyHost: HOST !== '127.0.0.1' && HOST !== 'localhost' });

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} ist belegt. Läuft der Picker schon? Sonst anderen Port wählen: PORT=3001 npm start`);
  } else {
    console.error(err);
  }
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  console.log(`Anzeigen-Picker läuft: ${url}`);
  console.log('Beenden mit Strg+C.');
  if (process.argv.includes('--open')) openBrowser(url);
});
