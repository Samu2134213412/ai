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
 * pickaxe ← planks ← logs), really mines and hunts for the raw materials, and crafts and smelts
 * like a player: small recipes in its inventory grid, the rest at a crafting table it places,
 * smelting in a furnace it places and fuels (with the furnace's real cooking time).
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
        recipe(Items.CRAFTING_TABLE, 1, Res.PLANKS, 4);
        recipe(Items.FURNACE, 1, Res.COBBLE, 8);
    }

    /** What fits into the 2x2 grid of the inventory; everything else needs a crafting table. */
    private static final java.util.Set<Item> SMALL_GRID = java.util.Set.of(Items.OAK_PLANKS, Items.STICK, Items.CRAFTING_TABLE,
            Items.BLAZE_POWDER, Items.ENDER_EYE, Items.FLINT_AND_STEEL);

    static boolean needsTable(Recipe recipe) {
        return !SMALL_GRID.contains(recipe.output());
    }

    private static final Item[] IRON_ARMOR = {Items.IRON_HELMET, Items.IRON_CHESTPLATE, Items.IRON_LEGGINGS, Items.IRON_BOOTS};
    private static final Item[] DIAMOND_ARMOR = {Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS};
    private static final EquipmentSlot[] ARMOR_SLOTS = {EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET};

    /** The next thing to do. */
    sealed interface Step permits Craft, Smelt, Mine, Hunt, Explore, Descend, StripMine, FillWater, MakeObsidian, BuildPortal,
            UsePortal, HuntMob, ExploreNether, ThrowEye, FollowEye, ExploreStronghold, FillEndPortal, UseEndPortal, ShootCrystal, FightDragon,
            GoHome, PlaceChest, StoreAtHome, ClimbUp, PlaceStation, PickUpStation {
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

    record PlaceStation(net.minecraft.world.level.block.Block block) implements Step {
        public String describe() {
            return "stellt " + this.block.getName().getString() + " auf";
        }
    }

    record PickUpStation(BlockPos pos) implements Step {
        public String describe() {
            return "nimmt Werkbank/Ofen wieder mit";
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
    static final int EYES_WANTED = 12; // (like speedrunners: 12 frames, some already filled, a few throws)
    private @Nullable BlockPos overworldPortal;
    private @Nullable BlockPos netherPortal;
    private boolean stage2Done;
    // Stage 3 and 4: stronghold and the dragon.
    static final int ARROWS_WANTED = 16;
    private @Nullable Vec3 eyeDir;
    private @Nullable Vec3 legStart;
    private boolean eyeWentDown;
    /** Where the eye of ender went down: the stronghold is under here, the search stays close. */
    private @Nullable BlockPos eyeDownAt;
    private int strongholdDigTicks;
    private @Nullable String strongholdLevel;
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

    private int pearlSearchTicks;
    private int spawnerRetryTick;

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
        // (Not in the End: there are no animals there, the dragon comes first.)
        if (!kit.has(Role.GAPPLE) && kit.count(Res.COOKED_MEAT.match) < 4 && !this.inEnd()) {
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
        int ingots = kit.count(st -> st.is(Items.IRON_INGOT));
        // (No stone in the nether: there a wooden pickaxe has to do - netherrack and bricks are soft.)
        Item minPick = this.inNether() && ingots < 3 && kit.count(Res.COBBLE.match) < 3 ? Items.WOODEN_PICKAXE : Items.STONE_PICKAXE;
        if (this.speedrun && this.portalBuilt && this.needPickaxe(minPick, 99) != null) {
            // Worn out all its pickaxes (the nether eats them): a new one before anything else.
            needs.add(new Need(ingots >= 3 ? Items.IRON_PICKAXE : minPick, "eine Spitzhacke"));
        }
        if (this.speedrun || this.autonomous) {
            ItemStack pick = ItemStack.EMPTY;
            int picks = 0;
            for (ItemStack st : kit.items()) {
                if (pickaxeTier(st.getItem()) > 0) {
                    picks++;
                    if (pickaxeTier(st.getItem()) > pickaxeTier(pick.getItem())) {
                        pick = st;
                    }
                }
            }
            if (picks == 1 && pick.isDamageableItem() && pick.getDamageValue() > pick.getMaxDamage() * 0.75) {
                // Worn: the next one now, while there is still a pickaxe to get the stuff with.
                Item spare = pick.is(Items.DIAMOND_PICKAXE) || pick.is(Items.NETHERITE_PICKAXE) ? Items.IRON_PICKAXE
                        : pick.is(Items.GOLDEN_PICKAXE) ? Items.STONE_PICKAXE : pick.getItem();
                needs.add(0, new Need(spare, "eine Ersatz-Spitzhacke")); // (first: without one nothing else works)
            }
        }
        if (this.autonomous && this.needPickaxe(Items.DIAMOND_PICKAXE, 99) != null) {
            needs.add(new Need(Items.DIAMOND_PICKAXE, "eine Diamantspitzhacke"));
        }
        return needs;
    }

    // ------------------------------------------------------------------ planning

    private @Nullable Step plan() {
        Step next = this.planWork();
        if ((next instanceof Descend || next instanceof StripMine) && (this.speedrun || this.autonomous) && !this.underground()
                && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD
                && this.kit().count(Res.LOG.match) * 4 + this.kit().count(Res.PLANKS.match) + this.kit().count(Res.STICK.match) / 2 < 12) {
            // About to go down: wood for tools and sticks first (there are no trees down there).
            Step wood = this.resolve(Res.LOG, 1, 0);
            if (wood != null) {
                this.goalLabel = "Holzvorrat (bevor es nach unten geht)";
                next = wood;
            }
        }
        if (!(next instanceof Craft) && !(next instanceof Smelt) && !(next instanceof PlaceStation) && !(next instanceof PickUpStation)) {
            // Done at the crafting table / furnace: take them along (a furnace only once it is empty).
            for (BlockPos st : new BlockPos[]{this.tablePos, this.furnacePos}) {
                if (st != null && st.closerToCenterThan(this.bot.position(), 6.0) && this.kit().hasRoom()
                        && (st != this.furnacePos || this.furnaceEmpty(st))) {
                    return new PickUpStation(st);
                }
            }
        }
        return next;
    }

    private boolean furnaceEmpty(BlockPos pos) {
        if (this.level().getBlockEntity(pos) instanceof net.minecraft.world.level.block.entity.AbstractFurnaceBlockEntity f) {
            return f.getItem(0).isEmpty() && f.getItem(2).isEmpty();
        }
        return true;
    }

    private @Nullable Step planWork() {
        for (Need need : this.needs()) {
            if (need.item() == Items.COOKED_BEEF && this.inNether() && this.speedrun && this.portalBuilt) {
                // No cows in the nether: back up through the portal for food, then come back.
                this.goalLabel = "Essen (zurück in die Oberwelt)";
                return new UsePortal(false);
            }
            Step s = need.item() == Items.COOKED_BEEF ? this.resolve(Res.COOKED_MEAT, 4, 0) : this.resolveItem(need.item(), 0);
            if (s != null) {
                this.goalLabel = need.label();
                return s;
            }
        }
        if (this.orderRes != null || this.orderItem != null) {
            Step s = this.orderStep();
            if (s != null) {
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

    // ------------------------------------------------------------------ orders (from the AI chat)

    private @Nullable Res orderRes;
    private @Nullable Item orderItem;
    private int orderCount;

    /**
     * An order: fetch {@code count} of a resource (by its name, e.g. "diamond") or of a craftable item
     * (by its id, e.g. "iron_pickaxe"). Returns null when accepted, else why not.
     */
    @Nullable String order(String what, int count) {
        String key = what.toLowerCase(java.util.Locale.ROOT).replace("minecraft:", "").trim();
        this.orderRes = null;
        this.orderItem = null;
        for (Res res : Res.values()) {
            if (res.name().equalsIgnoreCase(key) || res.label.equalsIgnoreCase(key)) {
                this.orderRes = res;
            }
        }
        if (this.orderRes == null) {
            net.minecraft.resources.Identifier id = net.minecraft.resources.Identifier.tryParse("minecraft:" + key.replace(' ', '_'));
            Item item = id == null ? null : net.minecraft.core.registries.BuiltInRegistries.ITEM.getOptional(id).orElse(null);
            if (item == null || !RECIPES.containsKey(item)) {
                return "kann ich nicht besorgen (möglich: " + orderOptions() + ")";
            }
            this.orderItem = item;
        }
        this.orderCount = Math.max(1, Math.min(count, 64 * 4));
        this.enabled = true;
        this.step = null;
        this.replanTimer = 0;
        return null;
    }

    void cancelOrder() {
        this.orderRes = null;
        this.orderItem = null;
    }

    @Nullable String currentOrder() {
        if (this.orderRes != null) {
            return this.orderCount + " " + this.orderRes.label;
        }
        return this.orderItem == null ? null : this.orderCount + " " + new ItemStack(this.orderItem).getHoverName().getString();
    }

    static String orderOptions() {
        StringBuilder sb = new StringBuilder();
        for (Res res : Res.values()) {
            sb.append(res.name().toLowerCase(java.util.Locale.ROOT)).append(", ");
        }
        for (Item item : RECIPES.keySet()) {
            sb.append(net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(item).getPath()).append(", ");
        }
        return sb.substring(0, Math.max(0, sb.length() - 2));
    }

    private @Nullable Step orderStep() {
        String label = this.currentOrder();
        Item item = this.orderItem;
        int have = this.orderRes != null ? this.kit().count(this.orderRes.match) : this.kit().count(st -> st.is(item));
        if (have >= this.orderCount) {
            this.cancelOrder();
            this.bot.tellOwner("Auftrag erledigt: " + label + " hab ich.", true);
            return null;
        }
        Step s = this.orderRes != null ? this.resolve(this.orderRes, this.orderCount, 0) : this.resolveItem(item, 0);
        if (s == null) {
            this.cancelOrder();
            this.bot.tellOwner("Auftrag abgebrochen: " + label + " bekomme ich gerade nicht.", true);
            return null;
        }
        this.goalLabel = "Auftrag: " + label;
        return s;
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
        } else if (this.breaking == null && ++this.digUpTicks > 100) {
            // Not getting higher this way: another direction. (Breaking a block is not "not getting
            // higher": stone by hand takes 7.5 s, and switching before that never breaks one.)
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
            if (this.kit().count(BRIDGE_BLOCK) == 0 && this.mineAnyStone(level)) {
                return; // (nothing to build with: a few blocks from the walls around first)
            }
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

    /** Drops on all four sides (standing on a pillar or a thin ledge). */
    private boolean onPillar(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        for (Direction d : Direction.Plane.HORIZONTAL) {
            BlockPos n = feet.relative(d).below();
            if (!level.getBlockState(n).getCollisionShape(level, n).isEmpty() || !level.getBlockState(n.below()).getCollisionShape(level, n.below()).isEmpty()) {
                return false;
            }
        }
        return true;
    }

    /** Solid blocks on all four sides at its feet (a hole in a tower, a shaft): only up is out. */
    private boolean walledIn(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        for (Direction d : Direction.Plane.HORIZONTAL) {
            if (level.getBlockState(feet.relative(d)).getCollisionShape(level, feet.relative(d)).isEmpty()) {
                return false;
            }
        }
        return true;
    }

    /** In a pit: the ground two blocks away is higher than its head on at least three sides. */
    private boolean inPit(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        int walls = 0;
        for (Direction d : Direction.Plane.HORIZONTAL) {
            BlockPos n = feet.relative(d, 2);
            if (level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, n.getX(), n.getZ()) > feet.getY() + 2) {
                walls++;
            }
        }
        return walls >= 3;
    }

    private @Nullable BlockPos landGoal;
    private @Nullable BlockPos lastLand;
    /** 24x24 areas of the overworld it has walked through (for exploring: new country first). */
    private final java.util.Set<Long> seenCountry = new java.util.HashSet<>();

    private static long cellOf(Vec3 p) {
        return ((long) Mth.floor(p.x / 24.0) << 32) ^ (Mth.floor(p.z / 24.0) & 0xFFFFFFFFL);
    }
    private int swimTicks;

    /** In open water (sea, lake): swim to the nearest land it can see, like a player. */
    private boolean swimToLand(ServerLevel level) {
        if (!this.bot.isInWater() || !level.canSeeSky(this.bot.blockPosition().above())) {
            this.swimTicks = 0;
            this.landGoal = null;
            return false;
        }
        if (++this.swimTicks < 40) {
            return false; // (just a splash: let the normal work carry on)
        }
        if (this.landGoal == null || this.swimTicks % 100 == 0) {
            this.landGoal = null;
            BlockPos here = this.bot.blockPosition();
            boolean ahead = !Double.isNaN(this.exploreHeading);
            for (int pass = ahead ? 0 : 1; pass < 2 && this.landGoal == null; pass++)
            for (int r = 4; r <= 64 && this.landGoal == null; r += 4) {
                for (int k = 0; k < 16; k++) {
                    double a = Math.PI * 2.0 * k / 16.0;
                    if (pass == 0 && Math.cos(a - this.exploreHeading) < 0.2) {
                        continue; // (first: land on the way it is going, not back where it came from)
                    }
                    int x = here.getX() + (int) Math.round(Math.cos(a) * r);
                    int z = here.getZ() + (int) Math.round(Math.sin(a) * r);
                    int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);
                    BlockPos top = new BlockPos(x, y - 1, z);
                    if (level.getFluidState(top).isEmpty() && y >= level.getSeaLevel()) {
                        this.landGoal = top.above();
                        break;
                    }
                }
            }
            if (this.landGoal == null && this.lastLand != null && this.lastLand.distSqr(here) > 160 * 160 && this.lastLand.distSqr(here) < 512 * 512) {
                // Open sea, no land in sight: back to the last shore it stood on (not on across the ocean).
                this.landGoal = this.lastLand;
            }
            if (this.landGoal == null) {
                this.landGoal = Double.isNaN(this.exploreHeading) ? here.relative(this.digDir, 32)
                        : here.offset((int) (Math.cos(this.exploreHeading) * 32), 0, (int) (Math.sin(this.exploreHeading) * 32));
            }
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   swims to land at {} from {}", this.landGoal.toShortString(), here.toShortString());
            }
        }
        if (this.swimTicks % 20 == 0 || this.bot.getNavigation().isDone()) {
            if (!this.bot.getNavigation().moveTo(this.landGoal.getX() + 0.5, this.landGoal.getY(), this.landGoal.getZ() + 0.5, 1.0)) {
                this.bot.getMoveControl().setWantedPosition(this.landGoal.getX() + 0.5, this.landGoal.getY(), this.landGoal.getZ() + 0.5, 1.0);
            }
        }
        this.bot.getLookControl().setLookAt(Vec3.atCenterOf(this.landGoal));
        this.bot.getJumpControl().jump(); // (keeps the head above water)
        return true;
    }

    private @Nullable Vec3 watchPos;
    private int watchKit;
    private int watchTicks;
    private int freeTicks;
    private int watchStreak;
    private @Nullable BlockPos lastWatchdogAt;

    /**
     * Not moved and nothing new in the kit for a minute while there is work: whatever it is doing
     * loops. Drop it, dig/build its way out in some direction for 10 s, then plan afresh.
     */
    private boolean watchdog(ServerLevel level) {
        if (this.freeTicks > 0) {
            this.freeTicks--;
            if (this.freeTicks % 60 == 0 && this.watchStreak < 2) {
                this.digDir = Direction.Plane.HORIZONTAL.getRandomDirection(this.bot.getRandom());
            }
            if (this.wet(level)) {
                this.climbOutOfWater(level);
            } else if (this.kit().count(BRIDGE_BLOCK) == 0 && this.onPillar(level)
                    && !level.getBlockState(this.bot.blockPosition().below(2)).getCollisionShape(level, this.bot.blockPosition().below(2)).isEmpty()) {
                // On a pillar with nothing to bridge with: down it block by block (and keep the blocks).
                this.breakBlock(level, this.bot.blockPosition().below());
            } else {
                // The way out the learner picked for this kind of situation.
                switch (this.freeWay) {
                    case "hochgraben" -> this.doDigUp(level);
                    case "hochbauen" -> this.pillarUp(level);
                    case "erkunden" -> this.doExplore();
                    case "runtergraben" -> this.doDig(level, true);
                    default -> this.doDig(level, false);
                }
            }
            if (this.freeTicks == 0) {
                // Reward: how far it got away from where it was stuck (12 blocks and more = worked).
                double moved = this.freeFrom == null ? 0.0 : Math.sqrt(this.bot.position().distanceToSqr(this.freeFrom));
                double reward = Math.min(1.0, moved / 12.0);
                de.samu.pvpbot.brain.TaskLearner.INSTANCE.learn(this.freeSituation, this.freeWay, reward);
                if (PvpBotEntity.DEBUG) {
                    PvpBotMod.LOGGER.info("[SELFTEST]   LEARN: {} -> {} got {} blocks away, reward {} (now worth {})", this.freeSituation, this.freeWay,
                            (int) moved, String.format("%.2f", reward),
                            String.format("%.2f", de.samu.pvpbot.brain.TaskLearner.INSTANCE.estimate(this.freeSituation, this.freeWay)));
                }
            }
            return true;
        }
        int kit = 0;
        for (ItemStack st : this.kit().items()) {
            kit += st.getCount();
        }
        // (Playing through, there is always work - in the End only while crystals are left: waiting
        // for the dragon to come down is fine.)
        boolean busy = this.speedrun && !this.gameBeaten && (!this.inEnd() || this.anyCrystal()) || this.autonomous && this.step != null;
        if (this.towerGroundY != Integer.MIN_VALUE) {
            busy = false; // up on its own pole (waiting for a clear shot): not stuck
        }
        if (busy && !this.bot.onGround() && !this.bot.isInWater() && !this.bot.isInLava() && this.watchPos != null) {
            return false; // mid-air (a jump, a fall): no place to dig - but the clock keeps its count
        }
        if (!busy || this.watchPos == null || this.bot.position().distanceToSqr(this.watchPos) > 5.0 * 5.0 || kit != this.watchKit) {
            this.watchPos = this.bot.position();
            this.watchKit = kit;
            this.watchTicks = 0;
            return false;
        }
        if (++this.watchTicks < 1200) {
            return false;
        }
        if (PvpBotEntity.DEBUG) {
            BlockPos f = this.bot.blockPosition();
            PvpBotMod.LOGGER.info("[SELFTEST]   WATCHDOG: no progress for 60 s with {} ({}) at {} -> frees itself | ground {} water {} lava {} hcol {}"
                            + " | feet {} head {} below {} | N {} E {} S {} W {} | above {} | target {} nav {}",
                    this.step, this.goalLabel, f.toShortString(), this.bot.onGround(), this.bot.isInWater(), this.bot.isInLava(),
                    this.bot.horizontalCollision, bn(level, f), bn(level, f.above()), bn(level, f.below()),
                    bn(level, f.north()), bn(level, f.east()), bn(level, f.south()), bn(level, f.west()), bn(level, f.above(2)),
                    this.bot.getTarget() == null ? "-" : this.bot.getTarget().getName().getString(), this.bot.getNavigation().isDone() ? "done" : "moving");
            PvpBotMod.LOGGER.info("[SELFTEST]   WATCHDOG: explore target {}, streak {}", this.exploreTarget, this.watchStreak);
        }
        String sit = this.situation(level); // (before the plan is dropped)
        this.watchTicks = 0;
        // Stuck at the same place again: get further away each time (one direction, longer).
        BlockPos here = this.bot.blockPosition();
        this.watchStreak = this.lastWatchdogAt != null && this.lastWatchdogAt.distSqr(here) < 12 * 12 ? Math.min(this.watchStreak + 1, 6) : 0;
        this.lastWatchdogAt = here;
        this.step = null;
        this.bot.setTarget(null);
        this.netherGoal = null;
        this.mineTarget = null;
        this.poleSpot = null;
        this.freeTicks = 200 * (1 + this.watchStreak);
        this.digDir = Direction.Plane.HORIZONTAL.getRandomDirection(this.bot.getRandom());
        this.exploreHeading = Double.NaN;
        this.freeSituation = sit;
        this.freeWay = de.samu.pvpbot.brain.TaskLearner.INSTANCE.choose(this.freeSituation, FREE_WAYS);
        this.freeFrom = this.bot.position();
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   LEARN: stuck in \"{}\" -> tries \"{}\"", this.freeSituation, this.freeWay);
        }
        return true;
    }

    /**
     * The last safety net (called by the entity, whatever goal runs): three minutes without moving
     * on or anything new in the bag. Drops the plan and explores away for half a minute.
     */
    void forceFree() {
        ServerLevel level = this.level();
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   HARD UNSTUCK: 3 min without progress with {} ({}) at {} -> explores away",
                    this.step, this.goalLabel, this.bot.blockPosition().toShortString());
        }
        this.freeSituation = this.situation(level);
        this.step = null;
        this.mineTarget = null;
        this.poleSpot = null;
        this.stopBreaking();
        this.freeWay = "erkunden";
        this.freeFrom = this.bot.position();
        this.freeTicks = 600;
        this.exploreHeading = Double.NaN;
        this.exploreTarget = null;
        this.watchTicks = 0;
    }

    /** Ways out of a stuck spot the learner chooses from. */
    private static final List<String> FREE_WAYS = List.of("graben", "hochgraben", "hochbauen", "erkunden", "runtergraben");
    private String freeWay = "graben";
    private String freeSituation = "";
    private @Nullable Vec3 freeFrom;

    /** A short description of where it is, as the learner's situation key. */
    private String situation(ServerLevel level) {
        String dim = this.inNether() ? "Nether" : this.inEnd() ? "End" : "Oberwelt";
        boolean under = !level.canSeeSky(this.bot.blockPosition().above());
        String what = this.step == null ? "planlos" : this.step.getClass().getSimpleName();
        return dim + (under ? ", unter Tage" : ", unter freiem Himmel") + (this.wet(level) ? ", im Wasser" : "") + ", " + what;
    }

    private int wetTicks;
    boolean reflexActive;
    private int poolTicks;
    private int poolDryTicks;
    private @Nullable Vec3 poolPos;

    /** Like a player in a pit of water: jump and put a block under its feet each time, up and out. */
    private void climbOutOfWater(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        this.bot.getNavigation().stop();
        this.bot.getJumpControl().jump();
        if (!level.canSeeSky(feet.above())) {
            // Underground, water pouring in (a flooded staircase): plug it with blocks like a
            // player - sources first, then the flowing water around its head and feet.
            BlockPos plug = null;
            for (BlockPos p : new BlockPos[]{feet.above(2), feet.north(), feet.east(), feet.south(), feet.west(),
                    feet.above().north(), feet.above().east(), feet.above().south(), feet.above().west()}) {
                var fluid = level.getFluidState(p);
                if (fluid.is(net.minecraft.tags.FluidTags.WATER) && level.getBlockState(p).canBeReplaced()
                        && (plug == null || fluid.isSource() && !level.getFluidState(plug).isSource())) {
                    plug = p.immutable();
                }
            }
            if (plug != null && this.bridge(level, plug, false)) {
                return;
            }
        }
        BlockPos below = feet.below();
        if (level.getBlockState(below).canBeReplaced()) {
            if (!this.bridge(level, below, false) && !this.mineAnyStone(level)) {
                // Nothing to build with and no stone in reach: swim up to the surface.
                BlockPos up = feet;
                while (up.getY() < level.getMaxY() && !level.getFluidState(up).isEmpty()) {
                    up = up.above();
                }
                this.bot.getMoveControl().setWantedPosition(this.bot.getX(), up.getY() + 0.5, this.bot.getZ(), 1.0);
            }
            return;
        }
        if (!level.getBlockState(feet.above(2)).getCollisionShape(level, feet.above(2)).isEmpty()) {
            this.breakBlock(level, feet.above(2)); // a ceiling over the pool
            return;
        }
        // Standing on the bottom, head out of the water: onto a step next to it (made of a block
        // into the water if there is none), like a player climbing out of a pool.
        Direction stepDir = null;
        Direction fillDir = null;
        for (Direction d : Direction.Plane.HORIZONTAL) {
            BlockPos side = feet.relative(d);
            boolean roomOnTop = level.getBlockState(side.above()).getCollisionShape(level, side.above()).isEmpty()
                    && level.getBlockState(side.above(2)).getCollisionShape(level, side.above(2)).isEmpty()
                    && level.getFluidState(side.above()).isEmpty();
            if (!roomOnTop) {
                continue;
            }
            if (!level.getBlockState(side).getCollisionShape(level, side).isEmpty()) {
                stepDir = d;
                break;
            }
            if (fillDir == null && level.getBlockState(side).canBeReplaced()) {
                fillDir = d;
            }
        }
        if (stepDir == null && fillDir != null) {
            this.bridge(level, feet.relative(fillDir), false);
            stepDir = fillDir;
        }
        if (stepDir != null) {
            BlockPos top = feet.relative(stepDir).above();
            this.bot.getMoveControl().setWantedPosition(top.getX() + 0.5, top.getY(), top.getZ() + 0.5, 1.0);
            return;
        }
        // Walled in (a flooded tunnel): make room above a side block, that becomes the step.
        BlockPos side = feet.relative(this.digDir);
        for (BlockPos p : new BlockPos[]{side.above(), side.above(2)}) {
            if (!level.getBlockState(p).getCollisionShape(level, p).isEmpty() && level.getBlockState(p).getDestroySpeed(level, p) >= 0.0F) {
                this.breakBlock(level, p);
                return;
            }
        }
        this.digDir = this.digDir.getClockWise();
    }

    /** Standing in water, also shallow or flowing water the game does not count as swimming. */
    private boolean wet(ServerLevel level) {
        return this.bot.isInWater() || level.getFluidState(this.bot.blockPosition()).is(net.minecraft.tags.FluidTags.WATER);
    }

    /** Breaks the closest stone-like block it can see within reach (not the one it stands on). */
    private boolean mineAnyStone(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        BlockPos best = null;
        double bestDist = Double.MAX_VALUE;
        for (BlockPos p : BlockPos.betweenClosed(feet.offset(-4, -1, -4), feet.offset(4, 3, 4))) {
            BlockState st = level.getBlockState(p);
            boolean stone = st.is(Blocks.STONE) || st.is(Blocks.DEEPSLATE) || st.is(Blocks.DIRT) || st.is(Blocks.GRANITE)
                    || st.is(Blocks.DIORITE) || st.is(Blocks.ANDESITE) || st.is(Blocks.TUFF) || st.is(Blocks.NETHERRACK)
                    || st.is(Blocks.BLACKSTONE) || st.is(Blocks.END_STONE) || st.is(Blocks.COBBLESTONE);
            if (!stone || p.equals(feet.below()) || this.nearLava(level, p) || !this.seesBlock(level, p)) {
                continue;
            }
            double d = this.bot.getEyePosition().distanceToSqr(Vec3.atCenterOf(p));
            if (d < bestDist && d < 4.5 * 4.5) {
                best = p.immutable();
                bestDist = d;
            }
        }
        if (best == null) {
            return false;
        }
        this.breakBlock(level, best);
        return true;
    }

    private static String bn(ServerLevel level, BlockPos p) {
        return net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(level.getBlockState(p).getBlock()).getPath();
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
        int wood = kit.count(Res.STICK.match) + kit.count(Res.PLANKS.match) * 2 + kit.count(Res.LOG.match) * 8;
        if (wood < 16 && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD
                && this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
                this.bot.getBlockX(), this.bot.getBlockZ()) <= this.bot.getY() + 6.0) {
            // Up top and low on wood: some logs along before going down (sticks for new pickaxes).
            Step s = this.resolve(Res.LOG, 3, 0);
            if (s != null) {
                this.goalLabel = "Holzvorrat für unter Tage";
                return s;
            }
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
            return this.nearest(Ore.LAVA) != null ? new MakeObsidian() : this.lavaStep();
        }
        if (kit.count(st -> st.is(Items.FLINT_AND_STEEL)) == 0) {
            this.goalLabel = "ein Feuerzeug";
            Step s = this.resolveItem(Items.FLINT_AND_STEEL, 0);
            return s != null ? s : new Explore("Kies");
        }
        this.goalLabel = "das Netherportal";
        if (this.portalBase == null && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD
                && this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
                this.bot.getBlockX(), this.bot.getBlockZ()) > this.bot.getY() + 3.0) {
            // Down in the caves water, lava and gravel get in the way: the portal goes up top.
            return new ClimbUp("Platz fürs Portal an der Oberfläche");
        }
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
                if (rodsNeeded <= 0) {
                    // Only pearls missing: endermen come out at night up here, like for a player.
                    return new Explore("Endermen (Enderperlen)");
                }
                return new UsePortal(true);
            }
            if (rodsNeeded <= 0 && this.nearest(Ore.WARPED) == null && ++this.pearlSearchTicks > 6000) {
                // No warped forest in sight after a good while: back to the overworld for them.
                return new UsePortal(false);
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
                if (this.strongholdLevel != null) {
                    // Found it at this depth: that was a good guess (the learner remembers).
                    de.samu.pvpbot.brain.TaskLearner.INSTANCE.learn("Festung suchen: Höhe", this.strongholdLevel, 1.0);
                    this.strongholdLevel = null;
                }
                return new ExploreStronghold();
            }
            // Strongholds lie at different depths: the learner picks a level to tunnel at for a while
            // (what worked before first), no luck there -> that counts against it, the next one.
            if (this.strongholdLevel == null || this.bot.tickCount - this.strongholdDigTicks > 6000) {
                if (this.strongholdLevel != null) {
                    de.samu.pvpbot.brain.TaskLearner.INSTANCE.learn("Festung suchen: Höhe", this.strongholdLevel, 0.0);
                }
                this.strongholdLevel = de.samu.pvpbot.brain.TaskLearner.INSTANCE.choose("Festung suchen: Höhe", List.of("20", "0", "-20", "-40"));
                this.strongholdDigTicks = this.bot.tickCount;
                if (PvpBotEntity.DEBUG) {
                    PvpBotMod.LOGGER.info("[SELFTEST]   LEARN: stronghold search at y {}", this.strongholdLevel);
                }
            }
            int level = Integer.parseInt(this.strongholdLevel);
            if (this.bot.getY() > level + 2.0) {
                return new Descend();
            }
            if (this.bot.getY() < level - 3.0) {
                return new ClimbUp("Festung weiter oben suchen");
            }
            return new StripMine();
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
                    && this.ignoredMobs.getOrDefault(e.getUUID(), 0) < this.bot.tickCount
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

    /** Lava for obsidian: the caves below y -55 are full of it - tunnel at that level. */
    private Step lavaStep() {
        return this.bot.getY() > -55.0 ? new Descend() : new StripMine();
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
        if (needsTable(recipe) && this.station(Blocks.CRAFTING_TABLE) == null) {
            // A 3x3 recipe: set up a crafting table first (make one if there is none in the bag).
            if (this.kit().count(st -> st.is(Items.CRAFTING_TABLE)) > 0) {
                return new PlaceStation(Blocks.CRAFTING_TABLE);
            }
            return this.resolveItem(Items.CRAFTING_TABLE, depth + 1);
        }
        return new Craft(recipe);
    }

    // ------------------------------------------------------------------ crafting table and furnace

    private @Nullable BlockPos tablePos;
    private @Nullable BlockPos furnacePos;

    /** A crafting table or furnace within reach (its own, or one it sees right here). */
    private @Nullable BlockPos station(net.minecraft.world.level.block.Block block) {
        ServerLevel level = this.level();
        BlockPos own = block == Blocks.CRAFTING_TABLE ? this.tablePos : this.furnacePos;
        if (own != null && level.getBlockState(own).is(block) && own.closerToCenterThan(this.bot.getEyePosition(), 4.5)) {
            return own;
        }
        BlockPos feet = this.bot.blockPosition();
        for (BlockPos p : BlockPos.betweenClosed(feet.offset(-3, -1, -3), feet.offset(3, 2, 3))) {
            if (level.getBlockState(p).is(block) && p.closerToCenterThan(this.bot.getEyePosition(), 4.5) && this.seesBlock(level, p)) {
                BlockPos found = p.immutable();
                if (block == Blocks.CRAFTING_TABLE) {
                    this.tablePos = found;
                } else {
                    this.furnacePos = found;
                }
                return found;
            }
        }
        return null;
    }

    private int stationWalk;
    private int stationTries;

    /** Puts a crafting table or furnace down next to it, like a player. */
    private void doPlaceStation(ServerLevel level, net.minecraft.world.level.block.Block block) {
        this.step = null;
        Item item = block.asItem();
        if (this.kit().count(st -> st.is(item)) == 0) {
            return;
        }
        if (this.wet(level) || !this.bot.onGround() || this.stationWalk > 0) {
            // Swimming or falling, or no room here: first somewhere else (a table needs ground).
            this.stationWalk = Math.max(0, this.stationWalk - 1);
            if (!this.swimToLand(level)) {
                this.doExplore();
            }
            return;
        }
        this.bot.getNavigation().stop();
        BlockPos feet = this.bot.blockPosition();
        boolean dryAround = false;
        for (Direction d : Direction.Plane.HORIZONTAL) {
            dryAround |= !level.getBlockState(feet.relative(d).below()).getCollisionShape(level, feet.relative(d).below()).isEmpty()
                    || !level.getBlockState(feet.relative(d)).getCollisionShape(level, feet.relative(d)).isEmpty();
        }
        if (!dryAround) {
            // At the edge of a lake, water on every side: a few steps on, then try again.
            this.stationWalk = 60;
            return;
        }
        for (Direction d : Direction.Plane.HORIZONTAL) {
            for (int dy = 0; dy <= 1; dy++) {
                BlockPos p = feet.relative(d).above(dy);
                if (level.getBlockState(p).canBeReplaced() && level.getFluidState(p).isEmpty()
                        && !level.getBlockState(p.below()).getCollisionShape(level, p.below()).isEmpty()) {
                    this.bot.lookAtBlock(p);
                    this.bot.swing(InteractionHand.MAIN_HAND, this.bot.getMainHandItem().getAttackAnimation());
                    level.setBlock(p, block.defaultBlockState(), 3);
                    level.playSound(null, p, SoundEvents.WOOD_PLACE, this.bot.getSoundSource(), 1.0F, 1.0F);
                    this.kit().remove(st -> st.is(item), 1);
                    this.bot.onKitChanged();
                    this.blacklist.add(p); // (its own, not something to mine for resources)
                    if (block == Blocks.CRAFTING_TABLE) {
                        this.tablePos = p;
                    } else {
                        this.furnacePos = p;
                    }
                    return;
                }
            }
        }
        // No room here (a 1-wide tunnel): make some (not into water or lava).
        BlockPos room = feet.relative(this.digDir);
        if (level.getFluidState(room).isEmpty() && !this.nearLava(level, room)
                && !level.getBlockState(room).getCollisionShape(level, room).isEmpty()) {
            this.breakBlock(level, room);
        } else if (++this.stationTries > 8) {
            this.stationTries = 0;
            this.stationWalk = 60; // (nothing to dig away either: somewhere else)
        } else {
            this.digDir = this.digDir.getClockWise();
        }
    }

    /** Takes its crafting table or furnace along again (break it, the drop gets picked up). */
    private void doPickUpStation(ServerLevel level, BlockPos pos) {
        this.bot.getNavigation().stop();
        if (!level.getBlockState(pos).is(Blocks.CRAFTING_TABLE) && !level.getBlockState(pos).is(Blocks.FURNACE)) {
            if (pos.equals(this.tablePos)) {
                this.tablePos = null;
            }
            if (pos.equals(this.furnacePos)) {
                this.furnacePos = null;
            }
            this.blacklist.remove(pos);
            this.step = null;
            return;
        }
        this.breakBlock(level, pos);
    }

    /** How to get {@code count} of a resource. */
    private @Nullable Step resolve(Res res, int count, int depth) {
        if (res == Res.LOG && (this.speedrun || this.autonomous) && !this.underground()
                && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD) {
            // Up here among the trees: take a stock along (a whole tree, like a player), not the one
            // log this recipe needs - otherwise it climbs up from the mine for every stick.
            int wood = this.kit().count(Res.LOG.match) * 4 + this.kit().count(Res.PLANKS.match) + this.kit().count(Res.STICK.match) / 2;
            if (wood < 24) {
                count = Math.max(count, this.kit().count(Res.LOG.match) + (24 - wood + 3) / 4);
            }
        }
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

    /** Wood (in planks) beyond what the next pickaxe and its sticks need - that may be burnt. */
    private int spareWood() {
        int wood = this.kit().count(Res.LOG.match) * 4 + this.kit().count(Res.PLANKS.match);
        return (this.speedrun || this.autonomous) ? Math.max(0, wood - 8) : wood;
    }

    private Step smelt(Res input, Res output, int missing, int depth) {
        if (this.kit().count(input.match) < 1) {
            Step s = this.resolve(input, Math.max(1, missing), depth + 1);
            return s != null ? s : new Explore(input.label);
        }
        if (this.kit().count(Res.COAL.match) == 0 && this.spareWood() < 2) {
            // Fuel: coal if we know where it is (or underground, where it is); wood only up top.
            if (this.needPickaxe(Items.WOODEN_PICKAXE, depth) == null) {
                if (!this.known.getOrDefault(Ore.COAL, List.of()).isEmpty()) {
                    return new Mine(Ore.COAL);
                }
                if (this.underground() && (this.speedrun || this.autonomous)) {
                    return this.deepStep(); // (coal shows up in the tunnel walls)
                }
            }
            return this.mine(Ore.LOG, depth);
        }
        if (this.station(Blocks.FURNACE) == null) {
            if (this.kit().count(st -> st.is(Items.FURNACE)) > 0) {
                return new PlaceStation(Blocks.FURNACE);
            }
            Step s = this.resolveItem(Items.FURNACE, depth + 1);
            if (s != null) {
                return s;
            }
        }
        return new Smelt(input, output);
    }

    private Step mine(Ore ore, int depth) {
        if (ore == Ore.LOG && this.nearest(ore) == null && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD
                && this.underground()) {
            return new ClimbUp("Holz gibt es oben"); // (no trees in caves)
        }
        if (this.nearest(ore) == null && !this.bot.isInWater() && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD) {
            if (ore == Ore.STONE) {
                // No stone in sight: it is right under the grass - dig a staircase down, like a player.
                return new Descend();
            }
            if ((ore == Ore.IRON || ore == Ore.COAL) && (this.speedrun || this.autonomous)) {
                // Ores are underground: down the staircase and strip-mine, instead of walking the hills.
                return this.deepStep();
            }
        }
        return this.nearest(ore) != null ? new Mine(ore) : new Explore(ore.label);
    }

    // ------------------------------------------------------------------ doing

    /**
     * Reflexes that must work whatever the bot is busy with (fighting, planning, nothing): out of
     * lava, out of a cobweb. Runs every tick from the entity. Returns true while one is acting.
     */
    boolean reflexes() {
        if (!this.speedrun && !this.autonomous || this.kit().isInfinite()) {
            return false;
        }
        ServerLevel level = this.level();
        if (this.escapeLava(level)) {
            return true;
        }
        for (BlockPos snow : new BlockPos[]{this.bot.blockPosition(), this.bot.blockPosition().above()}) {
            if (level.getBlockState(snow).is(Blocks.POWDER_SNOW)) {
                // Sinking into powder snow (it freezes you): dig out of it and jump, like a player.
                this.breakBlock(level, snow);
                this.bot.getJumpControl().jump();
                return true;
            }
        }
        for (BlockPos web : new BlockPos[]{this.bot.blockPosition(), this.bot.blockPosition().above(), this.bot.blockPosition().above(2)}) {
            if (level.getBlockState(web).is(Blocks.COBWEB)) {
                // Caught in a cobweb (strongholds, mineshafts): cut it, like a player with a sword.
                this.breakBlock(level, web);
                return true;
            }
        }
        return false;
    }

    void tick() {
        ServerLevel level = this.level();
        if (this.reflexActive) {
            return;
        }
        if (this.inNether() && this.speedrun && this.kit().count(BRIDGE_BLOCK) < 24 && this.bot.onGround()
                && this.mineNearby(level, Blocks.NETHERRACK)) {
            return; // low on blocks in the nether (bridges over lava): a few netherrack first
        }
        if (this.bot.tickCount % 40 == 0 && !this.kit().hasRoom() && this.kit().count(JUNK) > 192) {
            // Inventory full of rubble: throw a stack away, like a player makes room.
            for (ItemStack st : this.kit().items()) {
                if (JUNK.test(st)) {
                    ItemStack out = st.copy();
                    this.kit().remove(x -> x == st, st.getCount());
                    this.bot.spawnAtLocation(level, out);
                    this.bot.onKitChanged();
                    break;
                }
            }
        }
        if (this.speedrun && this.wet(level) && this.bot.getTarget() == null && !level.canSeeSky(this.bot.blockPosition().above())) {
            // (Only under ground: in open water it swims - across a lake, to the shore.)
            if (this.poolPos == null || this.bot.getY() > this.poolPos.y + 2.0) {
                // (Only real progress upwards counts: drifting around under water does not.)
                this.poolPos = this.bot.position();
                this.poolTicks = 0;
            } else if (++this.poolTicks > 200) {
                // Ten seconds in the water without getting anywhere: out of it, whatever the plan was.
                this.climbOutOfWater(level);
                return;
            }
        } else if (++this.poolDryTicks > 100) {
            // (Five seconds on dry land: really out. Bobbing at the edge of the water is not.)
            this.poolTicks = 0;
            this.poolPos = null;
        }
        if (this.wet(level)) {
            this.poolDryTicks = 0;
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
        if ((this.speedrun || this.autonomous) && this.watchdog(level)) {
            return;
        }
        if (this.bot.onGround() && !this.bot.isInWater() && this.bot.tickCount % 20 == 0 && level.canSeeSky(this.bot.blockPosition().above())) {
            this.lastLand = this.bot.blockPosition();
        }
        if (this.bot.tickCount % 20 == 0 && this.seenCountry.add(cellOf(this.bot.position())) && this.seenCountry.size() > 20000) {
            this.seenCountry.clear();
        }
        if ((this.speedrun || this.autonomous) && this.swimToLand(level)) {
            return;
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
            case PlaceStation ps -> this.doPlaceStation(level, ps.block());
            case PickUpStation pu -> this.doPickUpStation(level, pu.pos());
            case Mine mine -> this.doMine(level, mine.ore());
            case Hunt hunt -> this.doHunt();
            case Explore explore -> {
                if (level.dimension() == net.minecraft.world.level.Level.OVERWORLD && level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
                        this.bot.getBlockX(), this.bot.getBlockZ()) > this.bot.getY() + 6.0) {
                    // Trees, animals, endermen at night: all up top - a staircase up first.
                    this.doDigUp(level);
                    this.step = null;
                } else {
                    this.doExplore();
                }
            }
            case ClimbUp up -> {
                // A way out on foot first (a cave mouth, the edge of an overhang); dig only without one.
                if (this.skyExit == null || this.bot.tickCount - this.skyExitTick > 200) {
                    this.skyExit = this.findSkyExit(level);
                    if (this.skyExit == null && this.stairTop != null && this.stairTop.distSqr(this.bot.blockPosition()) < 256 * 256) {
                        this.skyExit = this.stairTop; // back up the staircase it dug on the way down
                    }
                    this.skyExitTick = this.bot.tickCount;
                }
                if (this.skyExit == null || !this.bot.getNavigation().moveTo(this.skyExit.getX() + 0.5, this.skyExit.getY(), this.skyExit.getZ() + 0.5, 1.1)
                        || this.noProgress()) {
                    this.skyExit = null;
                    // Inside a mountain the way straight up is long: dig out towards the nearest
                    // flank (where the surface is lowest, counting the way there), like a player.
                    if (this.bot.tickCount - this.flankTick > 400 || this.flank == null) {
                        this.flank = this.findFlank(level);
                        this.flankTick = this.bot.tickCount;
                    }
                    if (this.flank != null) {
                        this.tunnelTowards(level, this.flank);
                    } else {
                        this.doDigUp(level);
                    }
                }
                this.step = null;
            }
            case Descend d -> {
                if (!this.underground() && level.dimension() == net.minecraft.world.level.Level.OVERWORLD) {
                    this.stairTop = this.bot.blockPosition(); // (the way back up: its own staircase)
                }
                this.doDig(level, true);
            }
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
        if (needsTable(recipe)) {
            BlockPos table = this.station(Blocks.CRAFTING_TABLE);
            if (table == null) {
                this.step = null;
                return;
            }
            this.bot.lookAtBlock(table);
        }
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

    /**
     * Smelts in its furnace like a player: raw items into the top, fuel into the bottom, waits for
     * the furnace to cook them (its real speed), takes the result out.
     */
    private void doSmelt(ServerLevel level, Smelt smelt) {
        this.bot.getNavigation().stop();
        BlockPos pos = this.station(Blocks.FURNACE);
        if (pos == null || !(level.getBlockEntity(pos) instanceof net.minecraft.world.level.block.entity.AbstractFurnaceBlockEntity furnace)) {
            this.step = null;
            return;
        }
        this.bot.lookAtBlock(pos);
        if (++this.actionTicks % 10 != 0) {
            return;
        }
        ItemStack result = furnace.getItem(2);
        if (!result.isEmpty()) {
            ItemStack rest = this.kit().insert(result.copy());
            furnace.setItem(2, rest);
            this.bot.onKitChanged();
        }
        ItemStack in = furnace.getItem(0);
        if (in.isEmpty()) {
            // Everything of that kind it carries goes in (one stack at most).
            for (ItemStack stack : this.kit().items()) {
                if (smelt.input().match.test(stack)) {
                    ItemStack put = stack.copy();
                    this.kit().remove(st -> st == stack, put.getCount());
                    furnace.setItem(0, put);
                    in = put;
                    this.bot.onKitChanged();
                    break;
                }
            }
        }
        if (in.isEmpty()) {
            if (furnace.getItem(2).isEmpty() && this.actionTicks > 20) {
                this.actionTicks = 0;
                this.step = null; // all done
            }
            return;
        }
        if (furnace.getItem(1).isEmpty() && !furnace.getBlockState().getValue(net.minecraft.world.level.block.AbstractFurnaceBlock.LIT)) {
            // Fuel for what is in there: coal cooks 8, a log or a plank 1.5 items.
            int n = in.getCount();
            ItemStack fuelStack = ItemStack.EMPTY;
            for (ItemStack stack : this.kit().items()) {
                if (Res.COAL.match.test(stack)) {
                    fuelStack = stack.copyWithCount(Math.min(stack.getCount(), (n + 7) / 8));
                    break;
                }
            }
            if (fuelStack.isEmpty()) {
                // Wood only beyond the reserve for the next pickaxe and its sticks (never burn that).
                int spare = this.spareWood();
                for (ItemStack stack : this.kit().items()) {
                    boolean log = Res.LOG.match.test(stack);
                    if ((log || Res.PLANKS.match.test(stack)) && spare >= (log ? 4 : 1)) {
                        int allowed = log ? spare / 4 : spare;
                        fuelStack = stack.copyWithCount(Math.min(Math.min(stack.getCount(), allowed), (n * 2 + 2) / 3));
                        break;
                    }
                }
            }
            if (fuelStack.isEmpty()) {
                this.step = null; // no fuel: the planner fetches some
                return;
            }
            Item fuelItem = fuelStack.getItem();
            this.kit().remove(st -> st.is(fuelItem), fuelStack.getCount());
            furnace.setItem(1, fuelStack);
            this.bot.onKitChanged();
        }
        if (this.actionTicks > 20 * 60 * 3) {
            this.actionTicks = 0;
            this.step = null; // (not cooking for three minutes: look again what is missing)
        }
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

    private @Nullable BlockPos flank;
    private int flankTick;

    /** The surface spot that is cheapest to dig out to (blocks up plus blocks across), if better than straight up. */
    private @Nullable BlockPos findFlank(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        int upHere = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, feet.getX(), feet.getZ()) - feet.getY();
        BlockPos best = null;
        double bestCost = upHere;
        for (int r = 8; r <= 64; r += 8) {
            for (int k = 0; k < 16; k++) {
                double a = Math.PI * 2.0 * k / 16.0;
                int x = feet.getX() + (int) Math.round(Math.cos(a) * r);
                int z = feet.getZ() + (int) Math.round(Math.sin(a) * r);
                int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);
                if (!level.getFluidState(new BlockPos(x, y - 1, z)).isEmpty()) {
                    continue;
                }
                double cost = Math.max(0, y - feet.getY()) + r * 0.7;
                if (cost < bestCost * 0.8) {
                    bestCost = cost;
                    best = new BlockPos(x, y, z);
                }
            }
        }
        return best;
    }

    private @Nullable BlockPos skyExit;
    private @Nullable BlockPos stairTop;
    private int skyExitTick;

    /** Open sky within reach at about this height (a cave mouth, the edge of an overhang). */
    private @Nullable BlockPos findSkyExit(ServerLevel level) {
        BlockPos feet = this.bot.blockPosition();
        for (int r = 2; r <= 24; r += 2) {
            for (int k = 0; k < 16; k++) {
                double a = Math.PI * 2.0 * k / 16.0;
                int x = feet.getX() + (int) Math.round(Math.cos(a) * r);
                int z = feet.getZ() + (int) Math.round(Math.sin(a) * r);
                int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x, z);
                if (Math.abs(y - feet.getY()) <= 4 && level.getFluidState(new BlockPos(x, y - 1, z)).isEmpty()) {
                    return new BlockPos(x, y, z);
                }
            }
        }
        return null;
    }

    /** Rock overhead (in a cave, its own staircase): the sky is not in sight. */
    private boolean underground() {
        // (Deep down, not just under an overhang or a tree: from there a player simply walks out.)
        BlockPos head = BlockPos.containing(this.bot.getEyePosition());
        return !this.level().canSeeSky(head) && this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
                head.getX(), head.getZ()) > head.getY() + 6;
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
            if ((this.speedrun || this.autonomous) && this.level().dimension() == net.minecraft.world.level.Level.OVERWORLD) {
                // Like a player looking for something: out into country it has not seen yet, keeping
                // its direction, on dry land where it can (across water where it has to).
                double bestScore = -Double.MAX_VALUE;
                for (int k = 0; k < 12; k++) {
                    double a = angle + k * (Math.PI * 2.0 / 12.0);
                    Vec3 c = pos.add(Math.cos(a) * 40.0, 0.0, Math.sin(a) * 40.0);
                    int cy = this.level().getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING, (int) c.x, (int) c.z);
                    boolean dry = this.level().getFluidState(BlockPos.containing(c.x, cy - 1, c.z)).isEmpty();
                    double score = (this.seenCountry.contains(cellOf(c)) ? 0.0 : 3.0) + (dry ? 1.5 : 0.0)
                            + Math.cos(a - angle) + this.bot.getRandom().nextDouble() * 0.3;
                    if (score > bestScore) {
                        bestScore = score;
                        candidate = c;
                        y = cy;
                        this.exploreHeading = a;
                    }
                }
            }
            this.exploreTarget = new Vec3(candidate.x, y, candidate.z);
        }
        boolean moving = this.bot.getNavigation().moveTo(this.exploreTarget.x, this.exploreTarget.y, this.exploreTarget.z, 1.1);
        if (!moving && (this.speedrun || this.autonomous) && this.level() instanceof ServerLevel sl) {
            // No path at all (in a pit, walled in by a cliff): make one, like a player - dig up out
            // of a hole, otherwise tunnel through towards the target (bridging gaps on the way).
            BlockPos goal = BlockPos.containing(this.exploreTarget);
            if (this.inPit(sl) || goal.getY() > this.bot.getBlockY() + 3) {
                this.doDigUp(sl);
            } else {
                this.tunnelTowards(sl, goal);
            }
        }
        if (PvpBotEntity.DEBUG && ++this.exploreLog % 400 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   explore: at {} target {} path {} heading {} in water {}", this.bot.blockPosition().toShortString(),
                    BlockPos.containing(this.exploreTarget).toShortString(), moving, (int) Math.toDegrees(this.exploreHeading), this.bot.isInWater());
        }
        this.step = null;
    }

    private int exploreLog;

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
        if (this.wet(level) && ++this.wetTicks > 60) {
            // Floating in a pool (a player would not dig on from here): out of it on blocks first.
            this.climbOutOfWater(level);
            return;
        }
        if (!this.wet(level)) {
            this.wetTicks = 0;
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
        if (this.eyeWentDown && this.eyeDownAt != null && this.speedrun && this.stage2Done
                && Math.abs(feet.getX() - this.eyeDownAt.getX()) + Math.abs(feet.getZ() - this.eyeDownAt.getZ()) > 32) {
            // Wandered off: the stronghold is under the spot where the eye went down - back there.
            int dx = this.eyeDownAt.getX() - feet.getX();
            int dz = this.eyeDownAt.getZ() - feet.getZ();
            this.digDir = Math.abs(dx) > Math.abs(dz) ? (dx > 0 ? Direction.EAST : Direction.WEST) : (dz > 0 ? Direction.SOUTH : Direction.NORTH);
        }
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
            // (Air next to lava is fine - lava under the next step gets bridged below; digging out a
            // block that holds lava back is not.)
            boolean danger = !state.getCollisionShape(level, p).isEmpty() && this.nearLava(level, p)
                    || !level.getFluidState(p).isEmpty() || state.getDestroySpeed(level, p) < 0.0F;
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
        if (down) {
            // The next stair is one lower: no cave drop and no lava under it either.
            BlockPos stair = front.below();
            int depth = 0;
            boolean lava = false;
            while (depth < 4 && level.getBlockState(stair.below(depth + 1)).getCollisionShape(level, stair.below(depth + 1)).isEmpty()) {
                depth++;
                lava |= level.getFluidState(stair.below(depth)).is(net.minecraft.tags.FluidTags.LAVA);
            }
            lava |= level.getFluidState(stair.below(depth + 1)).is(net.minecraft.tags.FluidTags.LAVA);
            if (lava || depth >= 3) {
                if (PvpBotEntity.DEBUG && ++this.digLogTicks % 20 == 1) {
                    PvpBotMod.LOGGER.info("[SELFTEST]   dig: drop under the next stair at {} depth {} lava {}", stair.toShortString(), depth, lava);
                }
                if (!lava && this.bridge(level, stair.below())) {
                    this.step = null;
                    return;
                }
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
            || st.is(Items.NETHERRACK) || st.is(Items.DIRT) || st.is(Items.BLACKSTONE) || st.is(Items.END_STONE);

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
        int pickaxes = 0;
        for (ItemStack st : this.kit().items()) {
            if (pickaxeTier(st.getItem()) > 0) {
                pickaxes++;
            }
        }
        // (The last three cobblestones are the next pickaxe - not for building. Without a pickaxe
        // nothing it digs drops anything.)
        int reserve = pickaxes <= 1 ? 3 : 0;
        int cobble = this.kit().count(Res.COBBLE.match);
        for (ItemStack st : this.kit().items()) {
            if (BRIDGE_BLOCK.test(st) && (!Res.COBBLE.match.test(st) || cobble > reserve)) {
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
            if (!level.getFluidState(p).isEmpty() && this.kit().count(BRIDGE_BLOCK) > 0) {
                // Water or lava in the way: block it off first (then that block is dug out again).
                this.bridge(level, p, false);
                return;
            }
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
        if (PvpBotEntity.DEBUG && ++this.portalLog % 200 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   portal: at {} portal {} ({}) dist {} ground {} nav {}", this.bot.blockPosition().toShortString(),
                    portal.toShortString(), bn(level, portal), String.format("%.1f", Math.sqrt(this.bot.position().distanceToSqr(center))),
                    this.bot.onGround(), this.bot.getNavigation().isDone() ? "done" : "moving");
        }
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
        if (this.bot.position().distanceToSqr(center) > 9.0 && (this.bot.getNavigation().isDone() || this.noProgress())
                && !this.bot.getNavigation().moveTo(center.x, center.y, center.z, 1.1)) {
            // Close, but no way there (walls, a drop, lava): dig or build straight towards it.
            Vec3 to = center.subtract(this.bot.position());
            this.digDir = Math.abs(to.x) > Math.abs(to.z) ? (to.x > 0 ? Direction.EAST : Direction.WEST) : (to.z > 0 ? Direction.SOUTH : Direction.NORTH);
            if (to.y > 2.0) {
                this.doDigUp(level);
            } else {
                this.doDig(level, to.y < -2.0);
            }
        } else if (this.bot.position().distanceToSqr(center) > 2.0) {
            this.bot.getNavigation().moveTo(center.x, center.y, center.z, 1.1);
            if (this.bot.position().distanceToSqr(center) < 9.0 && center.y > this.bot.getY() + 1.2) {
                // The portal stands higher than a jump (built on a hillside): a block up first.
                this.pillarUp(level);
                return;
            }
            if (this.bot.position().distanceToSqr(center) < 9.0 && center.y > this.bot.getY() + 0.5 && this.bot.onGround()) {
                // The portal stands on its obsidian frame, a block up: jump in.
                this.bot.getJumpControl().jump();
            }
            if (this.bot.position().distanceToSqr(center) < 9.0) {
                this.bot.getMoveControl().setWantedPosition(center.x, center.y, center.z, 1.0);
            }
        } else {
            this.bot.getNavigation().stop();
            this.bot.getMoveControl().setWantedPosition(center.x, center.y, center.z, 0.6);
            if (center.y > this.bot.getY() + 0.5 && this.bot.onGround()) {
                this.bot.getJumpControl().jump();
            }
        }
        this.step = null;
    }

    private void doHuntMob(net.minecraft.world.entity.EntityType<?> type) {
        LivingEntity mob = this.visibleMob(type);
        if (mob == null || this.bot.isRetreating()) {
            this.step = null;
            return;
        }
        if (type == EntityTypes.BLAZE) {
            // Blazes set you on fire: fire resistance first, like a player would.
            this.drinkFireResistance(this.level());
        }
        // Not hurting it for 20 s (out of reach behind a wall, up in the air): leave that one for a minute.
        if (!mob.getUUID().equals(this.huntMob)) {
            this.huntMob = mob.getUUID();
            this.huntTicks = 0;
            this.huntHealth = mob.getHealth();
        } else if (mob.getHealth() < this.huntHealth) {
            this.huntHealth = mob.getHealth();
            this.huntTicks = 0;
        } else if (++this.huntTicks > 400) {
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   hunt: cannot get at {} at {} from {} - leaving it for a minute", type.toShortString(),
                        mob.blockPosition().toShortString(), this.bot.blockPosition().toShortString());
            }
            this.ignoredMobs.put(mob.getUUID(), this.bot.tickCount + 1200);
            this.huntMob = null;
            this.step = null;
            return;
        }
        this.bot.huntTarget(mob);
        this.step = null;
    }

    private java.util.@Nullable UUID huntMob;
    private int huntTicks;
    private float huntHealth;
    private final java.util.Map<java.util.UUID, Integer> ignoredMobs = new java.util.HashMap<>();

    /**
     * Nether exploring without x-ray: walk (or tunnel) in one direction for a long way, turning away
     * from lava; fortresses stretch far along one axis, so a straight line finds them best. Heads for
     * fortress blocks and spawners once they are in sight.
     */
    private void doExploreNether(ServerLevel level) {
        if (this.lowCooldown > 0) {
            this.lowCooldown--;
        } else if (this.bot.getY() < 45.0) {
            // Down at the lava sea (y 31): climb back up before going on - unless that gets nowhere
            // (lava all around): then explore from here for a while.
            if (this.bot.getBlockY() > this.lowBestY) {
                this.lowBestY = this.bot.getBlockY();
                this.lowTicks = 0;
            } else if (++this.lowTicks > 300) {
                this.lowTicks = 0;
                this.lowBestY = Integer.MIN_VALUE;
                this.lowCooldown = 600;
            }
            this.doDigUp(level);
            this.step = null;
            return;
        } else {
            this.lowBestY = Integer.MIN_VALUE;
            this.lowTicks = 0;
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
        BlockPos goal = wantRods && this.bot.tickCount > this.spawnerRetryTick ? this.nearest(Ore.SPAWNER) : null;
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
                if (level.getBlockState(goal).is(Blocks.SPAWNER)) {
                    // (A spawner stays worth it: try again in a minute, from wherever it is then.)
                    this.spawnerRetryTick = this.bot.tickCount + 1200;
                } else {
                    this.blacklist.add(goal);
                    this.fortressVisited.add(cellKey(goal));
                }
                this.netherGoal = null;
                this.step = null;
                return;
            }
            BlockPos stand = standBeside(level, goal);
            this.bot.getNavigation().moveTo(stand.getX() + 0.5, stand.getY(), stand.getZ() + 0.5, 1.1);
            // (A "path" that does not move it for 3 seconds is no path either.)
            if (this.bot.getNavigation().isDone() || this.netherGoalTicks > 60) {
                this.bot.getNavigation().stop();
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
        if (this.bot.getY() > 90.0 && this.bot.getNavigation().isDone()) {
            // Up under the nether ceiling (the portal came out up here): down to the open levels first,
            // nothing can be seen from inside the rock.
            this.doDig(level, true);
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
    private int lowTicks;
    private int lowBestY = Integer.MIN_VALUE;
    private int lowCooldown;
    private int netherrackTicks;

    /** Mines a netherrack block it can see within reach (not the floor it stands on). */
    private boolean mineNetherrack(ServerLevel level) {
        return this.mineNearby(level, Blocks.NETHERRACK);
    }

    /** Mines a block of this kind it can see within reach (not the floor it stands on). */
    private boolean mineNearby(ServerLevel level, net.minecraft.world.level.block.Block kind) {
        if (++this.netherrackTicks > 1200) {
            if (this.netherrackTicks > 2400) {
                this.netherrackTicks = 0; // (a while exploring, then try again)
            }
            return false;
        }
        BlockPos feet = this.bot.blockPosition();
        BlockPos best = null;
        double bestDist = Double.MAX_VALUE;
        for (BlockPos p : BlockPos.betweenClosed(feet.offset(-3, -1, -3), feet.offset(3, 2, 3))) {
            // (The floor around is fine, just not the block it stands on.)
            if (p.equals(feet.below()) || !level.getBlockState(p).is(kind) || this.nearLava(level, p) || !this.seesBlock(level, p)) {
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
            this.eyeDownAt = this.bot.blockPosition(); // (where it saw the eye drop, like a player)
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
        this.bot.setTarget(null); // (no fight is worth burning for)
        if (PvpBotEntity.DEBUG && this.bot.tickCount % 10 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   lava: at {} feet {} above {} below {} blocks {} fireRes {} lastSafe {}", feet.toShortString(),
                    bn(level, feet), bn(level, feet.above()), bn(level, feet.below()), this.kit().count(BRIDGE_BLOCK),
                    this.bot.hasEffect(net.minecraft.world.effect.MobEffects.FIRE_RESISTANCE), this.lastSafe);
        }
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
        } else if (level.getFluidState(feet).is(net.minecraft.tags.FluidTags.LAVA) && this.kit().count(BRIDGE_BLOCK) > 0
                && level.getBlockState(feet.below()).canBeReplaced()) {
            // Under the surface: a block under its feet each time, up and out (like out of water).
            this.bridge(level, feet.below(), false);
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
        BlockPos spawner = this.nearest(Ore.SPAWNER);
        if (spawner != null && !this.visitedCells.contains(cellKey(spawner)) && spawner.distSqr(here) < 64 * 64) {
            // The only spawner in a stronghold (silverfish) is in the end portal room: go there.
            best = spawner;
            bestDist = 0.0;
        }
        for (BlockPos p : this.known.getOrDefault(Ore.STRONGHOLD, List.of())) {
            if (best != null && bestDist == 0.0) {
                break;
            }
            if (this.visitedCells.contains(cellKey(p)) || this.blacklist.contains(p)) {
                continue;
            }
            double d = here.distSqr(p);
            if (d < bestDist) {
                best = p;
                bestDist = d;
            }
        }
        for (BlockPos p : this.known.getOrDefault(Ore.STRONGHOLD, List.of())) {
            // Floors it has seen (bricks with room above): that is where the corridors and rooms are -
            // behind the walls is only rock.
            if (level.getBlockState(p.above()).getCollisionShape(level, p.above()).isEmpty()) {
                this.strongholdSeen.add(cellKey(p.above()));
            }
        }
        if (best == null) {
            // Every part it has seen is done: on to the places right next to them (a corridor goes on
            // there, a room above or below) - the stronghold is a maze, not one hall.
            for (long cell : this.strongholdSeen) {
                BlockPos c = BlockPos.of(cell);
                for (Direction d : Direction.Plane.HORIZONTAL) {
                    BlockPos n = c.relative(d);
                    long key = BlockPos.asLong(n.getX(), n.getY(), n.getZ());
                    if (this.visitedCells.contains(key) || this.strongholdSeen.contains(key)) {
                        continue;
                    }
                    BlockPos center = new BlockPos(n.getX() * 8 + 4, c.getY() * 8 + 2, n.getZ() * 8 + 4);
                    double dd = here.distSqr(center);
                    if (dd < bestDist && !this.blacklist.contains(center)) {
                        best = center;
                        bestDist = dd;
                    }
                }
            }
            if (best != null && here.distSqr(best) <= 5 * 5) {
                this.visitedCells.add(cellKey(best));
                this.step = null;
                return;
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

    private final java.util.Set<Long> strongholdSeen = new java.util.HashSet<>();

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
        if (PvpBotEntity.DEBUG && ++this.frameLog % 200 == 0) {
            PvpBotMod.LOGGER.info("[SELFTEST]   frames: at {} known {} next {} dist {} eyes {}", this.bot.blockPosition().toShortString(), frames.size(),
                    next == null ? "-" : next.toShortString(), next == null ? "-" : String.format("%.1f", this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(next))),
                    this.kit().count(Res.EYE.match));
        }
        if (next != null) {
            if (this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(next)) > 4.0) {
                if ((this.bot.getNavigation().isDone() || this.noProgress())
                        && !this.bot.getNavigation().moveTo(next.getX() + 0.5, next.getY() + 1, next.getZ() + 0.5, 1.0)) {
                    // No path (lava pool, stairs, silverfish blocks in the way): dig straight there.
                    this.tunnelTowards(level, next.above());
                }
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
            // Not all frames in sight yet: walk round the ring, from one frame we know to the next
            // (standing on it you see the ones across), digging a way where there is none.
            double cx = frames.stream().mapToInt(BlockPos::getX).average().orElse(0.0);
            double cz = frames.stream().mapToInt(BlockPos::getZ).average().orElse(0.0);
            frames.sort(java.util.Comparator.comparingDouble(fr -> Math.atan2(fr.getZ() - cz, fr.getX() - cx)));
            BlockPos f = frames.get(Math.floorMod(this.frameVisit, frames.size()));
            BlockPos top = f.above();
            if (this.bot.blockPosition().distSqr(top) <= 2 || ++this.frameTicks > 200) {
                this.frameVisit++;
                this.frameTicks = 0;
            } else if (!this.bot.getNavigation().moveTo(top.getX() + 0.5, top.getY(), top.getZ() + 0.5, 1.0) || this.noProgress()) {
                this.tunnelTowards(level, top);
            }
        }
        this.step = null;
    }

    private int frameVisit;
    private int frameLog;
    private int portalLog;
    private int frameTicks;

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
        if (this.inPit(level)) {
            // Down in a hole (fell in, or dug its way down): out first, nothing can be reached from here.
            this.doDigUp(level);
            return;
        }
        boolean caged = this.isCaged(level, crystal);
        if (los && !caged && h <= 44.0 && (shots < 6 || this.kit().count(BRIDGE_BLOCK) == 0)) {
            this.bot.getNavigation().stop();
            this.shootCrystal(crystal);
            return;
        }
        // Enough blocks for the pole this one needs (its height plus a few for the rim)?
        int needed = Math.max(16, (int) (crystal.getY() - this.bot.getY()) + 8);
        if (this.kit().count(BRIDGE_BLOCK) < needed && this.towerGroundY == Integer.MIN_VALUE && this.mineNearby(level, Blocks.END_STONE)) {
            // Low on blocks for the poles: end stone from the ground around (like a player would).
            return;
        }
        if (this.kit().count(BRIDGE_BLOCK) == 0) {
            // Nothing to build with: just walk around for a clear shot.
            this.crystalNoLos++;
            if (this.crystalNoLos > 600) {
                this.giveUpCrystal(crystal, "no blocks, no clear shot");
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
                this.giveUpCrystal(crystal, "no pole spot");
                return;
            }
        }
        BlockPos spot = this.poleSpot;
        double dx = spot.getX() + 0.5 - this.bot.getX();
        double dz = spot.getZ() + 0.5 - this.bot.getZ();
        // (Higher up than the spot is fine: the pole just starts there.)
        if (dx * dx + dz * dz > 0.6 * 0.6) {
            if (++this.poleWalk > 900) {
                // Cannot get there: another spot next time.
                this.badPoleSpots.add(spot);
                this.poleSpot = null;
                this.giveUpCrystal(crystal, "cannot reach pole spot");
                return;
            }
            boolean stuck = this.noProgress();
            if (this.poleWalk > 300 && stuck) {
                // No way there on foot: dig one, like a player would.
                this.tunnelTowards(level, spot);
            } else if (dx * dx + dz * dz < 3.0 * 3.0) {
                this.bot.getNavigation().stop();
                this.bot.getMoveControl().setWantedPosition(spot.getX() + 0.5, spot.getY(), spot.getZ() + 0.5, 0.8);
            } else if (this.bot.getNavigation().isDone() || stuck) {
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
            this.giveUpCrystal(crystal, "not getting higher on pole");
            return;
        }
        this.bot.getLookControl().setLookAt(crystal);
        boolean caged = this.isCaged(level, crystal);
        double h = this.bot.position().subtract(crystal.position()).horizontalDistance();
        if (caged && h < 8.0) {
            // Right at the cage: break the bars between it and the crystal, then climb down and
            // shoot from further away (the crystal's blast would kill it this close).
            if (this.bot.getEyeY() < crystal.getY() - 0.5) { // (the bars reach up two blocks: breakable from here)
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
                this.poleStall = 0; // (breaking bars is progress too)
                this.breakBlock(level, hit.getBlockPos());
                return;
            }
            if (hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK && level.getBlockState(hit.getBlockPos()).is(Blocks.IRON_BARS)
                    && this.bot.onGround()) {
                // A wide tower: the bars are out of reach. Step over onto its top towards the cage (a
                // block down where there is no floor), and come back to the pole afterwards.
                if (this.cageStepFrom == null) {
                    this.cageStepFrom = this.bot.blockPosition();
                }
                Vec3 toward = crystal.position().subtract(this.bot.position()).multiply(1.0, 0.0, 1.0).normalize();
                Vec3 next = this.bot.position().add(toward);
                BlockPos under = BlockPos.containing(next.x, this.bot.getY() - 0.5, next.z);
                if (level.getBlockState(under).getCollisionShape(level, under).isEmpty()) {
                    this.bridge(level, under, false);
                }
                this.poleStall = 0;
                this.bot.getMoveControl().setWantedPosition(next.x, this.bot.getY(), next.z, 0.5);
                return;
            }
            if (hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK && level.getBlockState(hit.getBlockPos()).is(Blocks.IRON_BARS)) {
                // Bars out of reach, but still in the air (just jumped up the pole): land first.
                return;
            }
            if (hit.getType() != net.minecraft.world.phys.HitResult.Type.BLOCK) {
                // A bigger hole: every bar on this side within reach (the shot from further out comes
                // in at a slightly different angle).
                Vec3 side = this.bot.position().subtract(crystal.position()).multiply(1.0, 0.0, 1.0).normalize();
                BlockPos cb = crystal.blockPosition();
                for (BlockPos b : BlockPos.betweenClosed(cb.offset(-2, 0, -2), cb.offset(2, 2, 2))) {
                    Vec3 rel = Vec3.atCenterOf(b).subtract(crystal.position()).multiply(1.0, 0.0, 1.0);
                    if (level.getBlockState(b).is(Blocks.IRON_BARS) && rel.dot(side) > 1.0
                            && this.bot.getEyePosition().distanceTo(Vec3.atCenterOf(b)) < 4.5) {
                        this.poleStall = 0;
                        this.breakBlock(level, b.immutable());
                        return;
                    }
                }
                // Open on this side: down again, then out and up for the shot - from this same side.
                this.cageOpened.add(crystal.getUUID());
                this.cageSide.put(crystal.getUUID(), this.bot.position().subtract(crystal.position()).multiply(1.0, 0.0, 1.0));
            }
            if (PvpBotEntity.DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   cage at {}: {} (hit {} {} at {} away, bot eye {} at {})", crystal.blockPosition().toShortString(),
                        this.cageOpened.contains(crystal.getUUID()) ? "opened" : "cannot open from here", hit.getType(),
                        hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK ? level.getBlockState(hit.getBlockPos()).getBlock().getName().getString() : "-",
                        String.format("%.1f", hit.getLocation().distanceTo(this.bot.getEyePosition())), String.format("%.1f", this.bot.getEyeY()),
                        this.bot.blockPosition().toShortString());
            }
            if (this.cageStepFrom != null) {
                // Back onto the pole before climbing down it.
                if (this.bot.blockPosition().getX() != this.cageStepFrom.getX() || this.bot.blockPosition().getZ() != this.cageStepFrom.getZ()) {
                    this.poleStall = 0;
                    this.bot.getMoveControl().setWantedPosition(this.cageStepFrom.getX() + 0.5, this.cageStepFrom.getY(), this.cageStepFrom.getZ() + 0.5, 0.5);
                    return;
                }
                this.cageStepFrom = null;
            }
            if (!this.cageOpened.contains(crystal.getUUID())) {
                this.giveUpCrystal(crystal, "cage not opened");
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
                this.giveUpCrystal(crystal, "missed 10 shots from pole");
            }
            return;
        }
        if (this.bot.getEyeY() < crystal.getY() + 4.0) {
            this.pillarUp(level);
            return;
        }
        // Up high and still nothing to see: leave that one.
        this.giveUpCrystal(crystal, "up high, still no sight");
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

    private void giveUpCrystal(net.minecraft.world.entity.boss.enderdragon.EndCrystal crystal, String why) {
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   gives up on crystal at {} for now: {} (shots {}, at {}, blocks {}, above {})", crystal.blockPosition().toShortString(),
                    why, this.crystalShots.getOrDefault(crystal.getUUID(), 0), this.bot.blockPosition().toShortString(), this.kit().count(BRIDGE_BLOCK),
                    this.level().getBlockState(this.bot.blockPosition().above(2)).getBlock().getName().getString());
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
        if (this.cageSide.containsKey(crystal.getUUID())) {
            toBot = this.cageSide.get(crystal.getUUID()); // (the side where the cage is open)
        }
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
            // (Real ground, not the top of one of its old poles: those are one block wide.)
            int floor = 0;
            for (Direction d : Direction.Plane.HORIZONTAL) {
                if (!level.getBlockState(ground.relative(d)).getCollisionShape(level, ground.relative(d)).isEmpty()) {
                    floor++;
                }
            }
            BlockPos spot = new BlockPos(x, y, z);
            if (y > level.getMinY() + 10 && level.getBlockState(ground).is(Blocks.END_STONE) && floor >= 2
                    && !this.badPoleSpots.contains(spot) && new Vec3(x, 0, z).horizontalDistance() < 90.0) {
                return spot;
            }
        }
        return null;
    }

    private @Nullable BlockPos poleSpot;
    /** Pole spots it could not walk to (another one next time). */
    private final java.util.Set<BlockPos> badPoleSpots = new java.util.HashSet<>();
    private java.util.@Nullable UUID poleFor;
    private int poleWalk;
    private int poleShots;
    private double poleBestY;
    private int poleStall;
    private boolean poleDone;
    private final java.util.Set<java.util.UUID> cageOpened = new java.util.HashSet<>();
    private final java.util.Map<java.util.UUID, Vec3> cageSide = new java.util.HashMap<>();
    private @Nullable BlockPos cageStepFrom;

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
            BlockPos over = feet.above(2);
            if (!level.getBlockState(over).getCollisionShape(level, over).isEmpty()) {
                // No room above: clear it (not the towers' obsidian or bedrock - move away from those).
                if (!level.getBlockState(over).is(Blocks.OBSIDIAN) && level.getBlockState(over).getDestroySpeed(level, over) >= 0.0F) {
                    this.breakBlock(level, over);
                } else {
                    this.poleSpot = null;
                }
                return;
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
            if (ore != Ore.WATER && ore != Ore.LAVA && this.level().getFluidState(p.above()).is(net.minecraft.tags.FluidTags.WATER)) {
                continue; // (under water - the bottom of a lake or the sea: nobody mines there)
            }
            if (ore != Ore.LAVA && ore != Ore.OBSIDIAN && ore != Ore.WATER && this.lavaNear(p, ore == Ore.DIAMOND ? 1 : 2)) {
                continue; // (next to lava: one wrong step and everything is gone)
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

    private int mineBudget = 600;

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
            // Diamonds are worth a longer way (digging over to them, bridging a cave).
            double far = Math.sqrt(this.bot.blockPosition().distSqr(target));
            this.mineBudget = ore == Ore.DIAMOND ? 600 + (int) (far * 80.0) : 600;
        }
        if (++this.mineTargetTicks > this.mineBudget) {
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
        // Going down: never into a drop (a cave under the next block) - a block there, or not this way.
        if (dy < 0 && this.bot.onGround()) {
            BlockPos land = front.below();
            int depth = 0;
            while (depth < 4 && level.getBlockState(land.below(depth + 1)).getCollisionShape(level, land.below(depth + 1)).isEmpty()) {
                depth++;
            }
            if (depth >= 3 || level.getFluidState(land.below(depth + 1)).is(net.minecraft.tags.FluidTags.LAVA)) {
                if (!this.bridge(level, land.below())) {
                    this.digDir = this.digDir.getClockWise();
                    this.noProgressTicks = 0;
                }
                return;
            }
        }
        // Path is clear: step forward (and up if needed) - over a gap only on a block it puts there.
        if (dy >= 0 && this.bot.onGround() && level.getBlockState(front.below()).getCollisionShape(level, front.below()).isEmpty()
                && level.getFluidState(front.below()).isEmpty() && this.bridge(level, front.below())) {
            return;
        }
        Vec3 next = Vec3.atBottomCenterOf(dy > 0 ? front.above() : front);
        this.bot.getMoveControl().setWantedPosition(next.x, next.y, next.z, 1.0);
        if (dy > 0 && this.bot.onGround()) {
            this.bot.getJumpControl().jump();
        }
        this.noProgressTicks = 20;
    }

    private boolean lavaNear(BlockPos p, int r) {
        for (BlockPos q : BlockPos.betweenClosed(p.offset(-r, -r, -r), p.offset(r, r, r))) {
            if (this.level().getFluidState(q).is(net.minecraft.tags.FluidTags.LAVA)) {
                return true;
            }
        }
        return false;
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
        int cap = ore == Ore.STRONGHOLD ? 6000 : ore == Ore.FORTRESS ? 512 : 128;
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
        if (this.breaking != null) {
            return false;
        }
        ItemEntity closest = null;
        double best = 10.0 * 10.0;
        for (ItemEntity item : this.level().getEntitiesOfClass(ItemEntity.class, this.bot.getBoundingBox().inflate(10.0))) {
            if (item.isAlive() && isUseful(item.getItem()) && !this.enoughOf(item.getItem()) && this.worthRoom(item.getItem()) && this.bot.distanceToSqr(item) < best && this.bot.hasLineOfSight(item)
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

    // ------------------------------------------------------------------ what things are worth

    /**
     * How much an item matters right now (0-100): what it works towards counts most, rubble least.
     * A full inventory throws the least important stack away for something that matters more.
     */
    int value(ItemStack st) {
        if (st.is(Items.ENDER_EYE) || st.is(Items.BLAZE_ROD) || st.is(Items.BLAZE_POWDER) || st.is(Items.ENDER_PEARL)) {
            return 100;
        }
        if (st.is(Items.OBSIDIAN)) {
            return this.speedrun && !this.portalBuilt ? 96 : 15;
        }
        if (pickaxeTier(st.getItem()) > 0 || st.is(Items.FLINT_AND_STEEL) || st.is(Items.WATER_BUCKET) || st.is(Items.BUCKET)
                || st.is(Items.BOW) || st.is(Items.POTION) || st.is(Items.SHIELD) || Kit.classify(st) != Role.OTHER) {
            return 95;
        }
        if (st.is(Items.DIAMOND)) return 90;
        if (st.is(Items.ARROW)) return 80;
        if (st.is(Items.IRON_INGOT)) return 80;
        if (Res.COOKED_MEAT.match.test(st)) return 75;
        if (st.is(Items.RAW_IRON)) return 70;
        if (st.is(Items.CRAFTING_TABLE) || st.is(Items.FURNACE)) return 60;
        if (st.is(Items.FLINT)) return this.kit().count(x -> x.is(Items.FLINT_AND_STEEL)) == 0 ? 60 : 20;
        if (Res.RAW_MEAT.match.test(st)) return 55;
        if (Res.COAL.match.test(st) || Res.LOG.match.test(st)) return 50;
        if (Res.PLANKS.match.test(st) || Res.STICK.match.test(st)) return 45;
        if (st.is(Items.STRING) || st.is(Items.FEATHER)) return 40;
        if (BRIDGE_BLOCK.test(st)) {
            // The first stack to build with matters, more is rubble.
            // (Blocks save its life over lava and drops: the first stack is precious.)
            return this.kit().count(BRIDGE_BLOCK) <= 64 ? 85 : 6;
        }
        if (st.is(Items.ROTTEN_FLESH)) return 1;
        if (JUNK.test(st)) return 3;
        return 20;
    }

    /** Is this worth picking up with a full inventory (something clearly less important can go)? */
    boolean worthRoom(ItemStack incoming) {
        if (this.kit().hasRoom()) {
            return true;
        }
        int least = Integer.MAX_VALUE;
        for (ItemStack st : this.kit().items()) {
            least = Math.min(least, this.value(st));
        }
        return this.value(incoming) > least + 5;
    }

    /** Throws the least important stack away to make room for {@code incoming} (if it is worth it). */
    boolean makeRoomFor(ItemStack incoming) {
        if (this.kit().hasRoom()) {
            return true;
        }
        ItemStack least = null;
        int leastValue = Integer.MAX_VALUE;
        for (ItemStack st : this.kit().items()) {
            int v = this.value(st);
            if (v < leastValue) {
                leastValue = v;
                least = st;
            }
        }
        if (least == null || this.value(incoming) <= leastValue + 5) {
            return false;
        }
        ItemStack out = least.copy();
        ItemStack gone = least;
        this.kit().remove(x -> x == gone, out.getCount());
        net.minecraft.world.entity.item.ItemEntity dropped = this.bot.spawnAtLocation(this.level(), out);
        if (dropped != null) {
            dropped.setPickUpDelay(20 * 60); // (not picked right back up)
        }
        this.bot.onKitChanged();
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   inventory full: throws away {} (worth {}) for {} (worth {})", out, leastValue,
                    incoming, this.value(incoming));
        }
        return true;
    }

    /** Building blocks it already has plenty of (the room is for what it came for). */
    boolean enoughOf(ItemStack stack) {
        if (stack.is(Items.NETHERRACK) || stack.is(Items.END_STONE)) {
            return this.kit().count(st -> st.is(stack.getItem())) >= 128;
        }
        // Cobblestone, deepslate, dirt and the like: three stacks together are plenty.
        return JUNK.test(stack) && this.kit().count(JUNK) >= 192;
    }

    static boolean isUseful(ItemStack stack) {
        if (stack.is(Items.NETHERRACK) || stack.is(Items.END_STONE)) {
            return true; // for bridging over the lava sea and the poles in the End
        }
        for (Res res : Res.values()) {
            if (res.match.test(stack)) {
                return true;
            }
        }
        return Kit.classify(stack) != Role.OTHER || RECIPES.containsKey(stack.getItem()) || pickaxeTier(stack.getItem()) > 0;
    }
}
