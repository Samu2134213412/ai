package de.samu.pvpbot.entity;

import de.samu.pvpbot.PvpBotMod;
import de.samu.pvpbot.brain.Kit;
import de.samu.pvpbot.brain.Kit.Role;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.tags.BlockTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.util.Mth;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

/**
 * Lets a bot with a survival kit get what it is missing by itself: it works out a chain of steps
 * (e.g. iron sword ← iron ingots ← raw iron ← iron ore ← stone pickaxe ← cobblestone ← wooden
 * pickaxe ← planks ← logs), really mines and hunts for the raw materials, and crafts/smelts
 * "in its head" (no table or furnace is placed, but materials and fuel are really used up).
 */
final class Gatherer {

    /** Raw materials and intermediate products the planner works with. */
    enum Res {
        LOG("Holz", s -> s.is(ItemTags.LOGS)),
        PLANKS("Bretter", s -> s.is(ItemTags.PLANKS)),
        STICK("Stöcke", s -> s.is(Items.STICK)),
        COBBLE("Bruchstein", s -> s.is(ItemTags.STONE_TOOL_MATERIALS)),
        COAL("Kohle", s -> s.is(Items.COAL) || s.is(Items.CHARCOAL)),
        RAW_IRON("Roheisen", s -> s.is(Items.RAW_IRON)),
        IRON("Eisenbarren", s -> s.is(Items.IRON_INGOT)),
        DIAMOND("Diamanten", s -> s.is(Items.DIAMOND)),
        OBSIDIAN("Obsidian", s -> s.is(Items.OBSIDIAN)),
        FLINT("Feuerstein", s -> s.is(Items.FLINT)),
        BLAZE_ROD("Lohenruten", s -> s.is(Items.BLAZE_ROD)),
        BLAZE_POWDER("Lohenstaub", s -> s.is(Items.BLAZE_POWDER)),
        PEARL("Enderperlen", s -> s.is(Items.ENDER_PEARL)),
        EYE("Enderaugen", s -> s.is(Items.ENDER_EYE)),
        STRING("Faden", s -> s.is(Items.STRING)),
        FEATHER("Federn", s -> s.is(Items.FEATHER)),
        RAW_MEAT("rohes Fleisch", s -> s.is(Items.BEEF) || s.is(Items.PORKCHOP) || s.is(Items.CHICKEN) || s.is(Items.MUTTON) || s.is(Items.RABBIT)),
        COOKED_MEAT("gebratenes Fleisch", s -> s.is(Items.COOKED_BEEF) || s.is(Items.COOKED_PORKCHOP) || s.is(Items.COOKED_CHICKEN)
                || s.is(Items.COOKED_MUTTON) || s.is(Items.COOKED_RABBIT) || s.is(Items.BREAD));

        final String label;
        final Predicate<ItemStack> match;

        Res(String label, Predicate<ItemStack> match) {
            this.label = label;
            this.match = match;
        }
    }

    /** Blocks the bot can mine for raw materials. */
    enum Ore {
        LOG("Holz", Res.LOG, s -> s.is(BlockTags.LOGS)),
        STONE("Stein", Res.COBBLE, s -> s.is(BlockTags.BASE_STONE_OVERWORLD) || s.is(net.minecraft.world.level.block.Blocks.COBBLESTONE)),
        COAL("Kohleerz", Res.COAL, s -> s.is(net.minecraft.world.level.block.Blocks.COAL_ORE) || s.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_COAL_ORE)),
        IRON("Eisenerz", Res.RAW_IRON, s -> s.is(BlockTags.IRON_ORES)),
        DIAMOND("Diamanterz", Res.DIAMOND, s -> s.is(net.minecraft.world.level.block.Blocks.DIAMOND_ORE) || s.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_DIAMOND_ORE)),
        OBSIDIAN("Obsidian", Res.OBSIDIAN, s -> s.is(net.minecraft.world.level.block.Blocks.OBSIDIAN)),
        GRAVEL("Kies", Res.FLINT, s -> s.is(net.minecraft.world.level.block.Blocks.GRAVEL)),
        LAVA("Lava", Res.OBSIDIAN, s -> s.getFluidState().is(net.minecraft.tags.FluidTags.LAVA) && s.getFluidState().isSource()),
        WATER("Wasser", Res.OBSIDIAN, s -> s.getFluidState().is(net.minecraft.tags.FluidTags.WATER) && s.getFluidState().isSource()),
        FORTRESS("Netherfestung", Res.BLAZE_ROD, s -> s.is(net.minecraft.world.level.block.Blocks.NETHER_BRICKS)
                || s.is(net.minecraft.world.level.block.Blocks.NETHER_BRICK_FENCE)),
        SPAWNER("Spawner", Res.BLAZE_ROD, s -> s.is(net.minecraft.world.level.block.Blocks.SPAWNER)),
        // The blue warped forest: where endermen are in the nether.
        WARPED("Wirrwald", Res.PEARL, s -> s.is(net.minecraft.world.level.block.Blocks.WARPED_NYLIUM)
                || s.is(net.minecraft.world.level.block.Blocks.WARPED_STEM) || s.is(net.minecraft.world.level.block.Blocks.WARPED_WART_BLOCK)),
        PORTAL("Netherportal", Res.OBSIDIAN, s -> s.is(net.minecraft.world.level.block.Blocks.NETHER_PORTAL)),
        STRONGHOLD("Festungsmauern", Res.EYE, s -> s.is(net.minecraft.world.level.block.Blocks.STONE_BRICKS) || s.is(net.minecraft.world.level.block.Blocks.MOSSY_STONE_BRICKS)
                || s.is(net.minecraft.world.level.block.Blocks.CRACKED_STONE_BRICKS) || s.is(net.minecraft.world.level.block.Blocks.INFESTED_STONE_BRICKS) || s.is(net.minecraft.world.level.block.Blocks.INFESTED_MOSSY_STONE_BRICKS)
                || s.is(net.minecraft.world.level.block.Blocks.INFESTED_CRACKED_STONE_BRICKS)),
        END_FRAME("Endportalrahmen", Res.EYE, s -> s.is(net.minecraft.world.level.block.Blocks.END_PORTAL_FRAME)),
        END_PORTAL("Endportal", Res.EYE, s -> s.is(net.minecraft.world.level.block.Blocks.END_PORTAL));

        final String label;
        final Res gives;
        final Predicate<BlockState> match;

        Ore(String label, Res gives, Predicate<BlockState> match) {
            this.label = label;
            this.gives = gives;
            this.match = match;
        }
    }

    record Ingredient(Res res, int count) {
    }

    record Recipe(Item output, int outputCount, List<Ingredient> ingredients) {
    }

    private static final Map<Item, Recipe> RECIPES = new java.util.HashMap<>();

    private static void recipe(Item out, int count, Object... ingredients) {
        List<Ingredient> list = new ArrayList<>();
        for (int i = 0; i + 1 < ingredients.length; i += 2) {
            list.add(new Ingredient((Res) ingredients[i], (Integer) ingredients[i + 1]));
        }
        RECIPES.put(out, new Recipe(out, count, list));
    }

    static {
        recipe(Items.OAK_PLANKS, 4, Res.LOG, 1);
        recipe(Items.STICK, 4, Res.PLANKS, 2);
        recipe(Items.WOODEN_PICKAXE, 1, Res.PLANKS, 3, Res.STICK, 2);
        recipe(Items.WOODEN_SWORD, 1, Res.PLANKS, 2, Res.STICK, 1);
        recipe(Items.STONE_PICKAXE, 1, Res.COBBLE, 3, Res.STICK, 2);
        recipe(Items.STONE_SWORD, 1, Res.COBBLE, 2, Res.STICK, 1);
        recipe(Items.IRON_PICKAXE, 1, Res.IRON, 3, Res.STICK, 2);
        recipe(Items.IRON_SWORD, 1, Res.IRON, 2, Res.STICK, 1);
        recipe(Items.IRON_HELMET, 1, Res.IRON, 5);
        recipe(Items.IRON_CHESTPLATE, 1, Res.IRON, 8);
        recipe(Items.IRON_LEGGINGS, 1, Res.IRON, 7);
        recipe(Items.IRON_BOOTS, 1, Res.IRON, 4);
        recipe(Items.SHIELD, 1, Res.PLANKS, 6, Res.IRON, 1);
        recipe(Items.CHEST, 1, Res.PLANKS, 8);
        recipe(Items.DIAMOND_SWORD, 1, Res.DIAMOND, 2, Res.STICK, 1);
        recipe(Items.DIAMOND_PICKAXE, 1, Res.DIAMOND, 3, Res.STICK, 2);
        recipe(Items.DIAMOND_HELMET, 1, Res.DIAMOND, 5);
        recipe(Items.DIAMOND_CHESTPLATE, 1, Res.DIAMOND, 8);
        recipe(Items.DIAMOND_LEGGINGS, 1, Res.DIAMOND, 7);
        recipe(Items.DIAMOND_BOOTS, 1, Res.DIAMOND, 4);
        recipe(Items.BUCKET, 1, Res.IRON, 3);
        recipe(Items.FLINT_AND_STEEL, 1, Res.IRON, 1, Res.FLINT, 1);
        recipe(Items.BLAZE_POWDER, 2, Res.BLAZE_ROD, 1);
        recipe(Items.ENDER_EYE, 1, Res.BLAZE_POWDER, 1, Res.PEARL, 1);
        recipe(Items.BOW, 1, Res.STRING, 3, Res.STICK, 3);
        recipe(Items.ARROW, 4, Res.FLINT, 1, Res.STICK, 1, Res.FEATHER, 1);
    }

    private static final Item[] IRON_ARMOR = {Items.IRON_HELMET, Items.IRON_CHESTPLATE, Items.IRON_LEGGINGS, Items.IRON_BOOTS};
    private static final Item[] DIAMOND_ARMOR = {Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS};
    private static final EquipmentSlot[] ARMOR_SLOTS = {EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET};

    /** The next thing to do. */
    sealed interface Step permits Craft, Smelt, Mine, Hunt, Explore, Descend, StripMine, FillWater, MakeObsidian, BuildPortal,
            UsePortal, HuntMob, ExploreNether, ThrowEye, FollowEye, ExploreStronghold, FillEndPortal, UseEndPortal, ShootCrystal, FightDragon,
            GoHome, PlaceChest, StoreAtHome, ClimbUp {
        String describe();
    }

    record Craft(Recipe recipe) implements Step {
        public String describe() {
            return "stellt " + new ItemStack(this.recipe.output()).getHoverName().getString() + " her";
        }
    }

    record Smelt(Res input, Res output) implements Step {
        public String describe() {
            return "brät/schmilzt " + this.input.label;
        }
    }

    record Mine(Ore ore) implements Step {
        public String describe() {
            return "baut " + this.ore.label + " ab";
        }
    }

    record GoHome() implements Step {
        public String describe() {
            return "geht nach Hause";
        }
    }

    record PlaceChest() implements Step {
        public String describe() {
            return "stellt zu Hause eine Kiste auf";
        }
    }

    record StoreAtHome(BlockPos chest) implements Step {
        public String describe() {
            return "lagert Sachen in der Kiste zu Hause";
        }
    }

    record Hunt() implements Step {
        public String describe() {
            return "jagt Tiere für Essen";
        }
    }

    record ClimbUp(String reason) implements Step {
        public String describe() {
            return "steigt nach oben (" + this.reason + ")";
        }
    }

    record Explore(String reason) implements Step {
        public String describe() {
            return "sucht " + this.reason;
        }
    }

    record Descend() implements Step {
        public String describe() {
            return "gräbt eine Treppe nach unten auf Diamant-Höhe";
        }
    }

    record StripMine() implements Step {
        public String describe() {
            return "gräbt Stollen (Strip-Mining)";
        }
    }

    record FillWater() implements Step {
        public String describe() {
            return "füllt den Eimer mit Wasser";
        }
    }

    record MakeObsidian() implements Step {
        public String describe() {
            return "gießt Wasser auf Lava (Obsidian)";
        }
    }

    record UsePortal(boolean toNether) implements Step {
        public String describe() {
            return this.toNether ? "geht durchs Portal in den Nether" : "geht durchs Portal zurück in die Oberwelt";
        }
    }

    record HuntMob(String label, net.minecraft.world.entity.EntityType<?> type) implements Step {
        public String describe() {
            return "jagt " + this.label;
        }
    }

    record ExploreNether(String reason) implements Step {
        public String describe() {
            return "erkundet den Nether (" + this.reason + ")";
        }
    }

    record ThrowEye() implements Step {
        public String describe() {
            return "wirft ein Enderauge";
        }
    }

    record FollowEye() implements Step {
        public String describe() {
            return "folgt dem Enderauge";
        }
    }

    record ExploreStronghold() implements Step {
        public String describe() {
            return "erkundet die Festung";
        }
    }

    record FillEndPortal() implements Step {
        public String describe() {
            return "setzt Enderaugen in den Portalrahmen";
        }
    }

    record UseEndPortal() implements Step {
        public String describe() {
            return "springt ins Endportal";
        }
    }

    record FightDragon() implements Step {
        public String describe() {
            return "kämpft gegen den Enderdrachen";
        }
    }

    record ShootCrystal() implements Step {
        public String describe() {
            return "schießt Endkristalle ab";
        }
    }

    record BuildPortal() implements Step {
        public String describe() {
            return "baut das Netherportal";
        }
    }

    private final PvpBotEntity bot;
    private boolean enabled = true;
    private @Nullable Step step;
    private @Nullable String goalLabel;
    private int replanTimer;
    private int actionTicks;
    private int fuel;

    // Block memory from scanning.
    private final Map<Ore, List<BlockPos>> known = new EnumMap<>(Ore.class);
    private final Map<Ore, List<BlockPos>> scanning = new EnumMap<>(Ore.class);
    private int scanLayer = Integer.MIN_VALUE;
    private @Nullable BlockPos scanCenter;

    // Current mining job.
    private @Nullable BlockPos mineTarget;
    private final java.util.Set<BlockPos> blacklist = new java.util.HashSet<>();
    private @Nullable BlockPos breaking;
    private int breakProgress;
    private int breakNeeded;
    private int noProgressTicks;
    private @Nullable Vec3 lastPos;
    private @Nullable Vec3 exploreTarget;
    private double exploreHeading = Double.NaN;
    private @Nullable Vec3 anchor;
    private @Nullable String lastAnnounced;

    // "Beat the game" mode, stage 1: diamonds, obsidian and a lit nether portal.
    private boolean speedrun;
    private boolean portalBuilt;
    private Direction digDir = Direction.NORTH;
    private final java.util.Set<Long> dugTunnel = new java.util.HashSet<>();
    private @Nullable BlockPos mineSince;
    private int mineTargetTicks;
    private int digBlocked;
    private int dryWalkTicks;
    private int portalProgress;
    private @Nullable BlockPos portalBase;
    private Direction portalAlong = Direction.EAST;
    private final java.util.Set<Long> forcedChunks = new java.util.HashSet<>();
    // Stage 2: the nether (blaze rods, ender pearls, eyes of ender).
    static final int EYES_WANTED = 16;
    private @Nullable BlockPos overworldPortal;
    private @Nullable BlockPos netherPortal;
    private boolean stage2Done;
    // Stage 3 and 4: stronghold and the dragon.
    static final int ARROWS_WANTED = 16;
    private @Nullable Vec3 eyeDir;
    private @Nullable Vec3 legStart;
    private boolean eyeWentDown;
    private int legTicks;
    private @Nullable BlockPos lastSafe;
    private double legBest;
    private int legStuckTicks;
    private @Nullable BlockPos netherGoal;
    private @Nullable BlockPos strongholdTarget;
    private int strongholdTicks;
    private int strongholdCells;
    private double netherGoalBest;
    private int netherGoalTotal;
    private @Nullable BlockPos netherStuckPos;
    private int netherGoalTicks;
    private final java.util.Set<Long> visitedCells = new java.util.HashSet<>();
    private boolean seenDragon;
    private boolean gameBeaten;
    // Home and autonomous mode.
    private boolean autonomous;
    private boolean goingHome;
    private @Nullable BlockPos home;
    private net.minecraft.resources.@Nullable ResourceKey<net.minecraft.world.level.Level> homeLevel;
    private final List<BlockPos> homeChests = new ArrayList<>();
    private final java.util.Map<java.util.UUID, Integer> crystalShots = new java.util.HashMap<>();

    Gatherer(PvpBotEntity bot) {
        this.bot = bot;
    }

    boolean isEnabled() {
        return this.enabled;
    }

    void setEnabled(boolean enabled) {
        this.enabled = enabled;
        this.reset();
    }

    boolean isAutonomousMode() {
        return this.autonomous;
    }

    boolean isSpeedrun() {
        return this.speedrun;
    }

    void setSpeedrun(boolean speedrun) {
        this.speedrun = speedrun;
        this.enabled = this.enabled || speedrun;
        this.reset();
        if (!speedrun) {
            this.releaseChunks();
        }
    }

    boolean portalBuilt() {
        return this.portalBuilt;
    }

    boolean stage2Done() {
        return this.stage2Done;
    }

    void setStage2Done(boolean done) {
        this.stage2Done = done;
    }

    @Nullable BlockPos overworldPortal() {
        return this.overworldPortal;
    }

    @Nullable BlockPos netherPortal() {
        return this.netherPortal;
    }

    void setPortals(@Nullable BlockPos overworld, @Nullable BlockPos nether) {
        this.overworldPortal = overworld;
        this.netherPortal = nether;
    }

    boolean isAutonomous() {
        return this.autonomous;
    }

    /** Chests go anywhere within this many blocks of home. */
    static final int CHEST_RADIUS = 10;

    void setAutonomous(boolean autonomous) {
        this.autonomous = autonomous;
        this.enabled = this.enabled || autonomous;
        this.reset();
    }

    /**
     * Chests that already stand within CHEST_RADIUS of home are used too (only looked for while the
     * bot is at home, so it knows its own base, nothing more).
     */
    private void findHomeChests(ServerLevel level) {
        if (this.home == null || !this.atHomeLevel() || this.bot.tickCount % 100 != 0
                || this.bot.blockPosition().distSqr(this.home) > 16 * 16) {
            return;
        }
        for (BlockPos p : BlockPos.betweenClosed(this.home.offset(-CHEST_RADIUS, -4, -CHEST_RADIUS), this.home.offset(CHEST_RADIUS, 4, CHEST_RADIUS))) {
            if (p.distSqr(this.home) <= CHEST_RADIUS * CHEST_RADIUS && this.chestAt(p) != null && !this.homeChests.contains(p)) {
                this.homeChests.add(p.immutable());
            }
        }
    }

    @Nullable BlockPos home() {
        return this.home;
    }

    net.minecraft.resources.@Nullable ResourceKey<net.minecraft.world.level.Level> homeLevel() {
        return this.homeLevel;
    }

    void setHome(@Nullable BlockPos home, net.minecraft.resources.@Nullable ResourceKey<net.minecraft.world.level.Level> level) {
        this.home = home;
        this.homeLevel = home == null ? null : level;
        this.reset();
    }

    void goHome() {
        this.goingHome = this.home != null;
        this.step = null;
    }

    List<BlockPos> homeChests() {
        return this.homeChests;
    }

    boolean gameBeaten() {
        return this.gameBeaten;
    }

    void setGameBeaten(boolean beaten) {
        this.gameBeaten = beaten;
    }

    private boolean inEnd() {
        return this.bot.level().dimension() == net.minecraft.world.level.Level.END;
    }

    private boolean inNether() {
        return this.bot.level().dimension() == net.minecraft.world.level.Level.NETHER;
    }

    void setPortalBuilt(boolean built) {
        this.portalBuilt = built;
    }

    /** Far away from every player the bot would stop; keep the chunks around it loaded. */
    void keepChunksLoaded() {
        if (!this.speedrun && !this.autonomous || this.bot.tickCount % 20 != 0) {
            return;
        }
        ServerLevel level = this.level();
        java.util.Set<Long> wanted = new java.util.HashSet<>();
        int cx = this.bot.blockPosition().getX() >> 4;
        int cz = this.bot.blockPosition().getZ() >> 4;
        for (int dx = -1; dx <= 1; dx++) {
            for (int dz = -1; dz <= 1; dz++) {
                wanted.add(chunkKey(cx + dx, cz + dz));
            }
        }
        for (long key : this.forcedChunks) {
            if (!wanted.contains(key)) {
                level.setChunkForced((int) (key >> 32), (int) key, false);
            }
        }
        java.util.Set<Long> ours = new java.util.HashSet<>();
        for (long key : wanted) {
            if (this.forcedChunks.contains(key)) {
                ours.add(key);
            } else if (!level.getForceLoadedChunks().contains((key >> 32 & 0xFFFFFFFFL) | (key & 0xFFFFFFFFL) << 32)) {
                // Only the ones it loads itself are its to release again (never someone else's /forceload).
                level.setChunkForced((int) (key >> 32), (int) key, true);
                ours.add(key);
            }
        }
        this.forcedChunks.clear();
        this.forcedChunks.addAll(ours);
    }

    private int spawnerDelay = 20;
    private @Nullable BlockPos activeSpawner;
    private int naturalSpawnTicks;

    /**
     * Spawners and natural spawning only happen around players; playing on its own, the bot counts
     * as one (like the game would with a player standing here) - otherwise no blaze or enderman
     * ever shows up. Only while no real player is close enough to do it anyway.
     */
    void actLikePlayerForSpawns() {
        if (!this.speedrun && !this.autonomous) {
            return;
        }
        ServerLevel level = this.level();
        if (level.getDifficulty() == net.minecraft.world.Difficulty.PEACEFUL) {
            return;
        }
        // A spawner within 16 blocks (like vanilla): 4 mobs every 10 to 40 seconds, at most 6 around.
        // (The countdown only runs while a spawner is in reach, like in the game; checked once a second.)
        if (this.bot.tickCount % 20 == 0) {
            this.activeSpawner = null;
            // (Every spawner within reach counts, seen or not - like with a player standing here.)
            BlockPos spawner = null;
            int cx = this.bot.getBlockX() >> 4;
            int cz = this.bot.getBlockZ() >> 4;
            for (int dx = -1; dx <= 1 && spawner == null; dx++) {
                for (int dz = -1; dz <= 1 && spawner == null; dz++) {
                    var chunk = level.getChunkSource().getChunkNow(cx + dx, cz + dz);
                    if (chunk == null) {
                        continue;
                    }
                    for (BlockPos p : chunk.getBlockEntities().keySet()) {
                        if (p.closerToCenterThan(this.bot.position(), 16.0) && level.getBlockState(p).is(Blocks.SPAWNER)) {
                            spawner = p;
                            break;
                        }
                    }
                }
            }
            this.activeSpawner = spawner;
        }
        BlockPos spawner = this.activeSpawner;
        if (spawner == null) {
            this.spawnerDelay = Math.max(this.spawnerDelay, 20);
        } else if (--this.spawnerDelay <= 0) {
            this.spawnerDelay = 200 + this.bot.getRandom().nextInt(601);
            if (level.getBlockState(spawner).is(Blocks.SPAWNER)
                    && !level.hasNearbyAlivePlayer(spawner.getX() + 0.5, spawner.getY() + 0.5, spawner.getZ() + 0.5, 16.0)
                    && level.dimension() == net.minecraft.world.level.Level.NETHER) {
                // (Fortress spawners are blaze spawners.)
                int around = level.getEntitiesOfClass(net.minecraft.world.entity.monster.Blaze.class, new AABB(spawner).inflate(4.0, 1.0, 4.0)).size();
                for (int i = 0; i < 4 && around < 6; i++) {
                    double x = spawner.getX() + 0.5 + (this.bot.getRandom().nextDouble() - this.bot.getRandom().nextDouble()) * 4.0;
                    double y = spawner.getY() + this.bot.getRandom().nextInt(3) - 1;
                    double z = spawner.getZ() + 0.5 + (this.bot.getRandom().nextDouble() - this.bot.getRandom().nextDouble()) * 4.0;
                    var blaze = EntityTypes.BLAZE.create(level, net.minecraft.world.entity.EntitySpawnReason.SPAWNER);
                    if (blaze == null) {
                        break;
                    }
                    blaze.snapTo(x, y, z, this.bot.getRandom().nextFloat() * 360.0F, 0.0F);
                    if (level.noCollision(blaze) && !level.containsAnyLiquid(blaze.getBoundingBox())) {
                        level.addFreshEntity(blaze);
                        level.levelEvent(2004, spawner, 0); // the spawner's flame puff
                        blaze.spawnAnim();
                        around++;
                    }
                }
            }
        }
        // Natural spawning of endermen in the nether (warped forests, soul sand valleys, wastes).
        if (level.dimension() == net.minecraft.world.level.Level.NETHER && ++this.naturalSpawnTicks >= 200) {
            this.naturalSpawnTicks = 0;
            if (level.hasNearbyAlivePlayer(this.bot.getX(), this.bot.getY(), this.bot.getZ(), 128.0)
                    || level.getEntities(EntityTypes.ENDERMAN, this.bot.getBoundingBox().inflate(64.0), e -> e.isAlive()).size() >= 6) {
                return;
            }
            double angle = this.bot.getRandom().nextDouble() * Math.PI * 2.0;
            double dist = 24.0 + this.bot.getRandom().nextDouble() * 24.0;
            int x = Mth.floor(this.bot.getX() + Math.cos(angle) * dist);
            int z = Mth.floor(this.bot.getZ() + Math.sin(angle) * dist);
            for (int dy = -8; dy <= 8; dy++) {
                BlockPos feet = new BlockPos(x, this.bot.getBlockY() + dy, z);
                if (feet.getY() >= 127) {
                    break; // (nothing spawns up on the bedrock roof)
                }
                if (!level.getBlockState(feet.below()).isFaceSturdy(level, feet.below(), Direction.UP)
                        || !level.getBlockState(feet).isAir() || !level.getBlockState(feet.above()).isAir() || !level.getBlockState(feet.above(2)).isAir()) {
                    continue;
                }
                var biome = level.getBiome(feet);
                // (In a warped forest endermen are nearly all that spawns; elsewhere they are rare.)
                int chance = biome.is(net.minecraft.world.level.biome.Biomes.WARPED_FOREST) ? 1
                        : biome.is(net.minecraft.world.level.biome.Biomes.SOUL_SAND_VALLEY) || biome.is(net.minecraft.world.level.biome.Biomes.NETHER_WASTES) ? 10 : 0;
                if (chance > 0 && this.bot.getRandom().nextInt(chance) == 0) {
                    var enderman = EntityTypes.ENDERMAN.create(level, net.minecraft.world.entity.EntitySpawnReason.NATURAL);
                    if (enderman != null) {
                        enderman.snapTo(x + 0.5, feet.getY(), z + 0.5, this.bot.getRandom().nextFloat() * 360.0F, 0.0F);
                        if (level.noCollision(enderman)) {
                            level.addFreshEntity(enderman);
                        }
                    }
                }
                break;
            }
        }
    }

    private static long chunkKey(int x, int z) {
        return (long) x << 32 | z & 0xFFFFFFFFL;
    }

    void releaseChunks() {
        if (this.bot.level() instanceof ServerLevel level) {
            for (long key : this.forcedChunks) {
                level.setChunkForced((int) (key >> 32), (int) key, false);
            }
        }
        this.forcedChunks.clear();
    }

    int fuel() {
        return this.fuel;
    }

    void setFuel(int fuel) {
        this.fuel = fuel;
    }

    private BotKit kit() {
        return this.bot.getKit();
    }

    private ServerLevel level() {
        return (ServerLevel) this.bot.level();
    }

    /** True when there is something to fetch and nothing more important going on. */
    boolean wantsToWork() {
        if (this.goingHome && this.bot.getTarget() == null) {
            if (this.home == null || !this.atHomeLevel() || this.bot.blockPosition().distSqr(this.home) <= 3 * 3) {
                this.goingHome = false;
                this.step = null;
            } else {
                if (!(this.step instanceof GoHome)) {
                    this.step = new GoHome();
                    this.goalLabel = "Befehl: nach Hause";
                }
                return true;
            }
        }
        if (!this.enabled || this.kit().isInfinite() || this.bot.getTarget() != null) {
            return false;
        }
        Player owner = this.bot.getOwner();
        if (!this.speedrun && !this.autonomous && owner != null && owner.distanceToSqr(this.bot) > 96.0 * 96.0) {
            return false;
        }
        if (--this.replanTimer <= 0 || this.step == null) {
            this.replanTimer = 20;
            this.step = this.plan();
        }
        return this.step != null;
    }

    String describe() {
        if (this.kit().isInfinite()) {
            return "hat unendlich Nachschub, muss nichts sammeln";
        }
        if (!this.enabled) {
            return "Sammeln ist aus";
        }
        if (this.speedrun && this.gameBeaten) {
            return "hat Minecraft durchgespielt";
        }
        Step s = this.plan();
        return s == null ? "hat alles, was er braucht" : "will " + this.goalLabel + " → " + s.describe();
    }

    void reset() {
        this.step = null;
        this.mineTarget = null;
        this.stopBreaking();
        this.exploreTarget = null;
        this.actionTicks = 0;
    }

    // ------------------------------------------------------------------ what is missing

    private record Need(Item item, String label) {
    }

    private List<Need> needs() {
        List<Need> needs = new ArrayList<>();
        BotKit kit = this.kit();
        ItemStack blade = kit.bestBlade();
        boolean hasWeapon = !blade.isEmpty() || kit.has(Role.MACE) || kit.has(Role.SPEAR);
        double weaponDamage = Math.max(Kit.attackDamage(blade), kit.has(Role.MACE) || kit.has(Role.SPEAR) ? 99 : 0);
        boolean diamondsNearby = !this.known.getOrDefault(Ore.DIAMOND, List.of()).isEmpty() || kit.count(Res.DIAMOND.match) > 0;
        if (!hasWeapon) {
            needs.add(new Need(Items.STONE_SWORD, "eine Waffe"));
        }
        if (weaponDamage < Kit.attackDamage(new ItemStack(Items.IRON_SWORD))) {
            needs.add(new Need(Items.IRON_SWORD, "ein Eisenschwert"));
        }
        for (int i = 0; i < 4; i++) {
            if (Kit.armorValue(kit.bestArmor(ARMOR_SLOTS[i]), ARMOR_SLOTS[i]) < Kit.armorValue(new ItemStack(IRON_ARMOR[i]), ARMOR_SLOTS[i])) {
                needs.add(new Need(IRON_ARMOR[i], "Eisenrüstung"));
            }
        }
        if (!kit.has(Role.SHIELD) && !kit.has(Role.TOTEM)) {
            needs.add(new Need(Items.SHIELD, "einen Schild"));
        }
        if (!kit.has(Role.GAPPLE) && kit.count(Res.COOKED_MEAT.match) < 4) {
            needs.add(new Need(Items.COOKED_BEEF, "Essen"));
        }
        if ((diamondsNearby || this.autonomous) && !this.speedrun) {
            if (weaponDamage < Kit.attackDamage(new ItemStack(Items.DIAMOND_SWORD))) {
                needs.add(new Need(Items.DIAMOND_SWORD, "ein Diamantschwert"));
            }
            for (int i = 0; i < 4; i++) {
                if (Kit.armorValue(kit.bestArmor(ARMOR_SLOTS[i]), ARMOR_SLOTS[i]) < Kit.armorValue(new ItemStack(DIAMOND_ARMOR[i]), ARMOR_SLOTS[i])) {
                    needs.add(new Need(DIAMOND_ARMOR[i], "Diamantrüstung"));
                }
            }
        }
        if (this.autonomous && this.needPickaxe(Items.DIAMOND_PICKAXE, 99) != null) {
            needs.add(new Need(Items.DIAMOND_PICKAXE, "eine Diamantspitzhacke"));
        }
        return needs;
    }

    // ------------------------------------------------------------------ planning

    private @Nullable Step plan() {
        for (Need need : this.needs()) {
            Step s = need.item() == Items.COOKED_BEEF ? this.resolve(Res.COOKED_MEAT, 4, 0) : this.resolveItem(need.item(), 0);
            if (s != null) {
                this.goalLabel = need.label();
                return s;
            }
        }
        if (this.speedrun && !this.portalBuilt) {
            return this.speedrunStep();
        }
        if (this.speedrun && !this.stage2Done) {
            return this.stage2Step();
        }
        if (this.speedrun && !this.gameBeaten) {
            return this.inEnd() ? this.stage4Step() : this.stage3Step();
        }
        if (this.autonomous) {
            Step s = this.autonomousStep();
            if (s != null) {
                return s;
            }
        }
        if (this.home != null && this.atHomeLevel() && this.bot.blockPosition().distSqr(this.home) > 5 * 5) {
            // Nothing to do: back home, where the owner can always find it.
            this.goalLabel = "nichts zu tun";
            return new GoHome();
        }
        this.goalLabel = null;
        return null;
    }

    // ------------------------------------------------------------------ home, chests, spare sets

    /** Armor sets it keeps in the chests at home, in this order. */
    private static final Item[][] SPARE_SETS = {IRON_ARMOR, DIAMOND_ARMOR, DIAMOND_ARMOR};

    private boolean atHomeLevel() {
        return this.homeLevel != null && this.bot.level().dimension() == this.homeLevel;
    }

    /**
     * Autonomous mode, once its own gear is the best it can make: collect spare armor sets (one iron,
     * two diamond) and keep them - and the junk blocks it dug up - in chests it places at home.
     */
    private @Nullable Step autonomousStep() {
        if (this.home == null || !this.atHomeLevel()) {
            return null;
        }
        BotKit kit = this.kit();
        List<ItemStack> store = this.toStore(false);
        boolean crowded = kit.items().size() > BotKit.SIZE - 6;
        if (!store.isEmpty() && (crowded || !this.toStore(true).isEmpty())) {
            this.goalLabel = "Platz im Inventar / fertige Rüstungssets";
            BlockPos chest = this.chestWithRoom();
            if (chest != null) {
                return new StoreAtHome(chest);
            }
            if (this.bot.blockPosition().distSqr(this.home) > 16 * 16) {
                // First look at home: maybe there are chests already.
                return new GoHome();
            }
            if (kit.count(st -> st.is(Items.CHEST)) > 0) {
                return new PlaceChest();
            }
            Step s = this.resolveItem(Items.CHEST, 0);
            if (s != null) {
                this.goalLabel = "eine Kiste für zu Hause";
                return s;
            }
        }
        java.util.Map<Item, Integer> wanted = new java.util.HashMap<>();
        for (Item[] set : SPARE_SETS) {
            for (Item piece : set) {
                wanted.merge(piece, 1, Integer::sum);
            }
        }
        for (Item[] set : SPARE_SETS) {
            for (int i = 0; i < 4; i++) {
                Item piece = set[i];
                int have = this.storedCount(piece) + this.spareInKit(piece, ARMOR_SLOTS[i]);
                if (have < wanted.get(piece)) {
                    Step s = this.resolveItem(piece, 0);
                    if (s != null) {
                        this.goalLabel = "Rüstungssets für die Kiste (" + (set == IRON_ARMOR ? "Eisen" : "Diamant") + ")";
                        return s;
                    }
                }
            }
        }
        return null;
    }

    /** Pieces of this armor in the kit that it does not wear. */
    private int spareInKit(Item piece, EquipmentSlot slot) {
        int n = this.kit().count(st -> st.is(piece));
        return this.kit().bestArmor(slot).is(piece) ? n - 1 : n;
    }

    private static final Predicate<ItemStack> JUNK = st -> st.is(Items.COBBLESTONE) || st.is(Items.COBBLED_DEEPSLATE)
            || st.is(Items.DIRT) || st.is(Items.GRAVEL) || st.is(Items.SAND) || st.is(Items.ANDESITE) || st.is(Items.DIORITE)
            || st.is(Items.GRANITE) || st.is(Items.TUFF) || st.is(Items.NETHERRACK) || st.is(Items.ROTTEN_FLESH);

    /**
     * What goes into the chest: armor it does not wear (only whole sets when {@code setsOnly}) and
     * junk blocks beyond one stack of cobblestone for building.
     */
    private List<ItemStack> toStore(boolean setsOnly) {
        List<ItemStack> out = new ArrayList<>();
        BotKit kit = this.kit();
        for (Item[] set : new Item[][]{IRON_ARMOR, DIAMOND_ARMOR}) {
            boolean whole = true;
            List<ItemStack> pieces = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                ItemStack worn = kit.bestArmor(ARMOR_SLOTS[i]);
                ItemStack spare = ItemStack.EMPTY;
                for (ItemStack st : kit.items()) {
                    if (st.is(set[i]) && st != worn) {
                        spare = st;
                        break;
                    }
                }
                if (spare.isEmpty()) {
                    whole = false;
                } else {
                    pieces.add(spare);
                }
            }
            if (whole || !setsOnly) {
                out.addAll(pieces);
            }
        }
        if (!setsOnly) {
            int keptCobble = 0;
            for (ItemStack st : kit.items()) {
                if (JUNK.test(st)) {
                    if (st.is(Items.COBBLESTONE) && keptCobble < 64) {
                        keptCobble += st.getCount();
                        continue;
                    }
                    out.add(st);
                }
            }
        }
        return out;
    }

    private net.minecraft.world.@Nullable Container chestAt(BlockPos pos) {
        return this.level().getBlockEntity(pos) instanceof net.minecraft.world.level.block.entity.ChestBlockEntity chest ? chest : null;
    }

    private int storedCount(Item item) {
        int n = 0;
        for (BlockPos pos : this.homeChests) {
            var c = this.chestAt(pos);
            if (c != null) {
                for (int i = 0; i < c.getContainerSize(); i++) {
                    if (c.getItem(i).is(item)) {
                        n += c.getItem(i).getCount();
                    }
                }
            }
        }
        return n;
    }

    private @Nullable BlockPos chestWithRoom() {
        this.homeChests.removeIf(pos -> this.bot.level().isLoaded(pos) && this.chestAt(pos) == null);
        for (BlockPos pos : this.homeChests) {
            var c = this.chestAt(pos);
            if (c != null) {
                for (int i = 0; i < c.getContainerSize(); i++) {
                    if (c.getItem(i).isEmpty()) {
                        return pos;
                    }
                }
            }
        }
        return null;
    }

    /** Walks home: straight there when close, otherwise in legs of 24 blocks; digs through when stuck. */
    private void doGoHome(ServerLevel level) {
        if (this.home == null) {
            this.step = null;
            return;
        }
        Vec3 home = Vec3.atBottomCenterOf(this.home);
        Vec3 to = home.subtract(this.bot.position());
        if (to.horizontalDistance() < 3.0 && Math.abs(to.y) < 3.0) {
            this.bot.getNavigation().stop();
            this.step = null;
            return;
        }
        boolean stuck = this.noProgress();
        if (this.bot.getNavigation().isDone() || stuck) {
            Vec3 goal = home;
            if (to.horizontalDistance() > 32.0) {
                Vec3 leg = this.bot.position().add(to.multiply(1.0, 0.0, 1.0).normalize().scale(24.0));
                int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, Mth.floor(leg.x), Mth.floor(leg.z));
                goal = new Vec3(leg.x, y, leg.z);
            }
            if (stuck || !this.bot.getNavigation().moveTo(goal.x, goal.y, goal.z, 1.1)) {
                this.digDir = Direction.getApproximateNearest(to.x, 0.0, to.z);
                if (to.y > 3.0) {
                    this.doDigUp(level);
                } else {
                    this.doDig(level, to.y < -2.0);
                }
            }
        }
        this.step = null;
    }

    /** Staircase up (out of its mine): clear head room and the step ahead, then climb onto it. */
    private void doDigUp(ServerLevel level) {
        this.bot.getNavigation().stop();
        BlockPos feet = this.bot.blockPosition();
        // A staircase up, one block per step: the block in front is the step, with room above it
        // for the body and above the head for the jump.
        if (feet.getY() > this.digUpBestY) {
            this.digUpBestY = feet.getY();
            this.digUpTicks = 0;
        } else if (++this.digUpTicks > 100) {
            // Not getting higher this way: another direction.
            this.digUpTicks = 0;
            this.digUpBestY = feet.getY();
            this.digDir = this.bot.getRandom().nextBoolean() ? this.digDir.getClockWise() : this.digDir.getCounterClockWise();
        }
        BlockPos step = feet.relative(this.digDir);
        for (BlockPos p : new BlockPos[]{feet.above(2), step.above(2), step.above()}) {
            BlockState state = level.getBlockState(p);
            if (!level.getFluidState(p).isEmpty() || this.nearLava(level, p) || state.getDestroySpeed(level, p) < 0.0F) {
                this.digDir = this.bot.getRandom().nextBoolean() ? this.digDir.getClockWise() : this.digDir.getCounterClockWise();
                return;
            }
            if (!state.getCollisionShape(level, p).isEmpty()) {
                this.breakBlock(level, p);
                return;
            }
        }
        if (level.getBlockState(step).getCollisionShape(level, step).isEmpty()) {
            // No step there (air, or a drop): put a block down as the step, like a player would.
            if (!this.bot.onGround() || !this.bridge(level, step, false)) {
                this.digDir = this.digDir.getClockWise();
            }
            return;
        }
        if (this.bot.onGround()) {
            this.bot.getJumpControl().jump();
        }
        this.bot.getMoveControl().setWantedPosition(step.getX() + 0.5, step.getY() + 1, step.getZ() + 0.5, 1.0);
    }

    private int digUpBestY = Integer.MIN_VALUE;
    private int digUpTicks;

    /** Places a chest from its kit on free ground next to home (not touching another chest). */
    private void doPlaceChest(ServerLevel level) {
        if (this.home == null || this.kit().count(st -> st.is(Items.CHEST)) == 0) {
            this.step = null;
            return;
        }
        // Anywhere within CHEST_RADIUS blocks of home; the chests stay together (next to the last one,
        // one block gap so they do not join into double chests), the first one as close to home as possible.
        BlockPos near = this.homeChests.isEmpty() ? this.home : this.homeChests.get(this.homeChests.size() - 1);
        BlockPos spot = null;
        double bestDist = Double.MAX_VALUE;
        search:
        for (BlockPos p : BlockPos.betweenClosed(this.home.offset(-CHEST_RADIUS, -3, -CHEST_RADIUS), this.home.offset(CHEST_RADIUS, 3, CHEST_RADIUS))) {
            double d = p.distSqr(near);
            if (d >= bestDist || p.equals(this.home) || p.distSqr(this.home) > CHEST_RADIUS * CHEST_RADIUS
                    || !level.getBlockState(p).isAir() || !level.getBlockState(p.above()).isAir()
                    || !level.getBlockState(p.below()).isFaceSturdy(level, p.below(), Direction.UP)) {
                continue;
            }
            for (Direction dir : Direction.Plane.HORIZONTAL) {
                if (level.getBlockState(p.relative(dir)).is(net.minecraft.world.level.block.Blocks.CHEST)) {
                    continue search;
                }
            }
            spot = p.immutable();
            bestDist = d;
        }
        if (spot == null) {
            this.bot.tellOwner("§7Kein Platz für eine Kiste in " + CHEST_RADIUS + " Blöcken um das Zuhause.", false);
            this.step = null;
            return;
        }
        if (this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(spot)) > 4.0) {
            this.bot.getNavigation().moveTo(spot.getX() + 0.5, spot.getY(), spot.getZ() + 0.5, 1.0);
            this.step = null;
            return;
        }
        this.bot.getNavigation().stop();
        this.bot.lookAtBlock(spot);
        Direction facing = Direction.getApproximateNearest(this.bot.getX() - (spot.getX() + 0.5), 0.0, this.bot.getZ() - (spot.getZ() + 0.5));
        level.setBlock(spot, net.minecraft.world.level.block.Blocks.CHEST.defaultBlockState()
                .setValue(net.minecraft.world.level.block.ChestBlock.FACING, facing.getAxis().isHorizontal() ? facing : Direction.NORTH), 3);
        level.playSound(null, spot, SoundEvents.WOOD_PLACE, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
        this.kit().remove(st -> st.is(Items.CHEST), 1);
        this.homeChests.add(spot);
        this.bot.tellOwner("§6Kiste zu Hause aufgestellt §7(" + spot.getX() + " " + spot.getY() + " " + spot.getZ() + ")", false);
        this.step = null;
    }

    private void doStoreAtHome(ServerLevel level, BlockPos pos) {
        var chest = this.chestAt(pos);
        if (chest == null) {
            this.homeChests.remove(pos);
            this.step = null;
            return;
        }
        if (this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(pos)) > 4.0) {
            this.bot.getNavigation().moveTo(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5, 1.0);
            this.step = null;
            return;
        }
        this.bot.getNavigation().stop();
        this.bot.lookAtBlock(pos);
        if (++this.actionTicks < 10) {
            if (this.actionTicks == 1) {
                level.blockEvent(pos, level.getBlockState(pos).getBlock(), 1, 1);
                level.playSound(null, pos, SoundEvents.CHEST_OPEN, this.bot.getSoundSource(), 0.6F, 1.0F);
            }
            return;
        }
        this.actionTicks = 0;
        int moved = 0;
        for (ItemStack stack : this.toStore(false)) {
            ItemStack rest = stack.copy();
            for (int i = 0; i < chest.getContainerSize() && !rest.isEmpty(); i++) {
                ItemStack slot = chest.getItem(i);
                if (slot.isEmpty()) {
                    chest.setItem(i, rest.copy());
                    rest.setCount(0);
                } else if (ItemStack.isSameItemSameComponents(slot, rest) && slot.getCount() < slot.getMaxStackSize()) {
                    int n = Math.min(rest.getCount(), slot.getMaxStackSize() - slot.getCount());
                    slot.grow(n);
                    rest.shrink(n);
                }
            }
            moved += stack.getCount() - rest.getCount();
            stack.setCount(rest.getCount());
        }
        chest.setChanged();
        level.blockEvent(pos, level.getBlockState(pos).getBlock(), 1, 0);
        level.playSound(null, pos, SoundEvents.CHEST_CLOSE, this.bot.getSoundSource(), 0.6F, 1.0F);
        this.kit().items();
        this.bot.onKitChanged();
        if (moved > 0) {
            this.bot.tellOwner("§6In die Kiste gelegt: §f" + moved + " Sachen", false);
        }
        this.step = null;
    }

    /** Stage 1 of beating the game: water bucket, diamond pickaxe, 10 obsidian, flint and steel, portal. */
    private @Nullable Step speedrunStep() {
        BotKit kit = this.kit();
        boolean waterBucket = kit.count(st -> st.is(Items.WATER_BUCKET)) > 0;
        if (!waterBucket) {
            this.goalLabel = "einen Wassereimer (für Obsidian)";
            if (kit.count(st -> st.is(Items.BUCKET)) == 0) {
                Step s = this.resolveItem(Items.BUCKET, 0);
                if (s != null) {
                    return s;
                }
            }
            if (this.nearest(Ore.WATER) != null) {
                return new FillWater();
            }
            // Deep underground there is hardly any water: up to the surface, where lakes are.
            if (this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD && this.bot.getY() < 50.0
                    && this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
                    this.bot.getBlockX(), this.bot.getBlockZ()) > this.bot.getY() + 6.0) {
                return new ClimbUp("Wasser gibt es oben");
            }
            return new Explore("Wasser");
        }
        if (kit.count(st -> st.is(Items.STONE_PICKAXE)) == 0 && kit.count(Res.COBBLE.match) >= 3) {
            // A cheap pickaxe for tunnelling, so the iron one is still there when diamonds show up.
            Step s = this.resolveItem(Items.STONE_PICKAXE, 0);
            if (s instanceof Craft) {
                this.goalLabel = "eine Steinspitzhacke zum Tunneln";
                return s;
            }
        }
        if (this.needPickaxe(Items.DIAMOND_PICKAXE, 0) != null) {
            this.goalLabel = "eine Diamantspitzhacke";
            Step s = this.resolveItem(Items.DIAMOND_PICKAXE, 0);
            return s != null ? s : this.deepStep();
        }
        if (this.portalBase != null && kit.count(st -> st.is(Items.FLINT_AND_STEEL)) > 0) {
            // Already building: the blocks in the frame count too.
            this.goalLabel = "das Netherportal";
            return new BuildPortal();
        }
        if (kit.count(Res.OBSIDIAN.match) < 10) {
            this.goalLabel = "Obsidian fürs Netherportal (" + kit.count(Res.OBSIDIAN.match) + "/10)";
            if (this.nearest(Ore.OBSIDIAN) != null) {
                return new Mine(Ore.OBSIDIAN);
            }
            return this.nearest(Ore.LAVA) != null ? new MakeObsidian() : this.deepStep();
        }
        if (kit.count(st -> st.is(Items.FLINT_AND_STEEL)) == 0) {
            this.goalLabel = "ein Feuerzeug";
            Step s = this.resolveItem(Items.FLINT_AND_STEEL, 0);
            return s != null ? s : new Explore("Kies");
        }
        this.goalLabel = "das Netherportal";
        return new BuildPortal();
    }

    /**
     * Stage 2: through the portal, blaze rods from a nether fortress, ender pearls from endermen,
     * craft eyes of ender, back to the overworld.
     */
    private @Nullable Step stage2Step() {
        BotKit kit = this.kit();
        int eyes = kit.count(Res.EYE.match);
        int powder = kit.count(Res.BLAZE_POWDER.match);
        int rods = kit.count(Res.BLAZE_ROD.match);
        int pearls = kit.count(Res.PEARL.match);
        int missing = EYES_WANTED - eyes;
        if (missing <= 0) {
            if (this.inNether()) {
                this.goalLabel = "den Weg zurück (Etappe 2)";
                return new UsePortal(false);
            }
            this.stage2Done = true;
            this.bot.tellOwner("§5§lEtappe 2 geschafft: " + eyes + " Enderaugen! §7Als Nächstes: die Festung (Stronghold).", true);
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   gather: STAGE 2 DONE with {} eyes", eyes);
            }
            return null;
        }
        this.goalLabel = "Enderaugen (" + eyes + "/" + EYES_WANTED + ")";
        if (powder > 0 && pearls > 0) {
            return new Craft(RECIPES.get(Items.ENDER_EYE));
        }
        if (rods > 0 && powder == 0 && pearls > 0) {
            return new Craft(RECIPES.get(Items.BLAZE_POWDER));
        }
        int rodsNeeded = (missing - powder + 1) / 2 - rods;
        int pearlsNeeded = missing - pearls;
        // Endermen are worth it whenever one is in sight (nether or overworld).
        if (pearlsNeeded > 0 && this.visibleMob(EntityTypes.ENDERMAN) != null) {
            return new HuntMob("Endermen (Enderperlen)", EntityTypes.ENDERMAN);
        }
        if (rodsNeeded > 0 || pearlsNeeded > 0) {
            if (!this.inNether()) {
                return new UsePortal(true);
            }
            if (rodsNeeded > 0) {
                if (this.visibleMob(EntityTypes.BLAZE) != null) {
                    return new HuntMob("Lohen (Lohenruten)", EntityTypes.BLAZE);
                }
                if (this.nearest(Ore.SPAWNER) != null || this.nearest(Ore.FORTRESS) != null) {
                    return new ExploreNether("Lohen in der Festung");
                }
                return new ExploreNether("eine Netherfestung");
            }
            return new ExploreNether("Endermen");
        }
        return rods > 0 ? new Craft(RECIPES.get(Items.BLAZE_POWDER)) : new ExploreNether("Lohen");
    }

    /**
     * Stage 3: bow and arrows for the end crystals, then find the stronghold the fair way: throw an
     * eye of ender, follow its direction, throw again; where it goes down, dig down and explore until
     * the portal room is in sight, fill the frames and jump in.
     */
    private @Nullable Step stage3Step() {
        BotKit kit = this.kit();
        if (this.inNether()) {
            this.goalLabel = "den Weg zurück in die Oberwelt";
            return new UsePortal(false);
        }
        if (kit.count(st -> st.is(Items.BOW)) == 0) {
            this.goalLabel = "einen Bogen (für die Endkristalle)";
            Step s = this.resolveItem(Items.BOW, 0);
            if (s != null) {
                return s;
            }
        }
        if (kit.count(st -> st.is(Items.ARROW)) < ARROWS_WANTED) {
            this.goalLabel = "Pfeile (" + kit.count(st -> st.is(Items.ARROW)) + "/" + ARROWS_WANTED + ")";
            Step s = this.resolveItem(Items.ARROW, 0);
            if (s != null) {
                return s;
            }
        }
        this.goalLabel = "die Festung (Stronghold)";
        if (this.nearest(Ore.END_PORTAL) != null) {
            return new UseEndPortal();
        }
        if (this.nearest(Ore.END_FRAME) != null) {
            return new FillEndPortal();
        }
        if (this.eyeWentDown) {
            if (this.nearest(Ore.STRONGHOLD) != null) {
                return new ExploreStronghold();
            }
            return this.bot.getY() > -20.0 ? new Descend() : new StripMine();
        }
        if (kit.count(Res.EYE.match) == 0) {
            this.goalLabel = "neue Enderaugen (alle verbraucht)";
            this.stage2Done = false;
            return null;
        }
        // A new eye only after real headway (or a long time): stuck in one place, another eye shows
        // the same direction and may break.
        if (this.eyeDir == null || this.legTicks > 1200 && this.legBest > Math.min(24.0, this.eyeLeg - 4.0) || this.legTicks > 6000) {
            return new ThrowEye();
        }
        return new FollowEye();
    }

    /** Stage 4: shoot the end crystals it can see, then fight the dragon. */
    private @Nullable Step stage4Step() {
        this.goalLabel = "den Enderdrachen";
        net.minecraft.world.entity.boss.enderdragon.EnderDragon dragon = null;
        for (var d : this.level().getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EnderDragon.class,
                this.bot.getBoundingBox().inflate(300.0))) {
            if (d.isAlive()) {
                dragon = d;
            }
        }
        if (dragon != null) {
            this.seenDragon = true;
        } else if (this.seenDragon) {
            this.gameBeaten = true;
            this.bot.tellOwner("§6§lMINECRAFT DURCHGESPIELT! §eDer Enderdrache ist besiegt.", true);
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   gather: DRAGON DEAD - GAME BEATEN");
            }
            return null;
        }
        if (dragon != null) {
            var phase = dragon.getPhaseManager().getCurrentPhase().getPhase();
            if (PvpBotEntity.DEBUG && phase != this.lastDragonPhase) {
                PvpBotMod.LOGGER.info("[SELFTEST]   dragon phase {} hp {} at {}", phase, (int) dragon.getHealth(), dragon.blockPosition().toShortString());
            }
            this.lastDragonPhase = phase;
            if (PvpBotEntity.DEBUG && ++this.dragonLogTicks % 300 == 0) {
                PvpBotMod.LOGGER.info("[SELFTEST]   dragon status: {} hp {} at {} bot at {} hp {} arrows {}", phase, (int) dragon.getHealth(),
                        dragon.blockPosition().toShortString(), this.bot.blockPosition().toShortString(), (int) this.bot.getHealth(),
                        this.kit().count(st -> st.is(Items.ARROW)));
            }
            // Down at the fountain: that is the moment to hit it, crystals can wait.
            BlockPos fountain = this.level().getHeightmapPos(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, BlockPos.ZERO);
            // Crystals first (they heal it); only when it is really coming down right now, be at the
            // fountain (it sits just a few seconds).
            boolean crystalsLeft = this.visibleCrystal() != null && this.kit().count(st -> st.is(Items.ARROW)) > 0;
            boolean landing = phase == net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.LANDING
                    && dragon.position().horizontalDistanceSqr() < 40 * 40
                    || dragon.getPhaseManager().getCurrentPhase().isSitting();
            boolean sitting = dragon.getPhaseManager().getCurrentPhase().isSitting();
            if (crystalsLeft ? sitting && this.bot.position().horizontalDistanceSqr() < 24 * 24
                    : landing || dragon.getY() < fountain.getY() + 12 && dragon.position().horizontalDistanceSqr() < 16 * 16) {
                return new FightDragon();
            }
        }
        if (this.visibleCrystal() != null && this.kit().count(st -> st.is(Items.ARROW)) > 0) {
            return new ShootCrystal();
        }
        if (this.anyCrystal() && this.kit().count(st -> st.is(Items.ARROW)) > 0 && ++this.crystalRetryTicks > 1200) {
            // Gave up on the last ones for a while: try them again (the pole may work from another side).
            this.crystalRetryTicks = 0;
            this.crystalShots.replaceAll((k, v) -> v >= 99 ? 6 : v);
        }
        return new FightDragon();
    }

    private int crystalRetryTicks;

    private boolean anyCrystal() {
        return !this.level().getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EndCrystal.class, this.bot.getBoundingBox().inflate(200.0),
                net.minecraft.world.entity.Entity::isAlive).isEmpty();
    }

    private net.minecraft.world.entity.boss.enderdragon.phases.@Nullable EnderDragonPhase<?> lastDragonPhase;

    private java.util.@Nullable UUID crystalTarget;

    private net.minecraft.world.entity.boss.enderdragon.@Nullable EndCrystal visibleCrystal() {
        // Stay with the crystal it is going for (walking there, others come into sight and go again).
        if (this.crystalTarget != null && this.level().getEntity(this.crystalTarget) instanceof net.minecraft.world.entity.boss.enderdragon.EndCrystal c
                && c.isAlive() && this.crystalShots.getOrDefault(c.getUUID(), 0) < 18) {
            return c;
        }
        this.crystalTarget = null;
        net.minecraft.world.entity.boss.enderdragon.EndCrystal best = null;
        double bestDist = Double.MAX_VALUE;
        for (var c : this.level().getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EndCrystal.class,
                this.bot.getBoundingBox().inflate(160.0))) {
            // Ones in sight first; the others (behind a tower, caged, up high) need a pole.
            double d = this.bot.distanceToSqr(c) * (this.bot.hasLineOfSight(c) ? 1.0 : 4.0);
            if (c.isAlive() && this.crystalShots.getOrDefault(c.getUUID(), 0) < 18 && d < bestDist) {
                best = c;
                bestDist = d;
            }
        }
        if (best != null) {
            this.crystalTarget = best.getUUID();
        }
        return best;
    }

    private @Nullable LivingEntity visibleMob(net.minecraft.world.entity.EntityType<?> type) {
        LivingEntity best = null;
        double bestDist = Double.MAX_VALUE;
        for (Entity e : this.level().getEntities(this.bot, this.bot.getBoundingBox().inflate(32.0))) {
            if (e.getType() == type && e instanceof LivingEntity living && living.isAlive() && this.bot.getSensing().hasLineOfSight(living)
                    && this.bot.distanceToSqr(e) < bestDist) {
                best = living;
                bestDist = this.bot.distanceToSqr(e);
            }
        }
        return best;
    }

    /** Diamonds and lava are deep down: dig down first, then strip-mine. */
    private Step deepStep() {
        return this.bot.getY() > -50.0 ? new Descend() : new StripMine();
    }

    private @Nullable Step resolveItem(Item item, int depth) {
        Recipe recipe = RECIPES.get(item);
        if (recipe == null || depth > 8) {
            return null;
        }
        for (Ingredient ing : recipe.ingredients()) {
            if (this.kit().count(ing.res().match) < ing.count()) {
                return this.resolve(ing.res(), ing.count(), depth + 1);
            }
        }
        return new Craft(recipe);
    }

    /** How to get {@code count} of a resource. */
    private @Nullable Step resolve(Res res, int count, int depth) {
        if (this.kit().count(res.match) >= count || depth > 8) {
            return null;
        }
        return switch (res) {
            case PLANKS -> this.resolveItem(Items.OAK_PLANKS, depth);
            case STICK -> this.resolveItem(Items.STICK, depth);
            case LOG -> this.mine(Ore.LOG, depth);
            case COBBLE -> this.needPickaxe(Items.WOODEN_PICKAXE, depth) != null ? this.needPickaxe(Items.WOODEN_PICKAXE, depth) : this.mine(Ore.STONE, depth);
            case COAL -> this.needPickaxe(Items.WOODEN_PICKAXE, depth) != null ? this.needPickaxe(Items.WOODEN_PICKAXE, depth) : this.mine(Ore.COAL, depth);
            case RAW_IRON -> this.needPickaxe(Items.STONE_PICKAXE, depth) != null ? this.needPickaxe(Items.STONE_PICKAXE, depth) : this.mine(Ore.IRON, depth);
            case DIAMOND -> this.needPickaxe(Items.IRON_PICKAXE, depth) != null ? this.needPickaxe(Items.IRON_PICKAXE, depth)
                    : this.nearest(Ore.DIAMOND) != null ? new Mine(Ore.DIAMOND) : this.speedrun || this.autonomous ? this.deepStep() : new Explore(Ore.DIAMOND.label);
            case OBSIDIAN -> this.nearest(Ore.OBSIDIAN) != null ? new Mine(Ore.OBSIDIAN) : this.deepStep();
            case FLINT -> this.nearest(Ore.GRAVEL) != null ? new Mine(Ore.GRAVEL) : this.speedrun ? this.deepStep() : new Explore(Ore.GRAVEL.label);
            case IRON -> this.smelt(Res.RAW_IRON, Res.IRON, count - this.kit().count(res.match), depth);
            case COOKED_MEAT -> this.smelt(Res.RAW_MEAT, Res.COOKED_MEAT, count - this.kit().count(res.match), depth);
            case RAW_MEAT -> new Hunt();
            case STRING -> this.visibleMob(EntityTypes.SPIDER) != null ? new HuntMob("Spinnen (Faden)", EntityTypes.SPIDER) : new Explore("Spinnen (Faden)");
            case FEATHER -> this.visibleMob(EntityTypes.CHICKEN) != null ? new HuntMob("Hühner (Federn)", EntityTypes.CHICKEN) : new Explore("Hühner (Federn)");
            case BLAZE_ROD, BLAZE_POWDER, PEARL, EYE -> null;
        };
    }

    /** Null if a good enough pickaxe is there, otherwise the step towards one. */
    private @Nullable Step needPickaxe(Item minimum, int depth) {
        int needed = pickaxeTier(minimum);
        for (ItemStack stack : this.kit().items()) {
            if (pickaxeTier(stack.getItem()) >= needed) {
                return null;
            }
        }
        Step s = this.resolveItem(minimum, depth + 1);
        return s != null ? s : new Explore("Material für eine Spitzhacke");
    }

    private static int pickaxeTier(Item item) {
        if (item == Items.WOODEN_PICKAXE || item == Items.GOLDEN_PICKAXE) return 1;
        if (item == Items.STONE_PICKAXE) return 2;
        if (item == Items.IRON_PICKAXE || item == Items.COPPER_PICKAXE) return 3;
        if (item == Items.DIAMOND_PICKAXE || item == Items.NETHERITE_PICKAXE) return 4;
        return 0;
    }

    private Step smelt(Res input, Res output, int missing, int depth) {
        if (this.kit().count(input.match) < 1) {
            Step s = this.resolve(input, Math.max(1, missing), depth + 1);
            return s != null ? s : new Explore(input.label);
        }
        if (this.fuel <= 0 && this.kit().count(Res.COAL.match) == 0 && this.kit().count(Res.LOG.match) == 0
                && this.kit().count(Res.PLANKS.match) < 2) {
            // Fuel: coal if we know where it is, otherwise wood.
            if (!this.known.getOrDefault(Ore.COAL, List.of()).isEmpty() && this.needPickaxe(Items.WOODEN_PICKAXE, depth) == null) {
                return new Mine(Ore.COAL);
            }
            return this.mine(Ore.LOG, depth);
        }
        return new Smelt(input, output);
    }

    private Step mine(Ore ore, int depth) {
        return this.nearest(ore) != null ? new Mine(ore) : new Explore(ore.label);
    }

    // ------------------------------------------------------------------ doing

    void tick() {
        ServerLevel level = this.level();
        if (this.escapeLava(level)) {
            return;
        }
        if (this.bot.isInWall()) {
            // Gravel or sand fell onto its head: dig itself free before it suffocates.
            BlockPos head = BlockPos.containing(this.bot.getEyePosition());
            for (BlockPos p : new BlockPos[]{head, this.bot.blockPosition()}) {
                if (!level.getBlockState(p).getCollisionShape(level, p).isEmpty() && level.getBlockState(p).getDestroySpeed(level, p) >= 0.0F) {
                    this.bot.getNavigation().stop();
                    this.breakBlock(level, p);
                    return;
                }
            }
        }
        this.findHomeChests(level);
        if (!this.kit().hasRoom() && this.bot.tickCount % 20 == 0) {
            // Full: throw away dug-up junk (keeps one stack of cobblestone for building).
            int kept = 0;
            for (ItemStack st : this.kit().items()) {
                if (JUNK.test(st)) {
                    if (st.is(Items.COBBLESTONE) && kept++ == 0) {
                        continue;
                    }
                    st.setCount(0);
                }
            }
            this.kit().items();
        }
        if (this.speedrun && this.inNether() && this.netherPortal == null) {
            // Just arrived: remember the way home.
            for (BlockPos p : BlockPos.betweenClosed(this.bot.blockPosition().offset(-2, -1, -2), this.bot.blockPosition().offset(2, 3, 2))) {
                if (level.getBlockState(p).is(net.minecraft.world.level.block.Blocks.NETHER_PORTAL)) {
                    this.netherPortal = p.immutable();
                    this.bot.tellOwner("§5Im Nether angekommen! §7Jetzt: Netherfestung und Lohen suchen.", true);
                    break;
                }
            }
        }
        this.scanTick(level);
        boolean collecting = this.collectDrops();
        if (PvpBotEntity.DEBUG && this.bot.tickCount % 200 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   gatherer tick: step {} collecting {} actionTicks {}", this.step, collecting, this.actionTicks);
        }
        if (collecting) {
            return;
        }
        Step s = this.step;
        if (s == null) {
            return;
        }
        String text = s.describe();
        if (!text.equals(this.lastAnnounced)) {
            this.lastAnnounced = text;
            this.bot.tellOwner("§7Mir fehlt " + this.goalLabel + " – ich " + text + ".", false);
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   gather: {} -> {}", this.goalLabel, text);
            }
        }
        switch (s) {
            case Craft craft -> this.doCraft(level, craft.recipe());
            case Smelt smelt -> this.doSmelt(level, smelt);
            case Mine mine -> this.doMine(level, mine.ore());
            case Hunt hunt -> this.doHunt();
            case Explore explore -> this.doExplore();
            case ClimbUp up -> {
                this.doDigUp(level);
                this.step = null;
            }
            case Descend d -> this.doDig(level, true);
            case StripMine sm -> this.doDig(level, false);
            case FillWater fw -> this.doFillWater(level);
            case MakeObsidian mo -> this.doMakeObsidian(level);
            case BuildPortal bp -> this.doBuildPortal(level);
            case UsePortal up -> this.doUsePortal(level, up.toNether());
            case HuntMob hm -> this.doHuntMob(hm.type());
            case ExploreNether en -> this.doExploreNether(level);
            case ThrowEye te -> this.doThrowEye(level);
            case FollowEye fe -> this.doFollowEye(level);
            case ExploreStronghold es -> this.doExploreStronghold(level);
            case FillEndPortal fp -> this.doFillEndPortal(level);
            case UseEndPortal ue -> this.doUseEndPortal();
            case ShootCrystal sc -> this.doShootCrystal();
            case FightDragon fd -> this.doFightDragon(level);
            case GoHome gh -> this.doGoHome(level);
            case PlaceChest pc -> this.doPlaceChest(level);
            case StoreAtHome sh -> this.doStoreAtHome(level, sh.chest());
        }
    }

    private void doCraft(ServerLevel level, Recipe recipe) {
        this.bot.getNavigation().stop();
        if (++this.actionTicks < 20) {
            if (this.actionTicks % 5 == 0) {
                this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
            }
            return;
        }
        this.actionTicks = 0;
        for (Ingredient ing : recipe.ingredients()) {
            if (this.kit().count(ing.res().match) < ing.count()) {
                this.step = null;
                return;
            }
        }
        for (Ingredient ing : recipe.ingredients()) {
            this.kit().remove(ing.res().match, ing.count());
        }
        this.kit().insert(new ItemStack(recipe.output(), recipe.outputCount()));
        level.playSound(null, this.bot.getX(), this.bot.getY(), this.bot.getZ(), SoundEvents.VILLAGER_WORK_TOOLSMITH, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.bot.onKitChanged();
        this.step = null;
    }

    private void doSmelt(ServerLevel level, Smelt smelt) {
        this.bot.getNavigation().stop();
        if (++this.actionTicks < 40) {
            return;
        }
        this.actionTicks = 0;
        if (this.fuel <= 0) {
            // Coal smelts 8 items, wood 1.5 (rounded to 2 per log, 1 per plank pair).
            if (this.kit().remove(Res.COAL.match, 1) == 1) {
                this.fuel += 8;
            } else if (this.kit().remove(Res.LOG.match, 1) == 1) {
                this.fuel += 2;
            } else if (this.kit().remove(Res.PLANKS.match, 2) == 2) {
                this.fuel += 2;
            } else {
                this.step = null;
                return;
            }
        }
        ItemStack raw = ItemStack.EMPTY;
        for (ItemStack stack : this.kit().items()) {
            if (smelt.input().match.test(stack)) {
                raw = stack;
                break;
            }
        }
        if (raw.isEmpty()) {
            this.step = null;
            return;
        }
        Item out = cooked(raw.getItem());
        raw.shrink(1);
        this.fuel--;
        this.kit().insert(new ItemStack(out));
        level.playSound(null, this.bot.getX(), this.bot.getY(), this.bot.getZ(), SoundEvents.FURNACE_FIRE_CRACKLE, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.step = null;
    }

    private static Item cooked(Item raw) {
        if (raw == Items.RAW_IRON) return Items.IRON_INGOT;
        if (raw == Items.BEEF) return Items.COOKED_BEEF;
        if (raw == Items.PORKCHOP) return Items.COOKED_PORKCHOP;
        if (raw == Items.CHICKEN) return Items.COOKED_CHICKEN;
        if (raw == Items.MUTTON) return Items.COOKED_MUTTON;
        if (raw == Items.RABBIT) return Items.COOKED_RABBIT;
        return raw;
    }

    private void doHunt() {
        LivingEntity prey = null;
        double best = Double.MAX_VALUE;
        for (Entity e : this.level().getEntities(this.bot, this.bot.getBoundingBox().inflate(40.0))) {
            boolean food = e.getType() == EntityTypes.COW || e.getType() == EntityTypes.PIG || e.getType() == EntityTypes.SHEEP
                    || e.getType() == EntityTypes.CHICKEN || e.getType() == EntityTypes.RABBIT;
            if (food && e instanceof LivingEntity living && living.isAlive() && !living.isBaby() && this.bot.distanceToSqr(e) < best
                    && this.bot.getSensing().hasLineOfSight(living)) {
                prey = living;
                best = this.bot.distanceToSqr(e);
            }
        }
        if (prey == null && this.inNether() && (this.netherPortal != null || this.nearest(Ore.PORTAL) != null)) {
            // No cows in the nether: back through the portal to hunt, then on with the rest.
            this.doUsePortal(this.level(), false);
            return;
        }
        if (prey == null) {
            if (this.level() instanceof ServerLevel sl && sl.dimension() == net.minecraft.world.level.Level.OVERWORLD
                    && sl.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, this.bot.getBlockX(), this.bot.getBlockZ())
                    > this.bot.getY() + 6.0) {
                // Animals live up on the surface.
                this.doDigUp(sl);
                this.step = null;
                return;
            }
            this.doExplore();
            return;
        }
        this.bot.huntTarget(prey);
        this.step = null;
    }

    private void doExplore() {
        Vec3 pos = this.bot.position();
        if (this.anchor == null) {
            Player owner = this.bot.getOwner();
            this.anchor = owner != null ? owner.position() : pos;
        }
        if (this.exploreTarget == null || pos.distanceToSqr(this.exploreTarget) < 9.0 || this.bot.getNavigation().isDone() && ++this.actionTicks > 60) {
            boolean stuck = this.exploreTarget != null && pos.distanceToSqr(this.exploreTarget) >= 9.0;
            this.actionTicks = 0;
            double angle = this.bot.getRandom().nextDouble() * Math.PI * 2.0;
            if (this.speedrun || this.autonomous) {
                // Far from home: keep one heading like a player would, turn only when the way is blocked.
                if (Double.isNaN(this.exploreHeading) || stuck) {
                    this.exploreHeading = Double.isNaN(this.exploreHeading) ? angle
                            : this.exploreHeading + (this.bot.getRandom().nextBoolean() ? 1 : -1) * (Math.PI / 4 + this.bot.getRandom().nextDouble() * Math.PI / 2);
                }
                angle = this.exploreHeading;
            }
            Vec3 candidate = pos.add(Math.cos(angle) * 32.0, 0.0, Math.sin(angle) * 32.0);
            if (!this.speedrun && !this.autonomous && candidate.distanceTo(this.anchor) > 96.0) {
                candidate = this.anchor.add(pos.subtract(this.anchor).scale(-0.5));
            }
            int y = this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING, (int) candidate.x, (int) candidate.z);
            this.exploreTarget = new Vec3(candidate.x, y, candidate.z);
        }
        this.bot.getNavigation().moveTo(this.exploreTarget.x, this.exploreTarget.y, this.exploreTarget.z, 1.1);
        this.step = null;
    }

    // --- stage 1: digging down, water, obsidian, portal

    /** Staircase down (descend) or a straight 2-high tunnel (strip mine); turns away from lava and bedrock. */
    private void doDig(ServerLevel level, boolean down) {
        if (down && this.digBlocked >= 4 && this.bot.getY() < 50.0) {
            // Water or lava on every side of the way down: tunnel away sideways for a bit, then go on down.
            this.digBlocked = 0;
            this.sidewaysTicks = 300;
            this.digDir = Direction.Plane.HORIZONTAL.getRandomDirection(this.bot.getRandom());
        }
        if (this.sidewaysTicks > 0) {
            this.sidewaysTicks--;
            down = false;
        }
        if (this.digBlocked >= 4 || this.bot.isInWater()) {
            // Water (or lava) on every side, e.g. standing in the lake it just scooped from: walk to
            // dry ground first, then dig.
            this.digBlocked = 0;
            this.dryWalkTicks = 120;
        }
        if (this.dryWalkTicks > 0) {
            this.dryWalkTicks--;
            this.doExplore();
            return;
        }
        this.bot.getNavigation().stop();
        BlockPos feet = this.bot.blockPosition();
        BlockPos front = feet.relative(this.digDir);
        if (PvpBotEntity.DEBUG && ++this.digStateLog % 200 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   dig: at {} dir {} down {} front {} / {} blocked {} actionTicks {}", feet.toShortString(), this.digDir, down,
                    this.level().getBlockState(front).getBlock(), this.level().getBlockState(front.above()).getBlock(), this.digBlocked, this.actionTicks);
        }
        List<BlockPos> toClear = new ArrayList<>();
        toClear.add(front.above());
        toClear.add(front);
        if (down) {
            toClear.add(front.below());
        }
        if (!down) {
            this.dugTunnel.add(feet.asLong());
            if (this.dugTunnel.size() > 4000) {
                this.dugTunnel.clear();
            }
            if (this.dugTunnel.contains(front.asLong()) && level.getBlockState(front).isAir() && level.getBlockState(front.above()).isAir()) {
                // Back in its own tunnel: branch off into fresh rock instead of walking in circles.
                Direction fresh = null;
                for (Direction d : new Direction[]{this.digDir.getClockWise(), this.digDir.getCounterClockWise(), this.digDir}) {
                    if (!this.dugTunnel.contains(feet.relative(d).asLong())) {
                        fresh = d;
                        if (this.bot.getRandom().nextBoolean()) {
                            break;
                        }
                    }
                }
                this.digDir = fresh != null ? fresh : this.digDir.getOpposite();
                front = feet.relative(this.digDir);
                toClear.set(0, front.above());
                toClear.set(1, front);
            }
        }
        if (this.bot.getY() - feet.getY() > 0.05) {
            // Standing higher than a full block (on a fence, a slab): the head reaches into the
            // third block up.
            toClear.add(0, front.above(2));
        }
        for (BlockPos p : toClear) {
            BlockState state = level.getBlockState(p);
            boolean danger = this.nearLava(level, p) || !level.getFluidState(p).isEmpty() || state.getDestroySpeed(level, p) < 0.0F;
            if (danger) {
                // Lava, water or bedrock ahead: take another direction. Lava right behind the next
                // block is noticed (that is where obsidian comes from).
                for (Direction d : Direction.values()) {
                    BlockPos l = p.relative(d);
                    if (Ore.LAVA.match.test(level.getBlockState(l))) {
                        List<BlockPos> list = this.known.computeIfAbsent(Ore.LAVA, k -> new ArrayList<>());
                        if (!list.contains(l)) {
                            list.add(l.immutable());
                        }
                    }
                }
                this.stopBreaking();
                if (PvpBotEntity.DEBUG && ++this.digLogTicks % 20 == 1) {
                    PvpBotMod.LOGGER.info("[SELFTEST]   dig: danger at {} ({}) -> turns", p.toShortString(), state);
                }
                this.digDir = this.bot.getRandom().nextBoolean() ? this.digDir.getClockWise() : this.digDir.getCounterClockWise();
                this.digBlocked++;
                this.bot.tellOwner("§7Gefahr voraus – ich grabe in eine andere Richtung.", false);
                return;
            }
            if (!state.getCollisionShape(level, p).isEmpty()) {
                if (this.breakBlock(level, p)) {
                    this.digBlocked = 0;
                }
                return;
            }
        }
        if (!down) {
            // Before stepping into the cleared space: no deep drop and no lava under it.
            int depth = 0;
            boolean lavaBelow = false;
            while (depth < 4 && level.getBlockState(front.below(depth + 1)).getCollisionShape(level, front.below(depth + 1)).isEmpty()) {
                depth++;
                lavaBelow |= !level.getFluidState(front.below(depth)).isEmpty() && level.getFluidState(front.below(depth)).is(net.minecraft.tags.FluidTags.LAVA);
            }
            boolean bad = lavaBelow || depth >= 4 || level.getFluidState(front.below(depth + 1)).is(net.minecraft.tags.FluidTags.LAVA);
            if (PvpBotEntity.DEBUG && (bad || depth >= 2) && ++this.digLogTicks % 20 == 1) {
                PvpBotMod.LOGGER.info("[SELFTEST]   dig: gap ahead at {} depth {} lava {} -> {}", front.toShortString(), depth, bad,
                        this.kit().count(BRIDGE_BLOCK) > 0 ? "bridge" : "no blocks, turn");
            }
            if ((bad || depth >= 2) && this.bridge(level, front.below())) {
                // Bridged the gap like a player (block under the next step), go on.
                this.step = null;
                return;
            }
            if (bad) {
                this.stopBreaking();
                this.digDir = this.bot.getRandom().nextBoolean() ? this.digDir.getClockWise() : this.digDir.getCounterClockWise();
                this.digBlocked++;
                this.step = null;
                return;
            }
        }
        Vec3 next = Vec3.atBottomCenterOf(front);
        this.bot.getMoveControl().setWantedPosition(next.x, next.y, next.z, 1.0);
        if (++this.actionTicks > 60) {
            // Not getting anywhere (e.g. standing on a slab): try the next direction.
            this.actionTicks = 0;
            this.digDir = this.digDir.getClockWise();
        }
        if (!this.bot.blockPosition().equals(feet)) {
            this.actionTicks = 0;
        }
        this.step = null;
    }

    private static final Predicate<ItemStack> BRIDGE_BLOCK = st -> st.is(Items.COBBLESTONE) || st.is(Items.COBBLED_DEEPSLATE)
            || st.is(Items.NETHERRACK) || st.is(Items.DIRT) || st.is(Items.BLACKSTONE);

    /** Puts a block (cobblestone, netherrack, dirt) into the gap in front of its feet. */
    private boolean bridge(ServerLevel level, BlockPos gap) {
        return this.bridge(level, gap, true);
    }

    private boolean bridge(ServerLevel level, BlockPos gap, boolean needGround) {
        BlockState there = level.getBlockState(gap);
        if (!there.canBeReplaced() || needGround && !this.bot.onGround()) {
            return false;
        }
        ItemStack block = ItemStack.EMPTY;
        for (ItemStack st : this.kit().items()) {
            if (BRIDGE_BLOCK.test(st)) {
                block = st;
                break;
            }
        }
        if (block.isEmpty() || !(block.getItem() instanceof net.minecraft.world.item.BlockItem bi)) {
            return false;
        }
        this.bot.getNavigation().stop();
        this.bot.getMoveControl().setWantedPosition(this.bot.getX(), this.bot.getY(), this.bot.getZ(), 0.0);
        this.bot.lookAtBlock(gap);
        level.setBlock(gap, bi.getBlock().defaultBlockState(), 3);
        level.playSound(null, gap, SoundEvents.STONE_PLACE, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
        if (!this.kit().isInfinite()) {
            Item item = block.getItem();
            this.kit().remove(st -> st.is(item), 1);
            this.bot.onKitChanged();
        }
        return true;
    }

    private void doFillWater(ServerLevel level) {
        BlockPos water = this.nearest(Ore.WATER);
        if (water == null) {
            this.step = null;
            return;
        }
        if (this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(water)) > 4.0) {
            this.bot.getNavigation().moveTo(water.getX() + 0.5, water.getY(), water.getZ() + 0.5, 1.1);
            return;
        }
        this.bot.getNavigation().stop();
        this.bot.lookAtBlock(water);
        if (this.kit().remove(st -> st.is(Items.BUCKET), 1) == 1) {
            this.kit().insert(new ItemStack(Items.WATER_BUCKET));
            level.playSound(null, water, SoundEvents.BUCKET_FILL, this.bot.getSoundSource(), 1.0F, 1.0F);
            this.bot.onKitChanged();
        }
        this.step = null;
    }

    /** Pours water onto a lava source (it turns into obsidian) and scoops the water up again. */
    private void doMakeObsidian(ServerLevel level) {
        BlockPos lava = this.nearest(Ore.LAVA);
        if (lava == null) {
            this.step = null;
            return;
        }
        double dist = this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(lava));
        if (dist > 4.0) {
            this.bot.getNavigation().moveTo(lava.getX() + 0.5, lava.getY() + 1, lava.getZ() + 0.5, 1.0);
            if (++this.actionTicks > 200) {
                this.blacklist.add(lava);
                this.actionTicks = 0;
                this.step = null;
            }
            return;
        }
        this.actionTicks = 0;
        this.bot.getNavigation().stop();
        this.bot.lookAtBlock(lava);
        level.setBlock(lava, net.minecraft.world.level.block.Blocks.OBSIDIAN.defaultBlockState(), 3);
        level.playSound(null, lava, SoundEvents.BUCKET_EMPTY, this.bot.getSoundSource(), 1.0F, 1.0F);
        level.playSound(null, lava, SoundEvents.LAVA_EXTINGUISH, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.known.computeIfAbsent(Ore.OBSIDIAN, k -> new ArrayList<>()).add(lava);
        this.step = null;
    }

    /** Builds a 4x5 obsidian frame (corners left out: 10 blocks) next to the bot and lights it. */
    private void doBuildPortal(ServerLevel level) {
        this.bot.getNavigation().stop();
        if (this.portalBase == null) {
            Direction facing = this.bot.getDirection();
            this.portalBase = this.bot.blockPosition().relative(facing, 2).relative(facing.getClockWise(), -1);
            this.portalAlong = facing.getClockWise();
            this.portalProgress = 0;
        }
        if (++this.actionTicks < 5) {
            return;
        }
        this.actionTicks = 0;
        List<BlockPos> frame = new ArrayList<>();
        List<BlockPos> inside = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 5; j++) {
                BlockPos p = this.portalBase.relative(this.portalAlong, i).above(j);
                boolean side = (i == 0 || i == 3) && j >= 1 && j <= 3;
                boolean capOrFloor = (j == 0 || j == 4) && (i == 1 || i == 2);
                if (side || capOrFloor) {
                    frame.add(p);
                } else if (i >= 1 && i <= 2 && j >= 1 && j <= 3) {
                    inside.add(p);
                }
            }
        }
        for (BlockPos p : inside) {
            if (!level.getBlockState(p).isAir() && !level.getBlockState(p).is(net.minecraft.world.level.block.Blocks.NETHER_PORTAL)) {
                this.bot.lookAtBlock(p);
                this.breakBlock(level, p);
                return;
            }
        }
        if (this.portalProgress < frame.size()) {
            BlockPos p = frame.get(this.portalProgress);
            if (!level.getBlockState(p).is(net.minecraft.world.level.block.Blocks.OBSIDIAN)) {
                if (this.kit().remove(Res.OBSIDIAN.match, 1) == 0) {
                    this.portalBase = null;
                    this.step = null;
                    return;
                }
                this.bot.lookAtBlock(p);
                this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
                level.setBlock(p, net.minecraft.world.level.block.Blocks.OBSIDIAN.defaultBlockState(), 3);
                level.playSound(null, p, SoundEvents.STONE_PLACE, this.bot.getSoundSource(), 1.0F, 1.0F);
            }
            this.blacklist.add(p.immutable()); // its own frame is not obsidian to mine
            this.portalProgress++;
            return;
        }
        // Light it.
        BlockPos fire = inside.get(0);
        for (ItemStack stack : this.kit().items()) {
            if (stack.is(Items.FLINT_AND_STEEL)) {
                stack.hurtAndBreak(1, this.bot, EquipmentSlot.MAINHAND);
                break;
            }
        }
        this.bot.lookAtBlock(fire);
        level.setBlock(fire, net.minecraft.world.level.block.Blocks.FIRE.defaultBlockState(), 11);
        level.playSound(null, fire, SoundEvents.FLINTANDSTEEL_USE, this.bot.getSoundSource(), 1.0F, 1.0F);
        if (!level.getBlockState(fire).is(net.minecraft.world.level.block.Blocks.NETHER_PORTAL)) {
            // The fire did not open it by itself: fill the frame with portal blocks like the game does.
            var state = net.minecraft.world.level.block.Blocks.NETHER_PORTAL.defaultBlockState()
                    .setValue(net.minecraft.world.level.block.NetherPortalBlock.AXIS, this.portalAlong.getAxis());
            for (BlockPos p : inside) {
                level.setBlock(p, state, 18);
            }
        }
        this.portalBuilt = true;
        this.overworldPortal = fire;
        this.bot.tellOwner("§5§lEtappe 1 geschafft: Das Netherportal steht! §7(" + fire.getX() + " " + fire.getY() + " " + fire.getZ() + ")", true);
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   gather: PORTAL BUILT at {}", fire);
        }
        this.step = null;
    }

    // --- stage 2: nether

    private int wantPortalTick = -1000;

    /** While playing through, portals are only taken on purpose (not by walking through one by chance). */
    boolean mayUsePortal() {
        return !this.speedrun || this.bot.tickCount - this.wantPortalTick < 60;
    }

    private void doUsePortal(ServerLevel level, boolean toNether) {
        this.wantPortalTick = this.bot.tickCount;
        BlockPos portal = toNether ? this.overworldPortal : this.netherPortal;
        if (portal == null || !level.getBlockState(portal).is(net.minecraft.world.level.block.Blocks.NETHER_PORTAL)) {
            // Look for the portal we can see.
            portal = this.nearest(Ore.PORTAL);
        }
        if (portal == null) {
            if (!toNether && this.overworldPortal == null && !this.inNether()) {
                this.step = null;
                return;
            }
            this.doExplore();
            return;
        }
        Vec3 center = Vec3.atBottomCenterOf(portal);
        if (this.bot.position().distanceToSqr(center) > 40.0 * 40.0) {
            // Far away: towards it in legs (a path only reaches so far), tunnelling where there is no way.
            Vec3 to = center.subtract(this.bot.position());
            Vec3 leg = this.bot.position().add(to.normalize().scale(32.0));
            if ((this.bot.getNavigation().isDone() || this.noProgress())
                    && !this.bot.getNavigation().moveTo(leg.x, leg.y, leg.z, 1.1)) {
                this.digDir = Math.abs(to.x) > Math.abs(to.z) ? (to.x > 0 ? Direction.EAST : Direction.WEST) : (to.z > 0 ? Direction.SOUTH : Direction.NORTH);
                if (to.y > 3.0) {
                    this.doDigUp(level);
                } else {
                    this.doDig(level, to.y < -3.0 && this.bot.getY() > 40.0);
                }
            }
            this.step = null;
            return;
        }
        if (this.bot.position().distanceToSqr(center) > 2.0) {
            this.bot.getNavigation().moveTo(center.x, center.y, center.z, 1.1);
            if (this.bot.position().distanceToSqr(center) < 9.0) {
                this.bot.getMoveControl().setWantedPosition(center.x, center.y, center.z, 1.0);
            }
        } else {
            this.bot.getNavigation().stop();
            this.bot.getMoveControl().setWantedPosition(center.x, center.y, center.z, 0.6);
        }
        this.step = null;
    }

    private void doHuntMob(net.minecraft.world.entity.EntityType<?> type) {
        LivingEntity mob = this.visibleMob(type);
        if (mob == null) {
            this.step = null;
            return;
        }
        this.bot.huntTarget(mob);
        this.step = null;
    }

    /**
     * Nether exploring without x-ray: walk (or tunnel) in one direction for a long way, turning away
     * from lava; fortresses stretch far along one axis, so a straight line finds them best. Heads for
     * fortress blocks and spawners once they are in sight.
     */
    private void doExploreNether(ServerLevel level) {
        if (this.bot.getY() < 45.0) {
            // Down at the lava sea (y 31): climb back up before going on.
            this.doDigUp(level);
            this.step = null;
            return;
        }
        if (PvpBotEntity.DEBUG && ++this.netherLogTicks % 200 == 0) {
            BlockPos f = this.bot.blockPosition().relative(this.spiralDir);
            PvpBotMod.LOGGER.info("[SELFTEST]   nether: at {} leg {} {} stuck {} navDone {} digBlocked {} dryWalk {} ahead {} / {} fortress known {} visited {}",
                    this.bot.blockPosition().toShortString(), this.spiralLeg, this.spiralDir, this.spiralStuck, this.bot.getNavigation().isDone(),
                    this.digBlocked, this.dryWalkTicks, level.getBlockState(f).getBlock(), level.getBlockState(f.above()).getBlock(),
                    this.known.getOrDefault(Ore.FORTRESS, List.of()).size(), this.fortressVisited.size());
        }
        // (The spawner and the blazes only while it still needs rods; after that: endermen.)
        boolean wantRods = this.kit().count(Res.BLAZE_ROD.match) * 2 + this.kit().count(Res.BLAZE_POWDER.match)
                < EYES_WANTED - this.kit().count(Res.EYE.match);
        BlockPos goal = wantRods ? this.nearest(Ore.SPAWNER) : null;
        if (goal == null && wantRods) {
            // A blaze nearby can be heard (like a player hears them breathing): go that way.
            var blaze = this.level().getNearestEntity(net.minecraft.world.entity.monster.Blaze.class,
                    net.minecraft.world.entity.ai.targeting.TargetingConditions.forNonCombat().ignoreLineOfSight(), this.bot,
                    this.bot.getX(), this.bot.getY(), this.bot.getZ(), this.bot.getBoundingBox().inflate(24.0));
            if (blaze != null) {
                goal = blaze.blockPosition().below();
            }
        }
        if (goal == null && wantRods) {
            // In the fortress: go through its halls and bridges, to parts it has not been to yet.
            this.fortressVisited.add(cellKey(this.bot.blockPosition()));
            double bestDist = Double.MAX_VALUE;
            for (BlockPos p : this.known.getOrDefault(Ore.FORTRESS, List.of())) {
                // (Not the pillars the bridges stand on: they go down into the lava sea.)
                if (this.fortressVisited.contains(cellKey(p)) || this.blacklist.contains(p) || p.getY() < 45) {
                    continue;
                }
                double d = this.bot.blockPosition().distSqr(p);
                if (d < bestDist) {
                    goal = p;
                    bestDist = d;
                }
            }
        }
        for (BlockPos p : this.known.getOrDefault(Ore.FORTRESS, List.of())) {
            if (p.getY() >= 45) {
                this.fortressCells.add(cellKey(p));
            }
        }
        if (goal == null && !wantRods) {
            // Endermen: the warped forest is where they are (seen from afar, it is bright blue).
            BlockPos warped = this.nearest(Ore.WARPED);
            if (warped != null && this.bot.blockPosition().distSqr(warped) > 12 * 12) {
                goal = warped;
            } else if (warped != null) {
                // In the forest: wait for them (hunting starts as soon as one is in sight).
                this.bot.getNavigation().stop();
                this.step = null;
                return;
            }
        }
        if (goal == null && wantRods && !this.fortressCells.isEmpty()) {
            // Every part of the fortress it has seen is done: on along its halls and bridges, to the
            // places right next to the parts it has seen (a bridge goes on there, or it is lava).
            double bestDist = Double.MAX_VALUE;
            for (long cell : this.fortressCells) {
                BlockPos c = BlockPos.of(cell);
                for (Direction d : Direction.Plane.HORIZONTAL) {
                    BlockPos n = c.relative(d);
                    long key = BlockPos.asLong(n.getX(), n.getY(), n.getZ());
                    if (this.fortressVisited.contains(key) || this.fortressCells.contains(key)) {
                        continue;
                    }
                    BlockPos center = new BlockPos(n.getX() * 8 + 4, n.getY() * 8 + 2, n.getZ() * 8 + 4);
                    double dist = this.bot.blockPosition().distSqr(center);
                    if (dist < bestDist && !this.blacklist.contains(center)) {
                        goal = center;
                        bestDist = dist;
                    }
                }
            }
        }
        if (goal == null && this.kit().count(BRIDGE_BLOCK) < 16 && this.mineNetherrack(level)) {
            // Out of blocks to bridge lava with: netherrack from the walls around (like a player).
            this.step = null;
            return;
        }
        if (goal != null && this.bot.blockPosition().distSqr(goal) <= 25 && !level.getBlockState(goal).is(net.minecraft.world.level.block.Blocks.SPAWNER)) {
            // Close enough to see that part of the fortress: next part.
            this.fortressVisited.add(cellKey(goal));
        }
        boolean spawnerGoal = goal != null && level.getBlockState(goal).is(Blocks.SPAWNER);
        // (Waiting only where it can see the spawner: from the hall under it, it never sees the blazes.)
        boolean atSpawner = spawnerGoal && this.bot.blockPosition().distSqr(goal) <= 6 * 6 && this.seesBlock(level, goal);
        if (atSpawner) {
            // Close to the spawner: wait here for the blazes (they come out every few seconds).
            this.bot.getNavigation().stop();
            this.bot.getLookControl().setLookAt(Vec3.atCenterOf(goal));
            this.step = null;
            return;
        }
        if (goal != null && (this.bot.blockPosition().distSqr(goal) > 9 || spawnerGoal)) {
            // Getting closer? If not for a long while (behind lava, up a cliff), forget that block.
            double dist = Math.sqrt(this.bot.blockPosition().distSqr(goal));
            // (Switching back and forth between two goals without moving counts as stuck too.)
            boolean moved = this.netherStuckPos == null || this.bot.blockPosition().distSqr(this.netherStuckPos) > 3 * 3;
            if (!goal.equals(this.netherGoal)) {
                this.netherGoal = goal;
                this.netherGoalBest = dist;
                this.netherGoalTotal = 0;
            }
            if (moved || dist < this.netherGoalBest - 1.0) {
                this.netherGoalTicks = 0;
                this.netherGoalBest = Math.min(this.netherGoalBest, dist);
                this.netherStuckPos = this.bot.blockPosition();
            }
            if (++this.netherGoalTicks > 300 || ++this.netherGoalTotal > 1500) {
                StringBuilder around = new StringBuilder();
                BlockPos f0 = this.bot.blockPosition();
                for (Direction d : Direction.Plane.HORIZONTAL) {
                    around.append(d.getName().charAt(0)).append(':')
                            .append(level.getBlockState(f0.relative(d).below()).getBlock().getName().getString()).append('/')
                            .append(level.getBlockState(f0.relative(d)).getBlock().getName().getString()).append('/')
                            .append(level.getBlockState(f0.relative(d).above()).getBlock().getName().getString()).append(' ');
                }
                PvpBotMod.LOGGER.info("[SELFTEST]   nether: gives up on {} at {} (no way there) exact {} {} {} ground {} feet {} below {} head {} | {}", goal.toShortString(),
                        this.bot.blockPosition().toShortString(), String.format("%.2f", this.bot.getX()), String.format("%.2f", this.bot.getY()),
                        String.format("%.2f", this.bot.getZ()), this.bot.onGround(), level.getBlockState(f0).getBlock().getName().getString(),
                        level.getBlockState(f0.below()).getBlock().getName().getString(), level.getBlockState(f0.above(2)).getBlock().getName().getString(), around);
                this.blacklist.add(goal);
                this.fortressVisited.add(cellKey(goal));
                this.netherGoal = null;
                this.step = null;
                return;
            }
            BlockPos stand = standBeside(level, goal);
            this.bot.getNavigation().moveTo(stand.getX() + 0.5, stand.getY(), stand.getZ() + 0.5, 1.1);
            if (this.bot.getNavigation().isDone()) {
                // No path: tunnel towards it.
                Vec3 to = Vec3.atCenterOf(goal).subtract(this.bot.position());
                this.digDir = Math.abs(to.x) > Math.abs(to.z) ? (to.x > 0 ? Direction.EAST : Direction.WEST) : (to.z > 0 ? Direction.SOUTH : Direction.NORTH);
                if (to.y > (spawnerGoal ? 1.5 : 3.0)) {
                    // The fortress is up there (its bridges stand high): stairs up to it.
                    this.doDigUp(level);
                } else if (to.y < -2.5 && goal.getY() >= 45 && Math.abs(to.x) + Math.abs(to.z) < 12.0) {
                    // Standing on its roof, the halls are right below: straight down through the roof
                    // when it is a short, safe drop (never below the fortress, the lava sea is down there).
                    BlockPos under = this.bot.blockPosition().below();
                    int drop = 0;
                    boolean lava = false;
                    while (drop < 7 && level.getBlockState(under.below(drop + 1)).getCollisionShape(level, under.below(drop + 1)).isEmpty()) {
                        drop++;
                        lava |= !level.getFluidState(under.below(drop)).isEmpty();
                    }
                    lava |= !level.getFluidState(under.below(drop + 1)).isEmpty() || this.nearLava(level, under);
                    BlockState roof = level.getBlockState(under);
                    if (!lava && drop <= 5 && !roof.getCollisionShape(level, under).isEmpty() && roof.getDestroySpeed(level, under) >= 0.0F) {
                        this.bot.getNavigation().stop();
                        this.bot.getMoveControl().setWantedPosition(this.bot.getX(), this.bot.getY(), this.bot.getZ(), 0.0);
                        this.breakBlock(level, under);
                    } else {
                        this.doDig(level, true);
                    }
                } else {
                    this.doDig(level, false); // (never down towards the lava sea)
                }
            }
            this.step = null;
            return;
        }
        // A square spiral around where it arrived (legs of 64, 64, 128, 128, 192 ...), so it covers
        // the area around the portal instead of running off in one line.
        if (this.spiralStart == null) {
            this.spiralStart = this.bot.blockPosition();
            this.spiralLegStart = this.bot.blockPosition();
            this.spiralLeg = 0;
            this.spiralDir = this.digDir;
        }
        int legLength = 64 * (this.spiralLeg / 2 + 1);
        BlockPos here = this.bot.blockPosition();
        int travelled = Math.abs(here.getX() - this.spiralLegStart.getX()) + Math.abs(here.getZ() - this.spiralLegStart.getZ());
        // Real progress along the leg (jiggling on the spot does not count).
        if (travelled > this.spiralBest) {
            this.spiralBest = travelled;
            this.spiralStuck = 0;
        } else {
            this.spiralStuck++;
        }
        if (travelled >= legLength || this.noProgressTicks > 400 || this.spiralStuck > 600) {
            this.spiralBest = 0;
            this.spiralStuck = 0;
            this.spiralLeg++;
            this.spiralDir = this.spiralDir.getClockWise();
            this.spiralLegStart = here;
            this.noProgressTicks = 0;
            this.exploreTarget = null;
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   nether spiral: leg {} towards {} at {}", this.spiralLeg, this.spiralDir, here.toShortString());
            }
        }
        boolean stuck = this.noProgress();
        if (this.bot.getNavigation().isDone() || stuck || this.spiralStuck > 200 || this.exploreTarget == null
                || this.bot.position().distanceToSqr(this.exploreTarget) < 9.0) {
            Vec3 dir = new Vec3(this.spiralDir.getStepX(), 0.0, this.spiralDir.getStepZ());
            Vec3 candidate = this.bot.position().add(dir.scale(24.0));
            this.exploreTarget = candidate;
            if (stuck || this.spiralStuck > 200 || !this.bot.getNavigation().moveTo(candidate.x, candidate.y, candidate.z, 1.1)) {
                // No walkable way (or walking gets nowhere): tunnel straight on (doDig turns away from lava).
                this.digDir = this.spiralDir;
                this.doDig(level, false);
            }
        }
        this.step = null;
    }

    private @Nullable BlockPos spiralStart;
    private @Nullable BlockPos spiralLegStart;
    private int spiralLeg;
    private int spiralBest;
    private int crystalLogTicks;
    private int crystalAimTicks;
    private int crystalNoLos;
    private int digLogTicks;
    private int dragonLogTicks;
    private double eyeLeg = 180.0;
    private int strongholdLogTicks;
    private int dragonShotTicks;
    private int netherLogTicks;
    private int fireTicks;
    private int digStateLog;
    private int sidewaysTicks;
    private final java.util.Set<Long> fortressVisited = new java.util.HashSet<>();
    private final java.util.Set<Long> fortressCells = new java.util.HashSet<>();
    private int netherrackTicks;

    /** Mines a netherrack block it can see within reach (not the floor it stands on). */
    private boolean mineNetherrack(ServerLevel level) {
        if (++this.netherrackTicks > 1200) {
            if (this.netherrackTicks > 2400) {
                this.netherrackTicks = 0; // (a while exploring, then try again)
            }
            return false;
        }
        BlockPos feet = this.bot.blockPosition();
        BlockPos best = null;
        double bestDist = Double.MAX_VALUE;
        for (BlockPos p : BlockPos.betweenClosed(feet.offset(-3, 0, -3), feet.offset(3, 2, 3))) {
            if (!level.getBlockState(p).is(Blocks.NETHERRACK) || this.nearLava(level, p) || !this.seesBlock(level, p)) {
                continue;
            }
            double d = this.bot.getEyePosition().distanceToSqr(Vec3.atCenterOf(p));
            if (d < bestDist && d < 4.0 * 4.0) {
                best = p.immutable();
                bestDist = d;
            }
        }
        if (best == null) {
            return false;
        }
        this.bot.getNavigation().stop();
        this.breakBlock(level, best);
        return true;
    }
    private int spiralStuck;
    private Direction spiralDir = Direction.NORTH;

    // --- stage 3: stronghold

    /**
     * Throws an eye of ender. Like in the game it only shows the direction to the stronghold, and it
     * goes down when the stronghold is right below. One in five eyes breaks.
     */
    private void doThrowEye(ServerLevel level) {
        this.bot.getNavigation().stop();
        BlockPos target = level.findNearestMapStructure(net.minecraft.tags.StructureTags.EYE_OF_ENDER_LOCATED, this.bot.blockPosition(), 100, false);
        level.playSound(null, this.bot.blockPosition(), SoundEvents.ENDER_EYE_LAUNCH, this.bot.getSoundSource(), 1.0F, 1.0F);
        this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
        if (this.bot.getRandom().nextInt(5) == 0) {
            this.kit().remove(Res.EYE.match, 1);
            this.bot.tellOwner("§7Das Enderauge ist zerbrochen.", false);
        }
        this.legTicks = 0;
        this.legBest = 0.0;
        this.legStuckTicks = 0;
        this.legStart = this.bot.position();
        if (target == null) {
            this.bot.tellOwner("§cDas Enderauge zeigt nirgendwo hin – hier gibt es keine Festung.", true);
            this.eyeDir = null;
            this.step = null;
            return;
        }
        Vec3 toTarget = Vec3.atCenterOf(target).subtract(this.bot.position()).multiply(1.0, 0.0, 1.0);
        if (toTarget.length() < 12.0) {
            this.eyeWentDown = true;
            this.bot.tellOwner("§5Das Enderauge fliegt nach unten – die Festung ist hier drunter!", true);
        } else {
            Vec3 dir = toTarget.normalize();
            if (this.eyeDir != null && dir.dot(this.eyeDir) < 0.0) {
                // The eye points back: we walked past it. Shorter legs from now on.
                this.eyeLeg = Math.max(24.0, this.eyeLeg / 2.0);
            }
            this.eyeDir = dir;
            this.digDir = Direction.getApproximateNearest(this.eyeDir.x, 0.0, this.eyeDir.z);
        }
        this.step = null;
    }

    /**
     * Stuck swimming against a bank that is too high to climb: dig a notch into it (the two blocks
     * above water level) like a player would, then swim in and jump out.
     */
    private void climbBank(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        Direction d = this.eyeDir != null ? Direction.getApproximateNearest(this.eyeDir.x, 0.0, this.eyeDir.z) : this.digDir;
        BlockPos front = feet.relative(d);
        for (BlockPos p : new BlockPos[]{front.above(2), front.above()}) {
            BlockState st = level.getBlockState(p);
            if (!st.getCollisionShape(level, p).isEmpty() && st.getDestroySpeed(level, p) >= 0.0F && !this.nearLava(level, p)) {
                this.bot.getNavigation().stop();
                this.breakBlock(level, p);
                return;
            }
        }
        Vec3 c = Vec3.atBottomCenterOf(front.above());
        this.bot.getNavigation().stop();
        this.bot.getMoveControl().setWantedPosition(c.x, c.y, c.z, 1.0);
        this.bot.getJumpControl().jump();
    }

    /** Walks along the eye's direction for a while (tunnels where it cannot walk), then throws again. */
    private void doFollowEye(ServerLevel level) {
        if (this.eyeDir == null || this.legStart == null) {
            this.step = null;
            return;
        }
        this.legTicks++;
        if (this.bot.isInWater() && this.bot.horizontalCollision) {
            // Swimming against a bank: cut a step into it and climb out (a swimming mob cannot get up
            // a bank higher than one block).
            this.climbBank(level);
            this.step = null;
            return;
        }
        double travelled = this.bot.position().subtract(this.legStart).horizontalDistance();
        if (travelled > this.eyeLeg) {
            this.legTicks = Integer.MAX_VALUE / 2; // throw the next eye
            this.step = null;
            return;
        }
        // Progress is measured along the eye's line, not just as movement (pacing back and forth
        // in front of a lake is not progress).
        double along = this.bot.position().subtract(this.legStart).dot(this.eyeDir);
        if (along > this.legBest + 1.0) {
            this.legBest = along;
            this.legStuckTicks = 0;
        } else {
            this.legStuckTicks++;
        }
        boolean walking = !this.bot.getNavigation().isDone() && this.exploreTarget != null
                && this.bot.position().distanceToSqr(this.exploreTarget) > 4.0 && this.legStuckTicks < 100;
        if (!walking) {
            // Straight on if possible, otherwise the smallest detour around water, cliffs and hills.
            double[] turns = this.legStuckTicks < 100 ? new double[]{0.0} : new double[]{0.0, 45.0, -45.0, 90.0, -90.0, 135.0, -135.0};
            if (this.legStuckTicks >= 100 && this.bot.getRandom().nextBoolean()) {
                for (int i = 1; i + 1 < turns.length; i += 2) {
                    double t = turns[i];
                    turns[i] = turns[i + 1];
                    turns[i + 1] = t;
                }
            }
            boolean path = false;
            Vec3 goal = null;
            for (double turn : turns) {
                Vec3 dir = this.eyeDir.yRot((float) Math.toRadians(turn));
                Vec3 g = this.bot.position().add(dir.scale(turn == 0.0 ? 12.0 : 16.0));
                int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, Mth.floor(g.x), Mth.floor(g.z));
                var p = this.bot.getNavigation().createPath(Mth.floor(g.x), y, Mth.floor(g.z), 1);
                // A path that only gets part of the way is fine too, as long as it gets well closer.
                boolean useful = p != null && (p.canReach() || p.getEndNode() != null
                        && Vec3.atCenterOf(p.getEndNode().asBlockPos()).distanceTo(g) < this.bot.position().distanceTo(g) - 6.0);
                // (Stuck for long despite a path: walking does not work here, use the fallbacks below.)
                if (useful && this.legStuckTicks < 200 && level.getFluidState(new BlockPos(Mth.floor(g.x), y - 1, Mth.floor(g.z))).isEmpty()) {
                    this.bot.getNavigation().moveTo(p, 1.1);
                    goal = new Vec3(g.x, y, g.z);
                    path = true;
                    if (turn != 0.0) {
                        this.legStuckTicks = 40; // walk the detour, then try straight on again
                    }
                    break;
                }
            }
            this.exploreTarget = goal;
            BlockPos ahead = this.bot.blockPosition().offset(Mth.floor(this.eyeDir.x * 2.0 + 0.5), 0, Mth.floor(this.eyeDir.z * 2.0 + 0.5));
            boolean water = this.bot.isInWater() || !level.getFluidState(ahead).isEmpty() || !level.getFluidState(ahead.below()).isEmpty();
            // In the water and not getting anywhere (a steep bank, an overhang): swim straight on
            // first, then dig into the bank, then swim along the shore for a bit, and again.
            int waterPhase = this.legStuckTicks < 200 ? 0 : this.legStuckTicks < 300 ? 1 : 2;
            if (this.legStuckTicks >= 400) {
                this.legStuckTicks = 100;
            }
            if (!path && water && waterPhase != 1) {
                // A lake or the sea in the way: swim straight across like a player.
                Vec3 dir = waterPhase == 0 ? this.eyeDir : this.eyeDir.yRot((float) Math.toRadians((this.legTicks / 400) % 2 == 0 ? 90.0 : -90.0));
                Vec3 to = this.bot.position().add(dir.scale(3.0));
                this.bot.getNavigation().stop();
                this.bot.getMoveControl().setWantedPosition(to.x, this.bot.getY(), to.z, 1.0);
                if (this.bot.isInWater() || this.bot.horizontalCollision) {
                    this.bot.getJumpControl().jump();
                }
            } else if (!path && water) {
                this.climbBank(level);
            } else if (!path) {
                // No way to walk anywhere near the line: tunnel straight on.
                this.digDir = Direction.getApproximateNearest(this.eyeDir.x, 0.0, this.eyeDir.z);
                this.doDig(level, false);
            }
            if (PvpBotEntity.DEBUG && this.legTicks % 100 == 0) {
                PvpBotMod.LOGGER.info("[SELFTEST]   eye: pos {} goal {} path={} stuckTicks={} along={}", this.bot.blockPosition().toShortString(),
                        goal == null ? "-" : BlockPos.containing(goal).toShortString(), path, this.legStuckTicks, (int) along);
            }
        }
        this.step = null;
    }

    /**
     * In lava: bucket of water at its feet like a player would (the lava around turns to stone), jump
     * and head back to the last safe block. Remembers safe ground while all is well.
     */
    private boolean escapeLava(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        if (!this.bot.isInLava()) {
            if (this.bot.onGround() && !this.nearLava(level, feet) && !this.nearLava(level, feet.below())) {
                this.lastSafe = feet;
            }
            if (this.bot.isOnFire() && !this.bot.hasEffect(net.minecraft.world.effect.MobEffects.FIRE_RESISTANCE)) {
                if (this.bot.getHealth() < 14.0F) {
                    this.drinkFireResistance(level);
                }
                if (this.bot.isOnFire() && level.dimension() != net.minecraft.world.level.Level.NETHER
                        && this.kit().count(st -> st.is(Items.WATER_BUCKET)) > 0 && level.getBlockState(feet).canBeReplaced()
                        && level.getFluidState(feet).isEmpty()) {
                    // Burning: water at its feet puts it out (the bucket is filled again later).
                    level.setBlock(feet, net.minecraft.world.level.block.Blocks.WATER.defaultBlockState(), 3);
                    level.playSound(null, feet, SoundEvents.BUCKET_EMPTY, this.bot.getSoundSource(), 1.0F, 1.0F);
                    if (!this.kit().isInfinite()) {
                        this.kit().remove(st -> st.is(Items.WATER_BUCKET), 1);
                        this.kit().insert(new ItemStack(Items.BUCKET));
                        this.bot.onKitChanged();
                    }
                } else if (this.lastSafe != null && this.lastSafe.distSqr(feet) > 1 && ++this.fireTicks > 20) {
                    // Still burning after a second: back to the last safe spot, away from what burns.
                    this.bot.getNavigation().stop();
                    this.bot.getMoveControl().setWantedPosition(this.lastSafe.getX() + 0.5, this.lastSafe.getY(), this.lastSafe.getZ() + 0.5, 1.2);
                    if (this.mineTarget != null) {
                        this.blacklist.add(this.mineTarget);
                        this.mineTarget = null;
                    }
                    this.step = null;
                    return true;
                }
            } else {
                this.fireTicks = 0;
            }
            return false;
        }
        this.stopBreaking();
        this.bot.getNavigation().stop();
        this.drinkFireResistance(level);
        if (level.dimension() != net.minecraft.world.level.Level.NETHER && this.kit().count(st -> st.is(Items.WATER_BUCKET)) > 0
                && level.getBlockState(feet).getFluidState().is(net.minecraft.tags.FluidTags.LAVA)) {
            level.setBlock(feet, net.minecraft.world.level.block.Blocks.WATER.defaultBlockState(), 3);
            level.playSound(null, feet, SoundEvents.BUCKET_EMPTY, this.bot.getSoundSource(), 1.0F, 1.0F);
            if (!this.kit().isInfinite()) {
                this.kit().remove(st -> st.is(Items.WATER_BUCKET), 1);
                this.kit().insert(new ItemStack(Items.BUCKET));
                this.bot.onKitChanged();
            }
            this.bot.tellOwner("§6Lava! §7Wassereimer drauf und raus.", false);
        } else if (level.getFluidState(feet).is(net.minecraft.tags.FluidTags.LAVA) && this.kit().count(BRIDGE_BLOCK) > 0
                && !level.getFluidState(feet.above()).is(net.minecraft.tags.FluidTags.LAVA)) {
            // No water (the nether): a block where it stands, like a player would - it ends up on top.
            ItemStack block = ItemStack.EMPTY;
            for (ItemStack st : this.kit().items()) {
                if (BRIDGE_BLOCK.test(st)) {
                    block = st;
                    break;
                }
            }
            if (block.getItem() instanceof net.minecraft.world.item.BlockItem bi) {
                level.setBlock(feet, bi.getBlock().defaultBlockState(), 3);
                this.bot.setPos(this.bot.getX(), feet.getY() + 1.0, this.bot.getZ());
                if (!this.kit().isInfinite()) {
                    Item item = block.getItem();
                    this.kit().remove(st -> st.is(item), 1);
                    this.bot.onKitChanged();
                }
                this.bot.tellOwner("§6Lava! §7Block drunter und raus.", false);
            }
        }
        this.bot.getJumpControl().jump();
        // Out the nearest way: the closest shore around (the last safe spot may be far up a cliff).
        BlockPos shore = null;
        double best = Double.MAX_VALUE;
        for (BlockPos p : BlockPos.betweenClosed(feet.offset(-12, -2, -12), feet.offset(12, 3, 12))) {
            if (level.getFluidState(p).isEmpty() && level.getFluidState(p.above()).isEmpty()
                    && level.getBlockState(p).getCollisionShape(level, p).isEmpty() && level.getBlockState(p.above()).getCollisionShape(level, p.above()).isEmpty()
                    && !level.getBlockState(p.below()).getCollisionShape(level, p.below()).isEmpty() && level.getFluidState(p.below()).isEmpty()) {
                double d = p.distSqr(feet);
                if (d < best) {
                    best = d;
                    shore = p.immutable();
                }
            }
        }
        BlockPos out = shore != null && (this.lastSafe == null || best < this.lastSafe.distSqr(feet)) ? shore : this.lastSafe;
        if (out != null) {
            this.bot.getMoveControl().setWantedPosition(out.getX() + 0.5, out.getY(), out.getZ() + 0.5, 1.3);
        }
        // Whatever it was doing there is not worth it: forget that spot.
        if (this.mineTarget != null) {
            this.blacklist.add(this.mineTarget);
            this.mineTarget = null;
        }
        this.step = null;
        return true;
    }

    /** Drinks a fire resistance potion from the kit (once, while the effect is not active). */
    private void drinkFireResistance(ServerLevel level) {
        if (this.bot.hasEffect(net.minecraft.world.effect.MobEffects.FIRE_RESISTANCE)) {
            return;
        }
        for (ItemStack st : this.kit().items()) {
            var contents = st.get(net.minecraft.core.component.DataComponents.POTION_CONTENTS);
            if (st.is(Items.POTION) && contents != null && contents.is(net.minecraft.world.item.alchemy.Potions.FIRE_RESISTANCE)
                    || st.is(Items.POTION) && contents != null && contents.is(net.minecraft.world.item.alchemy.Potions.LONG_FIRE_RESISTANCE)) {
                int duration = contents.is(net.minecraft.world.item.alchemy.Potions.LONG_FIRE_RESISTANCE) ? 9600 : 3600;
                this.bot.addEffect(new net.minecraft.world.effect.MobEffectInstance(net.minecraft.world.effect.MobEffects.FIRE_RESISTANCE, duration));
                level.playSound(null, this.bot.blockPosition(), SoundEvents.GENERIC_DRINK.value(), this.bot.getSoundSource(), 1.0F, 1.0F);
                if (!this.kit().isInfinite()) {
                    st.shrink(1);
                    this.kit().insert(new ItemStack(Items.GLASS_BOTTLE));
                }
                this.bot.tellOwner("§6Feuerresistenz getrunken.", false);
                return;
            }
        }
    }

    private boolean noProgress() {
        Vec3 pos = this.bot.position();
        if (this.lastPos != null && pos.distanceToSqr(this.lastPos) < 0.01) {
            this.noProgressTicks++;
        } else {
            this.noProgressTicks = 0;
        }
        this.lastPos = pos;
        return this.noProgressTicks > 40;
    }

    /** Inside the stronghold: go to walls it has not been near yet; the portal room shows up on the way. */
    private void doExploreStronghold(ServerLevel level) {
        BlockPos here = this.bot.blockPosition();
        this.visitedCells.add(cellKey(here));
        BlockPos best = null;
        double bestDist = Double.MAX_VALUE;
        for (BlockPos p : this.known.getOrDefault(Ore.STRONGHOLD, List.of())) {
            if (this.visitedCells.contains(cellKey(p)) || this.blacklist.contains(p)) {
                continue;
            }
            double d = here.distSqr(p);
            if (d < bestDist) {
                best = p;
                bestDist = d;
            }
        }
        if (best == null) {
            this.doDig(level, false);
            this.step = null;
            return;
        }
        if (PvpBotEntity.DEBUG && ++this.strongholdLogTicks % 200 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   stronghold: at {} target {} known bricks {} visited cells {} frames {}", here.toShortString(),
                    best.toShortString(), this.known.getOrDefault(Ore.STRONGHOLD, List.of()).size(), this.visitedCells.size(),
                    this.known.getOrDefault(Ore.END_FRAME, List.of()).size());
        }
        // No new part of the stronghold for a while (the path ends short of that wall, two walls take
        // turns as the target, it jiggles on the spot): count that one as seen and take the next.
        if (this.visitedCells.size() != this.strongholdCells) {
            this.strongholdCells = this.visitedCells.size();
            this.strongholdTicks = 0;
        } else if (++this.strongholdTicks > 400) {
            this.visitedCells.add(cellKey(best));
            this.strongholdTicks = 0;
            this.step = null;
            return;
        }
        // Walk along the corridor next to the wall (not into the wall: that is slow and wakes silverfish).
        BlockPos stand = standBeside(level, best);
        if (this.strongholdTicks > 200 || !this.bot.getNavigation().moveTo(stand.getX() + 0.5, stand.getY(), stand.getZ() + 0.5, 1.0) || this.noProgress()) {
            this.mineTarget = best;
            this.tunnelTowards(level, best);
            if (this.noProgressTicks > 200) {
                this.visitedCells.add(cellKey(best));
                this.noProgressTicks = 0;
            }
        }
        this.step = null;
    }

    /** Where to stand to be at this block: on top of it (a floor) or in the free space next to it (a wall). */
    private static BlockPos standBeside(ServerLevel level, BlockPos block) {
        if (free(level, block.above()) && free(level, block.above(2))) {
            return block.above();
        }
        for (Direction d : Direction.Plane.HORIZONTAL) {
            BlockPos side = block.relative(d);
            if (free(level, side) && free(level, side.above())) {
                BlockPos stand = side;
                while (stand.getY() > level.getMinY() && free(level, stand.below()) && block.getY() - stand.getY() < 4) {
                    stand = stand.below();
                }
                return stand;
            }
        }
        return block.above();
    }

    private static boolean free(ServerLevel level, BlockPos p) {
        return level.getBlockState(p).getCollisionShape(level, p).isEmpty() && level.getFluidState(p).isEmpty();
    }

    private static long cellKey(BlockPos p) {
        return BlockPos.asLong(p.getX() >> 3, p.getY() >> 3, p.getZ() >> 3);
    }

    /** Puts eyes into the frames it can see; once all twelve are filled the portal opens. */
    private void doFillEndPortal(ServerLevel level) {
        List<BlockPos> frames = new ArrayList<>(this.known.getOrDefault(Ore.END_FRAME, List.of()));
        BlockPos next = null;
        for (BlockPos f : frames) {
            BlockState st = level.getBlockState(f);
            if (st.is(net.minecraft.world.level.block.Blocks.END_PORTAL_FRAME) && !st.getValue(net.minecraft.world.level.block.EndPortalFrameBlock.HAS_EYE)) {
                if (next == null || this.bot.blockPosition().distSqr(f) < this.bot.blockPosition().distSqr(next)) {
                    next = f;
                }
            }
        }
        if (next != null) {
            if (this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(next)) > 4.0) {
                this.bot.getNavigation().moveTo(next.getX() + 0.5, next.getY() + 1, next.getZ() + 0.5, 1.0);
                this.step = null;
                return;
            }
            if (this.kit().remove(Res.EYE.match, 1) == 0) {
                this.bot.tellOwner("§cMir fehlen Enderaugen für den Rahmen.", true);
                this.stage2Done = false;
                this.step = null;
                return;
            }
            this.bot.lookAtBlock(next);
            level.setBlock(next, level.getBlockState(next).setValue(net.minecraft.world.level.block.EndPortalFrameBlock.HAS_EYE, true), 2);
            level.playSound(null, next, SoundEvents.END_PORTAL_FRAME_FILL, this.bot.getSoundSource(), 1.0F, 1.0F);
            this.step = null;
            return;
        }
        // All frames we can see have eyes: once all 12 are there, open the portal (like the game does).
        if (frames.size() >= 12) {
            int minX = Integer.MAX_VALUE, maxX = Integer.MIN_VALUE, minZ = Integer.MAX_VALUE, maxZ = Integer.MIN_VALUE, y = frames.get(0).getY();
            for (BlockPos f : frames) {
                minX = Math.min(minX, f.getX());
                maxX = Math.max(maxX, f.getX());
                minZ = Math.min(minZ, f.getZ());
                maxZ = Math.max(maxZ, f.getZ());
            }
            for (int x = minX + 1; x < maxX; x++) {
                for (int z = minZ + 1; z < maxZ; z++) {
                    level.setBlock(new BlockPos(x, y, z), net.minecraft.world.level.block.Blocks.END_PORTAL.defaultBlockState(), 2);
                }
            }
            level.globalLevelEvent(1038, new BlockPos(minX + 2, y, minZ + 2), 0);
            this.bot.tellOwner("§5§lDas Endportal ist offen! §7Auf zum Drachen.", true);
            this.known.computeIfAbsent(Ore.END_PORTAL, k -> new ArrayList<>()).add(new BlockPos(minX + 2, y, minZ + 2));
        } else {
            // Not all frames in sight yet: walk into the middle of the ones we know.
            BlockPos f = frames.get(0);
            this.bot.getNavigation().moveTo(f.getX() + 0.5, f.getY() + 1, f.getZ() + 0.5, 1.0);
        }
        this.step = null;
    }

    private void doUseEndPortal() {
        this.wantPortalTick = this.bot.tickCount;
        BlockPos portal = this.nearest(Ore.END_PORTAL);
        if (portal == null) {
            this.step = null;
            return;
        }
        Vec3 c = Vec3.atBottomCenterOf(portal);
        this.bot.getNavigation().moveTo(c.x, c.y, c.z, 1.0);
        if (this.bot.position().distanceToSqr(c) < 9.0) {
            this.bot.getMoveControl().setWantedPosition(c.x, c.y, c.z, 1.0);
        }
        this.step = null;
    }

    // --- stage 4: the end

    private void doShootCrystal() {
        var crystal = this.visibleCrystal();
        if (crystal == null) {
            this.step = null;
            return;
        }
        ServerLevel level = this.level();
        if (PvpBotEntity.DEBUG && ++this.crystalLogTicks % 100 == 0) {
            int left = level.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EndCrystal.class, this.bot.getBoundingBox().inflate(200.0)).size();
            PvpBotMod.LOGGER.info("[SELFTEST]   crystals left {} - shooting at {} (shots {}) from {} pole {} caged {}", left, crystal.blockPosition().toShortString(),
                    this.crystalShots.getOrDefault(crystal.getUUID(), 0), this.bot.blockPosition().toShortString(),
                    this.towerGroundY == Integer.MIN_VALUE ? "-" : (int) (this.bot.getY() - this.towerGroundY), this.isCaged(level, crystal));
        }
        if (this.towerGroundY != Integer.MIN_VALUE && (this.poleDone || !crystal.getUUID().equals(this.towerCrystal))) {
            if (this.descendTower(level)) {
                this.step = null;
                return;
            }
        }
        this.step = null;
        Vec3 away = this.bot.position().subtract(crystal.position()).multiply(1.0, 0.0, 1.0);
        double h = away.length();
        boolean los = this.bot.hasLineOfSight(crystal);
        int shots = this.crystalShots.getOrDefault(crystal.getUUID(), 0);
        boolean onPole = this.towerGroundY != Integer.MIN_VALUE && this.bot.getY() > this.towerGroundY + 0.5;
        if (onPole) {
            this.onCrystalPole(level, crystal, los);
            return;
        }
        if (this.towerGroundY != Integer.MIN_VALUE && this.poleSpot != null
                && Vec3.atBottomCenterOf(this.poleSpot).subtract(this.bot.position()).horizontalDistanceSqr() > 2.0 * 2.0) {
            // Knocked off its pole: start a new one (the old one is in the way now).
            this.towerGroundY = Integer.MIN_VALUE;
            this.towerCrystal = null;
            this.poleSpot = null;
        }
        boolean caged = this.isCaged(level, crystal);
        if (los && !caged && h <= 44.0 && (shots < 6 || this.kit().count(BRIDGE_BLOCK) == 0)) {
            this.bot.getNavigation().stop();
            this.shootCrystal(crystal);
            return;
        }
        if (this.kit().count(BRIDGE_BLOCK) == 0) {
            // Nothing to build with: just walk around for a clear shot.
            this.crystalNoLos++;
            if (this.crystalNoLos > 600) {
                this.giveUpCrystal(crystal);
                return;
            }
            Vec3 spot = crystal.position().add((h < 1.0 ? new Vec3(1.0, 0.0, 0.0) : away.normalize()).scale(30.0));
            int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, Mth.floor(spot.x), Mth.floor(spot.z));
            if (this.bot.getNavigation().isDone() || this.noProgress()) {
                this.bot.getNavigation().moveTo(spot.x, y, spot.z, 1.1);
            }
            return;
        }
        // Like a player: walk to a spot next to it (caged: right at the tower, to break the bars;
        // otherwise far enough out that the blast cannot reach) and build a pole of blocks up.
        if (this.poleSpot == null || !crystal.getUUID().equals(this.poleFor)) {
            this.poleSpot = this.findPoleSpot(level, crystal, caged);
            this.poleFor = crystal.getUUID();
            this.poleWalk = 0;
            if (this.poleSpot == null) {
                this.giveUpCrystal(crystal);
                return;
            }
        }
        BlockPos spot = this.poleSpot;
        double dx = spot.getX() + 0.5 - this.bot.getX();
        double dz = spot.getZ() + 0.5 - this.bot.getZ();
        if (dx * dx + dz * dz > 0.6 * 0.6 || this.bot.getY() > spot.getY() + 0.5) {
            if (++this.poleWalk > 900) {
                // Cannot get there: another spot next time.
                this.poleSpot = null;
                this.giveUpCrystal(crystal);
                return;
            }
            if (dx * dx + dz * dz < 3.0 * 3.0) {
                this.bot.getNavigation().stop();
                this.bot.getMoveControl().setWantedPosition(spot.getX() + 0.5, spot.getY(), spot.getZ() + 0.5, 0.8);
            } else if (this.bot.getNavigation().isDone() || this.noProgress()) {
                this.bot.getNavigation().moveTo(spot.getX() + 0.5, spot.getY(), spot.getZ() + 0.5, 1.1);
            }
            return;
        }
        this.bot.getNavigation().stop();
        this.towerCrystal = crystal.getUUID();
        this.poleDone = false;
        this.poleShots = 0;
        this.poleBestY = this.bot.getY();
        this.poleStall = 0;
        this.pillarUp(level);
    }

    /** On top of its pole: open the cage, or shoot once it sees the crystal, or build further up. */
    private void onCrystalPole(ServerLevel level, net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal, boolean los) {
        this.bot.getNavigation().stop();
        if (this.bot.getY() > this.poleBestY + 0.5) {
            this.poleBestY = this.bot.getY();
            this.poleStall = 0;
        } else if (++this.poleStall > 400) {
            // Not getting any higher (no room above, or out of blocks).
            this.poleStall = 0;
            this.giveUpCrystal(crystal);
            return;
        }
        this.bot.getLookControl().setLookAt(crystal);
        boolean caged = this.isCaged(level, crystal);
        double h = this.bot.position().subtract(crystal.position()).horizontalDistance();
        if (caged && h < 8.0) {
            // Right at the cage: break the bars between it and the crystal, then climb down and
            // shoot from further away (the crystal's blast would kill it this close).
            if (this.bot.getEyeY() < crystal.getY() + 0.8) {
                this.pillarUp(level);
                return;
            }
            var hit = level.clip(new net.minecraft.world.level.ClipContext(this.bot.getEyePosition(), crystal.position().add(0.0, 1.0, 0.0),
                    net.minecraft.world.level.ClipContext.Block.COLLIDER, net.minecraft.world.level.ClipContext.Fluid.NONE, this.bot));
            if (hit.getType() != net.minecraft.world.phys.HitResult.Type.BLOCK) {
                // A bigger hole (two high) for the shot from further away.
                hit = level.clip(new net.minecraft.world.level.ClipContext(this.bot.getEyePosition(), crystal.position().add(0.0, 0.2, 0.0),
                        net.minecraft.world.level.ClipContext.Block.COLLIDER, net.minecraft.world.level.ClipContext.Fluid.NONE, this.bot));
            }
            if (hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK && level.getBlockState(hit.getBlockPos()).is(Blocks.IRON_BARS)
                    && hit.getLocation().distanceTo(this.bot.getEyePosition()) < 4.5) {
                this.breakBlock(level, hit.getBlockPos());
                return;
            }
            if (hit.getType() != net.minecraft.world.phys.HitResult.Type.BLOCK) {
                // Open on this side: down again, then out and up for the shot.
                this.cageOpened.add(crystal.getUUID());
            }
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   cage at {}: {}", crystal.blockPosition().toShortString(),
                        this.cageOpened.contains(crystal.getUUID()) ? "opened" : "cannot open from here");
            }
            if (!this.cageOpened.contains(crystal.getUUID())) {
                this.giveUpCrystal(crystal);
            }
            this.poleSpot = null;
            this.poleDone = true;
            return;
        }
        // Up level with it before shooting: from below, arrows catch the edge of its tower.
        boolean high = this.bot.getEyeY() >= crystal.getY() + 0.5;
        if (los && (high || this.poleStall > 100) && this.bot.onGround()) {
            // A rim of blocks around the feet first, so the dragon cannot push it off.
            BlockPos feet = this.bot.blockPosition();
            for (Direction d : Direction.Plane.HORIZONTAL) {
                if (level.getBlockState(feet.relative(d)).canBeReplaced() && this.bridge(level, feet.relative(d), false)) {
                    return;
                }
            }
        }
        if (los && (high || this.poleStall > 100)) {
            this.shootCrystal(crystal);
            if (this.poleShots > 10) {
                this.giveUpCrystal(crystal);
            }
            return;
        }
        if (this.bot.getEyeY() < crystal.getY() + 4.0) {
            this.pillarUp(level);
            return;
        }
        // Up high and still nothing to see: leave that one.
        this.giveUpCrystal(crystal);
    }

    private void shootCrystal(net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal) {
        this.bot.getLookControl().setLookAt(crystal);
        if (++this.crystalAimTicks >= 20) {
            this.crystalAimTicks = 0;
            if (this.bot.shootAt(crystal.position().add(0.0, 1.0, 0.0))) {
                this.crystalShots.merge(crystal.getUUID(), 1, Integer::sum);
                this.poleShots++;
            }
        }
    }

    private void giveUpCrystal(net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal) {
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   gives up on crystal at {} for now (shots {}, at {})", crystal.blockPosition().toShortString(),
                    this.crystalShots.getOrDefault(crystal.getUUID(), 0), this.bot.blockPosition().toShortString());
        }
        this.crystalShots.put(crystal.getUUID(), 99);
        this.crystalTarget = null;
        this.crystalNoLos = 0;
        this.poleSpot = null;
        this.poleDone = true;
    }

    /** Iron bars right around the crystal (the cage on the smaller towers), not yet broken open. */
    private boolean isCaged(ServerLevel level, net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal) {
        if (this.cageOpened.contains(crystal.getUUID())) {
            return false;
        }
        BlockPos c = crystal.blockPosition();
        for (BlockPos p : BlockPos.betweenClosed(c.offset(-2, 0, -2), c.offset(2, 3, 2))) {
            if (level.getBlockState(p).is(Blocks.IRON_BARS)) {
                return true;
            }
        }
        return false;
    }

    /** Where to build the pole: on the ground, towards the bot (or the middle of the island). */
    private @Nullable BlockPos findPoleSpot(ServerLevel level, net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal, boolean caged) {
        Vec3 c = crystal.position();
        Vec3 toBot = this.bot.position().subtract(c).multiply(1.0, 0.0, 1.0);
        Vec3 toMiddle = new Vec3(-c.x, 0.0, -c.z);
        int radius = 0;
        if (caged) {
            // How wide the obsidian tower is on this side.
            Vec3 dir = toBot.lengthSqr() > 1.0 ? toBot.normalize() : toMiddle.normalize();
            for (int k = 1; k <= 7; k++) {
                BlockPos p = BlockPos.containing(c.x + dir.x * k, c.y - 3.0, c.z + dir.z * k);
                if (level.getBlockState(p).is(Blocks.OBSIDIAN)) {
                    radius = k;
                }
            }
        }
        double dist = caged ? radius + 1.0 : 14.0;
        for (int attempt = 0; attempt < 16; attempt++) {
            Vec3 base = attempt == 0 && toBot.lengthSqr() > 1.0 ? toBot.normalize()
                    : (toMiddle.lengthSqr() > 1.0 ? toMiddle.normalize() : new Vec3(1.0, 0.0, 0.0));
            double angle = attempt == 0 ? 0.0 : ((attempt + 1) / 2) * 0.4 * (attempt % 2 == 0 ? 1 : -1);
            Vec3 dir = base.yRot((float) angle);
            int x = Mth.floor(c.x + dir.x * dist);
            int z = Mth.floor(c.z + dir.z * dist);
            if (caged) {
                // Right next to the obsidian: step out until the column is free.
                for (int k = 0; k < 4 && level.getBlockState(new BlockPos(x, Mth.floor(c.y) - 3, z)).is(Blocks.OBSIDIAN); k++) {
                    x = Mth.floor(c.x + dir.x * (dist + k + 1));
                    z = Mth.floor(c.z + dir.z * (dist + k + 1));
                }
            }
            int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);
            BlockPos ground = new BlockPos(x, y - 1, z);
            if (y > level.getMinY() + 10 && level.getBlockState(ground).is(Blocks.END_STONE) && new Vec3(x, 0, z).horizontalDistance() < 90.0) {
                return new BlockPos(x, y, z);
            }
        }
        return null;
    }

    private @Nullable BlockPos poleSpot;
    private java.util.@Nullable UUID poleFor;
    private int poleWalk;
    private int poleShots;
    private double poleBestY;
    private int poleStall;
    private boolean poleDone;
    private final java.util.Set<java.util.UUID> cageOpened = new java.util.HashSet<>();

    private int towerGroundY = Integer.MIN_VALUE;
    private java.util.@Nullable UUID towerCrystal;
    private @Nullable BlockPos pillarFrom;

    /** One block up: jump and put a block where its feet were. */
    private void pillarUp(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        if (this.towerGroundY == Integer.MIN_VALUE) {
            this.towerGroundY = feet.getY();
        }
        if (this.bot.onGround() && this.pillarFrom == null) {
            if (!level.getBlockState(feet.above(2)).getCollisionShape(level, feet.above(2)).isEmpty()) {
                return; // no room above
            }
            this.pillarFrom = feet;
            this.bot.getJumpControl().jump();
            return;
        }
        if (this.pillarFrom != null && this.bot.getY() >= this.pillarFrom.getY() + 1.0) {
            BlockPos spot = this.pillarFrom;
            this.pillarFrom = null;
            if (level.getBlockState(spot).canBeReplaced()) {
                this.bridge(level, spot, false);
            }
        } else if (this.pillarFrom != null && this.bot.onGround()) {
            this.pillarFrom = null; // landed without placing: try again
        }
    }

    /** Down its own pole again, block by block (never jump off it). Returns true while doing so. */
    private boolean descendTower(ServerLevel level) {
        if (this.bot.getY() <= this.towerGroundY + 0.5) {
            this.towerGroundY = Integer.MIN_VALUE;
            this.towerCrystal = null;
            this.poleDone = false;
            return false;
        }
        this.bot.getNavigation().stop();
        BlockPos below = this.bot.blockPosition().below();
        if (!level.getBlockState(below).getCollisionShape(level, below).isEmpty()) {
            this.breakBlock(level, below);
        } else if (this.bot.onGround()) {
            // Standing on the edge of the ground next to the pole: down already.
            this.towerGroundY = Integer.MIN_VALUE;
            this.towerCrystal = null;
            this.poleDone = false;
            return false;
        }
        return true;
    }

    /**
     * The dragon only lands on the exit fountain now and then; wait next to it, and hit the dragon
     * (head first) while it sits there.
     */
    private void doFightDragon(ServerLevel level) {
        if (this.towerGroundY != Integer.MIN_VALUE && this.descendTower(level)) {
            this.step = null;
            return;
        }
        net.minecraft.world.entity.boss.enderdragon.EnderDragon dragon = null;
        for (var d : level.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EnderDragon.class, this.bot.getBoundingBox().inflate(300.0))) {
            if (d.isAlive()) {
                dragon = d;
            }
        }
        if (dragon == null) {
            this.step = null;
            return;
        }
        Vec3 eye = this.bot.getEyePosition();
        Entity reachable = null;
        Entity nearest = null;
        double nearestDist = Double.MAX_VALUE;
        for (var part : dragon.getSubEntities()) {
            double d = part.getBoundingBox().distanceToSqr(eye);
            if (d < nearestDist) {
                nearest = part;
                nearestDist = d;
            }
            if (d < 3.6 * 3.6 && this.bot.hasLineOfSight(part) && (reachable == null || part == dragon.head)) {
                reachable = part;
            }
        }
        if (PvpBotEntity.DEBUG && this.bot.tickCount % 400 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   dragon: hp {} phase {} at {} nearest part {} bot {}", (int) dragon.getHealth(),
                    dragon.getPhaseManager().getCurrentPhase().getPhase(), dragon.blockPosition().toShortString(),
                    (int) Math.sqrt(nearestDist), this.bot.blockPosition().toShortString());
        }
        if (reachable != null) {
            this.bot.getNavigation().stop();
            this.bot.getLookControl().setLookAt(reachable.getX(), reachable.getY() + reachable.getBbHeight() / 2, reachable.getZ());
            if (++this.actionTicks >= 12) {
                this.actionTicks = 0;
                this.bot.hitDragonPart(level, reachable);
            }
            this.step = null;
            return;
        }
        BlockPos fountain = level.getHeightmapPos(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, BlockPos.ZERO);
        boolean sitting = dragon.getPhaseManager().getCurrentPhase().isSitting();
        var phase = dragon.getPhaseManager().getCurrentPhase().getPhase();
        boolean landing = phase == net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.LANDING
                || phase == net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase.LANDING_APPROACH;
        // Only hit it while it sits: flying or landing, its head hits hard. While it comes down, stay
        // near the middle (it sits only a few seconds) and just keep out of the head's way.
        double headDist = dragon.head.position().distanceToSqr(this.bot.position());
        if (!sitting && (landing ? headDist < 5.0 * 5.0 : nearest != null && nearestDist < 10 * 10)) {
            Vec3 from = landing ? dragon.head.position() : nearest.position();
            Vec3 away = this.bot.position().subtract(from).multiply(1.0, 0.0, 1.0).normalize().scale(landing ? 4.0 : 8.0);
            this.bot.getNavigation().moveTo(this.bot.getX() + away.x, this.bot.getY(), this.bot.getZ() + away.z, 1.3);
            this.step = null;
            return;
        }
        boolean low = sitting && nearest != null && nearestDist < 24 * 24;
        // Sitting: run straight to the head (it only sits a few seconds). Otherwise wait close to the
        // middle of the island, where it lands.
        Vec3 goal = low ? nearest.position() : new Vec3(fountain.getX() + 3.5, fountain.getY(), fountain.getZ() + 3.5);
        if (low) {
            this.bot.getNavigation().stop();
            this.bot.getMoveControl().setWantedPosition(goal.x, this.bot.getY(), goal.z, 1.4);
            this.bot.getLookControl().setLookAt(goal.x, goal.y, goal.z);
            if (this.bot.horizontalCollision && this.bot.onGround()) {
                this.bot.getJumpControl().jump();
            }
        } else if (this.bot.position().distanceToSqr(goal) > 4.0 && this.bot.getNavigation().isDone()) {
            this.bot.getNavigation().moveTo(goal.x, goal.y, goal.z, 1.0);
        }
        if (!low) {
            this.bot.getLookControl().setLookAt(dragon);
            // While it flies: arrows, like a player would (aim ahead of it, it is fast).
            double dist = this.bot.distanceTo(dragon);
            // (Only once the crystals are gone - they heal it - and with arrows to spare.)
            if (dist < 40.0 && !this.anyCrystal() && this.kit().count(st -> st.is(Items.ARROW)) > 16 && this.bot.hasLineOfSight(dragon)
                    && ++this.dragonShotTicks >= 20) {
                this.dragonShotTicks = 0;
                // At its body (the middle of the whole dragon is empty air between head, body and wings).
                Entity bodyPart = dragon;
                double biggest = 0.0;
                for (var part : dragon.getSubEntities()) {
                    double size = part.getBoundingBox().getSize();
                    if (size > biggest) {
                        biggest = size;
                        bodyPart = part;
                    }
                }
                Vec3 aim = bodyPart.getBoundingBox().getCenter().add(dragon.getDeltaMovement().scale(dist / 3.0));
                this.bot.shootAt(aim);
            }
        }
        this.step = null;
    }

    // --- mining

    private @Nullable BlockPos nearest(Ore ore) {
        List<BlockPos> list = this.known.getOrDefault(ore, List.of());
        BlockPos best = null;
        double bestScore = Double.MAX_VALUE;
        for (BlockPos p : list) {
            if (this.blacklist.contains(p) || !ore.match.test(this.level().getBlockState(p))) {
                continue;
            }
            // Exposed blocks are much cheaper to reach than buried ones.
            double score = this.bot.blockPosition().distSqr(p) * (this.isExposed(p) ? 1.0 : 3.0);
            if (score < bestScore) {
                best = p;
                bestScore = score;
            }
        }
        return best;
    }

    /** True when a line from the bot's eyes reaches this block without passing through others. */
    private boolean seesBlock(ServerLevel level, BlockPos p) {
        Vec3 eye = this.bot.getEyePosition();
        Vec3 center = Vec3.atCenterOf(p);
        if (eye.distanceToSqr(center) > 24.0 * 24.0) {
            return false;
        }
        var hit = level.clip(new net.minecraft.world.level.ClipContext(eye, center, net.minecraft.world.level.ClipContext.Block.COLLIDER,
                net.minecraft.world.level.ClipContext.Fluid.ANY, this.bot));
        return hit.getBlockPos().equals(p) || hit.getType() == net.minecraft.world.phys.HitResult.Type.MISS;
    }

    private boolean isExposed(BlockPos p) {
        for (Direction d : Direction.values()) {
            if (this.level().getBlockState(p.relative(d)).getCollisionShape(this.level(), p.relative(d)).isEmpty()) {
                return true;
            }
        }
        return false;
    }

    private void doMine(ServerLevel level, Ore ore) {
        if (this.mineTarget == null || !ore.match.test(level.getBlockState(this.mineTarget))) {
            this.stopBreaking();
            this.mineTarget = this.nearest(ore);
            this.noProgressTicks = 0;
            if (this.mineTarget == null) {
                this.step = null;
                return;
            }
        }
        BlockPos target = this.mineTarget;
        if (!target.equals(this.mineSince)) {
            this.mineSince = target;
            this.mineTargetTicks = 0;
        }
        if (++this.mineTargetTicks > 600) {
            // 30 seconds and still not mined (out of reach, behind water ...): take another one.
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   gather: gives up on {} at {}", ore, target.toShortString());
            }
            this.blacklist.add(target);
            this.mineTarget = null;
            this.stopBreaking();
            this.step = null;
            return;
        }
        Vec3 center = Vec3.atCenterOf(target);
        double dist = this.bot.getEyePosition().distanceTo(center);
        BlockPos under = this.bot.blockPosition().below();
        if (target.equals(under) && ore != Ore.STONE && this.lastSafe != null && !this.lastSafe.equals(this.bot.blockPosition())) {
            // Never dig out the block it stands on (obsidian sits on lava): step off first.
            this.bot.getNavigation().moveTo(this.lastSafe.getX() + 0.5, this.lastSafe.getY(), this.lastSafe.getZ() + 0.5, 1.0);
            return;
        }
        if (dist <= 4.5 && this.canSee(target)) {
            this.bot.getNavigation().stop();
            if (this.breakBlock(level, target)) {
                this.mineTarget = null;
                this.mineSince = null; // (gravel falling into the same spot is a new block, not "no progress")
                this.step = null;
            }
            return;
        }
        // Walk there; if walking does not get us closer, dig a tunnel towards it.
        Vec3 pos = this.bot.position();
        if (this.lastPos != null && pos.distanceToSqr(this.lastPos) < 0.01) {
            this.noProgressTicks++;
        } else {
            this.noProgressTicks = Math.max(0, this.noProgressTicks - 1);
        }
        this.lastPos = pos;
        if (this.noProgressTicks < 30) {
            this.bot.getNavigation().moveTo(target.getX() + 0.5, target.getY(), target.getZ() + 0.5, 1.1);
        } else {
            this.tunnelTowards(level, target);
        }
    }

    private boolean canSee(BlockPos target) {
        var hit = this.level().clip(new net.minecraft.world.level.ClipContext(this.bot.getEyePosition(), Vec3.atCenterOf(target),
                net.minecraft.world.level.ClipContext.Block.COLLIDER, net.minecraft.world.level.ClipContext.Fluid.NONE, this.bot));
        return hit.getBlockPos().equals(target);
    }

    private void tunnelTowards(ServerLevel level, BlockPos target) {
        this.bot.getNavigation().stop();
        BlockPos feet = this.bot.blockPosition();
        int dx = Integer.signum(target.getX() - feet.getX());
        int dz = Integer.signum(target.getZ() - feet.getZ());
        Direction dir = Math.abs(target.getX() - feet.getX()) >= Math.abs(target.getZ() - feet.getZ())
                ? (dx >= 0 ? Direction.EAST : Direction.WEST) : (dz >= 0 ? Direction.SOUTH : Direction.NORTH);
        BlockPos front = feet.relative(dir);
        int dy = target.getY() - feet.getY();
        List<BlockPos> toClear = new ArrayList<>();
        if (dy < 0) {
            toClear.add(front.above());
            toClear.add(front);
            toClear.add(front.below());
        } else if (dy > 1) {
            toClear.add(feet.above(2));
            toClear.add(front.above(2));
            toClear.add(front.above());
        } else {
            toClear.add(front.above());
            toClear.add(front);
        }
        for (BlockPos p : toClear) {
            BlockState state = level.getBlockState(p);
            if (!state.getCollisionShape(level, p).isEmpty()) {
                if (this.nearLava(level, p) || state.getDestroySpeed(level, p) < 0.0F) {
                    // Too dangerous or unbreakable: give up on this block and look for another.
                    if (this.mineTarget != null) {
                        this.blacklist.add(this.mineTarget);
                    }
                    this.mineTarget = null;
                    this.stopBreaking();
                    this.noProgressTicks = 0;
                    return;
                }
                this.breakBlock(level, p);
                return;
            }
        }
        // Path is clear: step forward (and up if needed).
        Vec3 next = Vec3.atBottomCenterOf(dy > 0 ? front.above() : front);
        this.bot.getMoveControl().setWantedPosition(next.x, next.y, next.z, 1.0);
        if (dy > 0 && this.bot.onGround()) {
            this.bot.getJumpControl().jump();
        }
        this.noProgressTicks = 20;
    }

    private boolean nearLava(ServerLevel level, BlockPos p) {
        for (Direction d : Direction.values()) {
            if (level.getFluidState(p.relative(d)).is(net.minecraft.tags.FluidTags.LAVA)) {
                return true;
            }
        }
        return false;
    }

    /** Breaks a block the way a player would (right tool, real time). Returns true when it is gone. */
    private boolean breakBlock(ServerLevel level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        if (state.getCollisionShape(level, pos).isEmpty() && state.isAir()) {
            this.stopBreaking();
            return true;
        }
        if (state.getDestroySpeed(level, pos) < 0.0F) {
            // Bedrock, barriers, end portal frames: nobody can break those.
            this.stopBreaking();
            return false;
        }
        if (!pos.equals(this.breaking)) {
            this.stopBreaking();
            this.breaking = pos;
            ItemStack tool = this.bestTool(state);
            this.bot.holdTool(tool);
            float hardness = state.getDestroySpeed(level, pos);
            float speed = tool.isEmpty() ? 1.0F : tool.getDestroySpeed(state);
            boolean correct = !state.requiresCorrectToolForDrops() || !tool.isEmpty() && tool.isCorrectToolForDrops(state);
            float perTick = hardness <= 0.0F ? 1.0F : speed / hardness / (correct ? 30.0F : 100.0F);
            this.breakNeeded = Math.max(1, (int) Math.ceil(1.0F / perTick));
            this.breakProgress = 0;
        }
        this.bot.lookAtBlock(pos);
        this.breakProgress++;
        if (this.breakProgress % 4 == 0) {
            this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
        }
        level.destroyBlockProgress(this.bot.getId(), pos, Math.min(9, this.breakProgress * 10 / this.breakNeeded));
        if (this.breakProgress >= this.breakNeeded) {
            // The tool picked for this block, even if the hand shows something else by now (that
            // cost diamonds: mined with the sword in hand, the ore dropped nothing).
            ItemStack tool = this.bestTool(state);
            this.bot.holdTool(tool);
            boolean drops = !state.requiresCorrectToolForDrops() || !tool.isEmpty() && tool.isCorrectToolForDrops(state);
            level.destroyBlockProgress(this.bot.getId(), pos, -1);
            level.destroyBlock(pos, drops, this.bot, 512);
            if (!tool.isEmpty() && tool.isDamageableItem()) {
                tool.hurtAndBreak(1, this.bot, EquipmentSlot.MAINHAND);
                if (tool.isEmpty()) {
                    this.bot.onKitChanged();
                }
            }
            this.breaking = null;
            return true;
        }
        return false;
    }

    private void stopBreaking() {
        if (this.breaking != null && this.bot.level() instanceof ServerLevel level) {
            level.destroyBlockProgress(this.bot.getId(), this.breaking, -1);
        }
        this.breaking = null;
        this.breakProgress = 0;
    }

    private ItemStack bestTool(BlockState state) {
        ItemStack best = ItemStack.EMPTY;
        float bestSpeed = 1.0F;
        for (ItemStack stack : this.kit().items()) {
            float speed = stack.getDestroySpeed(state);
            boolean correct = !state.requiresCorrectToolForDrops() || stack.isCorrectToolForDrops(state);
            if (!correct || speed <= 1.0F) {
                continue;
            }
            int tier = pickaxeTier(stack.getItem());
            int bestTier = pickaxeTier(best.getItem());
            // Plain stone does not need the good pickaxe: dig with the cheapest one that works, so the
            // iron/diamond pickaxe lasts for the ores that need it.
            boolean better = tier > 0 && bestTier > 0 ? tier < bestTier || tier == bestTier && speed > bestSpeed : speed > bestSpeed;
            if (better) {
                best = stack;
                bestSpeed = speed;
            }
        }
        return best;
    }

    // --- scanning & picking up

    /**
     * Looking around like a player: rays in all directions, up to 96 blocks, stopping at the first
     * block they hit - so it sees a fortress across a lava lake or a pool of lava in a big cave, but
     * never anything behind a wall.
     */
    private void lookAround(ServerLevel level) {
        if (this.bot.tickCount % 40 != 0) {
            return;
        }
        Vec3 eye = this.bot.getEyePosition();
        for (int pitch = -45; pitch <= 45; pitch += 15) {
            for (int yaw = 0; yaw < 360; yaw += 8) {
                Vec3 dir = Vec3.directionFromRotation(pitch, yaw + (this.bot.tickCount / 40 % 2) * 4);
                var hit = level.clip(new net.minecraft.world.level.ClipContext(eye, eye.add(dir.scale(96.0)),
                        net.minecraft.world.level.ClipContext.Block.COLLIDER, net.minecraft.world.level.ClipContext.Fluid.SOURCE_ONLY, this.bot));
                if (hit.getType() != net.minecraft.world.phys.HitResult.Type.BLOCK) {
                    continue;
                }
                BlockPos p = hit.getBlockPos();
                BlockState state = level.getBlockState(p);
                for (Ore ore : Ore.values()) {
                    if (ore != Ore.STONE && ore != Ore.LOG && ore.match.test(state)) {
                        remember(this.known.computeIfAbsent(ore, k -> new ArrayList<>()), ore, p.immutable());
                        break;
                    }
                }
            }
        }
    }

    /**
     * Keeps what it saw; when the list is full the oldest sighting makes room (in a stronghold or
     * fortress there is always more wall ahead than behind).
     */
    private static void remember(List<BlockPos> list, Ore ore, BlockPos p) {
        if (list.contains(p)) {
            return;
        }
        int cap = ore == Ore.STRONGHOLD || ore == Ore.FORTRESS ? 512 : 128;
        if (list.size() >= cap) {
            list.remove(0);
        }
        list.add(p);
    }

    private void scanTick(ServerLevel level) {
        this.lookAround(level);
        BlockPos here = this.bot.blockPosition();
        if (this.scanCenter == null || this.scanLayer > 12) {
            if (this.scanCenter != null) {
                // Remember what it has seen (like a player remembers the diamonds around the corner):
                // keep older sightings that are still there and not too far away.
                Map<Ore, List<BlockPos>> old = new EnumMap<>(Ore.class);
                old.putAll(this.known);
                this.known.clear();
                this.known.putAll(this.scanning);
                for (Map.Entry<Ore, List<BlockPos>> e : old.entrySet()) {
                    if (e.getKey() == Ore.STONE || e.getKey() == Ore.LOG) {
                        continue;
                    }
                    List<BlockPos> list = this.known.computeIfAbsent(e.getKey(), k -> new ArrayList<>());
                    for (BlockPos p : e.getValue()) {
                        if (p.distSqr(here) < 64 * 64 && e.getKey().match.test(level.getBlockState(p))) {
                            remember(list, e.getKey(), p);
                        }
                    }
                }
            }
            this.scanning.clear();
            this.scanCenter = here;
            this.scanLayer = -24;
        }
        int y = this.scanCenter.getY() + this.scanLayer++;
        for (int x = -20; x <= 20; x++) {
            for (int z = -20; z <= 20; z++) {
                BlockPos p = new BlockPos(this.scanCenter.getX() + x, y, this.scanCenter.getZ() + z);
                BlockState state = level.getBlockState(p);
                if (state.isAir()) {
                    continue;
                }
                for (Ore ore : Ore.values()) {
                    if (ore.match.test(state)) {
                        List<BlockPos> list = this.scanning.computeIfAbsent(ore, k -> new ArrayList<>());
                        // No x-ray: only blocks that are uncovered and in plain sight from where the bot is.
                        boolean big = ore == Ore.STRONGHOLD || ore == Ore.FORTRESS;
                        if ((big || list.size() < 64) && this.isExposed(p) && (ore == Ore.STONE || this.seesBlock(level, p))) {
                            if (big) {
                                remember(list, ore, p);
                            } else {
                                list.add(p);
                            }
                        }
                        break;
                    }
                }
            }
        }
    }

    /** Walks to useful items lying around (the bot picks them up when close). Returns true while doing so. */
    private boolean collectDrops() {
        if (!this.kit().hasRoom() || this.breaking != null) {
            return false;
        }
        ItemEntity closest = null;
        double best = 10.0 * 10.0;
        for (ItemEntity item : this.level().getEntitiesOfClass(ItemEntity.class, this.bot.getBoundingBox().inflate(10.0))) {
            if (item.isAlive() && isUseful(item.getItem()) && this.bot.distanceToSqr(item) < best && this.bot.hasLineOfSight(item)
                    && !this.unreachableDrops.contains(item.getId())
                    // Not into a lava pool after it (obsidian drops fall into the hole it leaves).
                    && !this.level().getFluidState(item.blockPosition()).is(net.minecraft.tags.FluidTags.LAVA)
                    && !this.level().getFluidState(item.blockPosition().below()).is(net.minecraft.tags.FluidTags.LAVA)) {
                closest = item;
                best = this.bot.distanceToSqr(item);
            }
        }
        if (closest != null && best > 4.0) {
            // Give up on drops it cannot get to (on a ledge, in a hole) instead of trying forever.
            if (closest.getId() != this.dropId) {
                this.dropId = closest.getId();
                this.dropTicks = 0;
            }
            if (!this.bot.getNavigation().moveTo(closest, 1.1) || ++this.dropTicks > 100) {
                this.unreachableDrops.add(closest.getId());
                if (this.unreachableDrops.size() > 200) {
                    this.unreachableDrops.clear();
                }
                return false;
            }
            return true;
        }
        return false;
    }

    private final java.util.Set<Integer> unreachableDrops = new java.util.HashSet<>();
    private int dropId = -1;
    private int dropTicks;

    // --- saving known state that matters

    static boolean isUseful(ItemStack stack) {
        if (stack.is(Items.NETHERRACK)) {
            return true; // for bridging over the lava sea
        }
        for (Res res : Res.values()) {
            if (res.match.test(stack)) {
                return true;
            }
        }
        return Kit.classify(stack) != Role.OTHER || RECIPES.containsKey(stack.getItem()) || pickaxeTier(stack.getItem()) > 0;
    }
}
