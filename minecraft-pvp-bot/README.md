# PvP-Bot (Fabric-Mod für Minecraft 26.3)

Ein Bot, der wie ein Spieler aussieht und kämpft. Er ist auf **Mace**, **Speer** und
**Elytra** spezialisiert und greift alles an, was du ihm sagst.

## Was der Bot kann

| Technik | Was passiert |
|---|---|
| **Mace-Sprung** | Er schießt sich mit einer Windladung ~7 Blöcke hoch, lenkt in der Luft aufs Ziel und landet einen Smash-Angriff (Density V + Wind Burst III → er springt nach dem Treffer direkt wieder hoch für Combos). |
| **Elytra-Mace-Sturzflug** | Bei Zielen, die weit weg sind: Er wechselt Brustpanzer ↔ Elytra, startet mit Raketen, steigt ~26 Blöcke über das Ziel und stürzt sich mit der Mace darauf (im Test fast 100 Schaden mit einem Treffer). |
| **Speer-Ansturm** | Er sprintet mit gesenktem Speer los. Der Schaden hängt vom Tempo ab (Vanilla-Speermechanik). Danach holt er Anlauf für den nächsten Ansturm. |
| **Elytra-Speer-Angriff** | Er fliegt im Tiefflug mit Raketen durch das Ziel, zieht hoch und dreht die nächste Runde (gut gegen fliehende oder fliegende Ziele). |
| **Nahkampf** | Speerstiche mit hoher Reichweite oder Mace-Schläge, dazu Strafing. |
| **Überleben** | Netherite-Rüstung (Protection IV), Totem der Unsterblichkeit, goldene Äpfel bei wenig Leben und ein Windladungs-„Clutch“ gegen Fallschaden. |

## Installation (einmalig, ca. 5 Minuten)

1. **Fabric installieren**: Lade den Installer von <https://fabricmc.net/use/installer/>,
   starte ihn, wähle **Minecraft 26.3** aus und klicke auf *Installieren*.
2. **Fabric API** herunterladen (Version für 26.3): <https://modrinth.com/mod/fabric-api>
3. **PvP-Bot-Mod** herunterladen: die Datei `pvpbot-1.0.0+26.3.jar` (siehe unten).
4. Lege beide `.jar`-Dateien in deinen `mods`-Ordner:
   - Windows: `%appdata%\.minecraft\mods` (in die Adresszeile vom Explorer eingeben)
   - macOS: `~/Library/Application Support/minecraft/mods`
   - Linux: `~/.minecraft/mods`
5. Starte im Minecraft Launcher das Profil **fabric-loader-26.3**.

### Wo bekomme ich die `pvpbot-….jar`?

Auf GitHub unter **Actions → „PvP Bot - build mod“ → neuester grüner Lauf → Artifacts → `pvpbot-mod`**.
Das ist eine ZIP-Datei, in der die `.jar` liegt. Selbst bauen geht auch mit
`./gradlew build` (Java 25 nötig). Die Datei landet dann in `build/libs/`.

## Befehle

| Befehl | Wirkung |
|---|---|
| `/pvpbot spawn [Name]` | Erschafft einen voll ausgerüsteten Bot bei dir. Du bist sein Besitzer. |
| `/pvpbot attack <Ziel>` | **Greif an!** Das Ziel ist ein normaler Selektor, z. B. `@e[type=zombie,distance=..50]`, `@e[type=!player,distance=..20]` oder ein Spielername. Mehrere Ziele werden der Reihe nach erledigt. |
| `/pvpbot stop` | Kampf abbrechen, alle Ziele vergessen |
| `/pvpbot follow` / `/pvpbot stay` | Dir folgen oder stehen bleiben |
| `/pvpbot assist on\|off` | Wenn an (Standard): Der Bot greift alles an, was **du schlägst** und was **dich schlägt**. |
| `/pvpbot weapon auto\|mace\|spear` | Kampfstil: beides gemischt, nur Mace oder nur Speer |
| `/pvpbot tp` | Holt deine Bots zu dir |
| `/pvpbot list` | Zeigt Leben und aktuellen Zustand deiner Bots |
| `/pvpbot remove` | Entfernt deine Bots |

Tipps:
- Für Elytra-Angriffe braucht der Bot **freien Himmel** über sich. In Höhlen oder im Nether
  kämpft er am Boden.
- Der Bot greift dich und die Bots, die dir gehören, nie an.
- Seine Rüstung und Waffen lässt er beim Tod nicht fallen. Nach 30 Sekunden ohne Kampf füllt
  er Totem und goldene Äpfel wieder auf.

## Multiplayer

Die Mod muss auf dem **Server und bei allen Spielern** installiert sein. Die `/pvpbot`-Befehle
kann dort jeder benutzen, also am besten nur auf Servern mit Freunden.

## Für Entwickler

- Code: `src/main/java/de/samu/pvpbot/` (Kampf-KI in `entity/PvpBotEntity.java`)
- CI (`.github/workflows/pvpbot-build.yml`) baut die Mod und startet danach einen echten
  26.3-Server, auf dem der Bot automatisch gegen Eisengolems und Zombies kämpft
  (`SelfTest.java`, nur aktiv mit `-Dpvpbot.selftest=true`). Lokal: `./gradlew runServer -Pselftest`.
