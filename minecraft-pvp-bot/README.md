# PvP-Bot (Fabric-Mods für Minecraft 26.3)

Hier gibt es **zwei Mods**:

| | **PvP-Bot** (`pvpbot-….jar`) | **Autopilot** (`pvpbot-autopilot-….jar`) |
|---|---|---|
| Was ist das? | Ein eigener Bot, der wie ein Spieler aussieht und für dich kämpft | **Dein eigener Spieler** wird zum PvP-Bot und kämpft von selbst |
| Wofür? | Singleplayer-Spaß, Sparring, Bots gegen Mobs oder Freunde | Mit deinem Account (oder einem Zweit-Account) auf einem Server der Bot sein |
| Wo muss es installiert sein? | Im Singleplayer nur bei dir, auf Servern auf Server **und** bei allen Spielern | **Nur bei dir** (reine Client-Mod), funktioniert auch auf Servern ohne Mods |
| Ausrüstung | Standard-Kit oder dein Kit (`/pvpbot kit`) | Genau das, was in deinem Inventar ist (Survival-tauglich) |
| Steuerung | `/pvpbot …` | Taste **K** (an/aus), Taste **J** (Ziel = was du anschaust), `/autopilot …` |

Beide lernen dazu (siehe unten) und passen sich an das Kit an, das sie gerade haben.

## Was der Bot kann

| Technik | Was passiert |
|---|---|
| **Mace-Sprung** | Er schießt sich mit einer Windladung ~7 Blöcke hoch, lenkt in der Luft aufs Ziel und landet einen Smash-Angriff. |
| **Elytra-Mace-Sturzflug** | Bei weit entfernten Zielen: Brustpanzer ↔ Elytra tauschen, mit Raketen starten, ~25 Blöcke über das Ziel steigen und sich mit der Mace draufstürzen. |
| **Speer-Ansturm** | Er sprintet mit gesenktem Speer los. Der Schaden hängt vom Tempo ab (Vanilla-Speermechanik). |
| **Elytra-Speerflug** | Er fliegt im Tiefflug mit Raketen durch das Ziel, zieht hoch und dreht die nächste Runde. |
| **Schwert/Axt-Nahkampf** | Mit Schwert, Axt oder Dreizack. Der Autopilot springt dabei für kritische Treffer. |
| **Bogenschüsse** | Hält Abstand, spannt voll und zielt mit Vorhalt und Pfeilabfall. |
| **Überleben** | Totem in die Zweithand, goldene Äpfel bei wenig Leben, Windladungs-„Clutch“ gegen Fallschaden. |
| **Selbst befreien** | Steckt er fest (z. B. mit der Elytra an einer Wand), zieht er erst hoch bzw. springt zur Seite, dann Windladung, dann baut er sich frei (nie Bedrock, Obsidian oder Kisten). Der Bot teleportiert sich als letzte Möglichkeit an eine freie Stelle. |

## Der Bot lernt dazu

Es gibt **8 Angriffsmuster**: Mace-Nahkampf, Speer-Stiche, Windladungs-Smash, Speer-Ansturm,
Elytra-Mace-Sturzflug, Elytra-Speerflug, Schwert/Axt-Nahkampf und Bogenschüsse.
Welches er nimmt, entscheidet er selbst:

1. **Er erkennt die Situation**: im Freien, in einer Höhle (Decke niedriger als 10 Blöcke) oder
   im Wasser, dazu die Entfernung (nah/mittel/fern), ob das Ziel am Boden ist oder fliegt,
   ob es ein Spieler oder ein Mob ist, **und welches Kit er gerade hat**.
2. **Er probiert nur, was mit seinem Kit geht.** Ohne Windladungen kein Mace-Sprung, ohne
   Elytra und Raketen kein Flug, mit Schwert und Bogen eben Schwert und Bogen.
3. **Er bewertet jeden Versuch**: Schaden am Gegner (plus Bonus fürs Töten) minus eigener
   Schaden, geteilt durch die Zeit. Feststecken zählt als schlechtes Ergebnis.
4. **Er merkt sich das pro Situation und Kit.** Was gut lief, nimmt er öfter. Was schlecht lief,
   lässt er erst einmal 10 Sekunden ganz weg und danach nur noch selten. Mit einem neuen Kit
   fängt er also von vorne an und lernt selbst, wie man es spielt.
5. **Etwas Zufall**: Ab und zu probiert er absichtlich etwas anderes aus, am Anfang öfter und
   mit mehr Erfahrung seltener.

Das Gedächtnis liegt in `.minecraft/config/pvpbot-memory.json` (Bot) bzw.
`pvpbot-autopilot-memory.json` (Autopilot). Es bleibt also auch nach Neustarts erhalten. Wenn er etwas
Neues lernt, schreibt er es in den Chat.

## Installation (einmalig, ca. 5 Minuten)

1. **Fabric installieren**: Lade den Installer von <https://fabricmc.net/use/installer/>,
   starte ihn, wähle **Minecraft 26.3** aus und klicke auf *Installieren*.
2. **Fabric API** herunterladen (Version für 26.3): <https://modrinth.com/mod/fabric-api>
3. Die Mod(s) herunterladen (siehe unten) – du kannst eine oder beide nehmen.
4. Lege die `.jar`-Dateien in deinen `mods`-Ordner:
   - Windows: `%appdata%\.minecraft\mods` (in die Adresszeile vom Explorer eingeben)
   - macOS: `~/Library/Application Support/minecraft/mods`
   - Linux: `~/.minecraft/mods`
5. Starte im Minecraft Launcher das Profil **fabric-loader-26.3**.

### Wo bekomme ich die `.jar`-Dateien?

Auf GitHub unter **Actions → „PvP Bot - build mod“ → neuester grüner Lauf → Artifacts**:
`pvpbot-mod` (Bot) und `pvpbot-autopilot` (Autopilot). Das sind ZIP-Dateien, in denen die `.jar` liegt.
Selbst bauen geht auch mit `./gradlew build` (Java 25 nötig).

## Befehle – PvP-Bot

| Befehl | Wirkung |
|---|---|
| `/pvpbot spawn [Name]` | Erschafft einen Bot mit Standard-Kit bei dir. Du bist sein Besitzer. |
| `/pvpbot attack <Ziel>` | **Greif an!** Ein Selektor wie `@e[type=zombie,distance=..50]` oder ein Spielername. Mehrere Ziele werden der Reihe nach erledigt. `@s` = **du selbst** (Duell). |
| `/pvpbot duel` | **Duell gegen dich.** Deine Bots kämpfen gegen dich, bis einer am Boden liegt (du musst im Survival sein). Aufgeben mit `/pvpbot stop`. |
| `/pvpbot kit` | Zeigt das Kit deiner Bots |
| `/pvpbot kit default` | Standard-Kit: Mace, Netherite-Speer, Elytra, Raketen, Windladungen, Netherite-Rüstung (unendlich Nachschub) |
| `/pvpbot kit copy` | Deine Bots bekommen eine **Kopie** deines Inventars (nur im Kreativmodus) |
| `/pvpbot kit give` | **Survival**: Der nächste Bot bekommt deine Rüstung, Hotbar und Zweithand (werden dir abgenommen). Er verbraucht Pfeile, Raketen usw. wirklich und lässt beim Tod alles fallen. |
| `/pvpbot kit take` | Holt dein Survival-Kit zurück |
| `/pvpbot stop` | Kampf abbrechen, alle Ziele vergessen |
| `/pvpbot follow` / `/pvpbot stay` | Dir folgen oder stehen bleiben |
| `/pvpbot assist on\|off` | Wenn an (Standard): Der Bot greift alles an, was **du schlägst** und was **dich schlägt**. |
| `/pvpbot weapon auto\|mace\|spear` | Mace und/oder Speer erlauben |
| `/pvpbot brain` / `brain reset` | Zeigt bzw. löscht, was die Bots gelernt haben |
| `/pvpbot chat on\|off` | Ob die Bots dir im Chat erzählen, was sie lernen oder ob sie feststecken |
| `/pvpbot tp` · `list` · `remove` | Herholen · Status · Entfernen |

## Befehle – Autopilot

| Taste / Befehl | Wirkung |
|---|---|
| **K** | Autopilot an/aus (ohne Ziel nimmt er, was du gerade anschaust) |
| **J** | Ziel = das, was du anschaust |
| `/autopilot on` / `off` | An/aus |
| `/autopilot target <Spieler>` | Einen bestimmten Spieler jagen |
| `/autopilot target nearest` | Immer den nächsten Spieler angreifen |
| `/autopilot target mobs` | Monster in der Nähe bekämpfen |
| `/autopilot stop` | Ziel vergessen |
| `/autopilot brain` / `brain reset` | Gelerntes anzeigen / löschen |

Die Tasten lassen sich in den Minecraft-Einstellungen unter *Steuerung → PvP-Autopilot* ändern.
Der Autopilot pausiert, sobald ein Menü oder der Chat offen ist, und du kannst jederzeit mit **K**
übernehmen.

So benutzt du ihn als „Bot-Account“: Starte Minecraft mit dem Account, der der Bot sein soll
(z. B. ein Zweit-Account), mit Fabric + Autopilot. Pack ihm ein Kit ins Inventar (Waffen, Rüstung,
Elytra + Raketen, Windladungen, Bogen + Pfeile, goldene Äpfel, Totems), stell ihn neben deine
Freunde und drück **K** oder `/autopilot target nearest`.

Hinweis: Auf öffentlichen Servern ist so etwas meist verboten und wird von Anti-Cheat-Plugins
erkannt. Nimm ihn nur auf eigenen oder privaten Servern, wo alle einverstanden sind.

## Für Entwickler

- Bot: `src/main/java/de/samu/pvpbot/` (Kampf-KI in `entity/PvpBotEntity.java`, Kits in
  `entity/BotKit.java`, Lernen in `brain/BotBrain.java`)
- Autopilot: `autopilot/` (eigenes Gradle-Teilprojekt, `Autopilot.java`). Das Lern-Gehirn wird
  beim Bauen in ein eigenes Paket kopiert, damit beide Mods gleichzeitig installiert sein können.
- CI (`.github/workflows/pvpbot-build.yml`):
  - baut beide Mods,
  - startet einen echten 26.3-Server, auf dem der Bot automatisch gegen Golems und Zombies kämpft
    (`SelfTest.java`, lokal: `./gradlew runServer -Pselftest`),
  - startet einen echten Client (ohne Bildschirm), in dem der Autopilot mit verschiedenen Kits
    kämpft und ein Duell gegen den Bot bestreitet (`autopilot/src/gametest`, lokal:
    `./gradlew :autopilot:runClientGameTest`).
