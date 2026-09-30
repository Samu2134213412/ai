package de.samu.pvpbot;

import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.Item;
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
import org.jspecify.annotations.Nullable;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.Heightmap;

/**
 * Automated in-game test, only active with {@code -Dpvpbot.selftest=true}. Spawns bots against
 * real mobs on a dedicated server, logs the fight and stops the server when done.
 */
final class SelfTest {
    private static final String TAG = "[SELFTEST] ";

    private record Scenario(String name, PvpBotEntity.Style style, int timeoutTicks, int baseX,
                            Function<ServerLevel, List<LivingEntity>> targets, java.util.function.@org.jspecify.annotations.Nullable Supplier<List<ItemStack>> kit,
                            java.util.function.@org.jspecify.annotations.Nullable Predicate<PvpBotEntity> goal) {
        Scenario(String name, PvpBotEntity.Style style, int timeoutTicks, int baseX, Function<ServerLevel, List<LivingEntity>> targets,
                 java.util.function.@org.jspecify.annotations.Nullable Supplier<List<ItemStack>> kit) {
            this(name, style, timeoutTicks, baseX, targets, kit, null);
        }

        Scenario(String name, PvpBotEntity.Style style, int timeoutTicks, Function<ServerLevel, List<LivingEntity>> targets) {
            this(name, style, timeoutTicks, 0, targets, null, null);
        }

        Scenario(String name, PvpBotEntity.Style style, int timeoutTicks, int baseX, Function<ServerLevel, List<LivingEntity>> targets) {
            this(name, style, timeoutTicks, baseX, targets, null, null);
        }
    }

    /** X offset of a small "resource island": trees, stone, coal, iron (some buried) and cows. */
    private static final int SURVIVAL_X = -80;

    private static boolean fullyGeared(PvpBotEntity bot) {
        var kit = bot.getKit();
        return kit.count(s -> s.is(Items.IRON_SWORD)) > 0 && kit.count(s -> s.is(Items.IRON_CHESTPLATE)) > 0
                && kit.count(s -> s.is(Items.IRON_HELMET)) > 0 && kit.count(s -> s.is(Items.IRON_LEGGINGS)) > 0
                && kit.count(s -> s.is(Items.IRON_BOOTS)) > 0 && kit.count(s -> s.is(Items.SHIELD)) > 0;
    }

    /** X offset of a 1x1 stone pit (4 high) the bot starts in and has to get out of. */
    private static final int PIT_X = -40;
    private static final int HOME_X = 120;

    private static List<ItemStack> swordKit() {
        return List.of(new ItemStack(Items.DIAMOND_SWORD), new ItemStack(Items.IRON_AXE), new ItemStack(Items.IRON_HELMET),
                new ItemStack(Items.IRON_CHESTPLATE), new ItemStack(Items.IRON_LEGGINGS), new ItemStack(Items.IRON_BOOTS),
                new ItemStack(Items.GOLDEN_APPLE, 3));
    }

    private static List<ItemStack> bowKit() {
        return List.of(new ItemStack(Items.BOW), new ItemStack(Items.ARROW, 64), new ItemStack(Items.STONE_SWORD),
                new ItemStack(Items.CHAINMAIL_CHESTPLATE));
    }

    /** X offset of the covered "cave" test area (stone roof 4 blocks above the ground). */
    private static final int CAVE_X = 60;
    private static int baseX;

    private static final List<Scenario> SCENARIOS = new ArrayList<>();
    private static final List<String> RESULTS = new ArrayList<>();
    private static final List<Entity> spawned = new ArrayList<>();
    private static int portalWait;
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
    private static int graceTicks;

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
        SCENARIOS.add(new Scenario("Elytra Speer vs laufender Zombie", PvpBotEntity.Style.SPEAR, 1800,
                level -> List.of(zombie(level, 38, -20))));
        for (int i = 1; i <= 3; i++) {
            SCENARIOS.add(new Scenario("Hoehle " + i + ": Eisengolem", PvpBotEntity.Style.AUTO, 1800, CAVE_X,
                    level -> List.of(golem(level, 7, 2, false))));
        }
        SCENARIOS.add(new Scenario("Hoehle: 3 Zombies", PvpBotEntity.Style.AUTO, 1800, CAVE_X,
                level -> List.of(zombie(level, 6, 4), zombie(level, -6, 3), zombie(level, 5, -7))));
        for (int i = 1; i <= 3; i++) {
            SCENARIOS.add(new Scenario("Lernen " + i + ": Auto vs Eisengolem", PvpBotEntity.Style.AUTO, 1800,
                    level -> List.of(golem(level, -9, 3, false))));
        }
        SCENARIOS.add(new Scenario("Kit Schwert+Axt vs 3 Zombies", PvpBotEntity.Style.AUTO, 1800, 0,
                level -> List.of(zombie(level, 6, 4), zombie(level, -6, 3), zombie(level, 5, -7)), SelfTest::swordKit));
        SCENARIOS.add(new Scenario("Kit Bogen vs Eisengolem (NoAI, 20 Bloecke)", PvpBotEntity.Style.AUTO, 2400, 0,
                level -> List.of(golem(level, 20, 3, true)), SelfTest::bowKit));
        SCENARIOS.add(new Scenario("Grube: Schwert-Kit, Ziel draussen", PvpBotEntity.Style.AUTO, 2400, PIT_X,
                level -> List.of(zombie(level, 7, 2)), SelfTest::swordKit));
        SCENARIOS.add(new Scenario("Survival: besorgt sich alles selbst", PvpBotEntity.Style.AUTO, 12000, SURVIVAL_X,
                level -> List.of(), List::of, SelfTest::fullyGeared));
        SCENARIOS.add(new Scenario("Befehlsliste: 4 Zombies", PvpBotEntity.Style.AUTO, 1800,
                level -> List.of(zombie(level, 6, 6), zombie(level, -7, 5), zombie(level, 12, -9), zombie(level, -3, -14))));
        SCENARIOS.add(new Scenario("Zuhause: Kiste aufstellen, Eisenset einlagern", PvpBotEntity.Style.AUTO, 2400, HOME_X,
                level -> List.of(), SelfTest::homeKit, SelfTest::ironSetStored));
        // Beat the game, stage 1, in untouched terrain (sped up with /tick sprint).
        SCENARIOS.add(new Scenario("Etappe 1: Diamanten, Obsidian, Netherportal", PvpBotEntity.Style.AUTO, 150000, 240,
                level -> List.of(), SelfTest::stage1Kit, PvpBotEntity::portalBuilt));
        SCENARIOS.add(new Scenario("Etappe 2: Nether, Lohenruten, Enderperlen", PvpBotEntity.Style.AUTO, 90000, -240,
                level -> List.of(), SelfTest::stage2Kit, PvpBotEntity::stage2Done));
        SCENARIOS.add(new Scenario("Etappe 3: Enderaugen werfen, Festung, Endportal", PvpBotEntity.Style.AUTO, 150000, 480,
                level -> List.of(), SelfTest::stage3Kit, PvpBotEntity::inEnd));
        SCENARIOS.add(new Scenario("Etappe 4: Endkristalle und Enderdrache", PvpBotEntity.Style.AUTO, 72000, 0,
                level -> List.of(), SelfTest::stage4Kit, PvpBotEntity::gameBeaten));
        // The whole game in one go, from nothing (like a new player): 1.5 hours of game time. It may be
        // slow; what counts is that it never gets stuck (see the progress watch below).
        SCENARIOS.add(new Scenario("Etappe voll: Minecraft komplett durchspielen", PvpBotEntity.Style.AUTO, 108000, 240,
                level -> List.of(), List::of, PvpBotEntity::gameBeaten));

        // The "beat the game" stages need a normal world; the fights need the flat test world.
        String stages = System.getProperty("pvpbot.stagetest");
        if (stages != null) {
            // "all" or a single stage number (CI runs the stages as parallel jobs).
            SCENARIOS.removeIf(sc -> !sc.name().startsWith("Etappe") || !stages.equals("all") && !stages.equals("true")
                    && !sc.name().startsWith("Etappe " + stages + ":"));
        } else {
            SCENARIOS.removeIf(sc -> sc.name().startsWith("Etappe"));
        }
        ServerLifecycleEvents.SERVER_STARTED.register(SelfTest::setup);
        ServerTickEvents.END_SERVER_TICK.register(SelfTest::tick);
        ServerLivingEntityEvents.AFTER_DAMAGE.register((entity, source, baseDamage, damageTaken, blocked) -> {
            if (bot != null && entity == bot && damageTaken >= 2.0F) {
                PvpBotMod.LOGGER.info(TAG + String.format("  bot took %.1f from %s (%s) at %s, hp now %.1f, %s",
                        damageTaken, source.typeHolder().getRegisteredName(),
                        source.getEntity() == null ? "-" : source.getEntity().getName().getString(),
                        bot.blockPosition().toShortString(), bot.getHealth(), bot.describeState()));
            }
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
        if (System.getProperty("pvpbot.stagetest") != null) {
            // "Beat the game" runs in an untouched world: nothing built, nothing forced.
            PvpBotMod.LOGGER.info(TAG + "origin " + origin);
            return;
        }
        for (int cx = -6; cx <= 6; cx++) {
            for (int cz = -6; cz <= 6; cz++) {
                level.setChunkForced(cx, cz, true);
            }
        }
        BlockPos roofCorner = origin.offset(CAVE_X, 4, 0);
        for (int x = -15; x <= 15; x++) {
            for (int z = -15; z <= 15; z++) {
                level.setBlock(roofCorner.offset(x, 0, z), Blocks.STONE.defaultBlockState(), 3);
            }
        }
        buildResourceIsland(level, origin.offset(SURVIVAL_X, 0, 0));
        BlockPos pit = origin.offset(PIT_X, 0, 0);
        for (int py = 0; py <= 3; py++) {
            for (int px = -1; px <= 1; px++) {
                for (int pz = -1; pz <= 1; pz++) {
                    if (px != 0 || pz != 0) {
                        level.setBlock(pit.offset(px, py, pz), Blocks.STONE.defaultBlockState(), 3);
                    }
                }
            }
        }
        PvpBotMod.LOGGER.info(TAG + "origin " + origin);
    }

    private static void buildResourceIsland(ServerLevel level, BlockPos c) {
        for (int x : new int[]{4, -5}) {
            for (int y = 0; y < 6; y++) {
                level.setBlock(c.offset(x, y, 5), Blocks.OAK_LOG.defaultBlockState(), 3);
            }
        }
        for (int x = 0; x < 3; x++) {
            for (int z = 0; z < 3; z++) {
                for (int y = 0; y < 2; y++) {
                    level.setBlock(c.offset(6 + x, y, -5 + z), Blocks.STONE.defaultBlockState(), 3);
                }
            }
        }
        for (int i = 0; i < 4; i++) {
            level.setBlock(c.offset(-1 + i, 0, -8), Blocks.COAL_ORE.defaultBlockState(), 3);
        }
        for (int x = 0; x < 5; x++) {
            for (int z = 0; z < 3; z++) {
                for (int y = 0; y < 2; y++) {
                    level.setBlock(c.offset(-9 + x, y, -5 + z), Blocks.IRON_ORE.defaultBlockState(), 3);
                }
            }
        }
        // A few ores buried under the grass: the bot has to dig down to them.
        for (int i = 0; i < 3; i++) {
            level.setBlock(c.offset(-2 + i, -2, 9), Blocks.IRON_ORE.defaultBlockState(), 3);
        }
        for (int i = 0; i < 3; i++) {
            Mob cow = EntityTypes.COW.create(level, EntitySpawnReason.COMMAND);
            cow.snapTo(c.getX() + 8.5 + i, c.getY(), c.getZ() + 8.5, 0.0F, 0.0F);
            cow.setPersistenceRequired();
            level.addFreshEntity(cow);
        }
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
        int x = origin.getX() + baseX + dx;
        mob.snapTo(x + 0.5, origin.getY(), origin.getZ() + dz + 0.5, 0.0F, 0.0F);
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
        if (index >= 0 && bot != null && bot.isRemoved() && bot.getRemovalReason() == Entity.RemovalReason.CHANGED_DIMENSION) {
            // Through a portal: the bot lives on as a new entity in the other dimension.
            for (ServerLevel l : server.getAllLevels()) {
                if (l.getEntity(bot.getUUID()) instanceof PvpBotEntity moved) {
                    bot = moved;
                    spawned.add(moved);
                    PvpBotMod.LOGGER.info(TAG + "  bot is now in " + l.dimension() + " at " + moved.blockPosition().toShortString());
                    if (l.dimension() == net.minecraft.world.level.Level.NETHER) {
                        // Test diagnostics only (the bot does not get this): where is the nearest fortress?
                        var structures = l.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.STRUCTURE);
                        var found = l.getChunkSource().getGenerator().findNearestMapStructure(l,
                                net.minecraft.core.HolderSet.direct(structures.getOrThrow(net.minecraft.world.level.levelgen.structure.BuiltinStructures.FORTRESS)),
                                moved.blockPosition(), 50, false);
                        BlockPos fortress = found == null ? null : found.getFirst();
                        PvpBotMod.LOGGER.info(TAG + "  (info) nearest fortress: " + (fortress == null ? "none" : fortress.toShortString()
                                + " = " + (int) Math.sqrt(fortress.distSqr(moved.blockPosition())) + " blocks away"));
                        var warped = l.findClosestBiome3d(b -> b.is(net.minecraft.world.level.biome.Biomes.WARPED_FOREST), moved.blockPosition(), 1200, 16, 16);
                        PvpBotMod.LOGGER.info(TAG + "  (info) nearest warped forest: " + (warped == null ? "none"
                                : warped.getFirst().toShortString() + " = " + (int) Math.sqrt(warped.getFirst().distSqr(moved.blockPosition())) + " blocks away"));
                    }
                    break;
                }
            }
            if (bot.isRemoved() && ++portalWait < 200) {
                return; // the copy in the other dimension shows up a moment later
            }
        }
        portalWait = 0;
        if (index >= 0 && bot != null && ticks % 1200 == 0 && bot.level() instanceof ServerLevel nether
                && nether.dimension() == net.minecraft.world.level.Level.NETHER) {
            // Test diagnostics only (the bot does not get this): spawners in the loaded chunks around it.
            int cx = bot.getBlockX() >> 4;
            int cz = bot.getBlockZ() >> 4;
            List<String> found = new ArrayList<>();
            int blazes = nether.getEntitiesOfClass(net.minecraft.world.entity.monster.Blaze.class, bot.getBoundingBox().inflate(96.0)).size();
            for (int dx = -8; dx <= 8; dx++) {
                for (int dz = -8; dz <= 8; dz++) {
                    var chunk = nether.getChunkSource().getChunkNow(cx + dx, cz + dz);
                    if (chunk != null) {
                        for (BlockPos p : chunk.getBlockEntities().keySet()) {
                            if (nether.getBlockState(p).is(net.minecraft.world.level.block.Blocks.SPAWNER)) {
                                found.add(p.toShortString() + " (" + (int) Math.sqrt(p.distSqr(bot.blockPosition())) + " away)");
                            }
                        }
                    }
                }
            }
            PvpBotMod.LOGGER.info(TAG + "  (info) bot at " + bot.blockPosition().toShortString() + ", spawners near: " + found + ", blazes within 96: " + blazes);
        }
        ServerLevel level = server.overworld();
        if (index < 0 || finished()) {
            if (index >= 0) {
                report();
            }
            cleanup();
            index++;
            if (index >= SCENARIOS.size()) {
                PvpBotMod.LOGGER.info(TAG + "voice chat running: " + de.samu.pvpbot.voice.BotVoice.available()
                        + ", babble samples: " + de.samu.pvpbot.voice.BotVoice.babble("Hallo, ich hole dir Eisen!", 7).length
                        + ", AI orders: " + PvpBotEntity.orderOptions());
                PvpBotMod.LOGGER.info(TAG + "==================== SUMMARY");
                RESULTS.forEach(r -> PvpBotMod.LOGGER.info(TAG + r));
                PvpBotMod.LOGGER.info(TAG + "==================== BRAIN");
                BotBrain.INSTANCE.summary(40).forEach(l -> PvpBotMod.LOGGER.info(TAG + l.replaceAll("§.", "")));
                BotBrain.INSTANCE.save();
                PvpBotMod.LOGGER.info(TAG + "==================== LEARNED STRATEGIES");
                de.samu.pvpbot.brain.TaskLearner.INSTANCE.summary().forEach(l -> PvpBotMod.LOGGER.info(TAG + l));
                de.samu.pvpbot.brain.TaskLearner.INSTANCE.save();
                PvpBotMod.LOGGER.info(TAG + "DONE");
                origin = null;
                server.halt(false);
                return;
            }
            start(level, SCENARIOS.get(index));
            return;
        }
        ticks++;
        if (SCENARIOS.get(index).name().startsWith("Etappe voll") && ticks % 20 == 0) {
            watchProgress();
        }
        if (SCENARIOS.get(index).name().startsWith("Etappe")) {
            TestWatcher.follow(bot);
        }
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

    // ------------------------------------------------------------------ full run: progress watch

    private static final java.util.LinkedHashMap<String, Integer> MILESTONES = new java.util.LinkedHashMap<>();
    private static net.minecraft.world.phys.@Nullable Vec3 anchor;
    private static @Nullable Object anchorLevel;
    private static String kitSig = "";
    private static int lastProgress;
    private static int longestStall;
    private static int stuckEpisodes;
    private static boolean stuckNow;
    /** How long without any progress counts as stuck (game seconds). */
    private static final int STUCK_SECONDS = 180;

    /** Progress = it moved on (6+ blocks, or another dimension) or its inventory changed (mined, crafted, picked up). */
    private static void watchProgress() {
        int now = ticks / 20;
        String sig = bot.getKit().items().stream().map(st -> st.getItem() + "x" + st.getCount()).sorted().toList().toString();
        boolean moved = anchor == null || anchorLevel != bot.level() || bot.position().distanceTo(anchor) > 6.0;
        if (moved || !sig.equals(kitSig)) {
            if (stuckNow) {
                PvpBotMod.LOGGER.info(TAG + String.format("  UNSTUCK at t=%ds after %ds (%s)", now, now - lastProgress, moved ? "moved on" : "inventory changed"));
                stuckNow = false;
            }
            anchor = bot.position();
            anchorLevel = bot.level();
            kitSig = sig;
            lastProgress = now;
        }
        int stall = now - lastProgress;
        longestStall = Math.max(longestStall, stall);
        if (stall >= STUCK_SECONDS && !stuckNow) {
            stuckNow = true;
            stuckEpisodes++;
            PvpBotMod.LOGGER.info(TAG + String.format("  STUCK #%d at t=%ds: no progress for %ds at %s in %s (water %s, ground %s, feet %s, below %s) | %s | kit %s",
                    stuckEpisodes, now, stall, bot.blockPosition().toShortString(), bot.level().dimension().toString(),
                    bot.isInWater(), bot.onGround(), bot.level().getBlockState(bot.blockPosition()).getBlock().getName().getString(),
                    bot.level().getBlockState(bot.blockPosition().below()).getBlock().getName().getString(),
                    bot.describeNeeds(), sig));
        }
        var kit = bot.getKit();
        milestone("Holz", kit.count(st -> st.is(net.minecraft.tags.ItemTags.LOGS)) > 0);
        milestone("Steinspitzhacke", kit.count(st -> st.is(Items.STONE_PICKAXE)) > 0);
        milestone("Eisenspitzhacke", kit.count(st -> st.is(Items.IRON_PICKAXE)) > 0);
        milestone("Eisenrüstung", bot.getItemBySlot(net.minecraft.world.entity.EquipmentSlot.CHEST).is(Items.IRON_CHESTPLATE));
        milestone("Wassereimer", kit.count(st -> st.is(Items.WATER_BUCKET)) > 0);
        milestone("Diamant", kit.count(st -> st.is(Items.DIAMOND)) > 0);
        milestone("Diamantspitzhacke", kit.count(st -> st.is(Items.DIAMOND_PICKAXE)) > 0);
        milestone("10 Obsidian", kit.count(st -> st.is(Items.OBSIDIAN)) >= 10);
        milestone("Netherportal gebaut", bot.portalBuilt());
        milestone("im Nether", bot.level().dimension() == net.minecraft.world.level.Level.NETHER);
        milestone("Lohenrute", kit.count(st -> st.is(Items.BLAZE_ROD)) > 0);
        milestone("Enderperle", kit.count(st -> st.is(Items.ENDER_PEARL)) > 0);
        milestone("Enderauge", kit.count(st -> st.is(Items.ENDER_EYE)) > 0);
        milestone("Etappe 2 fertig (Enderaugen)", bot.stage2Done());
        milestone("im End", bot.inEnd());
        milestone("Enderdrache besiegt", bot.gameBeaten());
    }

    private static void milestone(String name, boolean reached) {
        if (reached && !MILESTONES.containsKey(name)) {
            MILESTONES.put(name, ticks / 20);
            PvpBotMod.LOGGER.info(TAG + String.format("  MILESTONE %s at t=%ds (%d min)", name, ticks / 20, ticks / 1200));
        }
    }

    private static void start(ServerLevel level, Scenario scenario) {
        MILESTONES.clear();
        anchor = null;
        anchorLevel = null;
        kitSig = "";
        lastProgress = 0;
        longestStall = 0;
        stuckEpisodes = 0;
        stuckNow = false;
        ticks = 0;
        maxHeight = 0;
        smashHits = spearHits = otherHits = 0;
        maxHit = 0;
        flew = false;
        PvpBotMod.LOGGER.info(TAG + "==================== " + scenario.name());
        baseX = scenario.baseX();
        boolean end = scenario.name().startsWith("Etappe 4");
        if (end) {
            level = level.getServer().getLevel(net.minecraft.world.level.Level.END);
        }
        bot = PvpBotMod.PVP_BOT.create(level, EntitySpawnReason.COMMAND);
        bot.snapTo(origin.getX() + baseX + 0.5, origin.getY(), origin.getZ() + 0.5, 0.0F, 0.0F);
        boolean stage = scenario.name().startsWith("Etappe");
        if (stage) {
            int sx = end ? 0 : origin.getX() + baseX;
            int sz0 = end ? 60 : origin.getZ();
            if (scenario.name().startsWith("Etappe 2")) {
                // Portal ~60 blocks (nether) from the fortress at -752/-832 (overworld x8): the test is
                // about finding one, getting blaze rods and ender pearls.
                sx = -5600;
                sz0 = -6400;
                // (Any seed: the nearest fortress to the middle, start ~60 nether blocks from it.)
                ServerLevel nether = level.getServer().getLevel(net.minecraft.world.level.Level.NETHER);
                if (nether != null) {
                    var structures = nether.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.STRUCTURE);
                    var found = nether.getChunkSource().getGenerator().findNearestMapStructure(nether,
                            net.minecraft.core.HolderSet.direct(structures.getOrThrow(net.minecraft.world.level.levelgen.structure.BuiltinStructures.FORTRESS)),
                            new BlockPos(-700, 64, -800), 50, false);
                    if (found != null) {
                        BlockPos f = found.getFirst();
                        sx = (f.getX() + 50) * 8;
                        sz0 = (f.getZ() + 30) * 8;
                        PvpBotMod.LOGGER.info(TAG + "  (info) fortress at " + f.toShortString() + ", start ~60 blocks from it");
                    }
                }
            } else if (scenario.name().startsWith("Etappe 3")) {
                // Start ~300 blocks from the stronghold (the long walk is tested separately).
                BlockPos stronghold = level.findNearestMapStructure(net.minecraft.tags.StructureTags.EYE_OF_ENDER_LOCATED, origin, 100, false);
                if (stronghold != null) {
                    sx = stronghold.getX() + 300;
                    sz0 = stronghold.getZ();
                    PvpBotMod.LOGGER.info(TAG + "  (info) stronghold at " + stronghold.toShortString() + ", start 300 blocks east of it");
                }
            }
            int sz = sz0;
            level.getChunk(sx >> 4, sz >> 4); // loaded (not forced) to find the ground
            int sy = level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, sx, sz);
            if (sy <= level.getMinY() + 1) {
                // (Heightmap not ready yet, seen in the End: look for the ground by hand.)
                for (int y = 120; y > level.getMinY(); y--) {
                    if (!level.getBlockState(new BlockPos(sx, y - 1, sz)).isAir()) {
                        sy = y;
                        break;
                    }
                }
                PvpBotMod.LOGGER.info(TAG + "  (info) heightmap empty at start, ground found at y " + sy);
            }
            bot.snapTo(sx + 0.5, sy, sz + 0.5, 0.0F, 0.0F);
            level.getServer().getCommands().performPrefixedCommand(level.getServer().createCommandSourceStack(), "tick sprint " + scenario.timeoutTicks());
        }
        bot.setStyle(scenario.style());
        bot.setCustomName(Component.literal("TestBot"));
        if (scenario.kit() != null) {
            bot.setKit(scenario.kit().get().stream().map(ItemStack::copy).toList(), false);
        } else {
            bot.equipLoadout();
        }
        level.addFreshEntity(bot);
        spawned.add(bot);
        if (stage) {
            TestWatcher.follow(bot); // right away, so its chunks stay loaded
        }
        if (stage && (scenario.name().startsWith("Etappe 3") || end)) {
            bot.startAtStage3();
        } else if (stage) {
            bot.setSpeedrun(true);
        }
        if (scenario.name().startsWith("Zuhause")) {
            // Out of the spawn area: keep the chunks ticking.
            level.setChunkForced(bot.getBlockX() >> 4, bot.getBlockZ() >> 4, true);
            level.setChunkForced((bot.getBlockX() + 12) >> 4, bot.getBlockZ() >> 4, true);
            level.setChunkForced((bot.getBlockX() - 12) >> 4, bot.getBlockZ() >> 4, true);
            bot.setHome(bot.blockPosition().offset(4, 0, 0));
            bot.setAutonomous(true);
        }
        targets = scenario.targets().apply(level);
        for (LivingEntity target : targets) {
            bot.addTarget(target, true);
        }
    }

    private static boolean finished() {
        Scenario current = SCENARIOS.get(index);
        if (current.goal() != null) {
            if (ticks % 400 == 0) {
                PvpBotMod.LOGGER.info(TAG + "  kit: " + bot.getKit().items().stream()
                        .map(st -> st.getCount() + "x" + st.getItem().toString().replace("minecraft:", "")).toList()
                        + " | " + bot.describeNeeds() + " | pos " + bot.blockPosition().toShortString());
            }
            return current.goal().test(bot) || !bot.isAlive() || ticks >= current.timeoutTicks();
        }
        boolean allDead = targets.stream().noneMatch(LivingEntity::isAlive);
        // Give the bot a moment after the last kill so it can learn from the finishing blow.
        graceTicks = allDead ? graceTicks + 1 : 0;
        return allDead && graceTicks > 10 || !bot.isAlive() || ticks >= SCENARIOS.get(index).timeoutTicks();
    }

    private static void report() {
        Scenario scenario = SCENARIOS.get(index);
        long killed = targets.stream().filter(t -> !t.isAlive()).count();
        boolean pass = scenario.goal() != null ? scenario.goal().test(bot) && bot.isAlive() : killed == targets.size() && bot.isAlive();
        if (scenario.goal() != null) {
            PvpBotMod.LOGGER.info(TAG + "  final kit: " + bot.getKit().items().stream()
                    .map(st -> st.getCount() + "x" + st.getItem().toString().replace("minecraft:", "")).toList());
        }
        if (!bot.isAlive()) {
            PvpBotMod.LOGGER.info(TAG + "  bot gone: removal " + bot.getRemovalReason() + ", last damage "
                    + (bot.getLastDamageSource() == null ? "-" : bot.getLastDamageSource().typeHolder().getRegisteredName())
                    + " at " + bot.blockPosition().toShortString() + " in " + bot.level().dimension());
        }
        String line = String.format("%s %-40s kills=%d/%d time=%.1fs botAlive=%s botHp=%.1f smash=%d spear=%d other=%d maxHit=%.1f maxHeight=%d flew=%s",
                pass ? "PASS" : "FAIL", scenario.name(), killed, targets.size(), ticks / 20.0, bot.isAlive(),
                bot.getHealth(), smashHits, spearHits, otherHits, maxHit, maxHeight, flew);
        RESULTS.add(line);
        PvpBotMod.LOGGER.info(TAG + line);
        if (scenario.name().startsWith("Etappe voll")) {
            String full = String.format("FULL RUN: %d milestones %s | stuck (>%ds without progress): %d times, longest stall %ds",
                    MILESTONES.size(), MILESTONES.entrySet().stream().map(e -> e.getKey() + " " + e.getValue() / 60 + "min").toList(),
                    STUCK_SECONDS, stuckEpisodes, longestStall);
            RESULTS.add(full);
            PvpBotMod.LOGGER.info(TAG + full);
        }
    }

    private static List<ItemStack> homeKit() {
        return List.of(new ItemStack(Items.DIAMOND_SWORD), new ItemStack(Items.DIAMOND_PICKAXE), new ItemStack(Items.DIAMOND_HELMET),
                new ItemStack(Items.DIAMOND_CHESTPLATE), new ItemStack(Items.DIAMOND_LEGGINGS), new ItemStack(Items.DIAMOND_BOOTS),
                new ItemStack(Items.SHIELD), new ItemStack(Items.COOKED_BEEF, 16), new ItemStack(Items.IRON_HELMET),
                new ItemStack(Items.IRON_CHESTPLATE), new ItemStack(Items.IRON_LEGGINGS), new ItemStack(Items.IRON_BOOTS),
                new ItemStack(Items.OAK_PLANKS, 16), new ItemStack(Items.COBBLESTONE, 64), new ItemStack(Items.COBBLESTONE, 64),
                new ItemStack(Items.DIRT, 40));
    }

    /** Home test goal: a chest it placed holds the iron set, and it still wears diamond. */
    private static boolean ironSetStored(PvpBotEntity bot) {
        for (BlockPos pos : bot.homeChests()) {
            if (bot.level().getBlockEntity(pos) instanceof net.minecraft.world.Container chest) {
                int pieces = 0;
                for (Item piece : new Item[]{Items.IRON_HELMET, Items.IRON_CHESTPLATE, Items.IRON_LEGGINGS, Items.IRON_BOOTS}) {
                    for (int i = 0; i < chest.getContainerSize(); i++) {
                        if (chest.getItem(i).is(piece)) {
                            pieces++;
                            break;
                        }
                    }
                }
                if (pieces == 4 && bot.getItemBySlot(net.minecraft.world.entity.EquipmentSlot.CHEST).is(Items.DIAMOND_CHESTPLATE)) {
                    return true;
                }
            }
        }
        return false;
    }

    private static List<ItemStack> stage1Kit() {
        return List.of(new ItemStack(Items.IRON_SWORD), new ItemStack(Items.IRON_PICKAXE), new ItemStack(Items.IRON_HELMET),
                new ItemStack(Items.IRON_CHESTPLATE), new ItemStack(Items.IRON_LEGGINGS), new ItemStack(Items.IRON_BOOTS),
                new ItemStack(Items.SHIELD), new ItemStack(Items.COOKED_BEEF, 16), new ItemStack(Items.IRON_INGOT, 6),
                new ItemStack(Items.STICK, 8), new ItemStack(Items.OAK_PLANKS, 16));
    }

    private static List<ItemStack> stage2Kit() {
        List<ItemStack> kit = new ArrayList<>(stage1Kit());
        kit.add(new ItemStack(Items.DIAMOND_PICKAXE));
        kit.add(new ItemStack(Items.BOW));
        kit.add(new ItemStack(Items.ARROW, 64));
        kit.add(new ItemStack(Items.COOKED_BEEF, 32));
        // What stage 1 leaves in the inventory anyway: cobblestone (for bridging and pillaring).
        kit.add(new ItemStack(Items.COBBLESTONE, 64));
        kit.add(new ItemStack(Items.COBBLESTONE, 64));
        // ... and the water bucket it made the obsidian with.
        kit.add(new ItemStack(Items.WATER_BUCKET));
        // ... and what the portal is made of: it builds and lights it itself (the test builds nothing).
        kit.add(new ItemStack(Items.OBSIDIAN, 10));
        kit.add(new ItemStack(Items.FLINT_AND_STEEL));
        ItemStack fireRes = new ItemStack(Items.POTION);
        fireRes.set(net.minecraft.core.component.DataComponents.POTION_CONTENTS,
                new net.minecraft.world.item.alchemy.PotionContents(net.minecraft.world.item.alchemy.Potions.LONG_FIRE_RESISTANCE));
        kit.add(fireRes.copyWithCount(1));
        kit.add(fireRes.copyWithCount(1));
        kit.add(fireRes.copyWithCount(1));
        return kit;
    }

    private static List<ItemStack> stage3Kit() {
        List<ItemStack> kit = new ArrayList<>(stage2Kit());
        kit.add(new ItemStack(Items.ENDER_EYE, 16));
        return kit;
    }

    private static List<ItemStack> stage4Kit() {
        List<ItemStack> kit = new ArrayList<>(stage3Kit());
        kit.add(new ItemStack(Items.DIAMOND_SWORD));
        kit.add(new ItemStack(Items.ARROW, 64));
        return kit;
    }

    private static void cleanup() {
        if (!spawned.isEmpty() && spawned.get(0).level() instanceof ServerLevel sl) {
            sl.getServer().getCommands().performPrefixedCommand(sl.getServer().createCommandSourceStack(), "tick sprint stop");
        }
        spawned.forEach(Entity::discard);
        spawned.clear();
        TestWatcher.remove();
    }
}
