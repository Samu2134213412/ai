package de.samu.pvpbot.client;

import de.samu.pvpbot.brain.PvpMode;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElement;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import org.jspecify.annotations.Nullable;

/**
 * A small status box in the top left corner while your bot fights (or is in a PvP mode): its
 * health, what it is doing, and the hit score in Boxing. Only shows what the server sends about
 * your own bot. Can be switched off in the menu (key O → Verhalten).
 */
public final class PvpBotHud implements HudElement {
    static final int TEXT = 0xFFFFFFFF;
    static final int MUTED = 0xFFA8A8B8;
    static final int PANEL = 0xB0101018;
    static final int PANEL_EDGE = 0xFF3A3A4A;
    static final int HEALTH_BACK = 0xFF3A1212;
    static final int HEALTH = 0xFFE03C3C;
    static final int GOOD = 0xFF55E06A;
    static final int BAD = 0xFFE05555;
    static final int ACCENT = 0xFFFFD24A;

    private static boolean enabled = true;
    private static @Nullable PvpBotEntity current;

    public static boolean isEnabled() {
        return enabled;
    }

    public static void setEnabled(boolean on) {
        enabled = on;
        save();
    }

    /** Your nearest bot, as far as this client can see it. Looked up once per tick. */
    public static @Nullable PvpBotEntity bot() {
        return current != null && current.isAlive() && !current.isRemoved() ? current : null;
    }

    static void tick(Minecraft mc) {
        if (mc.player == null || mc.level == null) {
            current = null;
            return;
        }
        var me = mc.player.getUUID();
        PvpBotEntity best = null;
        double bestDist = Double.MAX_VALUE;
        for (PvpBotEntity b : mc.level.getEntitiesOfClass(PvpBotEntity.class, mc.player.getBoundingBox().inflate(160.0),
                e -> e.isAlive() && e.viewOwnedBy(me))) {
            double d = b.distanceToSqr(mc.player);
            if (d < bestDist) {
                best = b;
                bestDist = d;
            }
        }
        current = best;
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor g, DeltaTracker delta) {
        Minecraft mc = Minecraft.getInstance();
        PvpBotEntity bot = bot();
        if (!enabled || bot == null || mc.player == null || mc.gui.hud.isHidden() || mc.getDebugOverlay().showDebugScreen()
                || mc.gui.screen() instanceof PvpBotScreen) {
            return;
        }
        PvpMode mode = bot.viewMode();
        boolean busy = bot.viewFlag(PvpBotEntity.FLAG_FIGHTING) || bot.viewFlag(PvpBotEntity.FLAG_DUEL);
        if (!busy && mode == PvpMode.FREI) {
            return;
        }
        Font font = mc.font;
        boolean score = mode.hitsToWin > 0;
        int x = 4;
        int y = 4;
        int w = 200;
        int h = score ? 50 : 38;
        g.fill(x, y, x + w, y + h, PANEL);
        g.outline(x, y, w, h, PANEL_EDGE);
        g.text(font, fit(font, bot.getName().getString(), 130), x + 5, y + 4, 0xFF7FE8FF);
        String hp = Math.round(bot.getHealth()) + "/" + Math.round(bot.getMaxHealth());
        g.text(font, hp, x + w - 5 - font.width(hp), y + 4, TEXT);
        bar(g, x + 5, y + 15, w - 10, 5, bot.getHealth() / Math.max(1.0F, bot.getMaxHealth()), HEALTH_BACK, HEALTH);
        String line = (mode == PvpMode.FREI ? "" : mode.label + " · ") + bot.viewState();
        g.text(font, fit(font, line, w - 10), x + 5, y + 25, mode == PvpMode.FREI ? MUTED : ACCENT);
        if (score) {
            int mine = bot.viewHits();
            int yours = bot.viewHitsTaken();
            String s = "Bot " + mine + " : " + yours + " Du";
            g.text(font, s, x + 5, y + 37, mine >= yours ? GOOD : BAD);
            bar(g, x + 5 + font.width(s) + 6, y + 39, Math.max(10, w - 16 - font.width(s)), 4,
                    Math.max(mine, yours) / (float) mode.hitsToWin, 0xFF2A2A36, ACCENT);
        }
    }

    static void bar(GuiGraphicsExtractor g, int x, int y, int w, int h, float share, int back, int front) {
        g.fill(x, y, x + w, y + h, back);
        int filled = Math.round(w * Math.max(0.0F, Math.min(1.0F, share)));
        if (filled > 0) {
            g.fill(x, y, x + filled, y + h, front);
        }
    }

    /** Text without colour codes, cut to a width (with "…" if it was too long). */
    static String fit(Font font, String text, int width) {
        String plain = text.replaceAll("§.", "");
        if (font.width(plain) <= width) {
            return plain;
        }
        return font.plainSubstrByWidth(plain, Math.max(0, width - font.width("…"))) + "…";
    }

    // ------------------------------------------------------------------ setting

    private static Path file() {
        return FabricLoader.getInstance().getConfigDir().resolve("pvpbot-client.properties");
    }

    static void load() {
        Path file = file();
        if (!Files.exists(file)) {
            return;
        }
        Properties p = new Properties();
        try (Reader r = Files.newBufferedReader(file)) {
            p.load(r);
            enabled = Boolean.parseBoolean(p.getProperty("hud", "true"));
        } catch (IOException e) {
            // keep the default
        }
    }

    private static void save() {
        Properties p = new Properties();
        p.setProperty("hud", Boolean.toString(enabled));
        try {
            Files.createDirectories(file().getParent());
            try (Writer w = Files.newBufferedWriter(file())) {
                p.store(w, "PvP-Bot client settings");
            }
        } catch (IOException e) {
            // not important enough to bother the player
        }
    }
}
