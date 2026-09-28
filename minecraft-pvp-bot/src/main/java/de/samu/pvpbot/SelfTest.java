package de.samu.pvpbot;

import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.levelgen.Heightmap;

/**
 * Automated in-game test, only active with {@code -Dpvpbot.selftest=true}. Spawns bots against
 * real mobs on a dedicated server, logs the fight and stops the server when done.
 */
final class SelfTest {
    private static final String TAG = "[SELFTEST] ";

    private record Scenario(String name, PvpBotEntity.Style style, int timeoutTicks,
                            Function<ServerLevel, List<LivingEntity>> targets) {
    }

    private static final List<Scenario> SCENARIOS = new ArrayList<>();
    private static final List<String> RESULTS = new ArrayList<>();
    private static final List<Entity> spawned = new ArrayList<>();
    private static int index = -1;
    private static int ticks;
    private static int warmup = 100;
    private static PvpBotEntity bot;
    private static List<LivingEntity> targets = List.of();
    private static BlockPos origin;
    private static int maxHeight;
    private static int smashHits;
    private static int spearHits;
    private static int otherHits;
    private static float maxHit;
    private static boolean flew;

    private SelfTest() {
    }

    static void init() {
        if (!Boolean.getBoolean("pvpbot.selftest")) {
            return;
        }
        PvpBotMod.LOGGER.info(TAG + "self test enabled");
        SCENARIOS.add(new Scenario("Auto vs Eisengolem (8 Bloecke)", PvpBotEntity.Style.AUTO, 1800,
                level -> List.of(golem(level, 8, 0, false))));
        SCENARIOS.add(new Scenario("Nur Mace vs Eisengolem", PvpBotEntity.Style.MACE, 1800,
                level -> List.of(golem(level, 6, 3, false))));
        SCENARIOS.add(new Scenario("Nur Speer vs Eisengolem", PvpBotEntity.Style.SPEAR, 1800,
                level -> List.of(golem(level, 10, -4, false))));
        SCENARIOS.add(new Scenario("Elytra: Ziel 45 Bloecke entfernt", PvpBotEntity.Style.MACE, 1800,
                level -> List.of(golem(level, 45, 5, true))));
        SCENARIOS.add(new Scenario("Elytra Speer: Ziel 45 Bloecke entfernt", PvpBotEntity.Style.SPEAR, 1800,
                level -> List.of(golem(level, -40, 20, true))));
        SCENARIOS.add(new Scenario("Befehlsliste: 4 Zombies", PvpBotEntity.Style.AUTO, 1800,
                level -> List.of(zombie(level, 6, 6), zombie(level, -7, 5), zombie(level, 12, -9), zombie(level, -3, -14))));

        ServerLifecycleEvents.SERVER_STARTED.register(SelfTest::setup);
        ServerTickEvents.END_SERVER_TICK.register(SelfTest::tick);
        ServerLivingEntityEvents.AFTER_DAMAGE.register((entity, source, baseDamage, damageTaken, blocked) -> {
            if (bot != null && source.getEntity() == bot) {
                String type = source.typeHolder().getRegisteredName();
                if (type.contains("mace")) {
                    smashHits++;
                } else if (bot.getMainHandItem().is(Items.NETHERITE_SPEAR)) {
                    spearHits++;
                } else {
                    otherHits++;
                }
                maxHit = Math.max(maxHit, damageTaken);
                PvpBotMod.LOGGER.info(TAG + String.format("  hit %s for %.1f (%s, fall=%.1f, mode=%s)",
                        entity.getName().getString(), damageTaken, type, bot.fallDistance, bot.describeState()));
            }
        });
    }

    private static void setup(MinecraftServer server) {
        ServerLevel level = server.overworld();
        int y = level.getHeight(Heightmap.Types.MOTION_BLOCKING, 0, 0);
        origin = new BlockPos(0, y, 0);
        for (int cx = -6; cx <= 6; cx++) {
            for (int cz = -6; cz <= 6; cz++) {
                level.setChunkForced(cx, cz, true);
            }
        }
        PvpBotMod.LOGGER.info(TAG + "origin " + origin);
    }

    private static LivingEntity golem(ServerLevel level, int dx, int dz, boolean noAi) {
        Mob mob = EntityTypes.IRON_GOLEM.create(level, EntitySpawnReason.COMMAND);
        mob.setNoAi(noAi);
        return place(level, mob, dx, dz);
    }

    private static LivingEntity zombie(ServerLevel level, int dx, int dz) {
        Mob mob = EntityTypes.ZOMBIE.create(level, EntitySpawnReason.COMMAND);
        mob.setItemSlot(EquipmentSlot.HEAD, new ItemStack(Items.IRON_HELMET));
        mob.setItemSlot(EquipmentSlot.CHEST, new ItemStack(Items.IRON_CHESTPLATE));
        return place(level, mob, dx, dz);
    }

    private static LivingEntity place(ServerLevel level, Mob mob, int dx, int dz) {
        int y = level.getHeight(Heightmap.Types.MOTION_BLOCKING, origin.getX() + dx, origin.getZ() + dz);
        mob.snapTo(origin.getX() + dx + 0.5, y, origin.getZ() + dz + 0.5, 0.0F, 0.0F);
        mob.setPersistenceRequired();
        level.addFreshEntity(mob);
        spawned.add(mob);
        return mob;
    }

    private static void tick(MinecraftServer server) {
        if (origin == null) {
            return;
        }
        if (warmup > 0) {
            warmup--;
            return;
        }
        ServerLevel level = server.overworld();
        if (index < 0 || finished()) {
            if (index >= 0) {
                report();
            }
            cleanup();
            index++;
            if (index >= SCENARIOS.size()) {
                PvpBotMod.LOGGER.info(TAG + "==================== SUMMARY");
                RESULTS.forEach(r -> PvpBotMod.LOGGER.info(TAG + r));
                PvpBotMod.LOGGER.info(TAG + "DONE");
                origin = null;
                server.halt(false);
                return;
            }
            start(level, SCENARIOS.get(index));
            return;
        }
        ticks++;
        if (bot.getY() - origin.getY() > maxHeight) {
            maxHeight = (int) (bot.getY() - origin.getY());
        }
        flew |= bot.isFallFlying();
        if (ticks % 20 == 0) {
            LivingEntity t = bot.getTarget();
            PvpBotMod.LOGGER.info(TAG + String.format("t=%3ds bot hp=%4.1f y=%+5.1f fly=%s hand=%s | %s | target hp=%s dist=%s",
                    ticks / 20, bot.getHealth() + bot.getAbsorptionAmount(), bot.getY() - origin.getY(), bot.isFallFlying(),
                    bot.getMainHandItem().getItem().toString(), bot.describeState(),
                    t == null ? "-" : String.format("%.1f", t.getHealth()),
                    t == null ? "-" : String.format("%.1f", bot.distanceTo(t))));
        }
    }

    private static void start(ServerLevel level, Scenario scenario) {
        ticks = 0;
        maxHeight = 0;
        smashHits = spearHits = otherHits = 0;
        maxHit = 0;
        flew = false;
        PvpBotMod.LOGGER.info(TAG + "==================== " + scenario.name());
        bot = PvpBotMod.PVP_BOT.create(level, EntitySpawnReason.COMMAND);
        bot.snapTo(origin.getX() + 0.5, origin.getY(), origin.getZ() + 0.5, 0.0F, 0.0F);
        bot.setStyle(scenario.style());
        bot.setCustomName(Component.literal("TestBot"));
        bot.equipLoadout();
        level.addFreshEntity(bot);
        spawned.add(bot);
        targets = scenario.targets().apply(level);
        for (LivingEntity target : targets) {
            bot.addTarget(target, true);
        }
    }

    private static boolean finished() {
        boolean allDead = targets.stream().noneMatch(LivingEntity::isAlive);
        return allDead || !bot.isAlive() || ticks >= SCENARIOS.get(index).timeoutTicks();
    }

    private static void report() {
        Scenario scenario = SCENARIOS.get(index);
        long killed = targets.stream().filter(t -> !t.isAlive()).count();
        boolean pass = killed == targets.size() && bot.isAlive();
        String line = String.format("%s %-40s kills=%d/%d time=%.1fs botAlive=%s botHp=%.1f smash=%d spear=%d other=%d maxHit=%.1f maxHeight=%d flew=%s",
                pass ? "PASS" : "FAIL", scenario.name(), killed, targets.size(), ticks / 20.0, bot.isAlive(),
                bot.getHealth(), smashHits, spearHits, otherHits, maxHit, maxHeight, flew);
        RESULTS.add(line);
        PvpBotMod.LOGGER.info(TAG + line);
    }

    private static void cleanup() {
        spawned.forEach(Entity::discard);
        spawned.clear();
    }
}
