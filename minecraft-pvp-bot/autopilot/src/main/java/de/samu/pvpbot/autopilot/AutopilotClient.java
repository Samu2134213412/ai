package de.samu.pvpbot.autopilot;

import com.mojang.brigadier.arguments.StringArgumentType;
import de.samu.pvpbot.autopilot.brain.BotBrain;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.ClientCommands;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.EntityHitResult;

public class AutopilotClient implements ClientModInitializer {
    // Key codes are SDL scancodes in this Minecraft version (W = 26, space = 44).
    private static final int KEY_J = 13;
    private static final int KEY_K = 14;
    private static final int KEY_N = 17;
    private static KeyMapping menuKey;
    private static KeyMapping toggleKey;
    private static KeyMapping targetKey;

    @Override
    public void onInitializeClient() {
        KeyMapping.Category category = KeyMapping.Category.register(Identifier.fromNamespaceAndPath("pvpbot_autopilot", "autopilot"));
        toggleKey = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.pvpbot_autopilot.toggle", KEY_K, category));
        targetKey = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.pvpbot_autopilot.target", KEY_J, category));
        menuKey = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.pvpbot_autopilot.menu", KEY_N, category));
        AutopilotSettings.INSTANCE.load(FabricLoader.getInstance().getConfigDir().resolve("pvpbot-autopilot.properties"));

        AutopilotAi.INSTANCE.load(FabricLoader.getInstance().getConfigDir().resolve("pvpbot-autopilot-ai.json"));
        // "@auto ..." in the chat is for the autopilot's AI: answered here, not sent to the server.
        net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents.ALLOW_CHAT.register(
                message -> !AutopilotAi.INSTANCE.onChat(Minecraft.getInstance(), message));
        BotBrain.INSTANCE.load(FabricLoader.getInstance().getConfigDir().resolve("pvpbot-autopilot-memory.json"));
        ClientLifecycleEvents.CLIENT_STOPPING.register(mc -> BotBrain.INSTANCE.save());

        ClientTickEvents.START_CLIENT_TICK.register(mc -> {
            while (toggleKey.consumeClick()) {
                Autopilot ap = Autopilot.INSTANCE;
                if (!ap.isEnabled() && ap.getTarget() == null) {
                    lookTarget(mc);
                }
                ap.setEnabled(mc, !ap.isEnabled());
            }
            while (targetKey.consumeClick()) {
                lookTarget(mc);
            }
            while (menuKey.consumeClick()) {
                if (mc.player != null && mc.gui.screen() == null) {
                    mc.gui.setScreen(new AutopilotScreen());
                }
            }
            Autopilot.INSTANCE.tick(mc);
            if (mc.player != null && mc.player.tickCount % 1200 == 0) {
                BotBrain.INSTANCE.saveIfDirty();
            }
        });

        ClientCommandRegistrationCallback.EVENT.register((dispatcher, registryAccess) -> dispatcher.register(
                ClientCommands.literal("autopilot")
                        .executes(ctx -> help(ctx.getSource()))
                        .then(ClientCommands.literal("on").executes(ctx -> {
                            Autopilot.INSTANCE.setEnabled(ctx.getSource().getClient(), true);
                            return 1;
                        }))
                        .then(ClientCommands.literal("off").executes(ctx -> {
                            Autopilot.INSTANCE.setEnabled(ctx.getSource().getClient(), false);
                            return 1;
                        }))
                        .then(ClientCommands.literal("home")
                                .then(ClientCommands.literal("set").executes(ctx -> {
                                    setHome(ctx.getSource().getClient());
                                    return 1;
                                }))
                                .then(ClientCommands.literal("clear").executes(ctx -> {
                                    AutopilotSettings.INSTANCE.homeSet = false;
                                    AutopilotSettings.INSTANCE.save();
                                    Autopilot.INSTANCE.say(ctx.getSource().getClient(), "§eZuhause gelöscht.");
                                    return 1;
                                })))
                        .then(ClientCommands.literal("full").executes(ctx -> {
                            Autopilot.INSTANCE.setFullControl(ctx.getSource().getClient(), !Autopilot.INSTANCE.isFullControl());
                            return 1;
                        }))
                        .then(ClientCommands.literal("stop").executes(ctx -> {
                            Autopilot.INSTANCE.setTarget(ctx.getSource().getClient(), null);
                            return 1;
                        }))
                        .then(ClientCommands.literal("target")
                                .then(ClientCommands.literal("nearest").executes(ctx -> {
                                    Autopilot.INSTANCE.setTargetMode(ctx.getSource().getClient(), Autopilot.TargetMode.NEAREST_PLAYER);
                                    return 1;
                                }))
                                .then(ClientCommands.literal("mobs").executes(ctx -> {
                                    Autopilot.INSTANCE.setTargetMode(ctx.getSource().getClient(), Autopilot.TargetMode.MOBS);
                                    return 1;
                                }))
                                .then(ClientCommands.literal("look").executes(ctx -> {
                                    lookTarget(ctx.getSource().getClient());
                                    return 1;
                                }))
                                .then(ClientCommands.argument("player", StringArgumentType.word())
                                        .suggests((ctx, builder) -> {
                                            Minecraft mc = ctx.getSource().getClient();
                                            if (mc.level != null) {
                                                for (Player player : mc.level.players()) {
                                                    if (player != mc.player) {
                                                        builder.suggest(player.getName().getString());
                                                    }
                                                }
                                            }
                                            return builder.buildFuture();
                                        })
                                        .executes(ctx -> {
                                            String name = StringArgumentType.getString(ctx, "player");
                                            Minecraft mc = ctx.getSource().getClient();
                                            for (Player player : mc.level.players()) {
                                                if (player.getName().getString().equalsIgnoreCase(name)) {
                                                    Autopilot.INSTANCE.setTarget(mc, player);
                                                    return 1;
                                                }
                                            }
                                            ctx.getSource().sendError(Component.literal("Spieler " + name + " ist nicht in Sichtweite."));
                                            return 0;
                                        })))
                        .then(ClientCommands.literal("trick")
                                .then(ClientCommands.argument("name", StringArgumentType.word())
                                        .suggests((c, sb) -> {
                                            for (BotBrain.Pattern p : BotBrain.Pattern.values()) {
                                                sb.suggest(p.trickName());
                                            }
                                            return sb.buildFuture();
                                        })
                                        .executes(ctx -> {
                                            BotBrain.Pattern pattern = BotBrain.Pattern.byTrickName(StringArgumentType.getString(ctx, "name"));
                                            if (pattern == null) {
                                                ctx.getSource().sendFeedback(Component.literal("§cUnbekannter Trick. Möglich: kombo, smash, ansturm, stiche, sturzflug, speerflug, mace, schwert, bogen"));
                                                return 0;
                                            }
                                            Autopilot.INSTANCE.forcePattern(pattern);
                                            ctx.getSource().sendFeedback(Component.literal("§aNächster Angriff: §f" + pattern.label));
                                            return 1;
                                        })))
                        .then(ClientCommands.literal("auftrag")
                                .then(ClientCommands.literal("stop").executes(ctx -> {
                                    Autopilot.INSTANCE.order(null, 0);
                                    ctx.getSource().sendFeedback(Component.literal("§eAuftrag abgebrochen."));
                                    return 1;
                                }))
                                .then(ClientCommands.argument("was", StringArgumentType.word())
                                        .suggests((c, sb) -> {
                                            Survival.ORDERS.forEach(sb::suggest);
                                            return sb.buildFuture();
                                        })
                                        .executes(ctx -> order(ctx.getSource(), StringArgumentType.getString(ctx, "was"), 1))
                                        .then(ClientCommands.argument("anzahl", com.mojang.brigadier.arguments.IntegerArgumentType.integer(1, 256))
                                                .executes(ctx -> order(ctx.getSource(), StringArgumentType.getString(ctx, "was"),
                                                        com.mojang.brigadier.arguments.IntegerArgumentType.getInteger(ctx, "anzahl"))))))
                        .then(ClientCommands.literal("ki")
                                .executes(ctx -> {
                                    AutopilotAi ai = AutopilotAi.INSTANCE;
                                    ctx.getSource().sendFeedback(Component.literal("§6KI-Chat §7– " + (ai.hasKey() ? "§aAPI-Key gesetzt" : "§ckein API-Key")
                                            + " §7Modell: §f" + ai.model()));
                                    ctx.getSource().sendFeedback(Component.literal("§7Schreib im Chat §f@auto <text>§7 – die KI antwortet und setzt die Ziele des Autopiloten."));
                                    ctx.getSource().sendFeedback(Component.literal("§f/autopilot ki key <key> §7· §f/autopilot ki aus §7· §f/autopilot ki frag <text>"));
                                    return 1;
                                })
                                .then(ClientCommands.literal("key")
                                        .then(ClientCommands.argument("key", StringArgumentType.greedyString()).executes(ctx -> {
                                            String key = StringArgumentType.getString(ctx, "key").strip();
                                            if (!key.startsWith("sk-")) {
                                                ctx.getSource().sendError(Component.literal("Das sieht nicht wie ein Anthropic-API-Key aus (fängt mit sk- an)."));
                                                return 0;
                                            }
                                            AutopilotAi.INSTANCE.setKey(key);
                                            // (the key itself is never shown again)
                                            ctx.getSource().sendFeedback(Component.literal("§aAPI-Key gespeichert §7(nur auf diesem Computer). Schreib jetzt §f@auto hallo"));
                                            return 1;
                                        })))
                                .then(ClientCommands.literal("aus").executes(ctx -> {
                                    AutopilotAi.INSTANCE.setKey(null);
                                    ctx.getSource().sendFeedback(Component.literal("§eAPI-Key gelöscht, KI-Chat aus."));
                                    return 1;
                                }))
                                .then(ClientCommands.literal("frag")
                                        .then(ClientCommands.argument("text", StringArgumentType.greedyString()).executes(ctx -> {
                                            AutopilotAi.INSTANCE.ask(ctx.getSource().getClient(), StringArgumentType.getString(ctx, "text"));
                                            return 1;
                                        }))))
                        .then(ClientCommands.literal("brain")
                                .executes(ctx -> {
                                    var lines = BotBrain.INSTANCE.summary(12);
                                    if (lines.isEmpty()) {
                                        ctx.getSource().sendFeedback(Component.literal("§7Noch nichts gelernt."));
                                    }
                                    lines.forEach(line -> ctx.getSource().sendFeedback(Component.literal(line)));
                                    return lines.size();
                                })
                                .then(ClientCommands.literal("reset").executes(ctx -> {
                                    BotBrain.INSTANCE.reset();
                                    ctx.getSource().sendFeedback(Component.literal("§eAutopilot-Gedächtnis gelöscht."));
                                    return 1;
                                })))));
    }

    private static int help(FabricClientCommandSource source) {
        Autopilot ap = Autopilot.INSTANCE;
        source.sendFeedback(Component.literal("§6PvP-Autopilot §7– " + (ap.isEnabled() ? "§aAN" : "§cAUS") + " §7Ziel: §f" + ap.describeTarget()));
        source.sendFeedback(Component.literal("§7Taste §fK§7: an/aus · Taste §fJ§7: Ziel = was du anschaust"));
        source.sendFeedback(Component.literal("§f/autopilot on|off|full|stop · target <Spieler>|nearest|mobs|look · brain [reset]"));
        source.sendFeedback(Component.literal("§f/autopilot auftrag <holz|stein|kohle|eisen|diamanten|essen|heim> [anzahl] · ki §7(Chat: §f@auto …§7)"));
        return 1;
    }

    private static int order(FabricClientCommandSource source, String what, int count) {
        String err = Autopilot.INSTANCE.order(what, count);
        if (err != null) {
            source.sendError(Component.literal("Auftrag " + what + ": " + err));
            return 0;
        }
        if (!Autopilot.INSTANCE.isFullControl()) {
            Autopilot.INSTANCE.setFullControl(source.getClient(), true);
        }
        source.sendFeedback(Component.literal("§aAuftrag: §f" + Autopilot.INSTANCE.currentOrder()));
        return 1;
    }

    static void lookTarget(Minecraft mc) {
        if (mc.player == null) {
            return;
        }
        // Whatever is under the crosshair, up to 64 blocks away.
        var hit = net.minecraft.world.entity.projectile.ProjectileUtil.getEntityHitResult(mc.player, mc.player.getEyePosition(),
                mc.player.getEyePosition().add(mc.player.getViewVector(1.0F).scale(64.0)),
                mc.player.getBoundingBox().expandTowards(mc.player.getViewVector(1.0F).scale(64.0)).inflate(1.0),
                e -> e.isAlive() && e.isPickable() && !e.isSpectator(), 64.0 * 64.0);
        Entity entity = hit instanceof EntityHitResult ehr ? ehr.getEntity() : null;
        if (entity == null) {
            Autopilot.INSTANCE.say(mc, "§7Kein Ziel im Visier.");
            return;
        }
        Autopilot.INSTANCE.setTarget(mc, entity);
    }

    /** Home = where the player stands now. Chests within 10 blocks of it are used for storage. */
    public static void setHome(Minecraft mc) {
        if (mc.player == null) {
            return;
        }
        AutopilotSettings st = AutopilotSettings.INSTANCE;
        st.homeSet = true;
        st.homeX = mc.player.getBlockX();
        st.homeY = mc.player.getBlockY();
        st.homeZ = mc.player.getBlockZ();
        st.homeLevel = mc.player.level().dimension().toString();
        st.save();
        Autopilot.INSTANCE.say(mc, "§6Zuhause gesetzt: §f" + st.homeX + " " + st.homeY + " " + st.homeZ
                + " §7– Kisten in 10 Blöcken Umkreis werden benutzt, hierhin kommt er zurück.");
    }
}
