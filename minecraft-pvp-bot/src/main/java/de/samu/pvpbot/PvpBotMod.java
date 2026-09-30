package de.samu.pvpbot;

import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.brain.TaskLearner;
import de.samu.pvpbot.entity.PvpBotEntity;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.player.AttackEntityCallback;
import net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.entity.player.Player;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PvpBotMod implements ModInitializer {
    public static final String MOD_ID = "pvpbot";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    public static final ResourceKey<EntityType<?>> PVP_BOT_KEY =
            ResourceKey.create(Registries.ENTITY_TYPE, Identifier.fromNamespaceAndPath(MOD_ID, "pvp_bot"));

    public static final EntityType<PvpBotEntity> PVP_BOT = Registry.register(
            BuiltInRegistries.ENTITY_TYPE,
            PVP_BOT_KEY,
            EntityType.Builder.of(PvpBotEntity::new, MobCategory.MISC)
                    .sized(0.6F, 1.8F)
                    .eyeHeight(1.62F)
                    .clientTrackingRange(16)
                    .build(PVP_BOT_KEY));

    @Override
    public void onInitialize() {
        FabricDefaultAttributeRegistry.register(PVP_BOT, PvpBotEntity.createAttributes());

        CommandRegistrationCallback.EVENT.register(
                (dispatcher, registryAccess, environment) -> BotCommands.register(dispatcher));

        // Whatever the owner hits becomes the bots' target.
        AttackEntityCallback.EVENT.register((player, level, hand, entity, hitResult) -> {
            if (!level.isClientSide() && entity instanceof LivingEntity living && !(entity instanceof PvpBotEntity)) {
                for (PvpBotEntity bot : PvpBotEntity.botsOf(player)) {
                    if (bot.isAssisting()) {
                        bot.addTarget(living, false);
                    }
                }
            }
            return InteractionResult.PASS;
        });

        // Whoever hurts the owner becomes the bots' target.
        ServerLivingEntityEvents.AFTER_DAMAGE.register((entity, source, baseDamage, damageTaken, blocked) -> {
            if (entity instanceof Player owner && source.getEntity() instanceof LivingEntity attacker
                    && attacker != owner && !(attacker instanceof PvpBotEntity)
                    && entity.level() instanceof ServerLevel) {
                for (PvpBotEntity bot : PvpBotEntity.botsOf(owner)) {
                    if (bot.isAssisting()) {
                        bot.addTarget(attacker, false);
                    }
                }
            }
        });

        // Like a tamed wolf: what the bot hits counts as hit by its owner (the vanilla rule for pets),
        // so "killed by player" loot such as blaze rods drops. No owner, no credit.
        ServerLivingEntityEvents.AFTER_DAMAGE.register((entity, source, baseDamage, damageTaken, blocked) -> {
            if (source.getEntity() instanceof PvpBotEntity bot && damageTaken > 0.0F && bot.getOwner() instanceof Player owner) {
                entity.setLastHurtByPlayer(owner, 100);
            }
        });

        // The shared combat memory: loaded with the server, saved regularly and on shutdown.
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            BotBrain.INSTANCE.load(FabricLoader.getInstance().getConfigDir().resolve("pvpbot-memory.json"));
            TaskLearner.INSTANCE.load(FabricLoader.getInstance().getConfigDir().resolve("pvpbot-tasks.json"));
        });
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            BotBrain.INSTANCE.save();
            TaskLearner.INSTANCE.save();
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (server.getTickCount() % 1200 == 0) {
                BotBrain.INSTANCE.saveIfDirty();
                TaskLearner.INSTANCE.saveIfDirty();
            }
        });

        SelfTest.init();
        LOGGER.info("PvP Bot geladen - /pvpbot spawn");
    }
}
