package de.samu.pvpbot.ai;

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
import de.samu.pvpbot.PvpBotMod;
import de.samu.pvpbot.entity.PvpBotEntity;
import de.samu.pvpbot.voice.BotVoice;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.LivingEntity;
import org.jspecify.annotations.Nullable;

/**
 * Talk to your bot in the normal chat ("@bot hol mir 10 Eisen") - Claude answers for it and can set
 * its goals. Every player uses their own API key ({@code /pvpbot ki key <key>}), stored in
 * {@code config/pvpbot-ai.json}; the key is never written to the log or the chat.
 */
public final class BotAi {
    public static final BotAi INSTANCE = new BotAi();

    private static final String DEFAULT_MODEL = "claude-opus-5-5";
    private static final int MAX_HISTORY = 16;
    private static final int MAX_TOOL_ROUNDS = 5;

    /** What is stored in config/pvpbot-ai.json. */
    private static final class Config {
        Map<String, String> keys = new HashMap<>();
        String model = DEFAULT_MODEL;
        /** Servers may set one key for everybody (only by editing the file). */
        @Nullable String serverKey;
    }

    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    private final ExecutorService pool = Executors.newFixedThreadPool(2, r -> {
        Thread t = new Thread(r, "pvpbot-ai");
        t.setDaemon(true);
        return t;
    });
    private final Map<UUID, List<MessageParam>> history = new HashMap<>();
    private final Map<String, AnthropicClient> clients = new HashMap<>();
    private final Map<UUID, Boolean> busy = new java.util.concurrent.ConcurrentHashMap<>();
    private Config config = new Config();
    private @Nullable Path file;

    private BotAi() {
    }

    // ------------------------------------------------------------------ config

    public synchronized void load(Path path) {
        this.file = path;
        try {
            if (Files.exists(path)) {
                Config c = this.gson.fromJson(Files.readString(path), Config.class);
                if (c != null) {
                    this.config = c;
                    if (this.config.keys == null) {
                        this.config.keys = new HashMap<>();
                    }
                    if (this.config.model == null || this.config.model.isBlank()) {
                        this.config.model = DEFAULT_MODEL;
                    }
                }
            }
        } catch (Exception e) {
            PvpBotMod.LOGGER.warn("pvpbot-ai.json nicht lesbar: {}", e.getMessage());
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
            PvpBotMod.LOGGER.warn("pvpbot-ai.json nicht speicherbar: {}", e.getMessage());
        }
    }

    public synchronized void setKey(UUID player, @Nullable String key) {
        if (key == null || key.isBlank()) {
            this.config.keys.remove(player.toString());
        } else {
            this.config.keys.put(player.toString(), key.trim());
        }
        this.save();
    }

    public synchronized boolean hasKey(UUID player) {
        return this.keyOf(player) != null;
    }

    private synchronized @Nullable String keyOf(UUID player) {
        String key = this.config.keys.get(player.toString());
        if (key == null || key.isBlank()) {
            key = this.config.serverKey;
        }
        return key == null || key.isBlank() ? null : key;
    }

    public synchronized void setModel(String model) {
        this.config.model = model;
        this.save();
    }

    public synchronized String model() {
        return this.config.model;
    }

    public void forget(UUID bot) {
        synchronized (this.history) {
            this.history.remove(bot);
        }
    }

    private synchronized AnthropicClient client(String key) {
        return this.clients.computeIfAbsent(key, k -> AnthropicOkHttpClient.builder().apiKey(k).build());
    }

    // ------------------------------------------------------------------ chat

    /**
     * A chat message: "@bot ...", "@Name ..." or "Name, ..." talks to the sender's own bot.
     * Returns true when a bot was addressed.
     */
    public boolean onChat(ServerPlayer sender, String text) {
        String msg = text.strip();
        List<PvpBotEntity> bots = PvpBotEntity.botsOf(sender);
        if (bots.isEmpty() || msg.isEmpty()) {
            return false;
        }
        String lower = msg.toLowerCase(Locale.ROOT);
        for (PvpBotEntity bot : bots) {
            String name = bot.getName().getString().toLowerCase(Locale.ROOT);
            String rest = null;
            if (lower.startsWith("@bot")) {
                rest = msg.substring(4);
            } else if (lower.startsWith("@" + name)) {
                rest = msg.substring(name.length() + 1);
            } else if (lower.startsWith(name + ",") || lower.startsWith(name + ":")) {
                rest = msg.substring(name.length() + 1);
            }
            if (rest != null) {
                this.ask(sender, bot, rest.replaceFirst("^[\\s,:]+", ""));
                return true;
            }
        }
        return false;
    }

    /** Sends the player's words to Claude (off the server thread) and lets the bot answer. */
    public void ask(ServerPlayer player, PvpBotEntity bot, String words) {
        if (words.isBlank()) {
            return;
        }
        String key = this.keyOf(player.getUUID());
        if (key == null) {
            player.sendSystemMessage(Component.literal("§c" + bot.getName().getString()
                    + " kann noch nicht mit dir reden: setz erst deinen API-Key mit §f/pvpbot ki key <dein-anthropic-key>"));
            return;
        }
        if (this.busy.putIfAbsent(bot.getUUID(), Boolean.TRUE) != null) {
            player.sendSystemMessage(Component.literal("§7" + bot.getName().getString() + " denkt noch nach …"));
            return;
        }
        MinecraftServer server = ((ServerLevel) bot.level()).getServer();
        String situation = this.situation(bot, player);
        UUID botId = bot.getUUID();
        String model = this.model();
        this.pool.execute(() -> {
            try {
                String answer = this.talk(key, model, botId, situation, words, server, player.getUUID());
                server.execute(() -> this.reply(server, botId, player.getUUID(), answer));
            } catch (AnthropicServiceException e) {
                String why = e.statusCode() == 401 ? "API-Key ungültig (/pvpbot ki key …)"
                        : e.statusCode() == 429 ? "zu viele Anfragen, gleich nochmal"
                        : "API-Fehler " + e.statusCode();
                server.execute(() -> this.error(server, player.getUUID(), why));
            } catch (Exception e) {
                PvpBotMod.LOGGER.warn("KI-Chat fehlgeschlagen: {}", e.toString());
                server.execute(() -> this.error(server, player.getUUID(), "keine Verbindung zur KI"));
            } finally {
                this.busy.remove(botId);
            }
        });
    }

    private void error(MinecraftServer server, UUID playerId, String why) {
        ServerPlayer p = server.getPlayerList().getPlayer(playerId);
        if (p != null) {
            p.sendSystemMessage(Component.literal("§c[KI] " + why));
        }
    }

    private void reply(MinecraftServer server, UUID botId, UUID playerId, String answer) {
        PvpBotEntity bot = findBot(server, botId);
        if (bot == null || answer.isBlank()) {
            return;
        }
        Component line = Component.literal("<" + bot.getName().getString() + "> " + answer);
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            if (p.getUUID().equals(playerId) || p.level() == bot.level() && p.distanceToSqr(bot) < 48.0 * 48.0) {
                p.sendSystemMessage(line);
            }
        }
        BotVoice.speak(bot, answer);
    }

    private static @Nullable PvpBotEntity findBot(MinecraftServer server, UUID id) {
        for (ServerLevel level : server.getAllLevels()) {
            if (level.getEntity(id) instanceof PvpBotEntity bot && bot.isAlive()) {
                return bot;
            }
        }
        return null;
    }

    /** What the bot knows right now (read on the server thread). */
    private String situation(PvpBotEntity bot, ServerPlayer player) {
        var key = bot.level().dimension();
        String dim = key == net.minecraft.world.level.Level.NETHER ? "Nether" : key == net.minecraft.world.level.Level.END ? "End" : "Oberwelt";
        LivingEntity target = bot.getTarget();
        String order = bot.currentOrder();
        return "Name: " + bot.getName().getString()
                + "\nLeben: " + (int) bot.getHealth() + "/" + (int) bot.getMaxHealth()
                + "\nDimension: " + dim + ", Position " + bot.blockPosition().toShortString()
                + "\nSpieler " + player.getName().getString() + " ist " + (int) Math.sqrt(bot.distanceToSqr(player)) + " Blöcke entfernt"
                + (player.level() == bot.level() ? "" : " (andere Dimension)")
                + "\nKampf: " + bot.describeState() + (target == null ? "" : " (Ziel " + target.getName().getString() + ")")
                + "\nModus: " + (bot.isSpeedrun() ? "Durchspielen" : bot.isAutonomous() ? "autonom" : bot.isGathering() ? "sammelt Ausrüstung" : "wartet")
                + "\nAuftrag: " + (order == null ? "keiner" : order)
                + "\nZuhause: " + (bot.getHome() == null ? "keins" : bot.getHome().toShortString())
                + "\nPlan: " + bot.describeNeeds()
                + "\nAusrüstung: " + bot.describeKit();
    }

    private static final String SYSTEM = """
            Du bist ein Minecraft-Bot, der wie ein echter Spieler auf einem Server spielt. Der Spieler, der mit dir \
            schreibt, ist dein Besitzer. Du antwortest im Chat: kurz (höchstens 2 Sätze), locker, in der Sprache \
            des Spielers, ohne Markdown. Du legst deine Ziele selbst fest: wenn der Spieler etwas will oder es \
            sinnvoll ist, benutze die Werkzeuge (set_goal, order_item, attack), statt nur zu reden. Du spielst fair \
            wie ein Mensch: du weißt nur, was du selbst siehst, und behauptest nichts, was nicht in deinem Zustand steht.""";

    private String talk(String key, String model, UUID botId, String situation, String words,
                        MinecraftServer server, UUID playerId) throws Exception {
        List<MessageParam> convo;
        synchronized (this.history) {
            convo = new ArrayList<>(this.history.getOrDefault(botId, List.of()));
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
                    String result = server.submit(() -> this.runTool(server, botId, playerId, use)).join();
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
            this.history.put(botId, kept);
        }
        return answer.toString().strip();
    }

    // ------------------------------------------------------------------ tools (the AI sets the goals)

    private static final List<Tool> TOOLS = List.of(
            tool("set_goal", "Legt fest, was der Bot ab jetzt tut. durchspielen = Minecraft durchspielen (Portal, Nether, "
                            + "Festung, Enderdrache); autonom = Ausrüstung bis Diamant verbessern und zu Hause einlagern; "
                            + "sammeln = fehlende Ausrüstung besorgen; folgen = dem Spieler folgen; bleiben = hier warten; "
                            + "nach_hause = heimgehen; stop = alles stoppen (Kampf, Auftrag, Durchspielen).",
                    Map.of("goal", Map.of("type", "string", "enum",
                            List.of("durchspielen", "autonom", "sammeln", "folgen", "bleiben", "nach_hause", "stop"))),
                    List.of("goal")),
            tool("order_item", "Gibt dem Bot einen Sammelauftrag: so viele von einem Rohstoff oder craftbaren Gegenstand besorgen. "
                            + "item ist ein Rohstoff (log, planks, stick, cobble, coal, raw_iron, iron, diamond, obsidian, flint, "
                            + "blaze_rod, blaze_powder, pearl, eye, string, feather, raw_meat, cooked_meat) oder eine Item-ID "
                            + "wie iron_pickaxe, shield, bow, bucket.",
                    Map.of("item", Map.of("type", "string"), "count", Map.of("type", "integer")),
                    List.of("item", "count")),
            tool("attack", "Greift ein Lebewesen an, das der Bot gerade sieht (Name eines Spielers oder Mob-Art wie zombie). "
                            + "Nicht den eigenen Besitzer.",
                    Map.of("target", Map.of("type", "string")),
                    List.of("target")));

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

    /** Runs on the server thread. */
    private String runTool(MinecraftServer server, UUID botId, UUID playerId, ToolUseBlock use) {
        PvpBotEntity bot = findBot(server, botId);
        ServerPlayer player = server.getPlayerList().getPlayer(playerId);
        if (bot == null) {
            return "Fehler: Bot nicht mehr da.";
        }
        Map<?, ?> in = use._input().convert(Map.class);
        if (in == null) {
            in = Map.of();
        }
        String name = use.name();
        PvpBotMod.LOGGER.info("[KI] {} -> {} {}", bot.getName().getString(), name, in);
        switch (name) {
            case "set_goal" -> {
                String goal = String.valueOf(in.get("goal"));
                return this.setGoal(bot, player, goal);
            }
            case "order_item" -> {
                Object c = in.get("count");
                int count = c instanceof Number n ? n.intValue() : 1;
                String err = bot.order(String.valueOf(in.get("item")), count);
                return err == null ? "Auftrag angenommen." : "Abgelehnt: " + err;
            }
            case "attack" -> {
                return this.attack(bot, player, String.valueOf(in.get("target")));
            }
            default -> {
                return "Unbekanntes Werkzeug.";
            }
        }
    }

    private String setGoal(PvpBotEntity bot, @Nullable ServerPlayer player, String goal) {
        boolean infinite = bot.getKit().isInfinite();
        switch (goal) {
            case "durchspielen" -> {
                if (infinite) {
                    return "Geht nicht: der Bot hat ein unendliches Kit (nur Survival-Bots spielen durch).";
                }
                bot.setSpeedrun(true);
            }
            case "autonom" -> {
                if (infinite) {
                    return "Geht nicht: der Bot hat ein unendliches Kit.";
                }
                bot.setAutonomous(true);
            }
            case "sammeln" -> bot.setGathering(true);
            case "folgen" -> bot.setFollowing(true);
            case "bleiben" -> bot.setFollowing(false);
            case "nach_hause" -> {
                if (bot.getHome() == null) {
                    return "Kein Zuhause gesetzt (/pvpbot home set).";
                }
                bot.setFollowing(false);
                bot.clearTargets();
                bot.goHome();
            }
            case "stop" -> {
                bot.clearTargets();
                bot.cancelOrder();
                bot.setSpeedrun(false);
                bot.setAutonomous(false);
            }
            default -> {
                return "Unbekanntes Ziel.";
            }
        }
        return "Ziel gesetzt: " + goal;
    }

    private String attack(PvpBotEntity bot, @Nullable ServerPlayer player, String what) {
        String w = what.toLowerCase(Locale.ROOT).strip();
        LivingEntity best = null;
        double bestDist = Double.MAX_VALUE;
        for (LivingEntity e : bot.level().getEntitiesOfClass(LivingEntity.class, bot.getBoundingBox().inflate(32.0))) {
            if (e == bot || e == player || e instanceof PvpBotEntity || !bot.hasLineOfSight(e)) {
                continue; // (fair: only what it can see)
            }
            String type = net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath();
            if (!e.getName().getString().toLowerCase(Locale.ROOT).equals(w) && !type.equals(w.replace(' ', '_'))) {
                continue;
            }
            double d = bot.distanceToSqr(e);
            if (d < bestDist) {
                bestDist = d;
                best = e;
            }
        }
        if (best == null) {
            return "Sehe kein " + what + ".";
        }
        bot.addTarget(best, true);
        return "Greife " + best.getName().getString() + " an.";
    }
}
