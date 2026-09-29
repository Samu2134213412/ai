package de.samu.pvpbot.client;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/**
 * Settings menu for the PvP bot (key O). Every button just runs the matching /pvpbot command, so the
 * menu works on any server that has the mod, and the answer shows up in the chat as usual.
 */
public class PvpBotScreen extends Screen {
    private static final String[] PAGES = {"Bot", "Einstellungen", "Kit", "Zuhause", "Tricks"};
    private static int page;

    private record Entry(String label, String command, String tip) {
    }

    public PvpBotScreen() {
        super(Component.literal("PvP-Bot"));
    }

    private List<Entry> entries() {
        List<Entry> list = new ArrayList<>();
        switch (page) {
            case 0 -> {
                list.add(new Entry("Bot erschaffen", "pvpbot spawn", "Neuer Bot mit Standard-Kit (Mace, Speer, Elytra ...)"));
                list.add(new Entry("Survival-Bot erschaffen", "pvpbot survival", "Startet mit leeren Händen und besorgt sich alles selbst"));
                list.add(new Entry("Nächsten Mob angreifen", "pvpbot attack @e[type=!minecraft:player,type=!pvpbot:pvp_bot,type=!minecraft:item,distance=..48,sort=nearest,limit=1]", "Greift das nächste Tier/Monster an"));
                list.add(new Entry("Nächsten Spieler angreifen", "pvpbot attack @a[distance=0.5..,sort=nearest,limit=1]", "Greift den nächsten anderen Spieler an"));
                list.add(new Entry("Duell gegen mich", "pvpbot duel", "Deine Bots kämpfen gegen dich (Survival nötig)"));
                list.add(new Entry("Stopp", "pvpbot stop", "Kampf abbrechen, alle Ziele vergessen"));
                list.add(new Entry("Mir folgen", "pvpbot follow", ""));
                list.add(new Entry("Hier bleiben", "pvpbot stay", ""));
                list.add(new Entry("Zu mir holen", "pvpbot tp", ""));
                list.add(new Entry("Liste / Status", "pvpbot list", ""));
                list.add(new Entry("§cBots entfernen", "pvpbot remove", "Entfernt alle deine Bots"));
            }
            case 1 -> {
                list.add(new Entry("Helfen: an", "pvpbot assist on", "Greift an, was du schlägst und was dich schlägt"));
                list.add(new Entry("Helfen: aus", "pvpbot assist off", ""));
                list.add(new Entry("Waffe: automatisch", "pvpbot weapon auto", ""));
                list.add(new Entry("Waffe: nur Mace", "pvpbot weapon mace", ""));
                list.add(new Entry("Waffe: nur Speer", "pvpbot weapon spear", ""));
                list.add(new Entry("Chat-Meldungen: an", "pvpbot chat on", "Bots erzählen, was sie lernen und tun"));
                list.add(new Entry("Chat-Meldungen: aus", "pvpbot chat off", ""));
                list.add(new Entry("Gelerntes anzeigen", "pvpbot brain", ""));
                list.add(new Entry("§cGelerntes löschen", "pvpbot brain reset", "Die Bots fangen beim Lernen von vorne an"));
            }
            case 2 -> {
                list.add(new Entry("Kit: Standard", "pvpbot kit default", "Mace, Speer, Axt, Elytra ... unendlich"));
                list.add(new Entry("Kit: mein Inventar kopieren", "pvpbot kit copy", "Nur im Kreativmodus"));
                list.add(new Entry("Kit: meins abgeben", "pvpbot kit give", "Survival: Rüstung, Hotbar, Zweithand gehen an den Bot"));
                list.add(new Entry("Kit: zurückholen", "pvpbot kit take", ""));
                list.add(new Entry("Kit anzeigen", "pvpbot kit", ""));
                list.add(new Entry("Sammeln: an", "pvpbot gather on", "Fehlt etwas zum Kämpfen, besorgt er es selbst"));
                list.add(new Entry("Sammeln: aus", "pvpbot gather off", ""));
                list.add(new Entry("Was fehlt?", "pvpbot needs", ""));
                list.add(new Entry("§5Durchspielen starten", "pvpbot durchspielen", "Etappe 1: Diamanten, Obsidian, Netherportal"));
                list.add(new Entry("Durchspielen stoppen", "pvpbot durchspielen stop", ""));
            }
            case 3 -> {
                list.add(new Entry("§6Zuhause hier setzen", "pvpbot home set", "Kisten im Umkreis von 10 Blöcken benutzt er, sonst stellt er dort welche auf. Hierhin kommt er immer zurück"));
                list.add(new Entry("Nach Hause gehen", "pvpbot home go", "Er läuft nach Hause und wartet dort"));
                list.add(new Entry("§6Autonom: an", "pvpbot autonom on",
                        "Verbessert seine Ausrüstung selbst (bis Diamant), sammelt Rüstungssets (1× Eisen, 2× Diamant) und lagert sie in Kisten im Umkreis von 10 Blöcken ums Zuhause (vorhandene Kisten benutzt er)"));
                list.add(new Entry("Autonom: aus", "pvpbot autonom off", ""));
                list.add(new Entry("Zuhause & Kisten anzeigen", "pvpbot home", ""));
                list.add(new Entry("§cZuhause löschen", "pvpbot home clear", ""));
            }
            default -> {
                String[][] tricks = {
                        {"kombo", "Windladung → Lunge → Mace"}, {"smash", "Windladungs-Smash"}, {"ansturm", "Speer-Ansturm"},
                        {"stiche", "Speer-Stiche im Vorbeirennen"}, {"sturzflug", "Elytra-Mace-Sturzflug"}, {"speerflug", "Elytra-Speerflug"},
                        {"mace", "Mace-Nahkampf"}, {"schwert", "Schwert/Axt-Nahkampf"}, {"bogen", "Bogenschüsse"}};
                for (String[] t : tricks) {
                    list.add(new Entry(t[1], "pvpbot trick " + t[0], "Nächster Angriff, sobald es möglich ist"));
                }
            }
        }
        return list;
    }

    @Override
    protected void init() {
        int columns = 2;
        int w = 150;
        int h = 20;
        int gap = 4;
        int left = this.width / 2 - (columns * w + gap) / 2;
        int top = 28;
        // Page tabs.
        int tabW = Math.min(100, (this.width - 20) / PAGES.length - 4);
        int tabLeft = this.width / 2 - (PAGES.length * (tabW + 4) - 4) / 2;
        for (int i = 0; i < PAGES.length; i++) {
            int index = i;
            Button tab = Button.builder(Component.literal(i == page ? "§e" + PAGES[i] : PAGES[i]), b -> {
                page = index;
                this.rebuildWidgets();
            }).bounds(tabLeft + i * (tabW + 4), 4, tabW, h).build();
            tab.active = i != page;
            this.addRenderableWidget(tab);
        }
        List<Entry> list = this.entries();
        for (int i = 0; i < list.size(); i++) {
            Entry e = list.get(i);
            int x = left + (i % columns) * (w + gap);
            int y = top + (i / columns) * (h + gap);
            Button button = Button.builder(Component.literal(e.label()), b -> this.run(e.command())).bounds(x, y, w, h).build();
            if (!e.tip().isEmpty()) {
                button.setTooltip(Tooltip.create(Component.literal(e.tip())));
            }
            this.addRenderableWidget(button);
        }
        this.addRenderableWidget(Button.builder(Component.literal("Fertig"), b -> this.onClose())
                .bounds(this.width / 2 - 50, this.height - 26, 100, h).build());
    }

    private void run(String command) {
        if (this.minecraft != null && this.minecraft.player != null) {
            this.minecraft.player.connection.sendCommand(command);
        }
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }
}
