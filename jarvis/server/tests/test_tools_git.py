"""Das Git-Pack: jedes Werkzeug gegen ein echtes Repository.

Kein Mock -- ein echtes ``git init`` im ``tmp_path`` der Testsitzung, echte
Commits, echte Branches. Die lokale Identität (``user.name``/``user.email``)
wird ausdrücklich gesetzt, damit der Test nicht von der globalen
Git-Konfiguration der Maschine abhängt, auf der er läuft (auf einem frisch
installierten Git gibt es die oft nicht).
"""

from __future__ import annotations

import subprocess

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


def _git(*args: str, cwd) -> None:
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                         text=True, check=False)
    assert res.returncode == 0, f"git {' '.join(args)} fehlgeschlagen: {res.stderr}"


@pytest.fixture
def repo(workspace):
    """Ein echtes Repository mit zwei Commits und einem zweiten Branch."""
    ordner = workspace / "projekt"
    ordner.mkdir()
    # -b main: fester Name statt der maschinenabhängigen Vorgabe (Git
    # unter 2.28 macht main/master von init.defaultBranch abhängig).
    _git("init", "-b", "main", cwd=ordner)
    _git("config", "user.name", "Testuser", cwd=ordner)
    _git("config", "user.email", "test@example.invalid", cwd=ordner)
    (ordner / "a.txt").write_text("eins\n", encoding="utf-8")
    _git("add", "a.txt", cwd=ordner)
    _git("commit", "-m", "erster commit", cwd=ordner)
    (ordner / "a.txt").write_text("eins\nzwei\n", encoding="utf-8")
    _git("add", "a.txt", cwd=ordner)
    _git("commit", "-m", "zweiter commit", cwd=ordner)
    _git("branch", "feature", cwd=ordner)
    return ordner


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


# ═══════════════════════════════════════════════════════════════ Lesend
def test_status_zeigt_saubere_und_schmutzige_arbeitskopie(tools, repo):
    sauber = erfolg(tools("git.status", repo=str(repo)))
    assert sauber.evidence["geaendert"] == 0

    (repo / "b.txt").write_text("neu\n", encoding="utf-8")
    schmutzig = erfolg(tools("git.status", repo=str(repo)))
    assert schmutzig.evidence["unversioniert"] == 1
    assert schmutzig.evidence["geaendert"] == 1


def test_log_zeigt_beide_commits(tools, repo):
    log = erfolg(tools("git.log", repo=str(repo)))
    assert log.evidence["anzahl"] == 2
    assert "zweiter commit" in log.payload
    assert "erster commit" in log.payload


def test_log_file_folgt_nur_der_angegebenen_datei(tools, repo):
    (repo / "c.txt").write_text("c\n", encoding="utf-8")
    _git("add", "c.txt", cwd=repo)
    _git("commit", "-m", "dritter commit nur c.txt", cwd=repo)

    log = erfolg(tools("git.log.file", repo=str(repo), path="a.txt"))
    assert log.evidence["anzahl"] == 2
    assert "dritter commit" not in log.payload


def test_diff_zeigt_unstaged_aenderung(tools, repo):
    (repo / "a.txt").write_text("eins\nzwei\ndrei\n", encoding="utf-8")
    diff = erfolg(tools("git.diff", repo=str(repo)))
    assert "+drei" in diff.payload


def test_diff_staged_zeigt_nur_vorgemerktes(tools, repo):
    (repo / "a.txt").write_text("eins\nzwei\ndrei\n", encoding="utf-8")
    leer = erfolg(tools("git.diff.staged", repo=str(repo)))
    assert leer.payload == "(nichts)"
    _git("add", "a.txt", cwd=repo)
    voll = erfolg(tools("git.diff.staged", repo=str(repo)))
    assert "+drei" in voll.payload


def test_show_zeigt_commit_details(tools, repo):
    show = erfolg(tools("git.show", repo=str(repo), ref="HEAD"))
    assert "zweiter commit" in show.payload


def test_blame_nennt_autor_je_zeile(tools, repo):
    blame = erfolg(tools("git.blame", repo=str(repo), path="a.txt"))
    assert "Testuser" in blame.payload
    assert blame.evidence["zeilen"] == 2


def test_branch_list_und_current(tools, repo):
    liste = erfolg(tools("git.branch.list", repo=str(repo)))
    assert "feature" in liste.payload
    aktuell = erfolg(tools("git.branch.current", repo=str(repo)))
    assert aktuell.evidence["branch"] == "main"


def test_repo_info_meldet_branch_und_sauberkeit(tools, repo):
    info = erfolg(tools("git.repo.info", repo=str(repo)))
    assert info.evidence["sauber"] is True
    (repo / "x.txt").write_text("x", encoding="utf-8")
    info2 = erfolg(tools("git.repo.info", repo=str(repo)))
    assert info2.evidence["sauber"] is False


def test_config_get_ungesetzten_schluessel_meldet_das_ehrlich(tools, repo):
    res = erfolg(tools("git.config.get", repo=str(repo), key="does.not.exist"))
    assert res.payload is None
    name = erfolg(tools("git.config.get", repo=str(repo), key="user.name"))
    assert name.payload == "Testuser"


def test_clean_preview_loescht_nichts(tools, repo):
    (repo / "muell.tmp").write_text("x", encoding="utf-8")
    vorschau = erfolg(tools("git.clean.preview", repo=str(repo)))
    assert vorschau.evidence["anzahl"] == 1
    assert (repo / "muell.tmp").exists()


# ═══════════════════════════════════════════════════════════════ WRITE
def test_add_commit_kompletter_zyklus(tools, repo):
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    erfolg(tools("git.add", repo=str(repo), paths=["b.txt"]))
    status = erfolg(tools("git.status", repo=str(repo)))
    assert status.evidence["staged"] == 1

    erfolg(tools("git.commit", repo=str(repo), message="dritter commit"))
    log = erfolg(tools("git.log", repo=str(repo)))
    assert log.evidence["anzahl"] == 3


def test_commit_ohne_nachricht_schlaegt_ehrlich_fehl(tools, repo):
    fehler(tools("git.commit", repo=str(repo), message=""))


def test_unstage_nimmt_aus_der_vormerkung(tools, repo):
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    erfolg(tools("git.add", repo=str(repo), paths=["b.txt"]))
    erfolg(tools("git.unstage", repo=str(repo), paths=["b.txt"]))
    status = erfolg(tools("git.status", repo=str(repo)))
    assert status.evidence["staged"] == 0
    assert status.evidence["unversioniert"] == 1


def test_checkout_wechselt_branch(tools, repo):
    erfolg(tools("git.checkout", repo=str(repo), ref="feature"))
    aktuell = erfolg(tools("git.branch.current", repo=str(repo)))
    assert aktuell.evidence["branch"] == "feature"


def test_branch_create_erstellt_ohne_zu_wechseln(tools, repo):
    erfolg(tools("git.branch.create", repo=str(repo), name="neu"))
    vorher = erfolg(tools("git.branch.current", repo=str(repo)))
    assert vorher.evidence["branch"] != "neu"
    liste = erfolg(tools("git.branch.list", repo=str(repo)))
    assert "neu" in liste.payload


def test_stash_save_und_pop(tools, repo):
    (repo / "a.txt").write_text("eins\nzwei\nstash-inhalt\n", encoding="utf-8")
    erfolg(tools("git.stash.save", repo=str(repo), message="wip"))
    sauber = erfolg(tools("git.status", repo=str(repo)))
    assert sauber.evidence["geaendert"] == 0

    erfolg(tools("git.stash.pop", repo=str(repo)))
    zurueck = (repo / "a.txt").read_text(encoding="utf-8")
    assert "stash-inhalt" in zurueck


def test_tag_create_list_delete(tools, repo):
    erfolg(tools("git.tag.create", repo=str(repo), name="v1.0", message="Erste Version"))
    liste = erfolg(tools("git.tag.list", repo=str(repo)))
    assert "v1.0" in liste.payload
    erfolg(tools("git.tag.delete", repo=str(repo), name="v1.0"))
    liste2 = erfolg(tools("git.tag.list", repo=str(repo)))
    assert "v1.0" not in liste2.payload


def test_ignore_add_legt_datei_an_und_ist_idempotent(tools, repo):
    erfolg(tools("git.ignore.add", repo=str(repo), pattern="*.log"))
    inhalt = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "*.log" in inhalt
    erfolg(tools("git.ignore.add", repo=str(repo), pattern="*.log"))
    assert (repo / ".gitignore").read_text(encoding="utf-8").count("*.log") == 1


def test_config_set_schreibt_nur_lokal(tools, repo):
    erfolg(tools("git.config.set", repo=str(repo), key="user.name", value="Anders"))
    res = subprocess.run(["git", "config", "--local", "--get", "user.name"],
                         cwd=str(repo), capture_output=True, text=True)
    assert res.stdout.strip() == "Anders"


def test_revert_erstellt_neuen_commit_ohne_historie_umzuschreiben(tools, repo):
    log_vorher = erfolg(tools("git.log", repo=str(repo)))
    kopf = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True).stdout.strip()
    erfolg(tools("git.revert", repo=str(repo), ref=kopf))
    log_nachher = erfolg(tools("git.log", repo=str(repo)))
    assert log_nachher.evidence["anzahl"] == log_vorher.evidence["anzahl"] + 1
    assert (repo / "a.txt").read_text(encoding="utf-8") == "eins\n"


def test_remote_add_list_remove(tools, repo, tmp_path):
    ziel = tmp_path / "anderswo"
    erfolg(tools("git.remote.add", repo=str(repo), name="upstream", url=str(ziel)))
    liste = erfolg(tools("git.remote.list", repo=str(repo)))
    assert "upstream" in liste.payload
    erfolg(tools("git.remote.remove", repo=str(repo), name="upstream"))
    liste2 = erfolg(tools("git.remote.list", repo=str(repo)))
    assert "upstream" not in liste2.payload


def test_init_und_clone(tools, workspace, tmp_path):
    neu = "neues_repo"
    erfolg(tools("git.init", path=neu))
    assert (workspace / neu / ".git").is_dir()

    ziel_klon = "geklont"
    erfolg(tools("git.clone", repo_url=str(workspace / neu), path=ziel_klon))
    assert (workspace / ziel_klon / ".git").is_dir()


# ═══════════════════════════════════════════════════════════════ SYSTEM
def test_branch_delete_verweigert_unmerged(tools, repo):
    erfolg(tools("git.branch.create", repo=str(repo), name="ungemergt"))
    erfolg(tools("git.checkout", repo=str(repo), ref="ungemergt"))
    (repo / "nur_hier.txt").write_text("x\n", encoding="utf-8")
    _git("add", "nur_hier.txt", cwd=repo)
    _git("commit", "-m", "nur auf ungemergt", cwd=repo)
    erfolg(tools("git.checkout", repo=str(repo), ref="main"))
    fehler(tools("git.branch.delete", repo=str(repo), name="ungemergt"))


def test_branch_delete_erlaubt_gemergten(tools, repo):
    erfolg(tools("git.branch.create", repo=str(repo), name="gemergt"))
    erfolg(tools("git.branch.delete", repo=str(repo), name="gemergt"))


def test_stash_drop_dry_run_zeigt_inhalt_ohne_zu_loeschen(tools, repo):
    (repo / "a.txt").write_text("eins\nzwei\nstash2\n", encoding="utf-8")
    erfolg(tools("git.stash.save", repo=str(repo)))
    vorschau = erfolg(tools("git.stash.drop", repo=str(repo), dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    liste = erfolg(tools("git.stash.list", repo=str(repo)))
    assert liste.evidence["anzahl"] == 1


def test_stash_drop_wirklich(tools, repo):
    (repo / "a.txt").write_text("eins\nzwei\nstash3\n", encoding="utf-8")
    erfolg(tools("git.stash.save", repo=str(repo)))
    erfolg(tools("git.stash.drop", repo=str(repo)))
    liste = erfolg(tools("git.stash.list", repo=str(repo)))
    assert liste.evidence["anzahl"] == 0


def test_commit_amend_aendert_nachricht_nicht_anzahl(tools, repo):
    log_vorher = erfolg(tools("git.log", repo=str(repo)))
    erfolg(tools("git.commit.amend", repo=str(repo), message="geänderte nachricht"))
    log_nachher = erfolg(tools("git.log", repo=str(repo)))
    assert log_nachher.evidence["anzahl"] == log_vorher.evidence["anzahl"]
    assert "geänderte nachricht" in log_nachher.payload


def test_rebase_ohne_konflikt(tools, repo):
    """feature liegt hinter main zurück, hat aber keine widersprüchliche
    Änderung -- der Rebase muss also sauber durchlaufen."""
    erfolg(tools("git.checkout", repo=str(repo), ref="feature"))
    (repo / "feature.txt").write_text("f\n", encoding="utf-8")
    _git("add", "feature.txt", cwd=repo)
    _git("commit", "-m", "feature commit", cwd=repo)

    erfolg(tools("git.checkout", repo=str(repo), ref="main"))
    (repo / "unabhaengig.txt").write_text("m\n", encoding="utf-8")
    _git("add", "unabhaengig.txt", cwd=repo)
    _git("commit", "-m", "main commit", cwd=repo)

    erfolg(tools("git.checkout", repo=str(repo), ref="feature"))
    erfolg(tools("git.rebase", repo=str(repo), upstream="main"))
    log = erfolg(tools("git.log", repo=str(repo)))
    assert "main commit" in log.payload
    assert "feature commit" in log.payload


def test_rebase_abort_stellt_zustand_wieder_her(tools, repo):
    """main und feature ändern dieselbe Zeile -- das gibt einen echten
    Konflikt, den git.rebase.abort wieder auflöst."""
    erfolg(tools("git.checkout", repo=str(repo), ref="feature"))
    (repo / "a.txt").write_text("eins\nzwei\nfeature-version\n", encoding="utf-8")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-m", "feature aendert a.txt", cwd=repo)

    erfolg(tools("git.checkout", repo=str(repo), ref="main"))
    (repo / "a.txt").write_text("eins\nzwei\nmain-version\n", encoding="utf-8")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-m", "main aendert a.txt", cwd=repo)

    erfolg(tools("git.checkout", repo=str(repo), ref="feature"))
    konflikt = fehler(tools("git.rebase", repo=str(repo), upstream="main"))
    assert "conflict" in konflikt.summary.lower() or "konflikt" in konflikt.summary.lower()

    erfolg(tools("git.rebase.abort", repo=str(repo)))
    status = erfolg(tools("git.status", repo=str(repo)))
    assert status.evidence["geaendert"] == 0


# ═══════════════════════════════════════════════════════════════ CRITICAL
def test_reset_hard_dry_run_veraendert_nichts(tools, repo):
    (repo / "a.txt").write_text("verworfen\n", encoding="utf-8")
    vorschau = erfolg(tools("git.reset.hard", repo=str(repo), dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    assert (repo / "a.txt").read_text(encoding="utf-8") == "verworfen\n"


def test_reset_hard_verwirft_wirklich(tools, repo):
    (repo / "a.txt").write_text("verworfen\n", encoding="utf-8")
    erfolg(tools("git.reset.hard", repo=str(repo)))
    assert (repo / "a.txt").read_text(encoding="utf-8") == "eins\nzwei\n"


def test_clean_dry_run_loescht_nichts_clean_wirklich_schon(tools, repo):
    (repo / "muell.tmp").write_text("x", encoding="utf-8")
    vorschau = erfolg(tools("git.clean", repo=str(repo), dry_run=True))
    assert vorschau.evidence["probelauf"] is True
    assert (repo / "muell.tmp").exists()

    erfolg(tools("git.clean", repo=str(repo)))
    assert not (repo / "muell.tmp").exists()


# ═══════════════════════════════════════════════════════════════ Sicherheit
def test_werte_mit_fuehrendem_bindestrich_werden_abgelehnt(tools, repo):
    """Ein Branch-/Remote-/Tag-Name, der wie eine Option aussieht, darf nicht
    als Option bei git ankommen -- das wäre eine Befehlsinjektion."""
    fehler(tools("git.checkout", repo=str(repo), ref="--upload-pack=/bin/sh"))
    fehler(tools("git.branch.create", repo=str(repo), name="-x"))
    fehler(tools("git.remote.add", repo=str(repo), name="-x", url="https://example.invalid"))
    fehler(tools("git.tag.create", repo=str(repo), name="--force"))


def test_repo_pfad_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools):
    fehler(tools("git.status", repo="/etc"))


def test_nicht_existierender_ordner_wird_abgelehnt(tools, workspace):
    fehler(tools("git.status", repo=str(workspace / "gibtsnicht")))
