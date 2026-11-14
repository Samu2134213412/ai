package de.samu.pvpbot.autopilot;

import de.samu.pvpbot.autopilot.brain.BotBrain;
import de.samu.pvpbot.autopilot.brain.PvpMode;
import java.util.function.Consumer;
import java.util.function.Supplier;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Settings menu for the autopilot (key N): on/off, target, tricks and which tactics it may use. */
public class AutopilotScreen extends Screen {
    private static final String[] PAGES = {"Steuerung", "Modi", "Taktiken", "Tricks"};
    private static int page;

    public AutopilotScreen() {
        super(Component.literal("PvP-Autopilot"));
    }

    @Override
    protected void init() {
        int w = 150;
        int h = 20;
        int gap = 4;
        int left = this.width / 2 - (2 * w + gap) / 2;
        int top = 42;
        int tabW = Math.min(110, (this.width - 20) / PAGES.length - 4);
        int tabLeft = this.width / 2 - (PAGES.length * (tabW + 4) - 4) / 2;
        for (int i = 0; i < PAGES.length; i++) {
            int index = i;
            Button tab = Button.builder(Component.literal(i == page ? "§e" + PAGES[i] : PAGES[i]), b -> {
                page = index;
                this.rebuildWidgets();
            }).bounds(tabLeft + i * (tabW + 4), 18, tabW, h).build();
            tab.active = i != page;
            this.addRenderableWidget(tab);
        }
        int[] slot = {0};
        Consumer<Button> place = b -> {
            b.setX(left + (slot[0] % 2) * (w + gap));
            b.setY(top + (slot[0] / 2) * (h + gap));
            slot[0]++;
            this.addRenderableWidget(b);
        };
        Autopilot ap = Autopilot.INSTANCE;
        AutopilotSettings s = AutopilotSettings.INSTANCE;
        switch (page) {
            case 0 -> {
                place.accept(this.button(() -> ap.isFullControl() ? "§6Volle Kontrolle: §aAN" : "§6Volle Kontrolle: §cAUS",
                        () -> ap.setFullControl(this.minecraft, !ap.isFullControl()),
                        "Der Autopilot übernimmt den ganzen Account: kämpft gegen Monster und Spieler, die er sieht, isst, sammelt Beute und zieht umher. Taste K schaltet aus."));
                place.accept(this.button(() -> AutopilotSettings.INSTANCE.homeSet
                                ? "Zuhause: §f" + AutopilotSettings.INSTANCE.homeX + " " + AutopilotSettings.INSTANCE.homeY + " " + AutopilotSettings.INSTANCE.homeZ
                                : "§6Zuhause hier setzen",
                        () -> AutopilotClient.setHome(this.minecraft),
                        "Kisten in 10 Blöcken Umkreis benutzt er (oder stellt welche auf), hierhin kommt er zurück, wenn er nichts zu tun hat"));
                place.accept(this.button(() -> ap.isEnabled() ? "Autopilot: §aAN" : "Autopilot: §cAUS",
                        () -> ap.setEnabled(this.minecraft, !ap.isEnabled()), "Taste K"));
                place.accept(this.button(() -> "Ziel: was ich anschaue", () -> AutopilotClient.lookTarget(this.minecraft), "Taste J"));
                place.accept(this.button(() -> "Ziel: nächster Spieler", () -> ap.setTargetMode(this.minecraft, Autopilot.TargetMode.NEAREST_PLAYER), ""));
                place.accept(this.button(() -> "Ziel: Monster", () -> ap.setTargetMode(this.minecraft, Autopilot.TargetMode.MOBS), ""));
                place.accept(this.button(() -> "Ziel vergessen", () -> ap.setTarget(this.minecraft, null), ""));
                place.accept(this.button(() -> "Aktuelles Ziel: " + ap.describeTarget(), () -> { }, ""));
                place.accept(this.button(() -> "Gelerntes im Chat zeigen", () -> {
                    this.onClose();
                    BotBrain.INSTANCE.summary(12).forEach(line -> ap.say(this.minecraft, line));
                }, ""));
                place.accept(this.button(() -> "§cGelerntes löschen", () -> {
                    BotBrain.INSTANCE.reset();
                    ap.say(this.minecraft, "Gelerntes gelöscht.");
                }, "Der Autopilot fängt beim Lernen von vorne an"));
            }
            case 1 -> {
                // PvP modes: only the attacks the mode allows, each mode with its own memory.
                for (PvpMode m : PvpMode.values()) {
                    place.accept(this.button(() -> (ap.mode() == m ? "§a✔ " : "") + m.label, () -> {
                        s.mode = m.id;
                        s.save();
                        this.rebuildWidgets();
                    }, m.description + " – Angriffe: " + m.describeAttacks() + ". Das Kit packst du selbst ins Inventar."));
                }
            }
            case 2 -> {
                place.accept(this.toggle("Elytra-Angriffe", () -> s.elytra, v -> s.elytra = v, "Sturzflug und Speerflug"));
                place.accept(this.toggle("Windladungen", () -> s.windCharges, v -> s.windCharges = v, "Windladungs-Smash und Kombo"));
                place.accept(this.toggle("Speer", () -> s.spear, v -> s.spear = v, "Ansturm und Stiche im Vorbeirennen"));
                place.accept(this.toggle("Bogen", () -> s.bow, v -> s.bow = v, ""));
                place.accept(this.toggle("Attribute-Swap", () -> s.attributeSwap, v -> s.attributeSwap = v,
                        "Axt→Mace, Breach-Swap, Lunge-Swap, Stun-Slam"));
                place.accept(this.toggle("Schild blocken", () -> s.shield, v -> s.shield = v, ""));
                place.accept(this.toggle("W-Tap", () -> s.wTap, v -> s.wTap = v, "Sprint nach jedem Treffer neu starten"));
                place.accept(this.toggle("Enderperlen", () -> s.pearls, v -> s.pearls = v, "Hinterher oder weg bei wenig Leben"));
                place.accept(this.toggle("Wassereimer-Clutch", () -> s.waterClutch, v -> s.waterClutch = v, ""));
                place.accept(this.toggle("Tränke", () -> s.potions, v -> s.potions = v, "Buffs vor dem Kampf, Heilung bei wenig Leben"));
                place.accept(this.toggle("Automatisch essen", () -> s.autoEat, v -> s.autoEat = v, ""));
                place.accept(this.toggle("Beute einsammeln", () -> s.lootPickup, v -> s.lootPickup = v, ""));
                place.accept(this.toggle("Chat-Meldungen", () -> s.chat, v -> s.chat = v, ""));
            }
            default -> {
                for (BotBrain.Pattern pattern : BotBrain.Pattern.values()) {
                    place.accept(this.button(() -> pattern.label, () -> {
                        ap.forcePattern(pattern);
                        ap.say(this.minecraft, "§aNächster Angriff: §f" + pattern.label);
                    }, "/autopilot trick " + pattern.trickName()));
                }
            }
        }
        this.addRenderableWidget(Button.builder(Component.literal("Fertig"), b -> this.onClose())
                .bounds(this.width / 2 - 50, this.height - 26, 100, h).build());
    }

    /** A live status line above the tabs: on/off, mode, target. */
    @Override
    public void extractRenderState(net.minecraft.client.gui.GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        Autopilot ap = Autopilot.INSTANCE;
        String status = "Autopilot " + (ap.isEnabled() ? "§aAN" : "§cAUS") + (ap.isFullControl() ? " §6(volle Kontrolle)" : "")
                + " §7· Modus §e" + ap.mode().label + " §7· Ziel §f" + ap.describeTarget();
        int w = Math.min(this.width - 8, this.font.width(status) + 16);
        g.fill(this.width / 2 - w / 2, 2, this.width / 2 + w / 2, 15, 0xB0101018);
        g.centeredText(this.font, Component.literal(status), this.width / 2, 5, 0xFFFFFFFF);
        super.extractRenderState(g, mouseX, mouseY, partialTick);
    }

    private Button button(Supplier<String> label, Runnable action, String tip) {
        Button b = Button.builder(Component.literal(label.get()), btn -> {
            action.run();
            btn.setMessage(Component.literal(label.get()));
        }).size(150, 20).build();
        if (!tip.isEmpty()) {
            b.setTooltip(Tooltip.create(Component.literal(tip)));
        }
        return b;
    }

    private Button toggle(String name, Supplier<Boolean> get, Consumer<Boolean> set, String tip) {
        return this.button(() -> name + ": " + (get.get() ? "§aAN" : "§cAUS"), () -> {
            set.accept(!get.get());
            AutopilotSettings.INSTANCE.save();
        }, tip);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }
}
