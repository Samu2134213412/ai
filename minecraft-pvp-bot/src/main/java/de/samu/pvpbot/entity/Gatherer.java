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
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
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
        WATER("Wasser", Res.OBSIDIAN, s -> s.getFluidState().is(net.minecraft.tags.FluidTags.WATER) && s.getFluidState().isSource());

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
        recipe(Items.DIAMOND_SWORD, 1, Res.DIAMOND, 2, Res.STICK, 1);
        recipe(Items.DIAMOND_PICKAXE, 1, Res.DIAMOND, 3, Res.STICK, 2);
        recipe(Items.DIAMOND_HELMET, 1, Res.DIAMOND, 5);
        recipe(Items.DIAMOND_CHESTPLATE, 1, Res.DIAMOND, 8);
        recipe(Items.DIAMOND_LEGGINGS, 1, Res.DIAMOND, 7);
        recipe(Items.DIAMOND_BOOTS, 1, Res.DIAMOND, 4);
        recipe(Items.BUCKET, 1, Res.IRON, 3);
        recipe(Items.FLINT_AND_STEEL, 1, Res.IRON, 1, Res.FLINT, 1);
    }

    private static final Item[] IRON_ARMOR = {Items.IRON_HELMET, Items.IRON_CHESTPLATE, Items.IRON_LEGGINGS, Items.IRON_BOOTS};
    private static final Item[] DIAMOND_ARMOR = {Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS};
    private static final EquipmentSlot[] ARMOR_SLOTS = {EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET};

    /** The next thing to do. */
    sealed interface Step permits Craft, Smelt, Mine, Hunt, Explore, Descend, StripMine, FillWater, MakeObsidian, BuildPortal {
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

    record Hunt() implements Step {
        public String describe() {
            return "jagt Tiere für Essen";
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
    private @Nullable Vec3 anchor;
    private @Nullable String lastAnnounced;

    // "Beat the game" mode, stage 1: diamonds, obsidian and a lit nether portal.
    private boolean speedrun;
    private boolean portalBuilt;
    private Direction digDir = Direction.NORTH;
    private int portalProgress;
    private @Nullable BlockPos portalBase;
    private Direction portalAlong = Direction.EAST;
    private final java.util.Set<Long> forcedChunks = new java.util.HashSet<>();

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

    void setPortalBuilt(boolean built) {
        this.portalBuilt = built;
    }

    /** Far away from every player the bot would stop; keep the chunks around it loaded. */
    void keepChunksLoaded() {
        if (!this.speedrun || this.bot.tickCount % 20 != 0) {
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
        for (long key : wanted) {
            if (!this.forcedChunks.contains(key)) {
                level.setChunkForced((int) (key >> 32), (int) key, true);
            }
        }
        this.forcedChunks.clear();
        this.forcedChunks.addAll(wanted);
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
        if (!this.enabled || this.kit().isInfinite() || this.bot.getTarget() != null) {
            return false;
        }
        Player owner = this.bot.getOwner();
        if (!this.speedrun && owner != null && owner.distanceToSqr(this.bot) > 96.0 * 96.0) {
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
        if (this.speedrun && this.portalBuilt) {
            return "Etappe 1 geschafft: das Netherportal steht";
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
        if (diamondsNearby && !this.speedrun) {
            if (weaponDamage < Kit.attackDamage(new ItemStack(Items.DIAMOND_SWORD))) {
                needs.add(new Need(Items.DIAMOND_SWORD, "ein Diamantschwert"));
            }
            for (int i = 0; i < 4; i++) {
                if (Kit.armorValue(kit.bestArmor(ARMOR_SLOTS[i]), ARMOR_SLOTS[i]) < Kit.armorValue(new ItemStack(DIAMOND_ARMOR[i]), ARMOR_SLOTS[i])) {
                    needs.add(new Need(DIAMOND_ARMOR[i], "Diamantrüstung"));
                }
            }
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
        this.goalLabel = null;
        return null;
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
            return this.nearest(Ore.WATER) != null ? new FillWater() : new Explore("Wasser");
        }
        if (this.needPickaxe(Items.DIAMOND_PICKAXE, 0) != null) {
            this.goalLabel = "eine Diamantspitzhacke";
            Step s = this.resolveItem(Items.DIAMOND_PICKAXE, 0);
            return s != null ? s : this.deepStep();
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
                    : this.nearest(Ore.DIAMOND) != null ? new Mine(Ore.DIAMOND) : this.speedrun ? this.deepStep() : new Explore(Ore.DIAMOND.label);
            case OBSIDIAN -> this.nearest(Ore.OBSIDIAN) != null ? new Mine(Ore.OBSIDIAN) : this.deepStep();
            case FLINT -> this.nearest(Ore.GRAVEL) != null ? new Mine(Ore.GRAVEL) : this.speedrun ? this.deepStep() : new Explore(Ore.GRAVEL.label);
            case IRON -> this.smelt(Res.RAW_IRON, Res.IRON, count - this.kit().count(res.match), depth);
            case COOKED_MEAT -> this.smelt(Res.RAW_MEAT, Res.COOKED_MEAT, count - this.kit().count(res.match), depth);
            case RAW_MEAT -> new Hunt();
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
        this.scanTick(level);
        if (this.collectDrops()) {
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
            case Descend d -> this.doDig(level, true);
            case StripMine sm -> this.doDig(level, false);
            case FillWater fw -> this.doFillWater(level);
            case MakeObsidian mo -> this.doMakeObsidian(level);
            case BuildPortal bp -> this.doBuildPortal(level);
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
            if (food && e instanceof LivingEntity living && living.isAlive() && !living.isBaby() && this.bot.distanceToSqr(e) < best) {
                prey = living;
                best = this.bot.distanceToSqr(e);
            }
        }
        if (prey == null) {
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
            this.actionTicks = 0;
            double angle = this.bot.getRandom().nextDouble() * Math.PI * 2.0;
            Vec3 candidate = pos.add(Math.cos(angle) * 24.0, 0.0, Math.sin(angle) * 24.0);
            if (!this.speedrun && candidate.distanceTo(this.anchor) > 96.0) {
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
        this.bot.getNavigation().stop();
        BlockPos feet = this.bot.blockPosition();
        BlockPos front = feet.relative(this.digDir);
        List<BlockPos> toClear = new ArrayList<>();
        toClear.add(front.above());
        toClear.add(front);
        if (down) {
            toClear.add(front.below());
        }
        for (BlockPos p : toClear) {
            BlockState state = level.getBlockState(p);
            boolean danger = this.nearLava(level, p) || !level.getFluidState(p).isEmpty() || state.getDestroySpeed(level, p) < 0.0F;
            if (danger) {
                // Lava, water or bedrock ahead: take another direction.
                this.stopBreaking();
                this.digDir = this.digDir.getClockWise();
                this.bot.tellOwner("§7Gefahr voraus – ich grabe in eine andere Richtung.", false);
                return;
            }
            if (!state.getCollisionShape(level, p).isEmpty()) {
                this.breakBlock(level, p);
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
        this.bot.tellOwner("§5§lEtappe 1 geschafft: Das Netherportal steht! §7(" + fire.getX() + " " + fire.getY() + " " + fire.getZ() + ")", true);
        if (PvpBotEntity.DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   gather: PORTAL BUILT at {}", fire);
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
        Vec3 center = Vec3.atCenterOf(target);
        double dist = this.bot.getEyePosition().distanceTo(center);
        if (dist <= 4.5 && this.canSee(target)) {
            this.bot.getNavigation().stop();
            if (this.breakBlock(level, target)) {
                this.mineTarget = null;
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
            ItemStack tool = this.bot.getMainHandItem();
            boolean drops = !state.requiresCorrectToolForDrops() || !tool.isEmpty() && tool.isCorrectToolForDrops(state);
            level.destroyBlockProgress(this.bot.getId(), pos, -1);
            level.destroyBlock(pos, drops, this.bot, 512);
            if (!tool.isEmpty() && tool.isDamageableItem()) {
                tool.hurtAndBreak(1, this.bot, EquipmentSlot.MAINHAND);
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
            if (correct && speed > bestSpeed) {
                best = stack;
                bestSpeed = speed;
            }
        }
        return best;
    }

    // --- scanning & picking up

    private void scanTick(ServerLevel level) {
        BlockPos here = this.bot.blockPosition();
        if (this.scanCenter == null || this.scanLayer > 12) {
            if (this.scanCenter != null) {
                this.known.clear();
                this.known.putAll(this.scanning);
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
                        // Plain stone is everywhere: remember only exposed pieces.
                        if (list.size() < 64 && (ore != Ore.STONE || this.isExposed(p))) {
                            list.add(p);
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
            if (item.isAlive() && isUseful(item.getItem()) && this.bot.distanceToSqr(item) < best) {
                closest = item;
                best = this.bot.distanceToSqr(item);
            }
        }
        if (closest != null && best > 4.0) {
            this.bot.getNavigation().moveTo(closest, 1.1);
            return true;
        }
        return false;
    }

    // --- saving known state that matters

    static boolean isUseful(ItemStack stack) {
        for (Res res : Res.values()) {
            if (res.match.test(stack)) {
                return true;
            }
        }
        return Kit.classify(stack) != Role.OTHER || RECIPES.containsKey(stack.getItem()) || pickaxeTier(stack.getItem()) > 0;
    }
}
