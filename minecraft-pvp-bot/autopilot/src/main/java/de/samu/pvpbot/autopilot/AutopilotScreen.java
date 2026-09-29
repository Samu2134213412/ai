package de.samu.pvpbot.autopilot;

import de.samu.pvpbot.autopilot.brain.BotBrain;
import java.util.function.Consumer;
import java.util.function.Supplier;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Settings menu for the autopilot (key N): on/off, target, tricks and which tactics it may use. */
public class AutopilotScreen extends Screen {
    private static final String[] PAGES = {"Steuerung", "Taktiken", "Tricks"};
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
        int top = 28;
        int tabW = Math.min(110, (this.width - 20) / PAGES.length - 4);
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
