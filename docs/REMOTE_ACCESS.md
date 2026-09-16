# Using CodePilot away from home

Your PC stays at home and keeps working. You are at school. You want to open the
app, watch a task, approve a command, read a diff.

The answer is **Tailscale**, not port forwarding.

```
Android phone (mobile data / school Wi-Fi)
        │
        ▼
   the internet            ← nothing is listening here
        │
        ▼
 Tailscale private network (WireGuard, end-to-end encrypted)
        │
        ▼
 Windows PC at home  →  CodePilot  →  Claude Code  →  Ollama  →  qwen3-coder:30b
```

## Why not port forwarding

Forwarding a port publishes your PC to the entire internet. CodePilot is
authenticated, but it also — by design — lets an authorised caller cause file
edits and shell commands on your machine. That is not something to put behind a
single bearer token on a public IP, where it will be found by scanners within
hours.

Tailscale gives your PC a private `100.x.y.z` address that only devices signed
into *your* account can reach. No inbound firewall rule, no router change, no
public port. CodePilot never configures your router or firewall, and will not
offer to.

## Setup

### 1. PC

1. Install Tailscale: <https://tailscale.com/download/windows>
2. Sign in, then check it is up:
   ```powershell
   tailscale ip -4
   ```
   You get something like `100.101.102.103`. That address works from anywhere you
   are signed into the same tailnet.
3. In CodePilot: **Settings → Network access → LAN + Tailscale**, then restart
   the server.

The dashboard's home page now lists your Tailscale address alongside the LAN one.
CodePilot detects it by running `tailscale status --json` — if it shows
"not available", Tailscale is not installed or not signed in.

### 2. Phone

1. Install Tailscale from the Play Store, sign in with the same account.
2. Leave the VPN toggle **on**. It is a private network, not a traffic tunnel —
   only tailnet addresses go through it.

### 3. Pair

Pair once, on the home Wi-Fi. The QR code carries **every** address the PC knows
about, LAN and Tailscale, and the app stores all of them.

## How switching works

Every time the app needs the server it tries the address that worked last, then
each of the others, with a short timeout. So:

* At home → the LAN address answers first, and traffic never leaves the network.
* At school → the LAN address fails in a couple of seconds and the Tailscale one
  takes over.
* Walking out of the door mid-task → the socket drops, the app notices the
  network change (via `NetInfo`) and reconnects on the Tailscale address.

**Connection** in the app shows every known address, which ones answer right now,
and which is in use. Tapping *Re-test* re-probes them all.

## What happens when the phone disconnects

Nothing stops. This is the important part:

* Claude Code is a child process of the CodePilot **server**, not of the socket.
  Closing the app, locking the phone or losing signal has no effect on it.
* Every event is written to SQLite with a monotonic sequence number *before* it
  is broadcast.
* When the app reconnects it sends the last sequence number it saw, and the
  server replays everything after it, in order, before resuming the live stream.

So you can start a task, put the phone away, and come back to a complete
transcript of what happened while you were gone.

The one exception: if the **server** restarts, its Claude Code processes die with
it. Those sessions are marked `failed` on the next start, with an explanation,
and you can use *Continue session* to resume the same Claude Code context in a
new turn.

## MagicDNS

If MagicDNS is enabled on your tailnet, CodePilot also advertises a name like
`your-pc.tail1234.ts.net`, which survives a change of Tailscale IP. It appears in
the address list automatically.

## If you would rather not use Tailscale

Any WireGuard-based private network works the same way — the app only cares that
the PC has an address it can reach. Point it at that address manually via
*Type the token instead* on the pairing screen. What CodePilot will not help you
do is expose the port publicly.
