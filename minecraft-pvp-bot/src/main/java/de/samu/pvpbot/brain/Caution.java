package de.samu.pvpbot.brain;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import net.minecraft.world.entity.LivingEntity;
import org.jspecify.annotations.Nullable;

/**
 * Learning from failure: which fights not to pick. For every foe (a mob type, or one player) and
 * the armor it wore itself, the bot remembers how its fights ended. Dying raises the odds it wants
 * before it fights that foe again with that armor (or worse) - below them it backs off instead.
 * Winning lowers them again, slowly. Better armor is a new question: with it, it dares again.
 * Stored as JSON in the config folder, shared by all bots, so a respawned bot still knows.
 */
public final class Caution {
    public static final Caution INSTANCE = new Caution();

    /** Armor classes, by armor points worn (see {@link FightOdds#armor}). */
    public static final String[] TIER_LABELS = {"ohne Rüstung", "leichter Rüstung", "Eisen-Rüstung", "Diamant-Rüstung", "Netherite-Rüstung"};
    private static final double MAX_NEED = 4.0;
    private static final double MIN_NEED = 0.6;

    public static final class Entry {
        /** Factor on the odds it wants before fighting (1 = the normal rule). */
        public double need = 1.0;
        public int wins;
        public int deaths;
    }

    private final Map<String, Entry> table = new TreeMap<>();
    private @Nullable Path file;
    private boolean dirty;

    private Caution() {
    }

    public static int tier(LivingEntity self) {
        double armor = FightOdds.armor(self);
        return armor < 5.0 ? 0 : armor < 13.0 ? 1 : armor < 18.0 ? 2 : armor < 25.5 ? 3 : 4;
    }

    private static String key(String foe, int tier) {
        return foe + "|" + tier;
    }

    /**
     * How much better than usual the odds must be against this foe with this armor: the worst lesson
     * learned with this armor or better (died in iron - then not in leather either).
     */
    public synchronized double need(String foe, int tier) {
        double need = 1.0;
        boolean known = false;
        for (int t = tier; t < TIER_LABELS.length; t++) {
            Entry e = this.table.get(key(foe, t));
            if (e != null) {
                known = true;
                need = Math.max(need, e.need);
            }
        }
        if (!known) {
            Entry same = this.table.get(key(foe, tier));
            return same != null ? same.need : 1.0;
        }
        // (A foe it has only ever beaten with this armor may be fought a little more boldly.)
        Entry same = this.table.get(key(foe, tier));
        return need > 1.0 ? need : same != null ? same.need : 1.0;
    }

    /** It died against this foe wearing this armor: next time it wants clearly better odds. */
    public synchronized double learnDeath(String foe, int tier) {
        Entry e = this.table.computeIfAbsent(key(foe, tier), k -> new Entry());
        e.deaths++;
        e.need = Math.min(MAX_NEED, Math.max(1.0, e.need) * 1.6);
        this.dirty = true;
        return e.need;
    }

    /** It beat this foe wearing this armor: a little bolder next time. */
    public synchronized void learnWin(String foe, int tier) {
        Entry e = this.table.computeIfAbsent(key(foe, tier), k -> new Entry());
        e.wins++;
        e.need = Math.max(MIN_NEED, e.need * 0.92);
        this.dirty = true;
    }

    public synchronized List<String> summary(int maxLines) {
        List<String> lines = new ArrayList<>();
        for (Map.Entry<String, Entry> row : this.table.entrySet()) {
            int bar = row.getKey().lastIndexOf('|');
            String foe = row.getKey().substring(0, bar);
            int tier = Math.max(0, Math.min(TIER_LABELS.length - 1, Integer.parseInt(row.getKey().substring(bar + 1))));
            Entry e = row.getValue();
            String name = foe.startsWith("p_") ? "Spieler " + foe.substring(2) : foe;
            String verdict = e.need >= 2.5 ? "§cweicht aus" : e.need > 1.05 ? "§evorsichtig" : e.need < 0.95 ? "§amutig" : "§fnormal";
            lines.add(String.format("§e%s §7mit %s: %s §8(%d gewonnen, %d† · braucht %.1f× Übermacht)",
                    name, TIER_LABELS[tier], verdict, e.wins, e.deaths, e.need));
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
            for (String key : root.keySet()) {
                JsonObject o = root.getAsJsonObject(key);
                Entry e = new Entry();
                e.need = o.get("need").getAsDouble();
                e.wins = o.get("wins").getAsInt();
                e.deaths = o.get("deaths").getAsInt();
                if (key.lastIndexOf('|') > 0) {
                    this.table.put(key, e);
                }
            }
        } catch (IOException | RuntimeException e) {
            this.table.clear();
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
        JsonObject root = new JsonObject();
        for (Map.Entry<String, Entry> row : this.table.entrySet()) {
            JsonObject o = new JsonObject();
            o.addProperty("need", Math.round(row.getValue().need * 100.0) / 100.0);
            o.addProperty("wins", row.getValue().wins);
            o.addProperty("deaths", row.getValue().deaths);
            root.add(row.getKey(), o);
        }
        try {
            Files.createDirectories(this.file.getParent());
            Files.writeString(this.file, new GsonBuilder().setPrettyPrinting().create().toJson(root), StandardCharsets.UTF_8);
            this.dirty = false;
        } catch (IOException e) {
            // tried; the next save may work
        }
    }
}
