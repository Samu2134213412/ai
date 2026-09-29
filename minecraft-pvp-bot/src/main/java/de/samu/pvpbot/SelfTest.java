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
        SCENARIOS.add(new Scenario("Etappe 1: Diamanten, Obsidian, Netherportal", PvpBotEntity.Style.AUTO, 72000, 240,
                level -> List.of(), SelfTest::stage1Kit, PvpBotEntity::portalBuilt));
        SCENARIOS.add(new Scenario("Etappe 2: Nether, Lohenruten, Enderperlen", PvpBotEntity.Style.AUTO, 72000, -240,
                level -> List.of(), SelfTest::stage2Kit, PvpBotEntity::stage2Done));
        SCENARIOS.add(new Scenario("Etappe 3: Enderaugen werfen, Festung, Endportal", PvpBotEntity.Style.AUTO, 90000, 480,
                level -> List.of(), SelfTest::stage3Kit, PvpBotEntity::inEnd));
        SCENARIOS.add(new Scenario("Etappe 4: Endkristalle und Enderdrache", PvpBotEntity.Style.AUTO, 72000, 0,
                level -> List.of(), SelfTest::stage4Kit, PvpBotEntity::gameBeaten));

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
                    }
                    break;
                }
            }
            if (bot.isRemoved() && ++portalWait < 200) {
                return; // the copy in the other dimension shows up a moment later
            }
        }
        portalWait = 0;
        if (index >= 0 && bot != null && ticks % 3600 == 600 && SCENARIOS.get(index).name().startsWith("Etappe 4")
                && bot.level() instanceof ServerLevel end) {
            // Without a player the dragon hardly ever lands; in a real fight it does - make it land now and then.
            for (var dragon : end.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EnderDragon.class, bot.getBoundingBox().inflate(300.0))) {
                var phase = dragon.getPhaseManager().getCurrentPhase();
                boolean frozen = dragonLastPos != null && dragon.position().distanceTo(dragonLastPos) < 0.5 && !phase.isSitting();
                dragonLastPos = dragon.position();
                if (frozen) {
                    // A summoned dragon sometimes loses its flight path and just hangs there: start it again.
                    PvpBotMod.LOGGER.info(TAG + "  (test) dragon hung in " + phase.getPhase() + " at " + dragon.blockPosition().toShortString()
                            + " - restarting its flight (tickCount " + dragon.tickCount + ", noAi " + dragon.isNoAi() + ", entity ticking "
                            + end.isPositionEntityTicking(dragon.blockPosition()) + ", removed " + dragon.isRemoved() + ", same level " + (dragon.level() == end)
                            + ", dragons in level " + end.getDragons().size() + ", forced chunks " + end.getForceLoadedChunks().size() + ", bot pos ticking " + end.isPositionEntityTicking(bot.blockPosition()) + ")");
                    // Its chunk is not ticking here (no player around): bring it back over the island.
                    for (int dx = -1; dx <= 1; dx++) {
                        for (int dz = -1; dz <= 1; dz++) {
                            end.setChunkForced((dragon.getBlockX() >> 4) + dx, (dragon.getBlockZ() >> 4) + dz, true);
                        }
                    }
                    dragon.snapTo(0.5, 85.0, 0.5, dragon.getYRot(), 0.0F);
                    dragon.getPhaseManager().setPhase(net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.HOLDING_PATTERN);
                } else if (phase.getPhase() == net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.HOLDING_PATTERN) {
                    dragon.getPhaseManager().setPhase(net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.LANDING);
                }
            }
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
                PvpBotMod.LOGGER.info(TAG + "==================== BRAIN");
                BotBrain.INSTANCE.summary(40).forEach(l -> PvpBotMod.LOGGER.info(TAG + l.replaceAll("§.", "")));
                BotBrain.INSTANCE.save();
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
            level.setChunkForced(sx >> 4, sz >> 4, true);
            int sy = level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, sx, sz);
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
        if (stage && scenario.name().startsWith("Etappe 2")) {
            // Start next to a lit portal (what stage 1 leaves behind), on a flat patch so it can walk in.
            BlockPos base = bot.blockPosition().offset(2, -1, 0);
            for (BlockPos p : BlockPos.betweenClosed(base.offset(-3, 0, -2), base.offset(3, 6, 5))) {
                level.setBlock(p, p.getY() == base.getY() ? Blocks.STONE.defaultBlockState() : Blocks.AIR.defaultBlockState(), 18);
            }
            // Frame first, then the portal blocks (a portal block next to an unfinished frame breaks).
            for (int pass = 0; pass < 2; pass++) {
                for (int i = 0; i < 4; i++) {
                    for (int j = 0; j < 5; j++) {
                        BlockPos p = base.offset(0, j, i);
                        boolean frame = i == 0 || i == 3 || j == 0 || j == 4;
                        if (frame == (pass == 0)) {
                            level.setBlock(p, frame ? Blocks.OBSIDIAN.defaultBlockState()
                                    : Blocks.NETHER_PORTAL.defaultBlockState().setValue(net.minecraft.world.level.block.NetherPortalBlock.AXIS,
                                    net.minecraft.core.Direction.Axis.Z), 18);
                        }
                    }
                }
            }
            bot.startAtStage2(base.offset(0, 1, 1));
        } else if (stage && (scenario.name().startsWith("Etappe 3") || end)) {
            bot.startAtStage3();
            if (end) {
                // No player here: keep the island ticking (the dragon freezes in unticked chunks). A real
                // fight does this with the dragon ticket around the island once a player is there.
                level.getChunkSource().addTicketWithRadius(net.minecraft.server.level.TicketType.DRAGON, new net.minecraft.world.level.ChunkPos(0, 0), 9);
                for (int cx = -7; cx <= 6; cx++) {
                    for (int cz = -7; cz <= 6; cz++) {
                        level.setChunkForced(cx, cz, true);
                    }
                }
            }
            if (end && level.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EnderDragon.class,
                    new net.minecraft.world.phys.AABB(-300, -64, -300, 300, 320, 300)).isEmpty()) {
                // Without a player nearby the End never spawns its dragon on its own.
                var dragon = net.minecraft.world.entity.EntityTypes.ENDER_DRAGON.create(level, EntitySpawnReason.COMMAND);
                if (dragon != null) {
                    dragon.snapTo(0.5, 90.0, 0.5, 0.0F, 0.0F);
                    // A summoned dragon just hovers; the real fight starts it circling like this.
                    dragon.getPhaseManager().setPhase(net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.HOLDING_PATTERN);
                    level.addFreshEntity(dragon);
                    spawned.add(dragon);
                }
            }
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
        String line = String.format("%s %-40s kills=%d/%d time=%.1fs botAlive=%s botHp=%.1f smash=%d spear=%d other=%d maxHit=%.1f maxHeight=%d flew=%s",
                pass ? "PASS" : "FAIL", scenario.name(), killed, targets.size(), ticks / 20.0, bot.isAlive(),
                bot.getHealth(), smashHits, spearHits, otherHits, maxHit, maxHeight, flew);
        RESULTS.add(line);
        PvpBotMod.LOGGER.info(TAG + line);
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

    private static net.minecraft.world.phys.@org.jspecify.annotations.Nullable Vec3 dragonLastPos;

    private static void cleanup() {
        if (!spawned.isEmpty() && spawned.get(0).level() instanceof ServerLevel sl) {
            sl.getServer().getCommands().performPrefixedCommand(sl.getServer().createCommandSourceStack(), "tick sprint stop");
        }
        spawned.forEach(Entity::discard);
        spawned.clear();
    }
}
