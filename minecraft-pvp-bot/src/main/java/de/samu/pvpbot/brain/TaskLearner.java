package de.samu.pvpbot.brain;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Learns by trying, like reinforcement learning: for every situation ("stuck underground in the
 * nether", "looking for the stronghold") it keeps an estimate of how well each strategy worked.
 * It picks with UCB1 - the best one so far, plus a bonus for strategies it has rarely tried, so it
 * keeps exploring until it knows. After each try the bot reports a reward from 0 (nothing gained)
 * to 1 (fully worked), and the estimate moves towards it. Saved as JSON next to the combat memory,
 * so what it learned carries over to the next game.
 */
public final class TaskLearner {
    private static final Logger LOGGER = LoggerFactory.getLogger("pvpbot");

    public static final TaskLearner INSTANCE = new TaskLearner();

    private static final class Arm {
        double value;
        int uses;
    }

    private final Map<String, Map<String, Arm>> table = new TreeMap<>();
    private final Random random = new Random();
    private @Nullable Path file;
    private boolean dirty;

    private TaskLearner() {
    }

    /** Picks a strategy for the situation (every option is tried once before the best one wins). */
    public synchronized String choose(String situation, List<String> options) {
        Map<String, Arm> row = this.table.computeIfAbsent(situation, k -> new TreeMap<>());
        List<String> untried = new ArrayList<>();
        int total = 0;
        for (String o : options) {
            Arm a = row.get(o);
            if (a == null || a.uses == 0) {
                untried.add(o);
            } else {
                total += a.uses;
            }
        }
        if (!untried.isEmpty()) {
            Collections.shuffle(untried, this.random);
            return untried.get(0);
        }
        String best = options.get(0);
        double bestScore = Double.NEGATIVE_INFINITY;
        for (String o : options) {
            Arm a = row.get(o);
            double score = a.value + 0.5 * Math.sqrt(2.0 * Math.log(total) / a.uses);
            if (score > bestScore) {
                bestScore = score;
                best = o;
            }
        }
        return best;
    }

    /** Feedback for a try: reward 0 (useless) .. 1 (worked). */
    public synchronized void learn(String situation, String option, double reward) {
        Arm a = this.table.computeIfAbsent(situation, k -> new TreeMap<>()).computeIfAbsent(option, k -> new Arm());
        a.uses++;
        double alpha = Math.max(0.1, 1.0 / a.uses);
        a.value += alpha * (Math.max(0.0, Math.min(1.0, reward)) - a.value);
        this.dirty = true;
    }

    /** The current estimate (for logs), or -1 if never tried. */
    public synchronized double estimate(String situation, String option) {
        Map<String, Arm> row = this.table.get(situation);
        Arm a = row == null ? null : row.get(option);
        return a == null ? -1.0 : a.value;
    }

    public synchronized List<String> summary() {
        List<String> lines = new ArrayList<>();
        for (Map.Entry<String, Map<String, Arm>> row : this.table.entrySet()) {
            StringBuilder sb = new StringBuilder(row.getKey()).append(":");
            row.getValue().entrySet().stream()
                    .sorted((x, y) -> Double.compare(y.getValue().value, x.getValue().value))
                    .forEach(e -> sb.append(String.format(" %s %.2f(%d)", e.getKey(), e.getValue().value, e.getValue().uses)));
            lines.add(sb.toString());
        }
        return lines;
    }

    public synchronized void load(Path file) {
        this.file = file;
        this.table.clear();
        if (!Files.exists(file)) {
            return;
        }
        try {
            JsonObject root = JsonParser.parseString(Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject();
            for (String situation : root.keySet()) {
                JsonObject options = root.getAsJsonObject(situation);
                Map<String, Arm> row = new TreeMap<>();
                for (String option : options.keySet()) {
                    JsonArray v = options.getAsJsonArray(option);
                    Arm a = new Arm();
                    a.value = v.get(0).getAsDouble();
                    a.uses = v.get(1).getAsInt();
                    row.put(option, a);
                }
                this.table.put(situation, row);
            }
            LOGGER.info("Aufgaben-Gedächtnis geladen: {} Situationen", this.table.size());
        } catch (IOException | RuntimeException e) {
            LOGGER.warn("Aufgaben-Gedächtnis konnte nicht gelesen werden, starte neu", e);
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
        for (Map.Entry<String, Map<String, Arm>> row : this.table.entrySet()) {
            JsonObject options = new JsonObject();
            for (Map.Entry<String, Arm> e : row.getValue().entrySet()) {
                JsonArray v = new JsonArray();
                v.add(Math.round(e.getValue().value * 1000.0) / 1000.0);
                v.add(e.getValue().uses);
                options.add(e.getKey(), v);
            }
            root.add(row.getKey(), options);
        }
        try {
            Files.createDirectories(this.file.getParent());
            Files.writeString(this.file, new GsonBuilder().setPrettyPrinting().create().toJson(root), StandardCharsets.UTF_8);
            this.dirty = false;
        } catch (IOException e) {
            LOGGER.warn("Aufgaben-Gedächtnis konnte nicht gespeichert werden", e);
        }
    }
}
