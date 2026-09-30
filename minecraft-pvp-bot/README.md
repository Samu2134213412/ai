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

## Ressourcen selbst beschaffen (Survival-Bot)

Mit `/pvpbot survival [Name]` erschaffst du einen Bot mit **leerem Inventar**. Fehlt ihm etwas
zum Kämpfen, geht er selbst los und besorgt es sich (auch Bots mit `/pvpbot kit give`):

1. **Er prüft, was fehlt** – der Reihe nach: eine Waffe (erst Steinschwert, dann Eisenschwert),
   Eisenrüstung, ein Schild (wenn er kein Totem hat), Essen (4 gebratenes Fleisch, wenn er keine
   goldenen Äpfel hat) und – sobald er Diamanten kennt – Diamant-Ausrüstung.
2. **Er plant rückwärts**: Für ein Eisenschwert braucht er Eisen → Eisenerz abbauen → dafür
   eine Steinspitzhacke → Stein → Holzspitzhacke → Stöcke und Bretter → Holz.
3. **Er sucht die Blöcke** in der Umgebung (Bäume, Stein, Kohle-, Eisen- und Diamanterz),
   läuft hin, baut sie mit der richtigen Spitzhacke ab (echte Abbauzeiten) und gräbt sich
   notfalls einen Tunnel. Findet er nichts, erkundet er die Gegend. Lava meidet er.
4. **Er jagt** Kühe, Schweine, Schafe, Hühner und Hasen für Essen und sammelt Drops ein.
5. **Er stellt her und schmilzt** (Werkzeuge, Waffen, Rüstung, Schild, Erz mit Kohle oder Holz)
   und zieht sich das Beste gleich an.

Wird er oder du angegriffen, hört er sofort auf und kämpft. Danach sammelt er weiter.
Er schreibt dir im Chat, was er gerade holt.

Vereinfachungen: Er braucht keine Werkbank und keinen Ofen (stellt „aus dem Rucksack“ her) und
schmilzt etwas schneller als ein Ofen. Mit `/pvpbot gather off` schaltest du das Sammeln aus.

**Autopilot**: Ohne Ziel sammelt er herumliegende Items in der Nähe ein (z. B. die Beute nach
einem Kampf) und isst, wenn er Hunger hat. Richtig abbauen und herstellen tut nur der Bot.

Das Gedächtnis liegt in `.minecraft/config/pvpbot-memory.json` (Bot) bzw.
`pvpbot-autopilot-memory.json` (Autopilot). Es bleibt also auch nach Neustarts erhalten. Wenn er etwas
Neues lernt, schreibt er es in den Chat.

## Installation (einmalig, ca. 5 Minuten)

1. **Fabric installieren**: Lade den Installer von <https://fabricmc.net/use/installer/>,
   starte ihn, wähle **Minecraft 26.3** aus und klicke auf *Installieren*.
2. **Fabric API** herunterladen (Version für 26.3): <https://modrinth.com/mod/fabric-api>
3. **Simple Voice Chat** herunterladen (Fabric, Version für 26.3): <https://modrinth.com/plugin/simple-voice-chat>
   – **Pflicht** für den PvP-Bot (Server *und* alle Spieler).
4. Die Mod(s) herunterladen (siehe unten) – du kannst eine oder beide nehmen.
5. Lege die `.jar`-Dateien in deinen `mods`-Ordner:
   - Windows: `%appdata%\.minecraft\mods` (in die Adresszeile vom Explorer eingeben)
   - macOS: `~/Library/Application Support/minecraft/mods`
   - Linux: `~/.minecraft/mods`
6. Starte im Minecraft Launcher das Profil **fabric-loader-26.3**.

### Wo bekomme ich die `.jar`-Dateien?

Auf GitHub unter **Actions → „PvP Bot - build mod“ → neuester grüner Lauf → Artifacts**:
`pvpbot-mod` (Bot) und `pvpbot-autopilot` (Autopilot). Das sind ZIP-Dateien, in denen die `.jar` liegt.
Selbst bauen geht auch mit `./gradlew build` (Java 25 nötig).

## Menüs

- **Taste O**: PvP-Bot-Menü (Bot erschaffen, angreifen, Duell, folgen, Kit, Sammeln, Durchspielen, Tricks, Gelerntes …).
  Jeder Button führt einfach den passenden `/pvpbot`-Befehl aus.
- **Taste N**: Autopilot-Menü (an/aus, Ziel, Tricks) und Schalter für jede Taktik
- **Volle Kontrolle** (ganz oben im Menü oder `/autopilot full`): der Autopilot übernimmt den ganzen Account – kämpft gegen Monster und Spieler, die er sieht, isst, sammelt Beute und zieht sonst umher (weicht Abgründen, Lava und Wasser aus). Taste K schaltet wieder aus.
  (Elytra, Windladungen, Speer, Bogen, Attribute-Swap, Schild, W-Tap, Enderperlen, Wassereimer, Tränke, Essen, Beute, Chat).
  Die Schalter werden in `config/pvpbot-autopilot.properties` gespeichert.

Die Tasten lassen sich in den Minecraft-Einstellungen unter *Steuerung* ändern.

## Fair Play – kein Cheaten

Beide sehen nur, was ein Spieler auch sehen würde:
- Ziele werden nur angegriffen, wenn sie **in Sichtlinie** sind. Verschwindet ein Ziel hinter einer Wand,
  gehen sie zur letzten gesehenen Stelle, suchen kurz und geben dann auf („aus den Augen verloren“).
- Beim Sammeln kennt der Bot nur **freiliegende Blöcke, die er sehen kann** – kein Röntgenblick durch Stein.
- Der Autopilot dreht sich mit menschlicher Geschwindigkeit und schlägt nur zu, wenn das Fadenkreuz wirklich
  auf dem Gegner ist (normale Reichweite, keine Treffer um die Ecke).

## Durchspielen (Etappe 1)

`/pvpbot durchspielen` (für einen Survival-Bot): Wassereimer → Treppe nach unten auf Diamant-Höhe und Stollen
graben → Diamantspitzhacke → Wasser auf Lava gießen und 10 Obsidian abbauen → Feuerstein aus Kies → Feuerzeug →
Netherportal bauen und anzünden. Die nächsten Etappen (Nether, Stronghold, Drache) folgen.

## Befehle – PvP-Bot

| Befehl | Wirkung |
|---|---|
| `/pvpbot spawn [Name]` | Erschafft einen Bot mit Standard-Kit bei dir. Du bist sein Besitzer. |
| `/pvpbot survival [Name]` | Bot mit leerem Inventar, der sich seine Ausrüstung selbst besorgt |
| `/pvpbot gather on\|off` | Selbst Ressourcen beschaffen an (Standard) / aus |
| `/pvpbot needs` | Zeigt, was deinen Bots noch fehlt und was sie als Nächstes holen |
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
| `/pvpbot trick <name>` | Nächster Angriff: `kombo`, `smash`, `ansturm`, `stiche`, `sturzflug`, `speerflug`, `mace`, `schwert`, `bogen` |
| `/pvpbot durchspielen` / `durchspielen stop` | Survival-Bot spielt Minecraft durch (Etappe 1: Netherportal) |
| `/pvpbot brain` / `brain reset` | Zeigt bzw. löscht, was die Bots gelernt haben |
| `/pvpbot chat on\|off` | Ob die Bots dir im Chat erzählen, was sie lernen oder ob sie feststecken |
| `/pvpbot tp` · `list` · `remove` | Herholen · Status · Entfernen |
| `/pvpbot ki key <key>` | Deinen **Anthropic-API-Key** hinterlegen (von <https://console.anthropic.com>). Jeder Spieler nutzt seinen eigenen Key; er wird in `config/pvpbot-ai.json` gespeichert und nie im Chat oder Log gezeigt. `/pvpbot ki` zeigt den Status, `/pvpbot ki aus` löscht den Key. |
| `@bot <text>` im Chat | **Mit deinem Bot reden** (auch `@Name <text>`, `Name, <text>` oder `/pvpbot sag <text>`). Die KI (Claude) antwortet für ihn **und legt seine Ziele fest**: „spiel Minecraft durch“, „hol mir 10 Eisen“, „bau mir eine Eisenspitzhacke“, „komm mit“, „geh nach Hause“, „greif den Zombie an“, „hör auf“. |

## KI-Chat & Voice Chat

- **KI-Chat:** Deine Nachricht und der Zustand des Bots (Leben, Ort, Ausrüstung, aktueller Plan) gehen an Claude
  (Modell `claude-opus-5-5`, änderbar in `config/pvpbot-ai.json` → `"model"`). Die KI entscheidet selbst, ob sie nur
  antwortet oder dem Bot ein Ziel gibt (Werkzeuge: *Ziel setzen*, *Sammelauftrag*, *angreifen*). Fair bleibt es trotzdem:
  angreifen kann er nur, was er selbst sieht. Ist der Auftrag fertig, meldet er sich. Falls Claude eine Anfrage ablehnt,
  versucht es der Server automatisch mit dem empfohlenen Ersatzmodell (server-side fallback, `"fallbacks": "default"`).
  Serverbetreiber können in `config/pvpbot-ai.json` einen `"serverKey"` für alle eintragen.
- **Simple Voice Chat:** Antwortet dein Bot, hörst du ihn auch „reden“ – ein kurzes Brabbeln von dort, wo er steht
  (Reichweite 32 Blöcke). Sprichst du in dein Mikro, dreht er sich zu dir um und hört zu.

## Befehle – Autopilot

| Taste / Befehl | Wirkung |
|---|---|
| **K** | Autopilot an/aus (ohne Ziel nimmt er, was du gerade anschaust) |
| **J** | Ziel = das, was du anschaust |
| `/autopilot on` / `off` | An/aus |
| `/autopilot full` | Volle Kontrolle an/aus |
| `/autopilot target <Spieler>` | Einen bestimmten Spieler jagen |
| `/autopilot target nearest` | Immer den nächsten Spieler angreifen |
| `/autopilot target mobs` | Monster in der Nähe bekämpfen |
| `/autopilot stop` | Ziel vergessen |
| `/autopilot trick <name>` | Nächster Angriff (wie beim Bot) |
| **N** | Autopilot-Menü mit allen Einstellungen |
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

## Getestet

Jede Änderung wird automatisch in echtem Minecraft 26.3 getestet (siehe unten). Stand der letzten Tests:

- **Survival-Bot** mit leerem Inventar: Holz → Bretter → Stöcke → Holzspitzhacke → Stein →
  Steinschwert → Steinspitzhacke → Eisenerz + Kohle → schmelzen → Eisenschwert, komplette
  Eisenrüstung und Schild in ca. 2,5 Minuten, ganz allein.
- **Bot** auf einem echten Server: 17 von 17 Kämpfen gewonnen, z. B. Elytra-Mace-Sturzflug auf einen
  45 Blöcke entfernten Eisengolem (bis zu 96 Schaden mit einem Treffer), Speer-Flugangriff (46 Schaden),
  Schwert-Kit gegen 3 Zombies, Bogen-Kit, und aus einer 1×1-Steingrube hat er sich selbst freigebaut.
- **Autopilot** in einem echten Client: gewinnt mit Schwert, Mace + Windladungen, Speer, Bogen und
  Elytra + Mace (Sturzflug aus 35 Blöcken Entfernung: 62 Schaden) gegen Eisengolems und gegen 3 Zombies.
- **Duell Autopilot gegen Bot** mit exakt gleichem Kit: knapp, bisher gewinnt meist der Bot
  (mit ~9 Herzpunkten übrig).
- Nicht getestet: gegen echte menschliche Spieler. Da ist die erste Zeit Lernphase.

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

### Zuhause & Autonom-Modus

- `/pvpbot home set` (oder Menü **O → Zuhause**): setzt das Zuhause des Bots auf deine Position. Hat er nichts zu tun, läuft er dorthin zurück und wartet – dort findest du ihn immer und kannst ihm neue Befehle geben.
- `/pvpbot home go` schickt ihn sofort nach Hause, `/pvpbot home` zeigt Zuhause, Kisten und Modus, `/pvpbot home clear` löscht es.
- `/pvpbot autonom on|off` (nur Survival-Bots): er verbessert seine Ausrüstung selbst bis Diamant (Schwert, Rüstung, Spitzhacke), sammelt danach Ersatz-Rüstungssets (1× Eisen, 2× Diamant), lagert die Sets und überflüssige Blöcke in Kisten im Umkreis von 10 Blöcken um das Zuhause. Stehen dort schon Kisten, benutzt er die; sonst craftet er selbst welche und stellt sie zusammen nah ans Zuhause. Das Zuhause bestimmst immer du.
