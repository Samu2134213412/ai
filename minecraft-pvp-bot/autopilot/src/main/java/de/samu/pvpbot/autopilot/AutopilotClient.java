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
    private static KeyMapping toggleKey;
    private static KeyMapping targetKey;

    @Override
    public void onInitializeClient() {
        KeyMapping.Category category = KeyMapping.Category.register(Identifier.fromNamespaceAndPath("pvpbot_autopilot", "autopilot"));
        toggleKey = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.pvpbot_autopilot.toggle", KEY_K, category));
        targetKey = KeyMappingHelper.registerKeyMapping(
                new KeyMapping("key.pvpbot_autopilot.target", KEY_J, category));

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
        source.sendFeedback(Component.literal("§f/autopilot on|off|stop · target <Spieler>|nearest|mobs|look · brain [reset]"));
        return 1;
    }

    private static void lookTarget(Minecraft mc) {
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
}
