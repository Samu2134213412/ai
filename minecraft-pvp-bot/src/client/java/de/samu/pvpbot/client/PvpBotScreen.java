package de.samu.pvpbot.client;

import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.brain.PvpMode;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import org.jspecify.annotations.Nullable;

/**
 * The PvP bot's menu (key O). On top it shows your bot live - health, mode, what it is doing, what
 * it wears. Below that are the pages; switches show their real state, and the page "Modi" marks the
 * mode the bot is in. Every button still just runs a /pvpbot command, so the menu works on any
 * server that has the mod.
 */
public class PvpBotScreen extends Screen {
    private static final String[] PAGES = {"Kampf", "Modi", "Kit", "Verhalten", "Zuhause", "Tricks"};
    private static final int HEADER_TOP = 6;
    private static final int HEADER_H = 46;
    private static final int TAB_H = 18;
    private static final int ROW = 22;
    private static int page;

    private @Nullable PvpBotEntity bot;
    /** What the buttons were built from; when it changes (a switch flipped), they are rebuilt. */
    private String built = "";
    private int left;
    private int panelW;
    private int contentTop;
    private int contentBottom;
    private int nextRow;
    private final List<ModeButton> modeButtons = new ArrayList<>();
    private int modeInfoTop;
    private int modeInfoHeight;

    private record ModeButton(Button button, PvpMode mode) {
    }

    public PvpBotScreen() {
        super(Component.literal("PvP-Bot"));
    }

    // ------------------------------------------------------------------ layout

    @Override
    protected void init() {
        this.bot = PvpBotHud.bot();
        this.built = this.snapshot();
        this.modeButtons.clear();
        this.panelW = Math.min(400, this.width - 16);
        this.left = this.width / 2 - this.panelW / 2;
        int tabsTop = HEADER_TOP + HEADER_H + 4;
        this.contentTop = tabsTop + TAB_H + 6;
        this.contentBottom = this.height - 30;
        this.nextRow = 0;

        // Page tabs across the whole panel.
        int tabW = (this.panelW - (PAGES.length - 1) * 2) / PAGES.length;
        for (int i = 0; i < PAGES.length; i++) {
            int index = i;
            Button tab = Button.builder(Component.literal(i == page ? "§e" + PAGES[i] : PAGES[i]), b -> {
                page = index;
                this.rebuildWidgets();
            }).bounds(this.left + i * (tabW + 2), tabsTop, tabW, TAB_H).build();
            tab.active = i != page;
            this.addRenderableWidget(tab);
        }

        boolean has = this.bot != null;
        switch (page) {
            case 0 -> {
                this.row(this.command("Bot erschaffen", "pvpbot spawn", "Neuer Bot mit Standard-Kit (Mace, Speer, Elytra ...)", true),
                        this.command("Survival-Bot erschaffen", "pvpbot survival", "Startet mit leeren Händen und besorgt sich alles selbst", true));
                this.row(this.command("Nächsten Mob angreifen",
                                "pvpbot attack @e[type=!minecraft:player,type=!pvpbot:pvp_bot,type=!minecraft:item,distance=..48,sort=nearest,limit=1]",
                                "Greift das nächste Tier/Monster an", has),
                        this.command("Nächsten Spieler angreifen", "pvpbot attack @a[distance=0.5..,sort=nearest,limit=1]",
                                "Greift den nächsten anderen Spieler an", has));
                this.row(this.command("§c⚔ Duell gegen mich", "pvpbot duel", "Deine Bots kämpfen gegen dich, im gewählten Modus (Survival nötig)", has),
                        this.command("§e■ Stopp", "pvpbot stop", "Kampf abbrechen, alle Ziele vergessen", has));
                this.row(this.toggle("Mir folgen", PvpBotEntity.FLAG_FOLLOWING, "pvpbot follow", "pvpbot stay", "Aus: er bleibt, wo er ist"),
                        this.command("Zu mir holen", "pvpbot tp", "", has));
                this.row(this.command("Liste / Status", "pvpbot list", "", has),
                        this.command("§cBots entfernen", "pvpbot remove", "Entfernt alle deine Bots", has));
            }
            case 1 -> {
                PvpMode selected = has ? this.bot.viewMode() : null;
                PvpMode[] modes = PvpMode.values();
                int columns = 3;
                int w = (this.panelW - (columns - 1) * 3) / columns;
                for (int i = 0; i < modes.length; i++) {
                    PvpMode m = modes[i];
                    Button b = Button.builder(Component.literal(m == selected ? "§a✔ " + m.label : m.label), btn -> this.run("pvpbot modus " + m.id))
                            .bounds(this.left + (i % columns) * (w + 3), this.contentTop + (i / columns) * ROW, w, 20).build();
                    b.active = has;
                    this.modeButtons.add(new ModeButton(this.addRenderableWidget(b), m));
                }
                int rows = (modes.length + columns - 1) / columns;
                this.modeInfoTop = this.contentTop + rows * ROW + 2;
                // The mode's description is drawn between the grid and these two buttons.
                int half = (this.panelW - 4) / 2;
                int y = Math.min(this.contentBottom - 20, this.modeInfoTop + 46);
                // (A small window: one line instead of three, or nothing - the tooltips still explain the modes.)
                int room = y - this.modeInfoTop - 3;
                this.modeInfoHeight = room >= 42 ? 42 : room >= 16 ? 16 : 0;
                this.place(this.command("§c⚔ Duell in diesem Modus", "pvpbot duel", "Jede Runde mit frischem Kit. Aufgeben: Stopp (Seite Kampf)", has), this.left, y, half);
                this.place(this.command("§aKit des Modus holen", "pvpbot kit holen",
                        "Du bekommst das gleiche Kit wie der Bot (leeres Inventar; Kreativmodus oder Operator)", has), this.left + half + 4, y, half);
            }
            case 2 -> {
                this.row(this.command("Kit: Standard", "pvpbot kit default", "Mace, Speer, Axt, Elytra ... unendlich. Schaltet auf Modus Frei", has),
                        this.command("Kit anzeigen", "pvpbot kit", "", has));
                this.row(this.command("Mein Inventar kopieren", "pvpbot kit copy", "Nur im Kreativmodus. Der Bot lernt selbst, wie man damit kämpft", has),
                        this.command("Was fehlt?", "pvpbot needs", "Was er noch braucht und als Nächstes holt", has));
                this.row(this.command("Meins abgeben", "pvpbot kit give", "Survival: Rüstung, Hotbar, Zweithand gehen an den Bot", has),
                        this.command("Zurückholen", "pvpbot kit take", "", has));
                this.row(this.toggle("Selbst sammeln", PvpBotEntity.FLAG_GATHERING, "pvpbot gather on", "pvpbot gather off",
                                "Fehlt etwas zum Kämpfen, besorgt er es selbst (Survival-Bots)"),
                        this.toggle("§5Durchspielen", PvpBotEntity.FLAG_SPEEDRUN, "pvpbot durchspielen", "pvpbot durchspielen stop",
                                "Survival-Bot spielt Minecraft durch: Diamanten, Nether, Festung, Drache"));
            }
            case 3 -> {
                this.row(this.toggle("Helfen", PvpBotEntity.FLAG_ASSISTING, "pvpbot assist on", "pvpbot assist off",
                                "Greift an, was du schlägst und was dich schlägt"),
                        this.toggle("Chat-Meldungen", PvpBotEntity.FLAG_TALK, "pvpbot chat on", "pvpbot chat off", "Der Bot erzählt, was er tut"));
                String weapon = !has ? "§7–" : this.bot.viewFlag(PvpBotEntity.FLAG_STYLE_MACE) ? "§enur Mace"
                        : this.bot.viewFlag(PvpBotEntity.FLAG_STYLE_SPEAR) ? "§enur Speer" : "§aautomatisch";
                String nextWeapon = !has ? "auto" : this.bot.viewFlag(PvpBotEntity.FLAG_STYLE_MACE) ? "spear"
                        : this.bot.viewFlag(PvpBotEntity.FLAG_STYLE_SPEAR) ? "auto" : "mace";
                Button hud = Button.builder(Component.literal("Anzeige im Spiel: " + (PvpBotHud.isEnabled() ? "§aAN" : "§cAUS")), b -> {
                    PvpBotHud.setEnabled(!PvpBotHud.isEnabled());
                    this.rebuildWidgets();
                }).size(10, 20).tooltip(Tooltip.create(Component.literal("Kleines Feld oben links: Leben, Modus und Treffer deines Bots, solange er kämpft"))).build();
                this.row(this.command("Waffe: " + weapon, "pvpbot weapon " + nextWeapon, "Klick wechselt: automatisch → nur Mace → nur Speer", has), hud);
                this.row(this.toggle("§6Allein spielen", PvpBotEntity.FLAG_SOLO, "pvpbot allein on", "pvpbot allein off",
                                "Du musst nichts mehr tun: er rüstet sich aus, kämpft nur, was er schlagen kann, lernt aus jedem Tod und kommt danach von selbst zurück"),
                        this.command("Lehren aus Toden", "pvpbot vorsicht", "Wem er mit welcher Rüstung ausweicht (im Chat)", true));
                this.row(this.command("Nächstem Spieler vertrauen", "pvpbot vertraue @p[distance=0.5..]",
                                "Dieser Spieler darf dem Bot im Chat Befehle geben (@bot komm, @bot hilfe) und wird nie angegriffen", has),
                        this.command("Vertraute anzeigen", "pvpbot vertraute", "Zurücknehmen: /pvpbot misstraue <Name>", has));
                this.row(this.command("Gelerntes anzeigen", "pvpbot brain", "Was gegen wen wie gut klappt (im Chat)", true),
                        this.command("§cGelerntes löschen", "pvpbot brain reset", "Die Bots fangen beim Lernen von vorne an", true));
            }
            case 4 -> {
                this.row(this.command("§6Zuhause hier setzen", "pvpbot home set",
                                "Kisten im Umkreis von 10 Blöcken benutzt er, sonst stellt er dort welche auf. Hierhin kommt er immer zurück", has),
                        this.command("Nach Hause gehen", "pvpbot home go", "Er läuft nach Hause und wartet dort", has));
                this.row(this.toggle("§6Autonom", PvpBotEntity.FLAG_AUTONOMOUS, "pvpbot autonom on", "pvpbot autonom off",
                                "Verbessert seine Ausrüstung selbst (bis Diamant) und lagert Rüstungssets in Kisten ums Zuhause (Survival-Bots)"),
                        this.command("Zuhause & Kisten anzeigen", "pvpbot home", "", has));
                this.row(this.command("§cZuhause löschen", "pvpbot home clear", "", has), null);
            }
            default -> {
                BotBrain.Pattern[] patterns = BotBrain.Pattern.values();
                int columns = 2;
                int w = (this.panelW - 4) / columns;
                for (int i = 0; i < patterns.length; i++) {
                    BotBrain.Pattern p = patterns[i];
                    this.place(this.command(p.label, "pvpbot trick " + p.trickName(), "Nächster Angriff, sobald es möglich ist", has),
                            this.left + (i % columns) * (w + 4), this.contentTop + (i / columns) * ROW, w);
                }
            }
        }
        this.addRenderableWidget(Button.builder(Component.literal("Fertig"), b -> this.onClose())
                .bounds(this.width / 2 - 50, this.height - 24, 100, 20).build());
    }

    /** Two buttons side by side in the next free row (the second may be null). */
    private void row(Button first, @Nullable Button second) {
        int half = (this.panelW - 4) / 2;
        int y = this.contentTop + this.nextRow * ROW;
        this.nextRow++;
        this.place(first, this.left, y, half);
        if (second != null) {
            this.place(second, this.left + half + 4, y, half);
        }
    }

    private void place(Button button, int x, int y, int w) {
        button.setX(x);
        button.setY(y);
        button.setWidth(w);
        this.addRenderableWidget(button);
    }

    private Button command(String label, String command, String tip, boolean enabled) {
        Button b = Button.builder(Component.literal(label), btn -> this.run(command)).size(10, 20).build();
        if (!tip.isEmpty()) {
            b.setTooltip(Tooltip.create(Component.literal(tip)));
        }
        b.active = enabled;
        return b;
    }

    /** A switch that shows its real state (from the bot) and runs the opposite command. */
    private Button toggle(String name, int flag, String commandOn, String commandOff, String tip) {
        boolean has = this.bot != null;
        boolean on = has && this.bot.viewFlag(flag);
        return this.command(name + ": " + (!has ? "§7–" : on ? "§aAN" : "§cAUS"), on ? commandOff : commandOn, tip, has);
    }

    private void run(String command) {
        if (this.minecraft != null && this.minecraft.player != null) {
            this.minecraft.player.connection.sendCommand(command);
        }
    }

    // ------------------------------------------------------------------ live state

    private String snapshot() {
        PvpBotEntity b = this.bot;
        if (b == null) {
            return "-";
        }
        int flags = 0;
        for (int f = 1; f <= PvpBotEntity.FLAG_SOLO; f <<= 1) {
            // (Fighting flickers on and off and no button shows it.)
            if (f != PvpBotEntity.FLAG_FIGHTING && b.viewFlag(f)) {
                flags |= f;
            }
        }
        return b.getId() + "|" + b.viewMode().id + "|" + flags;
    }

    @Override
    public void tick() {
        super.tick();
        this.bot = PvpBotHud.bot();
        if (!this.snapshot().equals(this.built)) {
            this.rebuildWidgets();
        }
    }

    // ------------------------------------------------------------------ drawing

    @Override
    public void extractRenderState(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        this.header(g);
        if (page == 1) {
            this.modeInfo(g);
        }
        super.extractRenderState(g, mouseX, mouseY, partialTick);
        if (page == 1 && this.bot != null) {
            PvpMode selected = this.bot.viewMode();
            for (ModeButton mb : this.modeButtons) {
                if (mb.mode() == selected) {
                    Button b = mb.button();
                    g.outline(b.getX() - 1, b.getY() - 1, b.getWidth() + 2, b.getHeight() + 2, PvpBotHud.GOOD);
                }
            }
        }
    }

    private void header(GuiGraphicsExtractor g) {
        int x = this.left;
        int y = HEADER_TOP;
        g.fill(x, y, x + this.panelW, y + HEADER_H, PvpBotHud.PANEL);
        g.outline(x, y, this.panelW, HEADER_H, PvpBotHud.PANEL_EDGE);
        PvpBotEntity b = this.bot;
        if (b == null) {
            g.centeredText(this.font, "Kein eigener Bot in der Nähe", this.width / 2, y + 11, PvpBotHud.ACCENT);
            g.centeredText(this.font, "Erschaffe einen auf der Seite Kampf.", this.width / 2, y + 25, PvpBotHud.MUTED);
            return;
        }
        int icons = 3 * 18;
        int textW = this.panelW - 16 - icons - 6;
        // Name and health.
        g.text(this.font, PvpBotHud.fit(this.font, b.getName().getString(), 96), x + 8, y + 6, 0xFF7FE8FF);
        String hp = Math.round(b.getHealth()) + "/" + Math.round(b.getMaxHealth());
        PvpBotHud.bar(g, x + 8, y + 19, 96, 6, b.getHealth() / Math.max(1.0F, b.getMaxHealth()), PvpBotHud.HEALTH_BACK, PvpBotHud.HEALTH);
        g.text(this.font, hp, x + 8, y + 30, PvpBotHud.TEXT);
        // Mode, what it is doing, kit.
        int tx = x + 114;
        int tw = Math.max(40, textW - 106);
        PvpMode mode = b.viewMode();
        String modeLine = "Modus: " + mode.label;
        if (mode.hitsToWin > 0) {
            modeLine += "  ·  Treffer " + b.viewHits() + " : " + b.viewHitsTaken();
        }
        g.text(this.font, PvpBotHud.fit(this.font, modeLine, tw), tx, y + 6, PvpBotHud.ACCENT);
        boolean fighting = b.viewFlag(PvpBotEntity.FLAG_FIGHTING);
        g.text(this.font, PvpBotHud.fit(this.font, (b.viewFlag(PvpBotEntity.FLAG_DUEL) ? "Duell: " : "") + b.viewState(), tw), tx, y + 18,
                fighting ? PvpBotHud.BAD : PvpBotHud.TEXT);
        g.text(this.font, PvpBotHud.fit(this.font, "Kit: " + b.viewKit(), tw), tx, y + 30, PvpBotHud.MUTED);
        // What it holds and wears.
        EquipmentSlot[] slots = {EquipmentSlot.MAINHAND, EquipmentSlot.HEAD, EquipmentSlot.CHEST,
                EquipmentSlot.OFFHAND, EquipmentSlot.LEGS, EquipmentSlot.FEET};
        int ix = x + this.panelW - 6 - icons;
        for (int i = 0; i < slots.length; i++) {
            int sx = ix + (i % 3) * 18;
            int sy = y + 5 + (i / 3) * 18;
            g.fill(sx, sy, sx + 17, sy + 17, 0x40FFFFFF);
            ItemStack stack = b.getItemBySlot(slots[i]);
            if (!stack.isEmpty()) {
                g.item(stack, sx, sy);
            }
        }
    }

    /** Under the mode grid: what the mode under the mouse (or the chosen one) is about. */
    private void modeInfo(GuiGraphicsExtractor g) {
        PvpMode shown = this.bot != null ? this.bot.viewMode() : PvpMode.FREI;
        for (ModeButton mb : this.modeButtons) {
            if (mb.button().isHovered()) {
                shown = mb.mode();
            }
        }
        int x = this.left;
        int y = this.modeInfoTop;
        int h = this.modeInfoHeight;
        if (h == 0) {
            return;
        }
        g.fill(x, y, x + this.panelW, y + h, PvpBotHud.PANEL);
        g.outline(x, y, this.panelW, h, PvpBotHud.PANEL_EDGE);
        int w = this.panelW - 12;
        if (h < 42) {
            g.text(this.font, PvpBotHud.fit(this.font, shown.label + " – " + shown.description, w), x + 6, y + 4, PvpBotHud.ACCENT);
            return;
        }
        g.text(this.font, PvpBotHud.fit(this.font, shown.label + " – " + shown.description, w), x + 6, y + 5, PvpBotHud.ACCENT);
        g.text(this.font, PvpBotHud.fit(this.font, "Angriffe: " + shown.describeAttacks(), w), x + 6, y + 17, PvpBotHud.TEXT);
        g.text(this.font, PvpBotHud.fit(this.font, shown.describeRules(), w), x + 6, y + 29, PvpBotHud.MUTED);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }
}
