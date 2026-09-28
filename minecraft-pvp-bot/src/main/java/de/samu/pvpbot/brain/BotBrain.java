package de.samu.pvpbot.brain;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import de.samu.pvpbot.PvpBotMod;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import net.minecraft.util.RandomSource;
import org.jspecify.annotations.Nullable;

/**
 * The shared, persistent memory of all PvP bots: for every combat situation it remembers how well
 * each attack pattern worked and picks patterns accordingly (mostly the best one, sometimes a random
 * one to keep learning). Stored as JSON in the config folder so it survives restarts and new worlds.
 */
public final class BotBrain {

    public enum Pattern {
        MACE_MELEE("Mace-Nahkampf", true),
        SPEAR_KITE("Speer-Stiche", true),
        WIND_SMASH("Windladungs-Smash", false),
        SPEAR_CHARGE("Speer-Ansturm", false),
        ELYTRA_DIVE("Elytra-Mace-Sturzflug", false),
        ELYTRA_LANCE("Elytra-Speerflug", false);

        public final String label;
        public final boolean melee;

        Pattern(String label, boolean melee) {
            this.label = label;
            this.melee = melee;
        }

        public boolean aerial() {
            return this == ELYTRA_DIVE || this == ELYTRA_LANCE;
        }
    }

    public enum Env { OPEN("im Freien"), CAVE("in Höhlen"), WATER("im Wasser");
        final String label;
        Env(String label) { this.label = label; }
    }

    public enum Range { CLOSE("nah"), MID("mittel"), FAR("fern");
        final String label;
        Range(String label) { this.label = label; }

        public static Range of(double horizontalDistance) {
            return horizontalDistance < 4.0 ? CLOSE : horizontalDistance < 12.0 ? MID : FAR;
        }
    }

    /** One combat situation. */
    public record Context(Env env, Range range, boolean targetInAir, boolean targetIsPlayer) {
        public String key() {
            return env.name() + "|" + range.name() + "|" + (targetInAir ? "AIR" : "GROUND") + "|" + (targetIsPlayer ? "PLAYER" : "MOB");
        }

        public String describe() {
            return env.label + ", " + range.label + ", Ziel " + (targetInAir ? "in der Luft" : "am Boden")
                    + ", gegen " + (targetIsPlayer ? "Spieler" : "Mobs");
        }

        static @Nullable Context parse(String key) {
            String[] p = key.split("\\|");
            if (p.length != 4) {
                return null;
            }
            try {
                return new Context(Env.valueOf(p[0]), Range.valueOf(p[1]), p[2].equals("AIR"), p[3].equals("PLAYER"));
            } catch (IllegalArgumentException e) {
                return null;
            }
        }
    }

    public static final class Stat {
        public double value;
        public int uses;
        public double best = Double.NEGATIVE_INFINITY;
    }

    /** What happened when a result was learned; used for chat feedback. */
    public record Lesson(boolean newFavourite, boolean flop, double score, double value) {
    }

    public static final BotBrain INSTANCE = new BotBrain();

    private final Map<String, EnumMap<Pattern, Stat>> table = new TreeMap<>();
    private @Nullable Path file;
    private boolean dirty;

    private BotBrain() {
    }

    // ------------------------------------------------------------------ decisions

    /** Starting guesses before anything was learned, so the bot fights sensibly from the start. */
    static double prior(Context ctx, Pattern p) {
        double v = 5.0;
        switch (ctx.range()) {
            case CLOSE -> v += switch (p) {
                case WIND_SMASH -> 3.0;
                case MACE_MELEE, SPEAR_KITE -> 1.5;
                case SPEAR_CHARGE -> -1.0;
                default -> -2.0;
            };
            case MID -> v += switch (p) {
                case WIND_SMASH -> 3.0;
                case SPEAR_CHARGE -> 2.0;
                case ELYTRA_DIVE -> 1.0;
                default -> 0.0;
            };
            case FAR -> v += switch (p) {
                case ELYTRA_DIVE -> 4.0;
                case ELYTRA_LANCE, SPEAR_CHARGE -> 2.0;
                case MACE_MELEE, SPEAR_KITE -> -2.0;
                default -> 0.0;
            };
        }
        if (ctx.targetInAir()) {
            v += switch (p) {
                case ELYTRA_LANCE -> 4.0;
                case SPEAR_KITE -> 1.0;
                case ELYTRA_DIVE, SPEAR_CHARGE -> -2.0;
                default -> 0.0;
            };
        }
        if (ctx.env() == Env.CAVE && p == Pattern.WIND_SMASH) {
            v -= 1.0;
        }
        return v;
    }

    public synchronized Stat stat(Context ctx, Pattern p) {
        EnumMap<Pattern, Stat> row = this.table.computeIfAbsent(ctx.key(), k -> new EnumMap<>(Pattern.class));
        return row.computeIfAbsent(p, k -> {
            Stat s = new Stat();
            s.value = prior(ctx, p);
            return s;
        });
    }

    private synchronized int experience(Context ctx) {
        EnumMap<Pattern, Stat> row = this.table.get(ctx.key());
        return row == null ? 0 : row.values().stream().mapToInt(s -> s.uses).sum();
    }

    /**
     * Picks a pattern: with a small (and, with experience, shrinking) chance a random one to keep
     * exploring, otherwise a weighted choice that strongly prefers what worked best so far.
     */
    public Pattern choose(Context ctx, List<Pattern> options, RandomSource random) {
        if (options.size() == 1) {
            return options.get(0);
        }
        double explore = 0.08 + 0.35 / (1.0 + experience(ctx) / 4.0);
        if (random.nextDouble() < explore) {
            return options.get(random.nextInt(options.size()));
        }
        double temperature = 2.5;
        double max = options.stream().mapToDouble(p -> stat(ctx, p).value).max().orElse(0.0);
        double[] weights = new double[options.size()];
        double sum = 0.0;
        for (int i = 0; i < options.size(); i++) {
            weights[i] = Math.exp((stat(ctx, options.get(i)).value - max) / temperature);
            sum += weights[i];
        }
        double roll = random.nextDouble() * sum;
        for (int i = 0; i < options.size(); i++) {
            roll -= weights[i];
            if (roll <= 0.0) {
                return options.get(i);
            }
        }
        return options.get(options.size() - 1);
    }

    public synchronized @Nullable Pattern favourite(Context ctx) {
        EnumMap<Pattern, Stat> row = this.table.get(ctx.key());
        if (row == null) {
            return null;
        }
        return row.entrySet().stream().filter(e -> e.getValue().uses > 0)
                .max(Comparator.comparingDouble(e -> e.getValue().value)).map(Map.Entry::getKey).orElse(null);
    }

    /** Feeds back how well an attempt went (higher = better). */
    public synchronized Lesson learn(Context ctx, Pattern p, double score) {
        Pattern before = favourite(ctx);
        Stat s = stat(ctx, p);
        double alpha = s.uses == 0 ? 0.5 : Math.max(0.2, 1.0 / (s.uses + 1));
        s.value += alpha * (score - s.value);
        s.uses++;
        s.best = Math.max(s.best, score);
        this.dirty = true;
        Pattern after = favourite(ctx);
        return new Lesson(after == p && before != p, score <= 0.0, score, s.value);
    }

    // ------------------------------------------------------------------ display

    public synchronized List<String> summary(int maxLines) {
        List<String> lines = new ArrayList<>();
        List<Map.Entry<String, EnumMap<Pattern, Stat>>> rows = new ArrayList<>(this.table.entrySet());
        rows.sort(Comparator.comparingInt((Map.Entry<String, EnumMap<Pattern, Stat>> e) ->
                e.getValue().values().stream().mapToInt(s -> s.uses).sum()).reversed());
        for (Map.Entry<String, EnumMap<Pattern, Stat>> row : rows) {
            Context ctx = Context.parse(row.getKey());
            int uses = row.getValue().values().stream().mapToInt(s -> s.uses).sum();
            if (ctx == null || uses == 0) {
                continue;
            }
            StringBuilder sb = new StringBuilder("§e" + ctx.describe() + " §7(" + uses + "x):");
            row.getValue().entrySet().stream().filter(e -> e.getValue().uses > 0)
                    .sorted(Comparator.comparingDouble((Map.Entry<Pattern, Stat> e) -> e.getValue().value).reversed())
                    .forEach(e -> sb.append(String.format(" §f%s §%s%.1f§8(%d)", e.getKey().label,
                            e.getValue().value > 0 ? "a" : "c", e.getValue().value, e.getValue().uses)));
            lines.add(sb.toString());
            if (lines.size() >= maxLines) {
                break;
            }
        }
        return lines;
    }

    public synchronized void reset() {
        this.table.clear();
        this.dirty = true;
        this.save();
    }

    // ------------------------------------------------------------------ persistence

    public synchronized void load(Path file) {
        this.file = file;
        this.table.clear();
        if (!Files.exists(file)) {
            return;
        }
        try {
            JsonObject root = JsonParser.parseString(Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject();
            JsonObject contexts = root.getAsJsonObject("contexts");
            for (String key : contexts.keySet()) {
                EnumMap<Pattern, Stat> row = new EnumMap<>(Pattern.class);
                JsonObject patterns = contexts.getAsJsonObject(key);
                for (String name : patterns.keySet()) {
                    try {
                        JsonObject o = patterns.getAsJsonObject(name);
                        Stat s = new Stat();
                        s.value = o.get("value").getAsDouble();
                        s.uses = o.get("uses").getAsInt();
                        s.best = o.has("best") ? o.get("best").getAsDouble() : s.value;
                        row.put(Pattern.valueOf(name), s);
                    } catch (RuntimeException ignored) {
                        // unknown pattern from another version
                    }
                }
                this.table.put(key, row);
            }
            PvpBotMod.LOGGER.info("PvP-Bot-Gedächtnis geladen: {} Situationen", this.table.size());
        } catch (IOException | RuntimeException e) {
            PvpBotMod.LOGGER.warn("PvP-Bot-Gedächtnis konnte nicht gelesen werden, starte neu", e);
        }
    }

    public synchronized void saveIfDirty() {
        if (this.dirty) {
            this.save();
        }
    }

    public synchronized void save() {
        if (this.file == null) {
            return;
        }
        JsonObject contexts = new JsonObject();
        for (Map.Entry<String, EnumMap<Pattern, Stat>> row : this.table.entrySet()) {
            JsonObject patterns = new JsonObject();
            for (Map.Entry<Pattern, Stat> e : row.getValue().entrySet()) {
                if (e.getValue().uses == 0) {
                    continue;
                }
                JsonObject o = new JsonObject();
                o.addProperty("value", Math.round(e.getValue().value * 100.0) / 100.0);
                o.addProperty("uses", e.getValue().uses);
                o.addProperty("best", Math.round(e.getValue().best * 100.0) / 100.0);
                patterns.add(e.getKey().name(), o);
            }
            if (!patterns.isEmpty()) {
                contexts.add(row.getKey(), patterns);
            }
        }
        JsonObject root = new JsonObject();
        root.addProperty("version", 1);
        root.add("contexts", contexts);
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        try {
            Files.createDirectories(this.file.getParent());
            Files.writeString(this.file, gson.toJson(root), StandardCharsets.UTF_8);
            this.dirty = false;
        } catch (IOException e) {
            PvpBotMod.LOGGER.warn("PvP-Bot-Gedächtnis konnte nicht gespeichert werden", e);
        }
    }
}
