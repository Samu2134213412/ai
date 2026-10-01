package de.samu.pvpbot.autopilot;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.core.JsonValue;
import com.anthropic.errors.AnthropicServiceException;
import com.anthropic.models.messages.ContentBlock;
import com.anthropic.models.messages.ContentBlockParam;
import com.anthropic.models.messages.Message;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.MessageParam;
import com.anthropic.models.messages.OutputConfig;
import com.anthropic.models.messages.Tool;
import com.anthropic.models.messages.ToolResultBlockParam;
import com.anthropic.models.messages.ToolUseBlock;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import org.jspecify.annotations.Nullable;

/**
 * Talk to your autopilot: "@auto hol mir 10 Eisen" in the chat (or {@code /autopilot ki frag ...}).
 * Claude answers and sets the autopilot's goals with tools. The message stays on this computer -
 * it is not sent to the server chat. The API key ({@code /autopilot ki key <key>}) is stored in
 * {@code config/pvpbot-autopilot-ai.json} and never shown or logged.
 */
public final class AutopilotAi {
    public static final AutopilotAi INSTANCE = new AutopilotAi();

    private static final String DEFAULT_MODEL = "claude-opus-5-5";
    private static final int MAX_HISTORY = 16;
    private static final int MAX_TOOL_ROUNDS = 5;

    private static final class Config {
        @Nullable String key;
        String model = DEFAULT_MODEL;
    }

    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    private final ExecutorService pool = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "pvpbot-autopilot-ai");
        t.setDaemon(true);
        return t;
    });
    private final List<MessageParam> history = new ArrayList<>();
    private final AtomicBoolean busy = new AtomicBoolean();
    private Config config = new Config();
    private @Nullable Path file;
    private @Nullable AnthropicClient client;
    private @Nullable String clientKey;

    private AutopilotAi() {
    }

    // ------------------------------------------------------------------ config

    public synchronized void load(Path path) {
        this.file = path;
        try {
            if (Files.exists(path)) {
                Config c = this.gson.fromJson(Files.readString(path), Config.class);
                if (c != null) {
                    this.config = c;
                    if (this.config.model == null || this.config.model.isBlank()) {
                        this.config.model = DEFAULT_MODEL;
                    }
                }
            }
        } catch (Exception e) {
            Autopilot.LOGGER.warn("pvpbot-autopilot-ai.json nicht lesbar: {}", e.getMessage());
        }
    }

    private synchronized void save() {
        if (this.file == null) {
            return;
        }
        try {
            Files.createDirectories(this.file.getParent());
            Files.writeString(this.file, this.gson.toJson(this.config));
        } catch (Exception e) {
            Autopilot.LOGGER.warn("pvpbot-autopilot-ai.json nicht speicherbar: {}", e.getMessage());
        }
    }

    public synchronized void setKey(@Nullable String key) {
        this.config.key = key == null || key.isBlank() ? null : key.trim();
        this.save();
    }

    public synchronized boolean hasKey() {
        return this.config.key != null;
    }

    public synchronized String model() {
        return this.config.model;
    }

    private synchronized @Nullable String key() {
        return this.config.key;
    }

    private synchronized AnthropicClient client(String key) {
        if (this.client == null || !key.equals(this.clientKey)) {
            this.client = AnthropicOkHttpClient.builder().apiKey(key).build();
            this.clientKey = key;
        }
        return this.client;
    }

    // ------------------------------------------------------------------ chat

    /** A chat line typed by the player: "@auto ..." / "@autopilot ..." / "@ki ..." is for us. Returns true if handled. */
    public boolean onChat(Minecraft mc, String text) {
        String msg = text.strip();
        String lower = msg.toLowerCase(Locale.ROOT);
        for (String prefix : new String[]{"@autopilot", "@auto", "@ki"}) {
            if (lower.startsWith(prefix) && (lower.length() == prefix.length() || !Character.isLetterOrDigit(lower.charAt(prefix.length())))) {
                this.ask(mc, msg.substring(prefix.length()).replaceFirst("^[\\s,:]+", ""));
                return true;
            }
        }
        return false;
    }

    public void ask(Minecraft mc, String words) {
        if (words.isBlank() || mc.player == null) {
            return;
        }
        Autopilot ap = Autopilot.INSTANCE;
        mc.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("§7Du → Autopilot: §f" + words));
        String key = this.key();
        if (key == null) {
            ap.say(mc, "§cDie KI braucht erst deinen API-Key: §f/autopilot ki key <dein-anthropic-key>");
            return;
        }
        if (!this.busy.compareAndSet(false, true)) {
            ap.say(mc, "§7denkt noch nach …");
            return;
        }
        String situation = situation(mc, mc.player);
        String model = this.model();
        this.pool.execute(() -> {
            try {
                String answer = this.talk(mc, key, model, situation, words);
                mc.execute(() -> {
                    if (!answer.isBlank()) {
                        ap.say(mc, "§b" + answer);
                    }
                });
            } catch (AnthropicServiceException e) {
                String why = e.statusCode() == 401 ? "API-Key ungültig (/autopilot ki key …)"
                        : e.statusCode() == 429 ? "zu viele Anfragen, gleich nochmal"
                        : "API-Fehler " + e.statusCode();
                mc.execute(() -> ap.say(mc, "§c[KI] " + why));
            } catch (Exception e) {
                Autopilot.LOGGER.warn("KI-Chat fehlgeschlagen: {}", e.getClass().getSimpleName());
                mc.execute(() -> ap.say(mc, "§c[KI] keine Verbindung zur KI"));
            } finally {
                this.busy.set(false);
            }
        });
    }

    /** What the player (and so the autopilot) knows right now - only its own state and what it sees. */
    private static String situation(Minecraft mc, LocalPlayer p) {
        Autopilot ap = Autopilot.INSTANCE;
        var dim = p.level().dimension();
        String dimName = dim == net.minecraft.world.level.Level.NETHER ? "Nether" : dim == net.minecraft.world.level.Level.END ? "End" : "Oberwelt";
        StringBuilder inv = new StringBuilder();
        Map<String, Integer> counts = new java.util.TreeMap<>();
        for (ItemStack st : p.getInventory().getNonEquipmentItems()) {
            if (!st.isEmpty()) {
                counts.merge(st.getHoverName().getString(), st.getCount(), Integer::sum);
            }
        }
        counts.forEach((k, v) -> inv.append(v).append("x ").append(k).append(", "));
        StringBuilder seen = new StringBuilder();
        for (Player other : mc.level.players()) {
            if (other != p && p.hasLineOfSight(other) && other.distanceTo(p) < 64.0F) {
                seen.append(other.getName().getString()).append(" (").append((int) other.distanceTo(p)).append(" Blöcke), ");
            }
        }
        AutopilotSettings st = AutopilotSettings.INSTANCE;
        String order = ap.currentOrder();
        return "Spieler: " + p.getName().getString()
                + "\nLeben: " + (int) p.getHealth() + "/" + (int) p.getMaxHealth() + ", Hunger: " + p.getFoodData().getFoodLevel() + "/20"
                + "\nDimension: " + dimName + ", Position " + p.blockPosition().toShortString()
                + "\nAutopilot: " + (ap.isEnabled() ? "an" : "aus") + ", Ziel: " + ap.describeTarget()
                + "\nTut gerade: " + ap.status().replaceAll("§.", "")
                + "\nAuftrag: " + (order == null ? "keiner" : order)
                + "\nZuhause: " + (st.homeSet ? st.homeX + " " + st.homeY + " " + st.homeZ : "keins")
                + "\nSichtbare Spieler: " + (seen.isEmpty() ? "keine" : seen)
                + "\nInventar: " + (inv.isEmpty() ? "leer" : inv);
    }

    private static final String SYSTEM = """
            Du bist der Autopilot eines Minecraft-Spielers: du steuerst seinen eigenen Account wie ein Mensch \
            (Tasten, Maus, Inventar-Klicks). Der Spieler schreibt dir; nur er sieht deine Antwort. Antworte kurz \
            (höchstens 2 Sätze), locker, in seiner Sprache, ohne Markdown. Wenn er etwas will, benutze die Werkzeuge \
            (set_mode, gather, attack_player, home), statt nur zu reden. Du spielst fair: du weißt nur, was in deinem \
            Zustand steht und was du siehst, und behauptest nichts anderes.""";

    private String talk(Minecraft mc, String key, String model, String situation, String words) throws Exception {
        List<MessageParam> convo;
        synchronized (this.history) {
            convo = new ArrayList<>(this.history);
        }
        int start = convo.size();
        convo.add(MessageParam.builder().role(MessageParam.Role.USER).content(words).build());
        AnthropicClient client = this.client(key);
        StringBuilder answer = new StringBuilder();
        for (int round = 0; round < MAX_TOOL_ROUNDS; round++) {
            MessageCreateParams params = MessageCreateParams.builder()
                    .model(model)
                    .maxTokens(4000L)
                    .system(SYSTEM + "\n\nDein Zustand gerade:\n" + situation)
                    .outputConfig(OutputConfig.builder().effort(OutputConfig.Effort.LOW).build())
                    .tools(TOOLS.stream().map(com.anthropic.models.messages.ToolUnion::ofTool).toList())
                    .messages(convo)
                    // If the model declines, the server retries on the recommended fallback model.
                    .putAdditionalHeader("anthropic-beta", "server-side-fallback-2026-07-01")
                    .putAdditionalBodyProperty("fallbacks", JsonValue.from("default"))
                    .build();
            Message response = client.messages().create(params);
            String stop = response.stopReason().map(Object::toString).orElse("");
            if (stop.equals("refusal")) {
                return "Dazu sag ich lieber nichts.";
            }
            answer.setLength(0);
            List<ContentBlockParam> results = new ArrayList<>();
            for (ContentBlock block : response.content()) {
                block.text().ifPresent(t -> answer.append(t.text()));
                if (block.toolUse().isPresent()) {
                    ToolUseBlock use = block.toolUse().get();
                    String result = mc.submit(() -> runTool(mc, use)).join();
                    results.add(ContentBlockParam.ofToolResult(ToolResultBlockParam.builder()
                            .toolUseId(use.id()).content(result).build()));
                }
            }
            convo.add(response.toParam());
            if (results.isEmpty() || !stop.equals("tool_use")) {
                break;
            }
            convo.add(MessageParam.builder().role(MessageParam.Role.USER).contentOfBlockParams(results).build());
        }
        // Remember only the plain talk (the words and the final answer), not the tool calls.
        synchronized (this.history) {
            List<MessageParam> kept = new ArrayList<>(convo.subList(0, start));
            kept.add(MessageParam.builder().role(MessageParam.Role.USER).content(words).build());
            kept.add(MessageParam.builder().role(MessageParam.Role.ASSISTANT)
                    .content(answer.isEmpty() ? "(erledigt)" : answer.toString()).build());
            while (kept.size() > MAX_HISTORY) {
                kept.subList(0, 2).clear();
            }
            this.history.clear();
            this.history.addAll(kept);
        }
        return answer.toString().strip();
    }

    // ------------------------------------------------------------------ tools (the AI sets the goals)

    private static final List<Tool> TOOLS = List.of(
            tool("set_mode", "Legt fest, was der Autopilot tut. voll = volle Kontrolle (spielt selbst: Ausrüstung bauen, "
                            + "kämpfen, essen, Beute); monster = kämpft gegen Monster in der Nähe; spieler = kämpft gegen den "
                            + "nächsten Spieler; aus = Autopilot aus, der Spieler steuert selbst; stop = Ziel und Auftrag abbrechen.",
                    Map.of("mode", Map.of("type", "string", "enum", List.of("voll", "monster", "spieler", "aus", "stop"))),
                    List.of("mode")),
            tool("gather", "Sammelauftrag in voller Kontrolle (schaltet sie ein): so viel von etwas besorgen. holz zählt "
                            + "Bretter (ein Stamm = 4), eisen zählt Barren (wird geschmolzen), essen zählt Essen im Inventar.",
                    Map.of("item", Map.of("type", "string", "enum", List.of("holz", "stein", "kohle", "eisen", "diamanten", "essen")),
                            "count", Map.of("type", "integer")),
                    List.of("item", "count")),
            tool("attack_player", "Greift einen Spieler an, den der Autopilot gerade sieht (Name).",
                    Map.of("name", Map.of("type", "string")),
                    List.of("name")),
            tool("home", "set = Zuhause hier setzen (Kisten in 10 Blöcken werden zum Einlagern benutzt); "
                            + "gehen = in voller Kontrolle nach Hause gehen.",
                    Map.of("action", Map.of("type", "string", "enum", List.of("set", "gehen"))),
                    List.of("action")));

    private static Tool tool(String name, String description, Map<String, Object> props, List<String> required) {
        Tool.InputSchema.Properties.Builder p = Tool.InputSchema.Properties.builder();
        props.forEach((k, v) -> p.putAdditionalProperty(k, JsonValue.from(v)));
        return Tool.builder()
                .name(name)
                .description(description)
                .strict(true)
                .inputSchema(Tool.InputSchema.builder()
                        .properties(p.build())
                        .required(required)
                        .putAdditionalProperty("additionalProperties", JsonValue.from(false))
                        .build())
                .build();
    }

    /** Runs on the client thread. */
    private static String runTool(Minecraft mc, ToolUseBlock use) {
        LocalPlayer p = mc.player;
        if (p == null) {
            return "Fehler: nicht in einer Welt.";
        }
        Map<?, ?> in = use._input().convert(Map.class);
        if (in == null) {
            in = Map.of();
        }
        Autopilot ap = Autopilot.INSTANCE;
        Autopilot.LOGGER.info("[KI] {} {}", use.name(), in);
        switch (use.name()) {
            case "set_mode" -> {
                switch (String.valueOf(in.get("mode"))) {
                    case "voll" -> ap.setFullControl(mc, true);
                    case "monster" -> {
                        ap.setTargetMode(mc, Autopilot.TargetMode.MOBS);
                        ap.setEnabled(mc, true);
                    }
                    case "spieler" -> {
                        ap.setTargetMode(mc, Autopilot.TargetMode.NEAREST_PLAYER);
                        ap.setEnabled(mc, true);
                    }
                    case "aus" -> ap.setFullControl(mc, false);
                    case "stop" -> {
                        ap.order(null, 0);
                        if (!ap.isFullControl()) {
                            ap.setTarget(mc, null);
                        }
                    }
                    default -> {
                        return "Unbekannter Modus.";
                    }
                }
                return "Modus gesetzt.";
            }
            case "gather" -> {
                Object c = in.get("count");
                String err = ap.order(String.valueOf(in.get("item")), c instanceof Number n ? n.intValue() : 1);
                if (err != null) {
                    return "Abgelehnt: " + err;
                }
                if (!ap.isFullControl()) {
                    ap.setFullControl(mc, true);
                }
                return "Auftrag angenommen.";
            }
            case "attack_player" -> {
                String name = String.valueOf(in.get("name"));
                for (Player other : mc.level.players()) {
                    // (fair: only players it can see)
                    if (other != p && other.getName().getString().equalsIgnoreCase(name.strip()) && p.hasLineOfSight(other)) {
                        ap.setTarget(mc, other);
                        if (!ap.isEnabled()) {
                            ap.setEnabled(mc, true);
                        }
                        return "Greife " + other.getName().getString() + " an.";
                    }
                }
                return "Sehe keinen Spieler " + name + ".";
            }
            case "home" -> {
                if ("set".equals(in.get("action"))) {
                    AutopilotClient.setHome(mc);
                    return "Zuhause gesetzt.";
                }
                String err = ap.order("heim", 1);
                if (err != null) {
                    return "Abgelehnt: " + err;
                }
                if (!ap.isFullControl()) {
                    ap.setFullControl(mc, true);
                }
                return "Geht nach Hause.";
            }
            default -> {
                return "Unbekanntes Werkzeug.";
            }
        }
    }
}
