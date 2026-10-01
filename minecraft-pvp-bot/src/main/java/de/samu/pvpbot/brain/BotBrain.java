package de.samu.pvpbot.brain;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The shared, persistent memory of all PvP bots: for every combat situation it remembers how well
 * each attack pattern worked and picks patterns accordingly (mostly the best one, sometimes a random
 * one to keep learning). Stored as JSON in the config folder so it survives restarts and new worlds.
 */
public final class BotBrain {

    public enum Pattern {
        MACE_MELEE("Mace-Nahkampf", true),
        SPEAR_KITE("Speer-Stiche im Vorbeirennen", true),
        WIND_SMASH("Windladungs-Smash", false),
        SPEAR_CHARGE("Speer-Ansturm", false),
        ELYTRA_DIVE("Elytra-Mace-Sturzflug", false),
        ELYTRA_LANCE("Elytra-Speerflug", false),
        BLADE_MELEE("Schwert/Axt-Nahkampf", true),
        BOW_SNIPE("Bogenschüsse", true),
        WIND_LUNGE_SMASH("Windladung → Lunge → Mace", false);

        public final String label;
        public final boolean melee;

        Pattern(String label, boolean melee) {
            this.label = label;
            this.melee = melee;
        }

        /** Short command name, e.g. for /pvpbot trick kombo. */
        public String trickName() {
            return switch (this) {
                case MACE_MELEE -> "mace";
                case SPEAR_KITE -> "stiche";
                case WIND_SMASH -> "smash";
                case SPEAR_CHARGE -> "ansturm";
                case ELYTRA_DIVE -> "sturzflug";
                case ELYTRA_LANCE -> "speerflug";
                case BLADE_MELEE -> "schwert";
                case BOW_SNIPE -> "bogen";
                case WIND_LUNGE_SMASH -> "kombo";
            };
        }

        public static @Nullable Pattern byTrickName(String name) {
            for (Pattern p : values()) {
                if (p.trickName().equalsIgnoreCase(name)) {
                    return p;
                }
            }
            return null;
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

    /**
     * One combat situation: surroundings, distance, target, the kit the bot is fighting with, and
     * what it fights ({@code foe}: the mob type like "zombie", "player", or "*" for any - what it
     * learned against all of them together, the fallback for a mob type it has not fought yet).
     */
    public record Context(Env env, Range range, boolean targetInAir, boolean targetIsPlayer, String kit, String foe) {
        /** The kit of the original mace/spear/elytra loadout, used for memories saved before kits existed. */
        public static final String DEFAULT_KIT = "MSEC";
        public static final String ANY = "*";

        public Context(Env env, Range range, boolean targetInAir, boolean targetIsPlayer, String kit) {
            this(env, range, targetInAir, targetIsPlayer, kit, ANY);
        }

        /** The foe key of an entity: "player" or the mob type ("zombie", "blaze", ...). */
        public static String foeOf(net.minecraft.world.entity.Entity e) {
            if (e instanceof net.minecraft.world.entity.player.Player) {
                return "player";
            }
            return net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath();
        }

        /** The same situation against any foe (what it learned in general). */
        public Context general() {
            return this.foe.equals(ANY) ? this : new Context(env, range, targetInAir, targetIsPlayer, kit, ANY);
        }

        public String key() {
            return env.name() + "|" + range.name() + "|" + (targetInAir ? "AIR" : "GROUND") + "|" + (targetIsPlayer ? "PLAYER" : "MOB") + "|" + kit
                    + (foe.equals(ANY) ? "" : "|" + foe);
        }

        public String foeLabel() {
            if (foe.equals(ANY)) {
                return targetIsPlayer ? "Spieler" : "Mobs";
            }
            if (foe.equals("player")) {
                return "Spieler";
            }
            var type = net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getValue(net.minecraft.resources.Identifier.withDefaultNamespace(foe));
            return type == null ? foe : type.getDescription().getString();
        }

        public String describe() {
            return env.label + ", " + range.label + ", Ziel " + (targetInAir ? "in der Luft" : "am Boden")
                    + ", gegen " + foeLabel() + ", Kit " + Kit.describeSignature(kit);
        }

        static @Nullable Context parse(String key) {
            String[] p = key.split("\\|");
            if (p.length < 4 || p.length > 6) {
                return null;
            }
            try {
                return new Context(Env.valueOf(p[0]), Range.valueOf(p[1]), p[2].equals("AIR"), p[3].equals("PLAYER"),
                        p.length >= 5 ? p[4] : DEFAULT_KIT, p.length == 6 ? p[5] : ANY);
            } catch (IllegalArgumentException e) {
                return null;
            }
        }
    }

    public static final class Stat {
        public double value;
        public int uses;
        public double best = Double.NEGATIVE_INFINITY;
        /** Fights this pattern finished off (the target died from it). */
        public int kills;
    }

    /** How much a kill counts on top of the damage (the attack that kills is the one to remember). */
    public static final double KILL_BONUS = 12.0;

    /** What happened when a result was learned; used for chat feedback. */
    public record Lesson(boolean newFavourite, boolean flop, double score, double value) {
    }

    private static final Logger LOGGER = LoggerFactory.getLogger("pvpbot");

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
                case WIND_LUNGE_SMASH -> 4.0;
                case MACE_MELEE, SPEAR_KITE, BLADE_MELEE -> 1.5;
                case BOW_SNIPE -> -3.0;
                case SPEAR_CHARGE -> 1.0;
                default -> -2.0;
            };
            case MID -> v += switch (p) {
                case WIND_SMASH, SPEAR_CHARGE -> 3.0;
                case WIND_LUNGE_SMASH -> 6.0;
                case ELYTRA_DIVE, BOW_SNIPE -> 1.0;
                default -> 0.0;
            };
            case FAR -> v += switch (p) {
                case ELYTRA_DIVE -> 4.0;
                case BOW_SNIPE -> 3.0;
                case ELYTRA_LANCE, SPEAR_CHARGE -> 2.0;
                case MACE_MELEE, SPEAR_KITE, BLADE_MELEE -> -2.0;
                default -> 0.0;
            };
        }
        if (ctx.targetInAir()) {
            v += switch (p) {
                case ELYTRA_LANCE -> 4.0;
                case BOW_SNIPE -> 2.0;
                case SPEAR_KITE -> 1.0;
                case ELYTRA_DIVE, SPEAR_CHARGE -> -2.0;
                default -> 0.0;
            };
        }
        if (ctx.env() == Env.CAVE && (p == Pattern.WIND_SMASH || p == Pattern.WIND_LUNGE_SMASH)) {
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

    /**
     * What a pattern is worth against this foe: what it learned against exactly this mob type,
     * blended with what it learned against all of them (until it has fought this type a few times).
     */
    public synchronized double value(Context ctx, Pattern p) {
        Stat specific = this.stat(ctx, p);
        if (ctx.foe().equals(Context.ANY)) {
            return specific.value;
        }
        double general = this.stat(ctx.general(), p).value;
        int n = specific.uses;
        return (n * specific.value + 2.0 * general) / (n + 2.0);
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
        double max = options.stream().mapToDouble(p -> value(ctx, p)).max().orElse(0.0);
        double[] weights = new double[options.size()];
        double sum = 0.0;
        for (int i = 0; i < options.size(); i++) {
            weights[i] = Math.exp((value(ctx, options.get(i)) - max) / temperature);
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
                .max(Comparator.comparingDouble(e -> value(ctx, e.getKey()))).map(Map.Entry::getKey).orElse(null);
    }

    /** Feeds back how well an attempt went (higher = better). */
    public synchronized Lesson learn(Context ctx, Pattern p, double score) {
        return this.learn(ctx, p, score, false);
    }

    /**
     * Feeds back an attempt; {@code killed}: the target died from it - then it counts as good
     * against that mob type in particular. Also updates what it knows against any foe.
     */
    public synchronized Lesson learn(Context ctx, Pattern p, double score, boolean killed) {
        Pattern before = favourite(ctx);
        Stat s = this.update(ctx, p, score, killed);
        if (!ctx.foe().equals(Context.ANY)) {
            this.update(ctx.general(), p, score, killed);
        }
        this.dirty = true;
        Pattern after = favourite(ctx);
        return new Lesson(after == p && before != p && score > 0.0, score <= 0.0, score, value(ctx, p));
    }

    private Stat update(Context ctx, Pattern p, double score, boolean killed) {
        Stat s = stat(ctx, p);
        double alpha = s.uses == 0 ? 0.4 : Math.max(0.15, 1.0 / (s.uses + 1));
        s.value += alpha * (score - s.value);
        s.uses++;
        s.best = Math.max(s.best, score);
        if (killed) {
            s.kills++;
        }
        return s;
    }

    /**
     * The target died shortly after the attempt ended (an arrow still in the air, burning, a fall
     * after the hit): that attack still gets the credit for the kill.
     */
    public synchronized void creditKill(Context ctx, Pattern p) {
        this.learn(ctx, p, KILL_BONUS, true);
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
                    .forEach(e -> sb.append(String.format(" §f%s §%s%.1f§8(%d%s)", e.getKey().label,
                            e.getValue().value > 0 ? "a" : "c", e.getValue().value, e.getValue().uses,
                            e.getValue().kills > 0 ? ", " + e.getValue().kills + " Kills" : "")));
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
                        s.kills = o.has("kills") ? o.get("kills").getAsInt() : 0;
                        row.put(Pattern.valueOf(name), s);
                    } catch (RuntimeException ignored) {
                        // unknown pattern from another version
                    }
                }
                Context ctx = Context.parse(key);
                // Older memories had no kit in the key: they belong to the default kit.
                this.table.put(ctx != null ? ctx.key() : key, row);
            }
            LOGGER.info("PvP-Bot-Gedächtnis geladen: {} Situationen", this.table.size());
        } catch (IOException | RuntimeException e) {
            LOGGER.warn("PvP-Bot-Gedächtnis konnte nicht gelesen werden, starte neu", e);
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
                if (e.getValue().kills > 0) {
                    o.addProperty("kills", e.getValue().kills);
                }
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
            LOGGER.warn("PvP-Bot-Gedächtnis konnte nicht gespeichert werden", e);
        }
    }
}
