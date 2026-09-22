"""Tool Pack: Git.

Kleine, benannte Operatoren statt eines einzigen ``git_do_everything`` --
jeder Befehl unten entspricht genau einem Git-Kommando mit einer festen,
bekannten Argumentliste. Das Modell liefert nur die Werte (Repository,
Branch-Name, Commit-Nachricht, ...); die Kommandozeile selbst baut das
Werkzeug, nie das Modell -- also kann auch kein Dateiname oder Branch-Name,
der mit ``-`` beginnt, zu einer zusätzlichen Option werden (``_kein_flag``
unten).

Die Sicherheitsstufen folgen Punkt 15/22 der Aufgabenstellung: was sich
leicht rückgängig machen lässt (``add``, ``commit``, ``checkout``, ...) ist
WRITE; was Historie umschreibt oder das Netz erreicht (``push``, ``rebase``,
``commit --amend``, einen Branch löschen) ist SYSTEM; was Daten unwiderruflich
verwirft (``reset --hard``, ``clean``) ist CRITICAL und bekommt einen echten
Probelauf, keinen kosmetischen. Kein Werkzeug hier ruft ``git`` mit einer vom
Modell zusammengesetzten Befehlszeile auf -- dafür gibt es ``run_command``
(``shell.py``), mit eigener Freigabe und Allowlist.

Alle Repository-Pfade laufen durch ``Workspace.resolve`` und bleiben damit
auf die freigegebenen Wurzeln beschränkt (Punkt 13/56: bestehende Funktion
wiederverwendet, nicht neu gebaut).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, run_process
from ._base import LIST, flag, integer, ok, params, planned, table, text

GIT_TIMEOUT = 30.0
NETWORK_TIMEOUT = 120.0
MAX_OUTPUT = 20_000


def _clip(value: str) -> str:
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


def _kein_flag(value: str, label: str) -> str:
    """Verweigert einen Wert, der als Option statt als Name/URL gelesen
    würde -- ein Branch namens ``--upload-pack=...`` ist kein Branch-Name,
    sondern ein Versuch, git zu einem beliebigen Befehl zu überreden."""
    wert = (value or "").strip()
    if not wert:
        raise ToolError(f"{label} fehlt.")
    if wert.startswith("-"):
        raise ToolError(f"{label} darf nicht mit '-' beginnen: {wert!r}")
    return wert


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def repo_of(raw: str, must_exist: bool = True) -> Path:
        pfad = ws.resolve(raw)
        if must_exist and not pfad.is_dir():
            raise ToolError(f"Ordner existiert nicht: {pfad}")
        return pfad

    def git(repo: Path, args: list[str], timeout: float = GIT_TIMEOUT):
        return run_process(["git", "-C", str(repo), *args], timeout=timeout)

    def mutate(repo: Path, args: list[str], tool: str, summary: str,
              timeout: float = GIT_TIMEOUT, **evidence: Any) -> ToolResult:
        res = git(repo, args, timeout)
        out, err = (res.stdout or "").strip(), (res.stderr or "").strip()
        if res.returncode != 0:
            raise ToolError(_clip(err or out or
                                  f"'git {' '.join(args)}' fehlgeschlagen "
                                  f"(Exit {res.returncode})"))
        return ok(tool, summary, payload=_clip(out or err) or None, **evidence)

    # ══════════════════════════════════════════════════════════ Lesend
    def git_status(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["status", "--porcelain=v1", "--branch"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git status fehlgeschlagen").strip()))
        zeilen = (res.stdout or "").splitlines()
        kopf = zeilen[0] if zeilen and zeilen[0].startswith("##") else ""
        eintraege = zeilen[1:] if kopf else zeilen
        staged = sum(1 for z in eintraege if z[:1] not in (" ", "?"))
        unstaged = sum(1 for z in eintraege if len(z) > 1 and z[1] not in (" ", "?"))
        untracked = sum(1 for z in eintraege if z.startswith("??"))
        branch = kopf[3:].split("...")[0] if kopf else "?"
        summary = (f"{branch}: sauber, keine Änderungen" if not eintraege else
                  f"{branch}: {len(eintraege)} Eintragung(en) "
                  f"({staged} vorgemerkt, {unstaged} geändert, {untracked} unversioniert)")
        return ok("git.status", summary, payload="\n".join(zeilen) or "(sauber)",
                  branch=branch, geaendert=len(eintraege), staged=staged,
                  unstaged=unstaged, unversioniert=untracked)

    def git_log(repo: str, limit: int = 20) -> ToolResult:
        r = repo_of(repo)
        n = max(1, min(int(limit or 20), 200))
        res = git(r, ["log", f"-n{n}", "--pretty=format:%h|%an|%ad|%s", "--date=short"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git log fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        rows = [z.split("|", 3) for z in zeilen]
        return ok("git.log", f"{len(rows)} Commit(s)" if rows else "Keine Commits",
                  payload=table(rows, headers=["Hash", "Autor", "Datum", "Nachricht"]),
                  anzahl=len(rows))

    def git_log_file(repo: str, path: str, limit: int = 20) -> ToolResult:
        r = repo_of(repo)
        p = _kein_flag(path, "path")
        n = max(1, min(int(limit or 20), 200))
        res = git(r, ["log", f"-n{n}", "--follow", "--pretty=format:%h|%an|%ad|%s",
                      "--date=short", "--", p])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or f"git log fehlgeschlagen für {p}").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        rows = [z.split("|", 3) for z in zeilen]
        return ok("git.log.file", f"{len(rows)} Commit(s) betreffen {p}",
                  payload=table(rows, headers=["Hash", "Autor", "Datum", "Nachricht"]),
                  datei=p, anzahl=len(rows))

    def git_diff(repo: str, path: str = "") -> ToolResult:
        r = repo_of(repo)
        args = ["diff"]
        if path:
            args += ["--", _kein_flag(path, "path")]
        res = git(r, args)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git diff fehlgeschlagen").strip()))
        out = (res.stdout or "").strip()
        return ok("git.diff", f"{len(out.splitlines())} Zeile(n) Unterschied" if out
                  else "Keine Unterschiede", payload=_clip(out) or "(keine Unterschiede)")

    def git_diff_staged(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["diff", "--cached"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git diff fehlgeschlagen").strip()))
        out = (res.stdout or "").strip()
        return ok("git.diff.staged", f"{len(out.splitlines())} Zeile(n) vorgemerkt" if out
                  else "Nichts vorgemerkt", payload=_clip(out) or "(nichts)")

    def git_diff_commit(repo: str, a: str, b: str = "") -> ToolResult:
        r = repo_of(repo)
        ra = _kein_flag(a, "a")
        args = ["diff", ra] + ([_kein_flag(b, "b")] if b else [])
        res = git(r, args)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git diff fehlgeschlagen").strip()))
        out = (res.stdout or "").strip()
        ziel = f"{ra} → {b}" if b else f"{ra} → Arbeitsverzeichnis"
        return ok("git.diff.commit", f"Unterschied {ziel}",
                  payload=_clip(out) or "(keine Unterschiede)")

    def git_show(repo: str, ref: str = "HEAD") -> ToolResult:
        r = repo_of(repo)
        rf = _kein_flag(ref or "HEAD", "ref")
        res = git(r, ["show", "--stat", "--patch", rf])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or f"git show fehlgeschlagen für {rf}").strip()))
        out = (res.stdout or "").strip()
        erste = out.splitlines()[0] if out else rf
        return ok("git.show", f"Commit {rf}: {erste}", payload=_clip(out))

    def git_blame(repo: str, path: str, limit: int = 0) -> ToolResult:
        r = repo_of(repo)
        p = _kein_flag(path, "path")
        res = git(r, ["blame", "--", p])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or f"git blame fehlgeschlagen für {p}").strip()))
        zeilen = (res.stdout or "").splitlines()
        n = max(1, min(int(limit) if limit else len(zeilen) or 1, 2000))
        return ok("git.blame", f"{len(zeilen)} Zeile(n) in {p}",
                  payload=_clip("\n".join(zeilen[:n])), datei=p, zeilen=len(zeilen))

    def git_branch_list(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["branch", "-a", "-v"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git branch fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("git.branch.list", f"{len(zeilen)} Branch(es)",
                  payload="\n".join(zeilen) or "(keine)", anzahl=len(zeilen))

    def git_branch_current(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["rev-parse", "--abbrev-ref", "HEAD"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "Kein Branch (leeres Repository?)").strip()))
        name = (res.stdout or "").strip()
        return ok("git.branch.current", f"Aktueller Branch: {name}", payload=name, branch=name)

    def git_remote_list(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["remote", "-v"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git remote fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("git.remote.list", f"{len({z.split()[0] for z in zeilen})} Remote(s)"
                  if zeilen else "Keine Remotes", payload="\n".join(zeilen) or "(keine)")

    def git_stash_list(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["stash", "list"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git stash list fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("git.stash.list", f"{len(zeilen)} Stash(es)",
                  payload="\n".join(zeilen) or "(keine)", anzahl=len(zeilen))

    def git_tag_list(repo: str) -> ToolResult:
        r = repo_of(repo)
        res = git(r, ["tag", "-n"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git tag fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("git.tag.list", f"{len(zeilen)} Tag(s)",
                  payload="\n".join(zeilen) or "(keine)", anzahl=len(zeilen))

    def git_contributors(repo: str, limit: int = 20) -> ToolResult:
        r = repo_of(repo)
        n = max(1, min(int(limit or 20), 200))
        res = git(r, ["shortlog", "-sn", "--all"])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git shortlog fehlgeschlagen").strip()))
        zeilen = [z.strip() for z in (res.stdout or "").splitlines() if z.strip()][:n]
        rows = [re.split(r"\t+", z, maxsplit=1) for z in zeilen]
        return ok("git.contributors", f"{len(rows)} Mitwirkende(r)",
                  payload=table(rows, headers=["Commits", "Name"]), anzahl=len(rows))

    def git_repo_info(repo: str) -> ToolResult:
        r = repo_of(repo)
        zweig = git(r, ["rev-parse", "--abbrev-ref", "HEAD"])
        remote = git(r, ["remote", "get-url", "origin"])
        status = git(r, ["status", "--porcelain"])
        voraus_hinter = git(r, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
        branch = (zweig.stdout or "").strip() if zweig.returncode == 0 else "(kein Branch)"
        url = (remote.stdout or "").strip() if remote.returncode == 0 else "(kein Remote)"
        sauber = not (status.stdout or "").strip()
        voraus = hinter = "?"
        if voraus_hinter.returncode == 0:
            teile = (voraus_hinter.stdout or "").split()
            if len(teile) == 2:
                voraus, hinter = teile
        return ok("git.repo.info",
                  f"{branch} · {url} · {'sauber' if sauber else 'Änderungen vorhanden'}",
                  branch=branch, remote=url, sauber=sauber, voraus=voraus, hinterher=hinter)

    def git_config_get(repo: str, key: str) -> ToolResult:
        r = repo_of(repo)
        k = _kein_flag(key, "key")
        res = git(r, ["config", "--local", "--get", k])
        if res.returncode != 0:
            return ok("git.config.get", f"{k} ist in diesem Repository nicht gesetzt",
                      payload=None, schluessel=k)
        wert = (res.stdout or "").strip()
        return ok("git.config.get", f"{k} = {wert}", payload=wert, schluessel=k)

    def git_clean_preview(repo: str, include_ignored: bool = False) -> ToolResult:
        r = repo_of(repo)
        args = ["clean", "-nd"] + (["-x"] if include_ignored else [])
        res = git(r, args)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git clean fehlgeschlagen").strip()))
        zeilen = [z for z in (res.stdout or "").splitlines() if z.strip()]
        return ok("git.clean.preview",
                  f"{len(zeilen)} Eintragung(en) würden entfernt" if zeilen
                  else "Nichts zu entfernen",
                  payload="\n".join(zeilen) or "(nichts)", anzahl=len(zeilen))

    def git_fetch(repo: str, timeout: int = 0) -> ToolResult:
        r = repo_of(repo)
        t = max(10.0, min(float(timeout or NETWORK_TIMEOUT), 600.0))
        res = git(r, ["fetch", "--prune"], timeout=t)
        out, err = (res.stdout or "").strip(), (res.stderr or "").strip()
        if res.returncode != 0:
            raise ToolError(_clip(err or out or "git fetch fehlgeschlagen"))
        info = err or out
        letzte_zeile = info.splitlines()[-1] if info else "keine Änderungen"
        return ok("git.fetch", f"Fetch ausgeführt: {letzte_zeile}", payload=_clip(info) or None)

    # ══════════════════════════════════════════════════════════ WRITE
    def git_add(repo: str, paths: list[str] | None = None, all: bool = False) -> ToolResult:
        r = repo_of(repo)
        if all:
            return mutate(r, ["add", "-A"], "git.add", "Alle Änderungen vorgemerkt")
        liste = [p.strip() for p in (paths or []) if p and p.strip()]
        if not liste:
            raise ToolError("Es wurden weder Pfade noch all=true angegeben.")
        return mutate(r, ["add", "--", *liste], "git.add",
                      f"Vorgemerkt: {', '.join(liste)}", pfade=liste)

    def git_unstage(repo: str, paths: list[str] | None = None) -> ToolResult:
        r = repo_of(repo)
        liste = [p.strip() for p in (paths or []) if p and p.strip()]
        args = ["reset", "--", *liste] if liste else ["reset"]
        return mutate(r, args, "git.unstage",
                      f"Aus der Vormerkung genommen: {', '.join(liste) if liste else 'alles'}")

    def git_commit(repo: str, message: str, add_all: bool = False) -> ToolResult:
        r = repo_of(repo)
        msg = (message or "").strip()
        if not msg:
            raise ToolError("Es wurde keine Commit-Nachricht angegeben.")
        args = ["commit", "-a", "-m", msg] if add_all else ["commit", "-m", msg]
        return mutate(r, args, "git.commit", f"Commit erstellt: {msg[:72]}", nachricht=msg)

    def git_checkout(repo: str, ref: str) -> ToolResult:
        r = repo_of(repo)
        zweig = _kein_flag(ref, "ref")
        return mutate(r, ["checkout", zweig], "git.checkout", f"Gewechselt zu: {zweig}",
                      ref=zweig)

    def git_branch_create(repo: str, name: str, start_point: str = "") -> ToolResult:
        r = repo_of(repo)
        n = _kein_flag(name, "name")
        args = ["branch", n] + ([_kein_flag(start_point, "start_point")] if start_point else [])
        return mutate(r, args, "git.branch.create", f"Branch erstellt: {n}", branch=n)

    def git_remote_add(repo: str, name: str, url: str) -> ToolResult:
        r = repo_of(repo)
        n, u = _kein_flag(name, "name"), _kein_flag(url, "url")
        return mutate(r, ["remote", "add", n, u], "git.remote.add",
                      f"Remote hinzugefügt: {n} → {u}", remote=n, url=u)

    def git_remote_remove(repo: str, name: str) -> ToolResult:
        r = repo_of(repo)
        n = _kein_flag(name, "name")
        return mutate(r, ["remote", "remove", n], "git.remote.remove",
                      f"Remote entfernt: {n}", remote=n)

    def git_stash_save(repo: str, message: str = "") -> ToolResult:
        r = repo_of(repo)
        args = ["stash", "push"] + (["-m", message.strip()] if message.strip() else [])
        return mutate(r, args, "git.stash.save", "Änderungen zwischengelegt (stash)")

    def git_stash_pop(repo: str, ref: str = "") -> ToolResult:
        r = repo_of(repo)
        args = ["stash", "pop"] + ([_kein_flag(ref, "ref")] if ref else [])
        return mutate(r, args, "git.stash.pop", "Stash zurückgeholt")

    def git_tag_create(repo: str, name: str, message: str = "", ref: str = "") -> ToolResult:
        r = repo_of(repo)
        n = _kein_flag(name, "name")
        if message.strip():
            args = ["tag", "-a", n, "-m", message.strip()]
        else:
            args = ["tag", n]
        if ref:
            args.append(_kein_flag(ref, "ref"))
        return mutate(r, args, "git.tag.create", f"Tag erstellt: {n}", tag=n)

    def git_tag_delete(repo: str, name: str) -> ToolResult:
        r = repo_of(repo)
        n = _kein_flag(name, "name")
        return mutate(r, ["tag", "-d", n], "git.tag.delete", f"Tag gelöscht: {n}", tag=n)

    def git_clone(repo_url: str, path: str, timeout: int = 0) -> ToolResult:
        u = _kein_flag(repo_url, "repo_url")
        ziel = ws.resolve(path)
        if ziel.is_dir() and any(ziel.iterdir()):
            raise ToolError(f"Zielordner ist nicht leer: {ziel}")
        t = max(10.0, min(float(timeout or NETWORK_TIMEOUT), 900.0))
        res = run_process(["git", "clone", "--", u, str(ziel)], timeout=t)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or res.stdout or "git clone fehlgeschlagen").strip()))
        return ok("git.clone", f"Repository geklont nach {ziel}", ziel=str(ziel), quelle=u)

    def git_init(path: str) -> ToolResult:
        ziel = ws.resolve(path)
        ziel.mkdir(parents=True, exist_ok=True)
        res = run_process(["git", "init", "--", str(ziel)])
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "git init fehlgeschlagen").strip()))
        return ok("git.init", f"Git-Repository angelegt: {ziel}", ziel=str(ziel))

    def git_ignore_add(repo: str, pattern: str) -> ToolResult:
        r = repo_of(repo)
        p = (pattern or "").strip()
        if not p:
            raise ToolError("Es wurde kein Muster angegeben.")
        datei = r / ".gitignore"
        bestehend = datei.read_text(encoding="utf-8").splitlines() if datei.is_file() else []
        if p in bestehend:
            return ok("git.ignore.add", f"Steht schon in .gitignore: {p}", muster=p)
        with datei.open("a", encoding="utf-8") as f:
            if bestehend and bestehend[-1] != "":
                f.write("\n")
            f.write(p + "\n")
        return ok("git.ignore.add", f"Zu .gitignore hinzugefügt: {p}",
                  muster=p, datei=str(datei))

    def git_config_set(repo: str, key: str, value: str) -> ToolResult:
        r = repo_of(repo)
        k = _kein_flag(key, "key")
        v = (value or "").strip()
        return mutate(r, ["config", "--local", k, v], "git.config.set",
                      f"{k} = {v}", schluessel=k, wert=v)

    def git_pull(repo: str, timeout: int = 0) -> ToolResult:
        r = repo_of(repo)
        t = max(10.0, min(float(timeout or NETWORK_TIMEOUT), 600.0))
        return mutate(r, ["pull"], "git.pull", "Pull ausgeführt", timeout=t)

    def git_revert(repo: str, ref: str) -> ToolResult:
        r = repo_of(repo)
        rf = _kein_flag(ref, "ref")
        return mutate(r, ["revert", "--no-edit", rf], "git.revert",
                      f"Revert-Commit erstellt für {rf}", ref=rf)

    # ══════════════════════════════════════════════════════════ SYSTEM
    def git_push(repo: str, remote: str = "", branch: str = "", timeout: int = 0,
                dry_run: bool = False) -> ToolResult:
        r = repo_of(repo)
        args = ["push"]
        if dry_run:
            args.append("--dry-run")
        if remote:
            args.append(_kein_flag(remote, "remote"))
            if branch:
                args.append(_kein_flag(branch, "branch"))
        t = max(10.0, min(float(timeout or NETWORK_TIMEOUT), 600.0))
        res = git(r, args, timeout=t)
        out, err = (res.stdout or "").strip(), (res.stderr or "").strip()
        if res.returncode != 0:
            raise ToolError(_clip(err or out or "git push fehlgeschlagen"))
        if dry_run:
            return planned("git.push", "Push würde durchgeführt", payload=_clip(err or out) or None)
        return ok("git.push", "Push erfolgreich", payload=_clip(err or out) or None)

    def git_branch_delete(repo: str, name: str) -> ToolResult:
        r = repo_of(repo)
        n = _kein_flag(name, "name")
        return mutate(r, ["branch", "-d", n], "git.branch.delete",
                      f"Branch gelöscht: {n}", branch=n)

    def git_stash_drop(repo: str, ref: str = "", dry_run: bool = False) -> ToolResult:
        r = repo_of(repo)
        ziel = _kein_flag(ref, "ref") if ref else "stash@{0}"
        if dry_run:
            zeige = git(r, ["stash", "show", "-p", ziel])
            inhalt = _clip((zeige.stdout or "").strip()) if zeige.returncode == 0 else "(nicht einsehbar)"
            return planned("git.stash.drop", f"{ziel} würde endgültig verworfen",
                           payload=inhalt, stash=ziel)
        args = ["stash", "drop"] + ([ziel] if ref else [])
        return mutate(r, args, "git.stash.drop", f"{ziel} endgültig verworfen", stash=ziel)

    def git_commit_amend(repo: str, message: str = "") -> ToolResult:
        r = repo_of(repo)
        msg = (message or "").strip()
        args = ["commit", "--amend", "-m", msg] if msg else ["commit", "--amend", "--no-edit"]
        return mutate(r, args, "git.commit.amend", "Letzter Commit geändert (amend)")

    def git_rebase(repo: str, upstream: str) -> ToolResult:
        r = repo_of(repo)
        u = _kein_flag(upstream, "upstream")
        return mutate(r, ["rebase", u], "git.rebase", f"Rebase auf {u} ausgeführt", ziel=u)

    def git_rebase_abort(repo: str) -> ToolResult:
        r = repo_of(repo)
        return mutate(r, ["rebase", "--abort"], "git.rebase.abort",
                      "Rebase abgebrochen, vorheriger Zustand wiederhergestellt")

    # ══════════════════════════════════════════════════════════ CRITICAL
    def git_reset_hard(repo: str, ref: str = "HEAD", dry_run: bool = False) -> ToolResult:
        r = repo_of(repo)
        rf = _kein_flag(ref or "HEAD", "ref")
        status = git(r, ["status", "--porcelain"])
        betroffen = [z for z in (status.stdout or "").splitlines() if z.strip()]
        if dry_run:
            return planned("git.reset.hard",
                           f"{len(betroffen)} Änderung(en) würden verworfen, HEAD → {rf}",
                           payload="\n".join(betroffen) or "(sauber)", ref=rf,
                           betroffen=len(betroffen))
        return mutate(r, ["reset", "--hard", rf], "git.reset.hard",
                      f"Zurückgesetzt auf {rf} ({len(betroffen)} Änderung(en) verworfen)",
                      ref=rf, verworfen=len(betroffen))

    def git_clean(repo: str, include_ignored: bool = False, dry_run: bool = False) -> ToolResult:
        r = repo_of(repo)
        vorschau_args = ["clean", "-nd"] + (["-x"] if include_ignored else [])
        vorschau = git(r, vorschau_args)
        if vorschau.returncode != 0:
            raise ToolError(_clip((vorschau.stderr or "git clean fehlgeschlagen").strip()))
        zeilen = [z for z in (vorschau.stdout or "").splitlines() if z.strip()]
        if dry_run:
            return planned("git.clean", f"{len(zeilen)} Eintragung(en) würden entfernt",
                           payload="\n".join(zeilen) or "(nichts)", anzahl=len(zeilen))
        args = ["clean", "-fd"] + (["-x"] if include_ignored else [])
        return mutate(r, args, "git.clean",
                      f"{len(zeilen)} Eintragung(en) entfernt", anzahl=len(zeilen))

    _p = text("Pfad des Git-Repositories (im Arbeitsbereich)")

    return [
        # ── Lesend ──────────────────────────────────────────────────────
        Tool("git.status", "Status des Arbeitsverzeichnisses: Branch, vorgemerkte, "
             "geänderte und unversionierte Dateien.",
             params("repo", repo=_p), git_status, level=P.READ, requires=("git",),
             tags=("git", "status"), returns="Branch, Anzahl je Kategorie, Rohliste",
             phrases=("git status", "was hat sich geändert", "ist das repo sauber")),
        Tool("git.log", "Die letzten Commits.",
             params("repo", repo=_p, limit=integer("Anzahl, Vorgabe 20")),
             git_log, level=P.READ, requires=("git",), tags=("git", "log"),
             phrases=("zeig mir die commits", "git log")),
        Tool("git.log.file", "Commit-Historie einer einzelnen Datei.",
             params("repo", "path", repo=_p, path=text("Pfad relativ zum Repository"),
                    limit=integer("Anzahl, Vorgabe 20")),
             git_log_file, level=P.READ, requires=("git",), tags=("git", "log")),
        Tool("git.diff", "Unterschiede im Arbeitsverzeichnis (noch nicht vorgemerkt).",
             params("repo", repo=_p, path=text("Nur diese Datei/diesen Ordner zeigen")),
             git_diff, level=P.READ, requires=("git",), tags=("git", "diff"),
             phrases=("was habe ich geändert", "git diff")),
        Tool("git.diff.staged", "Unterschiede der vorgemerkten (staged) Änderungen.",
             params("repo", repo=_p), git_diff_staged, level=P.READ, requires=("git",),
             tags=("git", "diff")),
        Tool("git.diff.commit", "Unterschied zwischen zwei Commits/Refs (oder einem "
             "Commit und dem Arbeitsverzeichnis).",
             params("repo", "a", repo=_p, a=text("Erster Ref/Commit"),
                    b=text("Zweiter Ref/Commit, leer = Arbeitsverzeichnis")),
             git_diff_commit, level=P.READ, requires=("git",), tags=("git", "diff")),
        Tool("git.show", "Details und Diff eines einzelnen Commits.",
             params("repo", repo=_p, ref=text("Commit/Ref, Vorgabe HEAD")),
             git_show, level=P.READ, requires=("git",), tags=("git", "log")),
        Tool("git.blame", "Wer hat welche Zeile einer Datei zuletzt geändert.",
             params("repo", "path", repo=_p, path=text("Pfad relativ zum Repository"),
                    limit=integer("Nur die ersten n Zeilen, 0 = alle")),
             git_blame, level=P.READ, requires=("git",), tags=("git", "blame"),
             phrases=("wer hat das geschrieben", "git blame")),
        Tool("git.branch.list", "Alle lokalen und entfernten Branches.",
             params("repo", repo=_p), git_branch_list, level=P.READ, requires=("git",),
             tags=("git", "branch"), phrases=("welche branches gibt es",)),
        Tool("git.branch.current", "Der aktuell ausgecheckte Branch.",
             params("repo", repo=_p), git_branch_current, level=P.READ, requires=("git",),
             tags=("git", "branch"), phrases=("auf welchem branch bin ich",)),
        Tool("git.remote.list", "Eingetragene Remotes samt URL.",
             params("repo", repo=_p), git_remote_list, level=P.READ, requires=("git",),
             tags=("git", "remote")),
        Tool("git.stash.list", "Zwischengelegte Änderungen (git stash).",
             params("repo", repo=_p), git_stash_list, level=P.READ, requires=("git",),
             tags=("git", "stash")),
        Tool("git.tag.list", "Alle Tags mit ihrer Nachricht.",
             params("repo", repo=_p), git_tag_list, level=P.READ, requires=("git",),
             tags=("git", "tag")),
        Tool("git.contributors", "Wer wie viel zu diesem Repository beigetragen hat.",
             params("repo", repo=_p, limit=integer("Anzahl, Vorgabe 20")),
             git_contributors, level=P.READ, requires=("git",), tags=("git", "log")),
        Tool("git.repo.info", "Branch, Remote, Sauberkeit und Vorsprung/Rückstand "
             "zum Upstream in einer Übersicht.",
             params("repo", repo=_p), git_repo_info, level=P.READ, requires=("git",),
             tags=("git", "status"), phrases=("wie steht das repo da",)),
        Tool("git.config.get", "Liest einen lokalen Git-Konfigurationswert dieses "
             "Repositories (nicht global).",
             params("repo", "key", repo=_p, key=text("z. B. user.name")),
             git_config_get, level=P.READ, requires=("git",), tags=("git", "config")),
        Tool("git.clean.preview", "Zeigt, welche unversionierten Dateien 'git clean' "
             "entfernen würde -- löscht nichts.",
             params("repo", repo=_p,
                    include_ignored=flag("Auch von .gitignore ausgeschlossene Dateien")),
             git_clean_preview, level=P.READ, requires=("git",), tags=("git", "aufraeumen")),
        Tool("git.fetch", "Holt neue Commits/Refs vom Remote, ohne den Arbeitsbereich "
             "zu verändern.",
             params("repo", repo=_p, timeout=integer("Sekunden, Vorgabe 120")),
             git_fetch, level=P.READ, requires=("git",), tags=("git", "remote"),
             timeout=NETWORK_TIMEOUT),

        # ── WRITE ───────────────────────────────────────────────────────
        Tool("git.add", "Merkt Dateien für den nächsten Commit vor.",
             params("repo", repo=_p, paths=LIST, all=flag("Alle Änderungen vormerken")),
             git_add, level=P.WRITE, requires=("git",), tags=("git", "commit"),
             phrases=("git add", "merk das für den commit vor")),
        Tool("git.unstage", "Nimmt Dateien aus der Vormerkung, ohne sie zu verändern.",
             params("repo", repo=_p, paths=LIST), git_unstage, level=P.WRITE,
             requires=("git",), tags=("git", "commit")),
        Tool("git.commit", "Erstellt einen Commit aus den vorgemerkten Änderungen.",
             params("repo", "message", repo=_p, message=text("Commit-Nachricht"),
                    add_all=flag("Alle geänderten (bereits verfolgten) Dateien mit erfassen")),
             git_commit, level=P.WRITE, requires=("git",), tags=("git", "commit"),
             phrases=("committe das", "git commit")),
        Tool("git.checkout", "Wechselt zu einem Branch oder Commit.",
             params("repo", "ref", repo=_p, ref=text("Branch-Name oder Commit")),
             git_checkout, level=P.WRITE, requires=("git",), tags=("git", "branch"),
             phrases=("wechsle zum branch", "git checkout")),
        Tool("git.branch.create", "Erstellt einen neuen Branch (ohne zu wechseln).",
             params("repo", "name", repo=_p, name=text("Name des neuen Branches"),
                    start_point=text("Ausgangspunkt, leer = aktueller HEAD")),
             git_branch_create, level=P.WRITE, requires=("git",), tags=("git", "branch")),
        Tool("git.remote.add", "Trägt ein neues Remote ein.",
             params("repo", "name", "url", repo=_p, name=text("z. B. origin"),
                    url=text("Git-URL")),
             git_remote_add, level=P.WRITE, requires=("git",), tags=("git", "remote")),
        Tool("git.remote.remove", "Entfernt ein eingetragenes Remote.",
             params("repo", "name", repo=_p, name=text("Name des Remotes")),
             git_remote_remove, level=P.WRITE, requires=("git",), tags=("git", "remote")),
        Tool("git.stash.save", "Legt unfertige Änderungen beiseite (git stash).",
             params("repo", repo=_p, message=text("Beschreibung des Stashes")),
             git_stash_save, level=P.WRITE, requires=("git",), tags=("git", "stash"),
             phrases=("leg die änderungen beiseite",)),
        Tool("git.stash.pop", "Holt den zuletzt (oder angegebenen) Stash zurück.",
             params("repo", repo=_p, ref=text("z. B. stash@{0}, leer = neuester")),
             git_stash_pop, level=P.WRITE, requires=("git",), tags=("git", "stash")),
        Tool("git.tag.create", "Setzt ein Tag auf einen Commit.",
             params("repo", "name", repo=_p, name=text("Tag-Name"),
                    message=text("Nachricht -- setzt ein annotiertes Tag"),
                    ref=text("Commit, leer = aktueller HEAD")),
             git_tag_create, level=P.WRITE, requires=("git",), tags=("git", "tag")),
        Tool("git.tag.delete", "Löscht ein Tag (nur lokal, nicht beim Remote).",
             params("repo", "name", repo=_p, name=text("Tag-Name")),
             git_tag_delete, level=P.WRITE, requires=("git",), tags=("git", "tag")),
        Tool("git.clone", "Klont ein Repository in den Arbeitsbereich.",
             params("repo_url", "path", repo_url=text("Git-URL"),
                    path=text("Zielordner im Arbeitsbereich"),
                    timeout=integer("Sekunden, Vorgabe 120")),
             git_clone, level=P.WRITE, requires=("git",), tags=("git",),
             timeout=NETWORK_TIMEOUT, phrases=("klon das repository", "git clone")),
        Tool("git.init", "Legt ein neues, leeres Git-Repository an.",
             params("path", path=text("Zielordner im Arbeitsbereich")),
             git_init, level=P.WRITE, requires=("git",), tags=("git",),
             phrases=("git init", "mach hier ein repo draus")),
        Tool("git.ignore.add", "Fügt ein Muster zu .gitignore hinzu (legt die Datei an, "
             "falls nötig).",
             params("repo", "pattern", repo=_p, pattern=text("z. B. *.log oder node_modules/")),
             git_ignore_add, level=P.WRITE, requires=("git",), tags=("git", "gitignore")),
        Tool("git.config.set", "Setzt einen lokalen Git-Konfigurationswert dieses "
             "Repositories -- nie global oder systemweit.",
             params("repo", "key", "value", repo=_p, key=text("z. B. user.name"),
                    value=text("Neuer Wert")),
             git_config_set, level=P.WRITE, requires=("git",), tags=("git", "config")),
        Tool("git.pull", "Holt Commits vom Remote und führt sie in den aktuellen "
             "Branch zusammen.",
             params("repo", repo=_p, timeout=integer("Sekunden, Vorgabe 120")),
             git_pull, level=P.WRITE, requires=("git",), tags=("git", "remote"),
             timeout=NETWORK_TIMEOUT, phrases=("hol die neuesten änderungen", "git pull")),
        Tool("git.revert", "Erstellt einen neuen Commit, der einen früheren Commit "
             "rückgängig macht -- ohne Historie umzuschreiben.",
             params("repo", "ref", repo=_p, ref=text("Zu revertierender Commit")),
             git_revert, level=P.WRITE, requires=("git",), tags=("git", "commit")),

        # ── SYSTEM ──────────────────────────────────────────────────────
        Tool("git.push", "Sendet lokale Commits an ein Remote.",
             params("repo", repo=_p, remote=text("Remote-Name, leer = Vorgabe"),
                    branch=text("Branch, leer = aktueller"),
                    timeout=integer("Sekunden, Vorgabe 120"), dry_run=flag(
                        "Nur zeigen, was gesendet würde")),
             git_push, level=P.SYSTEM, requires=("git",), tags=("git", "remote"),
             dry_run=True, timeout=NETWORK_TIMEOUT, phrases=("push das", "git push")),
        Tool("git.branch.delete", "Löscht einen Branch (nur wenn bereits gemergt -- "
             "git verweigert es sonst von selbst).",
             params("repo", "name", repo=_p, name=text("Branch-Name")),
             git_branch_delete, level=P.SYSTEM, requires=("git",), tags=("git", "branch")),
        Tool("git.stash.drop", "Verwirft einen Stash endgültig.",
             params("repo", repo=_p, ref=text("z. B. stash@{0}, leer = neuester"),
                    dry_run=flag("Nur zeigen, was verworfen würde")),
             git_stash_drop, level=P.SYSTEM, requires=("git",), tags=("git", "stash"),
             dry_run=True),
        Tool("git.commit.amend", "Ändert den letzten Commit (Nachricht und/oder "
             "vorgemerkte Änderungen) -- schreibt Historie um.",
             params("repo", repo=_p, message=text("Neue Nachricht, leer = behalten")),
             git_commit_amend, level=P.SYSTEM, requires=("git",), tags=("git", "commit")),
        Tool("git.rebase", "Setzt die Commits des aktuellen Branches auf einen anderen "
             "Stand um -- schreibt Historie um, kann Konflikte auslösen.",
             params("repo", "upstream", repo=_p, upstream=text("Ziel-Branch/-Commit")),
             git_rebase, level=P.SYSTEM, requires=("git",), tags=("git", "branch")),
        Tool("git.rebase.abort", "Bricht einen laufenden Rebase ab und stellt den "
             "vorherigen Zustand wieder her.",
             params("repo", repo=_p), git_rebase_abort, level=P.SYSTEM, requires=("git",),
             tags=("git", "branch")),

        # ── CRITICAL ────────────────────────────────────────────────────
        Tool("git.reset.hard", "Verwirft alle Änderungen im Arbeitsverzeichnis und "
             "setzt den Branch auf einen Commit zurück -- unwiderruflich.",
             params("repo", repo=_p, ref=text("Ziel-Commit, Vorgabe HEAD"),
                    dry_run=flag("Nur zeigen, was verworfen würde")),
             git_reset_hard, level=P.CRITICAL, requires=("git",), tags=("git", "loeschen"),
             dry_run=True),
        Tool("git.clean", "Löscht unversionierte Dateien endgültig von der Festplatte.",
             params("repo", repo=_p,
                    include_ignored=flag("Auch von .gitignore ausgeschlossene Dateien"),
                    dry_run=flag("Nur zeigen, was gelöscht würde")),
             git_clean, level=P.CRITICAL, requires=("git",), tags=("git", "loeschen"),
             dry_run=True),
    ]
