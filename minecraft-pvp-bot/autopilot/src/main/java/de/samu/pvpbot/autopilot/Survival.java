package de.samu.pvpbot.autopilot;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EnumMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Predicate;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.tags.BlockTags;
import net.minecraft.tags.FluidTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.AbstractFurnaceMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.CraftingMenu;
import net.minecraft.world.inventory.InventoryMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

/**
 * Full control, when there is nobody to fight: the autopilot gears up on its own like a player -
 * wood, crafting table, wooden and stone tools, food, furnace, iron (smelted), iron tools, armor and
 * a shield, then diamonds. Everything goes through the normal controls: walking keys along an A*
 * path, holding "attack" on a block to mine it, and clicking slots in the inventory, the crafting
 * table and the furnace. It only knows blocks it has actually looked at (rays from its eyes).
 */
final class Survival {
    private final Autopilot ap;

    Survival(Autopilot ap) {
        this.ap = ap;
    }

    // ------------------------------------------------------------------ what it has seen

    enum Kind { LOG, STONE, COAL, IRON, DIAMOND, TABLE, FURNACE }

    private final Map<Kind, Set<BlockPos>> seen = new EnumMap<>(Kind.class);
    private final Set<Long> unreachable = new java.util.HashSet<>();

    private static @Nullable Kind kindOf(BlockState state) {
        if (state.is(BlockTags.LOGS)) return Kind.LOG;
        if (state.is(Blocks.COAL_ORE) || state.is(Blocks.DEEPSLATE_COAL_ORE)) return Kind.COAL;
        if (state.is(Blocks.IRON_ORE) || state.is(Blocks.DEEPSLATE_IRON_ORE)) return Kind.IRON;
        if (state.is(Blocks.DIAMOND_ORE) || state.is(Blocks.DEEPSLATE_DIAMOND_ORE)) return Kind.DIAMOND;
        if (state.is(Blocks.CRAFTING_TABLE)) return Kind.TABLE;
        if (state.is(Blocks.FURNACE)) return Kind.FURNACE;
        if (state.is(Blocks.STONE) || state.is(Blocks.COBBLESTONE) || state.is(Blocks.DEEPSLATE) || state.is(Blocks.COBBLED_DEEPSLATE)) return Kind.STONE;
        return null;
    }

    /** Looks around: rays from the eyes, the first block each ray hits is what it sees. */
    private void lookAround(Level level, LocalPlayer p, int tick) {
        if (tick % 20 != 0) {
            return;
        }
        Vec3 eye = p.getEyePosition();
        int offset = (tick / 20) % 2 * 5;
        for (int pitch = -70; pitch <= 40; pitch += 10) {
            for (int yaw = 0; yaw < 360; yaw += 10) {
                Vec3 dir = Vec3.directionFromRotation(pitch, yaw + offset);
                BlockHitResult hit = level.clip(new ClipContext(eye, eye.add(dir.scale(48.0)), ClipContext.Block.OUTLINE, ClipContext.Fluid.ANY, p));
                if (hit.getType() != HitResult.Type.BLOCK || !level.getFluidState(hit.getBlockPos()).isEmpty()) {
                    continue;
                }
                Kind kind = kindOf(level.getBlockState(hit.getBlockPos()));
                if (kind != null) {
                    Set<BlockPos> set = this.seen.computeIfAbsent(kind, k -> new LinkedHashSet<>());
                    if (set.size() < 300) {
                        set.add(hit.getBlockPos().immutable());
                    }
                }
            }
        }
    }

    private @Nullable BlockPos nearest(Level level, LocalPlayer p, Kind kind) {
        Set<BlockPos> set = this.seen.get(kind);
        if (set == null) {
            return null;
        }
        set.removeIf(pos -> level.isLoaded(pos) && kindOf(level.getBlockState(pos)) != kind);
        BlockPos best = null;
        double bestDist = Double.MAX_VALUE;
        for (BlockPos pos : set) {
            double d = pos.distSqr(p.blockPosition());
            if (d < bestDist && d < 96 * 96 && !this.unreachable.contains(pos.asLong())) {
                best = pos;
                bestDist = d;
            }
        }
        return best;
    }

    // ------------------------------------------------------------------ inventory

    private static final Predicate<ItemStack> LOG = st -> st.is(ItemTags.LOGS);
    private static final Predicate<ItemStack> PLANKS = st -> st.is(ItemTags.PLANKS);
    private static final Predicate<ItemStack> STICK = st -> st.is(Items.STICK);
    private static final Predicate<ItemStack> COBBLE = st -> st.is(Items.COBBLESTONE) || st.is(Items.COBBLED_DEEPSLATE) || st.is(Items.BLACKSTONE);
    private static final Predicate<ItemStack> IRON = st -> st.is(Items.IRON_INGOT);
    private static final Predicate<ItemStack> DIAMOND = st -> st.is(Items.DIAMOND);
    private static final Predicate<ItemStack> COAL = st -> st.is(Items.COAL) || st.is(Items.CHARCOAL);

    private static int count(LocalPlayer p, Predicate<ItemStack> match) {
        int n = 0;
        for (ItemStack st : p.getInventory().getNonEquipmentItems()) {
            if (match.test(st)) {
                n += st.getCount();
            }
        }
        return n;
    }

    private static boolean has(LocalPlayer p, Item item) {
        if (count(p, st -> st.is(item)) > 0) {
            return true;
        }
        for (net.minecraft.world.entity.EquipmentSlot slot : net.minecraft.world.entity.EquipmentSlot.values()) {
            if (p.getItemBySlot(slot).is(item)) {
                return true;
            }
        }
        return false;
    }

    private static int pickaxeTier(LocalPlayer p) {
        if (has(p, Items.NETHERITE_PICKAXE) || has(p, Items.DIAMOND_PICKAXE)) return 4;
        if (has(p, Items.IRON_PICKAXE)) return 3;
        if (has(p, Items.STONE_PICKAXE) || has(p, Items.COPPER_PICKAXE)) return 2;
        if (has(p, Items.WOODEN_PICKAXE) || has(p, Items.GOLDEN_PICKAXE)) return 1;
        return 0;
    }

    private static int swordTier(LocalPlayer p) {
        if (has(p, Items.NETHERITE_SWORD) || has(p, Items.DIAMOND_SWORD)) return 4;
        if (has(p, Items.IRON_SWORD)) return 3;
        if (has(p, Items.STONE_SWORD) || has(p, Items.COPPER_SWORD)) return 2;
        if (has(p, Items.WOODEN_SWORD) || has(p, Items.GOLDEN_SWORD)) return 1;
        return 0;
    }

    private static int foodCount(LocalPlayer p) {
        return count(p, st -> st.has(net.minecraft.core.component.DataComponents.FOOD) && !st.is(Items.ROTTEN_FLESH) && !st.is(Items.SPIDER_EYE));
    }

    // ------------------------------------------------------------------ recipes (shaped, row by row)

    private record Recipe(String name, Item output, boolean big, String[] rows, Map<Character, Predicate<ItemStack>> keys) {
    }

    private static Recipe recipe(String name, Item output, boolean big, String[] rows, Object... keys) {
        Map<Character, Predicate<ItemStack>> map = new java.util.HashMap<>();
        for (int i = 0; i < keys.length; i += 2) {
            @SuppressWarnings("unchecked")
            Predicate<ItemStack> match = (Predicate<ItemStack>) keys[i + 1];
            map.put((Character) keys[i], match);
        }
        return new Recipe(name, output, big, rows, map);
    }

    private static final Recipe R_PLANKS = recipe("Bretter", Items.OAK_PLANKS, false, new String[]{"L"}, 'L', LOG);
    private static final Recipe R_STICKS = recipe("Stöcke", Items.STICK, false, new String[]{"P", "P"}, 'P', PLANKS);
    private static final Recipe R_TABLE = recipe("Werkbank", Items.CRAFTING_TABLE, false, new String[]{"PP", "PP"}, 'P', PLANKS);
    private static final Recipe R_WOOD_PICK = recipe("Holzspitzhacke", Items.WOODEN_PICKAXE, true, new String[]{"PPP", " S ", " S "}, 'P', PLANKS, 'S', STICK);
    private static final Recipe R_STONE_PICK = recipe("Steinspitzhacke", Items.STONE_PICKAXE, true, new String[]{"CCC", " S ", " S "}, 'C', COBBLE, 'S', STICK);
    private static final Recipe R_STONE_SWORD = recipe("Steinschwert", Items.STONE_SWORD, true, new String[]{"C", "C", "S"}, 'C', COBBLE, 'S', STICK);
    private static final Recipe R_FURNACE = recipe("Ofen", Items.FURNACE, true, new String[]{"CCC", "C C", "CCC"}, 'C', COBBLE);
    private static final Recipe R_IRON_PICK = recipe("Eisenspitzhacke", Items.IRON_PICKAXE, true, new String[]{"III", " S ", " S "}, 'I', IRON, 'S', STICK);
    private static final Recipe R_IRON_SWORD = recipe("Eisenschwert", Items.IRON_SWORD, true, new String[]{"I", "I", "S"}, 'I', IRON, 'S', STICK);
    private static final Recipe R_SHIELD = recipe("Schild", Items.SHIELD, true, new String[]{"PIP", "PPP", " P "}, 'P', PLANKS, 'I', IRON);
    private static final Recipe R_IRON_HELMET = recipe("Eisenhelm", Items.IRON_HELMET, true, new String[]{"III", "I I"}, 'I', IRON);
    private static final Recipe R_IRON_CHEST = recipe("Eisenbrustpanzer", Items.IRON_CHESTPLATE, true, new String[]{"I I", "III", "III"}, 'I', IRON);
    private static final Recipe R_IRON_LEGS = recipe("Eisenhose", Items.IRON_LEGGINGS, true, new String[]{"III", "I I", "I I"}, 'I', IRON);
    private static final Recipe R_IRON_BOOTS = recipe("Eisenschuhe", Items.IRON_BOOTS, true, new String[]{"I I", "I I"}, 'I', IRON);
    private static final Recipe R_DIA_PICK = recipe("Diamantspitzhacke", Items.DIAMOND_PICKAXE, true, new String[]{"DDD", " S ", " S "}, 'D', DIAMOND, 'S', STICK);
    private static final Recipe R_DIA_SWORD = recipe("Diamantschwert", Items.DIAMOND_SWORD, true, new String[]{"D", "D", "S"}, 'D', DIAMOND, 'S', STICK);
    private static final Recipe R_DIA_HELMET = recipe("Diamanthelm", Items.DIAMOND_HELMET, true, new String[]{"DDD", "D D"}, 'D', DIAMOND);
    private static final Recipe R_DIA_CHEST = recipe("Diamantbrustpanzer", Items.DIAMOND_CHESTPLATE, true, new String[]{"D D", "DDD", "DDD"}, 'D', DIAMOND);
    private static final Recipe R_DIA_LEGS = recipe("Diamanthose", Items.DIAMOND_LEGGINGS, true, new String[]{"DDD", "D D", "D D"}, 'D', DIAMOND);
    private static final Recipe R_DIA_BOOTS = recipe("Diamantschuhe", Items.DIAMOND_BOOTS, true, new String[]{"D D", "D D"}, 'D', DIAMOND);

    private static int needed(Recipe r, char key) {
        int n = 0;
        for (String row : r.rows) {
            for (char c : row.toCharArray()) {
                if (c == key) {
                    n++;
                }
            }
        }
        return n;
    }

    private static boolean canCraft(LocalPlayer p, Recipe r) {
        for (Map.Entry<Character, Predicate<ItemStack>> e : r.keys.entrySet()) {
            if (count(p, e.getValue()) < needed(r, e.getKey())) {
                return false;
            }
        }
        return true;
    }

    // ------------------------------------------------------------------ main loop

    private String doing = "";
    private int tick;

    /** Returns true while it is busy with something (keys are set on the autopilot). */
    boolean tick(Minecraft mc, LocalPlayer p) {
        this.tick++;
        Level level = p.level();
        this.lookAround(level, p, this.tick);
        if (this.job != null) {
            return this.tickJob(mc, p);
        }
        if (p.isUnderWater() && p.getAirSupply() < p.getMaxAirSupply() / 2) {
            // Running out of air: straight up.
            this.say(p, "taucht auf");
            this.ap.lookAt(p, p.getYRot(), -60.0F, 30.0F);
            this.ap.kJump = true;
            this.ap.kForward = true;
            return true;
        }
        if (this.ap.collectLoot(mc, p)) {
            this.say(p, "sammelt Beute auf");
            return true;
        }
        return this.plan(mc, p, level);
    }

    boolean ownsScreen() {
        return this.job != null;
    }

    private final Deque<String> recentlySaid = new ArrayDeque<>();

    private void say(LocalPlayer p, String what) {
        if (!what.equals(this.doing)) {
            this.doing = what;
            // Log each new activity once (not every time two labels take turns in the same tick).
            if (!this.recentlySaid.contains(what)) {
                Autopilot.LOGGER.info("[AUTOPILOT] survival: {}", what);
                this.recentlySaid.addLast(what);
                if (this.recentlySaid.size() > 6) {
                    this.recentlySaid.removeFirst();
                }
            }
        }
        this.ap.status(p, "§6Ausrüstung §7– " + what);
    }

    private boolean plan(Minecraft mc, LocalPlayer p, Level level) {
        int pick = pickaxeTier(p);
        if (this.tick % 6000 == 0) {
            this.unreachable.clear(); // things change (and it may have died meanwhile)
        }
        // Food: nothing to eat and getting hungry -> hunt (from the surface), before anything else.
        int hunger = p.getFoodData().getFoodLevel();
        if (foodCount(p) == 0 && hunger <= 14) {
            if (this.hunt(mc, p, level)) {
                return true;
            }
            if (hunger <= 8) {
                if (p.getY() < 55 && !level.canSeeSky(p.blockPosition())) {
                    this.say(p, "hat Hunger – geht nach oben, Tiere suchen");
                    return this.digUp(mc, p, level);
                }
                return this.explore(mc, p, level, "sucht Tiere (Hunger)");
            }
        }
        // 1. Wooden pickaxe.
        if (pick == 0) {
            return this.makeWithTable(mc, p, level, R_WOOD_PICK, "eine Holzspitzhacke");
        }
        // 2. Stone pickaxe and sword.
        if (pick < 2) {
            return this.makeWithTable(mc, p, level, R_STONE_PICK, "eine Steinspitzhacke");
        }
        if (swordTier(p) < 2) {
            return this.makeWithTable(mc, p, level, R_STONE_SWORD, "ein Steinschwert");
        }
        // Before going underground: sticks and planks for the next tools, and a spare crafting table.
        if (p.getY() > 50 && foodCount(p) < 4 && this.hunt(mc, p, level)) {
            return true;
        }
        if (p.getY() > 50 && (count(p, STICK) < 6 || count(p, PLANKS) + count(p, LOG) * 4 < 12 || !has(p, Items.CRAFTING_TABLE))) {
            if (count(p, STICK) < 6 && count(p, PLANKS) >= 2) {
                return this.craft(mc, p, level, R_STICKS);
            }
            if (!has(p, Items.CRAFTING_TABLE) && count(p, PLANKS) >= 4) {
                return this.craft(mc, p, level, R_TABLE);
            }
            if (count(p, PLANKS) + count(p, LOG) * 4 < 12 || count(p, PLANKS) < 2) {
                return this.getPlanks(mc, p, level, count(p, PLANKS) + 4, "Holzvorrat für unter Tage");
            }
        }
        // 3. Food, when there is little and an animal is in sight.
        if (foodCount(p) < 4 && this.hunt(mc, p, level)) {
            return true;
        }
        // 4. Iron: pickaxe, sword, armor, shield.
        Recipe[] iron = {R_IRON_PICK, R_IRON_SWORD, R_IRON_CHEST, R_IRON_LEGS, R_IRON_HELMET, R_IRON_BOOTS, R_SHIELD};
        int ironNeeded = 0;
        Recipe nextIron = null;
        for (Recipe r : iron) {
            if (!this.gotBetter(p, r.output)) {
                ironNeeded += needed(r, 'I');
                if (nextIron == null) {
                    nextIron = r;
                }
            }
        }
        if (nextIron != null) {
            if (canCraft(p, nextIron)) {
                return this.makeWithTable(mc, p, level, nextIron, nextIron.name);
            }
            return this.getIron(mc, p, level, ironNeeded, nextIron);
        }
        // 5. Diamonds.
        Recipe[] dia = {R_DIA_PICK, R_DIA_SWORD, R_DIA_CHEST, R_DIA_LEGS, R_DIA_HELMET, R_DIA_BOOTS};
        int diaNeeded = 0;
        Recipe nextDia = null;
        for (Recipe r : dia) {
            if (!this.gotBetter(p, r.output)) {
                diaNeeded += needed(r, 'D');
                if (nextDia == null) {
                    nextDia = r;
                }
            }
        }
        if (nextDia != null) {
            if (canCraft(p, nextDia)) {
                return this.makeWithTable(mc, p, level, nextDia, nextDia.name);
            }
            if (count(p, STICK) < 2 && nextDia.keys.containsKey('S')) {
                return this.makeWithTable(mc, p, level, R_STICKS, "Stöcke");
            }
            this.say(p, "sucht Diamanten (" + count(p, DIAMOND) + "/" + diaNeeded + ")");
            return this.mineOre(mc, p, level, Kind.DIAMOND, -54);
        }
        this.doing = "";
        return false;
    }

    /** True if it already has this item or a better one of the same kind. */
    private boolean gotBetter(LocalPlayer p, Item item) {
        String name = net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(item).getPath();
        String kind = name.substring(name.indexOf('_') + 1);
        for (String material : new String[]{"iron", "diamond", "netherite"}) {
            if (name.startsWith("diamond") && material.equals("iron")) {
                continue;
            }
            Item better = net.minecraft.core.registries.BuiltInRegistries.ITEM.getValue(net.minecraft.resources.Identifier.withDefaultNamespace(material + "_" + kind));
            if (better != Items.AIR && has(p, better)) {
                return true;
            }
        }
        return item == Items.SHIELD && has(p, Items.SHIELD) || has(p, item);
    }

    // ------------------------------------------------------------------ crafting chain

    /**
     * Makes {@code r}: first the materials it can make from wood (planks, sticks), then a crafting
     * table if the recipe needs 3x3, then the item. Missing raw materials: wood from trees, cobble
     * from stone.
     */
    private boolean makeWithTable(Minecraft mc, LocalPlayer p, Level level, Recipe r, String label) {
        for (Map.Entry<Character, Predicate<ItemStack>> e : r.keys.entrySet()) {
            int want = needed(r, e.getKey());
            Predicate<ItemStack> key = e.getValue();
            if (count(p, key) >= want) {
                continue;
            }
            if (key == PLANKS) {
                return this.getPlanks(mc, p, level, want, label);
            }
            if (key == STICK) {
                if (count(p, PLANKS) < 2) {
                    return this.getPlanks(mc, p, level, 2, label);
                }
                return this.craft(mc, p, level, R_STICKS);
            }
            if (key == COBBLE) {
                this.say(p, "holt Stein für " + label + " (" + count(p, COBBLE) + "/" + want + ")");
                return this.mineStone(mc, p, level);
            }
            return false;
        }
        if (r.big && this.tableNear(level, p) == null && !has(p, Items.CRAFTING_TABLE)) {
            if (count(p, PLANKS) < 4 + needed(r, 'P')) {
                return this.getPlanks(mc, p, level, 4 + needed(r, 'P'), "eine Werkbank");
            }
            return this.craft(mc, p, level, R_TABLE);
        }
        this.say(p, "baut " + label);
        return this.craft(mc, p, level, r);
    }

    private boolean getPlanks(Minecraft mc, LocalPlayer p, Level level, int want, String label) {
        if (count(p, PLANKS) >= want) {
            return false;
        }
        if (count(p, LOG) > 0) {
            return this.craft(mc, p, level, R_PLANKS);
        }
        this.say(p, "fällt Bäume für " + label);
        BlockPos log = this.nearest(level, p, Kind.LOG);
        if (log == null && p.getY() < 50 && !level.canSeeSky(p.blockPosition())) {
            // Underground and no wood: climb back up (a staircase to the surface).
            return this.digUp(mc, p, level);
        }
        if (log == null) {
            return this.explore(mc, p, level, "sucht Bäume");
        }
        return this.mine(mc, p, level, log);
    }

    private @Nullable BlockPos tableNear(Level level, LocalPlayer p) {
        BlockPos t = this.nearest(level, p, Kind.TABLE);
        return t != null && t.distSqr(p.blockPosition()) < 24 * 24 ? t : null;
    }

    private @Nullable BlockPos furnaceNear(Level level, LocalPlayer p) {
        BlockPos f = this.nearest(level, p, Kind.FURNACE);
        return f != null && f.distSqr(p.blockPosition()) < 24 * 24 ? f : null;
    }

    /** Crafts one recipe: small ones in the inventory, big ones at a crafting table (placed if needed). */
    private boolean craft(Minecraft mc, LocalPlayer p, Level level, Recipe r) {
        if (!r.big) {
            this.startCraftJob(mc, p, r, null);
            return true;
        }
        BlockPos table = this.tableNear(level, p);
        if (table == null) {
            return this.place(mc, p, level, Items.CRAFTING_TABLE, "stellt eine Werkbank auf");
        }
        if (!this.reach(p, table)) {
            this.say(p, "geht zur Werkbank");
            return this.walkNear(mc, p, level, table);
        }
        this.startCraftJob(mc, p, r, table);
        return true;
    }

    /** Places a block from the inventory on free ground next to the player. */
    private int placeTries;

    private boolean place(Minecraft mc, LocalPlayer p, Level level, Item item, String what) {
        this.say(p, what);
        BlockPos feet = p.blockPosition();
        Direction[] dirs = {Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST};
        for (int k = 0; k < 8; k++) {
            // Two blocks away (never where the player itself stands), a different spot each try.
            int i = (k + this.placeTries) % 8;
            BlockPos spot = feet.relative(dirs[i % 4], 2).offset(i >= 4 ? dirs[(i + 1) % 4].getStepX() : 0, 0, i >= 4 ? dirs[(i + 1) % 4].getStepZ() : 0);
            if (!level.getBlockState(spot).canBeReplaced() || !level.getBlockState(spot.above()).canBeReplaced()
                    || !PathFinder.solidGround(level, spot.below()) || p.getBoundingBox().intersects(new AABB(spot))) {
                continue;
            }
            int index = this.indexOf(p, st -> st.is(item));
            int slot = this.ap.toHotbar(mc, p, index);
            if (slot < 0) {
                return false;
            }
            p.getInventory().setSelectedSlot(slot);
            BlockPos ground = spot.below();
            Vec3 face = Vec3.atCenterOf(ground).add(0.0, 0.5, 0.0);
            this.ap.face(p, face.subtract(p.getEyePosition()), 90.0F);
            if (this.placeWait++ < 4) {
                return true; // turn towards it first
            }
            this.placeWait = 0;
            this.placeTries++;
            mc.gameMode.useItemOn(p, InteractionHand.MAIN_HAND, new BlockHitResult(face, Direction.UP, ground, false));
            Kind kind = item == Items.CRAFTING_TABLE ? Kind.TABLE : Kind.FURNACE;
            this.seen.computeIfAbsent(kind, key -> new LinkedHashSet<>()).add(spot);
            return true;
        }
        // No free spot around: step somewhere else.
        this.placeTries++;
        return this.explore(mc, p, level, what);
    }

    private int placeWait;

    private int indexOf(LocalPlayer p, Predicate<ItemStack> match) {
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        for (int i = 0; i < items.size(); i++) {
            if (match.test(items.get(i))) {
                return i;
            }
        }
        return -1;
    }

    // ------------------------------------------------------------------ container jobs (real clicks)

    private record Click(int slot, int button, ContainerInput input) {
    }

    private static final class Job {
        final String name;
        final @Nullable BlockPos block;
        final Predicate<AbstractContainerMenu> menuOk;
        final java.util.function.Function<AbstractContainerMenu, List<Click>> plan;
        Deque<Click> clicks;
        int waited;
        int after;

        Job(String name, @Nullable BlockPos block, Predicate<AbstractContainerMenu> menuOk,
                java.util.function.Function<AbstractContainerMenu, List<Click>> plan) {
            this.name = name;
            this.block = block;
            this.menuOk = menuOk;
            this.plan = plan;
        }
    }

    private @Nullable Job job;

    private void startCraftJob(Minecraft mc, LocalPlayer p, Recipe r, @Nullable BlockPos table) {
        this.say(p, "craftet " + r.name);
        this.job = new Job(r.name, table, table == null ? m -> m instanceof InventoryMenu : m -> m instanceof CraftingMenu,
                menu -> this.craftClicks(menu, r));
        if (table == null) {
            // The 2x2 grid of the inventory is always there.
            this.job.clicks = null;
        }
    }

    /** The clicks for one craft: each ingredient onto its grid slots, take the result, clear the grid. */
    private List<Click> craftClicks(AbstractContainerMenu menu, Recipe r) {
        List<Click> clicks = new ArrayList<>();
        int width = menu instanceof CraftingMenu ? 3 : 2;
        List<Integer> used = new ArrayList<>();
        for (Map.Entry<Character, Predicate<ItemStack>> e : r.keys.entrySet()) {
            List<Integer> grid = new ArrayList<>();
            for (int row = 0; row < r.rows.length; row++) {
                String line = r.rows[row];
                for (int col = 0; col < line.length(); col++) {
                    if (line.charAt(col) == e.getKey()) {
                        grid.add(1 + row * width + col);
                    }
                }
            }
            int placed = 0;
            for (Slot slot : menu.slots) {
                if (placed >= grid.size()) {
                    break;
                }
                if (!(slot.container instanceof Inventory) || !e.getValue().test(slot.getItem())) {
                    continue;
                }
                clicks.add(new Click(slot.index, 0, ContainerInput.PICKUP));
                int take = Math.min(slot.getItem().getCount(), grid.size() - placed);
                for (int i = 0; i < take; i++) {
                    clicks.add(new Click(grid.get(placed++), 1, ContainerInput.PICKUP));
                }
                clicks.add(new Click(slot.index, 0, ContainerInput.PICKUP));
            }
            used.addAll(grid);
        }
        clicks.add(new Click(0, 0, ContainerInput.QUICK_MOVE));
        for (int g : used) {
            clicks.add(new Click(g, 0, ContainerInput.QUICK_MOVE));
        }
        return clicks;
    }

    private boolean tickJob(Minecraft mc, LocalPlayer p) {
        Job j = this.job;
        this.say(p, j.name);
        AbstractContainerMenu menu = p.containerMenu;
        if (j.block != null && !j.menuOk.test(menu)) {
            // Open the table or furnace: look at it and right-click.
            if (j.waited++ == 0 || j.waited % 20 == 0) {
                Vec3 c = Vec3.atCenterOf(j.block);
                this.ap.face(p, c.subtract(p.getEyePosition()), 90.0F);
                mc.gameMode.useItemOn(p, InteractionHand.MAIN_HAND, new BlockHitResult(c, Direction.UP, j.block, false));
            }
            if (j.waited > 80) {
                Autopilot.LOGGER.info("[AUTOPILOT] survival: could not open {} at {}", j.name, j.block);
                this.job = null;
            }
            return true;
        }
        if (j.block == null) {
            menu = p.inventoryMenu;
        }
        if (j.clicks == null) {
            j.clicks = new ArrayDeque<>(j.plan.apply(menu));
        }
        if (!j.clicks.isEmpty()) {
            Click c = j.clicks.poll();
            mc.gameMode.handleContainerInput(menu.containerId, c.slot, c.button, c.input, p);
            return true;
        }
        if (++j.after < 3) {
            return true;
        }
        if (j.block != null) {
            p.closeContainer();
        }
        this.job = null;
        return true;
    }

    // ------------------------------------------------------------------ iron and smelting

    private int smeltUntil;
    private int smeltingCount;

    private boolean getIron(Minecraft mc, LocalPlayer p, Level level, int ironNeeded, Recipe next) {
        if (next.keys.containsKey('S') && count(p, STICK) < 2) {
            return this.makeWithTable(mc, p, level, R_STICKS, "Stöcke");
        }
        if (next == R_SHIELD && count(p, PLANKS) < 6) {
            return this.getPlanks(mc, p, level, 6, "einen Schild");
        }
        int ingots = count(p, IRON);
        int raw = count(p, st -> st.is(Items.RAW_IRON));
        // Waiting for the furnace.
        if (this.smeltingCount > 0) {
            BlockPos furnace = this.furnaceNear(level, p);
            if (furnace == null) {
                this.smeltingCount = 0;
                return false;
            }
            if (this.tick < this.smeltUntil) {
                this.say(p, "wartet am Ofen (" + this.smeltingCount + " Eisen)");
                if (!this.reach(p, furnace)) {
                    return this.walkNear(mc, p, level, furnace);
                }
                return true;
            }
            if (!this.reach(p, furnace)) {
                return this.walkNear(mc, p, level, furnace);
            }
            this.smeltingCount = 0;
            this.job = new Job("nimmt das Eisen aus dem Ofen", furnace, m -> m instanceof AbstractFurnaceMenu,
                    menu -> List.of(new Click(2, 0, ContainerInput.QUICK_MOVE)));
            return true;
        }
        if (ingots + raw >= needed(next, 'I') && raw > 0 || ingots + raw >= ironNeeded && raw > 0) {
            return this.smelt(mc, p, level, raw);
        }
        this.say(p, "sucht Eisen (" + (ingots + raw) + "/" + ironNeeded + ")");
        return this.mineOre(mc, p, level, Kind.IRON, 16);
    }

    private boolean smelt(Minecraft mc, LocalPlayer p, Level level, int raw) {
        int coal = count(p, COAL);
        int woodFuel = count(p, PLANKS) + count(p, LOG);
        if (coal * 8 < raw && woodFuel * 3 / 2 < raw) {
            BlockPos coalOre = this.nearest(level, p, Kind.COAL);
            if (coalOre != null) {
                this.say(p, "holt Kohle");
                return this.mine(mc, p, level, coalOre);
            }
            return this.getPlanks(mc, p, level, raw * 2 / 3 + 1, "Brennstoff");
        }
        BlockPos furnace = this.furnaceNear(level, p);
        if (furnace == null) {
            if (has(p, Items.FURNACE)) {
                return this.place(mc, p, level, Items.FURNACE, "stellt einen Ofen auf");
            }
            return this.makeWithTable(mc, p, level, R_FURNACE, "einen Ofen");
        }
        if (!this.reach(p, furnace)) {
            this.say(p, "geht zum Ofen");
            return this.walkNear(mc, p, level, furnace);
        }
        this.smeltingCount = raw;
        this.smeltUntil = this.tick + raw * 200 + 60;
        boolean useCoal = coal * 8 >= raw;
        this.job = new Job("legt " + raw + " Roheisen in den Ofen", furnace, m -> m instanceof AbstractFurnaceMenu, menu -> {
            List<Click> clicks = new ArrayList<>();
            this.moveInto(menu, clicks, st -> st.is(Items.RAW_IRON), 0);
            this.moveInto(menu, clicks, useCoal ? COAL : PLANKS.or(LOG), 1);
            return clicks;
        });
        return true;
    }

    /** Picks up the first matching stack and puts all of it into the given container slot. */
    private void moveInto(AbstractContainerMenu menu, List<Click> clicks, Predicate<ItemStack> match, int target) {
        for (Slot slot : menu.slots) {
            if (slot.container instanceof Inventory && match.test(slot.getItem())) {
                clicks.add(new Click(slot.index, 0, ContainerInput.PICKUP));
                clicks.add(new Click(target, 0, ContainerInput.PICKUP));
                clicks.add(new Click(slot.index, 0, ContainerInput.PICKUP));
                return;
            }
        }
    }

    // ------------------------------------------------------------------ mining

    private boolean mineStone(Minecraft mc, LocalPlayer p, Level level) {
        BlockPos stone = this.nearest(level, p, Kind.STONE);
        if (stone != null && stone.distSqr(p.blockPosition()) < 32 * 32) {
            return this.mine(mc, p, level, stone);
        }
        // No stone in sight: dig down a staircase until there is.
        return this.digStairs(mc, p, level, true);
    }

    private boolean mineOre(Minecraft mc, LocalPlayer p, Level level, Kind kind, int depth) {
        BlockPos ore = this.nearest(level, p, kind);
        if (ore != null) {
            return this.mine(mc, p, level, ore);
        }
        if (kind == Kind.DIAMOND && pickaxeTier(p) < 3) {
            return false;
        }
        // Down to the right depth, then a straight tunnel (turning away from lava).
        return this.digStairs(mc, p, level, p.getY() > depth);
    }

    private @Nullable BlockPos breaking;
    private @Nullable BlockPos mineTarget;
    private int mineTicks;

    /** Walks into reach of the block and holds "attack" on it until it breaks. */
    private boolean mine(Minecraft mc, LocalPlayer p, Level level, BlockPos pos) {
        if (level.getBlockState(pos).isAir()) {
            this.breaking = null;
            return false;
        }
        // The same block for 10 seconds and still there: give up on it, take another one.
        if (!pos.equals(this.mineTarget)) {
            this.mineTarget = pos;
            this.mineTicks = 0;
        }
        if (++this.mineTicks > 200) {
            HitResult h = mc.hitResult;
            Autopilot.LOGGER.info("[AUTOPILOT] survival: gives up mining {} ({}) - reach={} aim={} {} path={}", pos.toShortString(),
                    level.getBlockState(pos).getBlock(), this.reach(p, pos), h == null ? "-" : h.getType(),
                    h instanceof BlockHitResult bh ? bh.getBlockPos().toShortString() + " " + level.getBlockState(bh.getBlockPos()).getBlock() : "",
                    this.path == null ? "-" : this.pathIndex + "/" + this.path.size());
            this.unreachable.add(pos.asLong());
            this.mineTarget = null;
            this.path = null;
            return false;
        }
        if (!this.reach(p, pos)) {
            return this.walkNear(mc, p, level, pos);
        }
        this.selectTool(mc, p, level.getBlockState(pos));
        Vec3 c = Vec3.atCenterOf(pos);
        this.ap.face(p, c.subtract(p.getEyePosition()), 30.0F);
        if (mc.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
            // What the game does every tick while left-click is held on a block (holding the key
            // alone only mines while the window has mouse focus).
            this.ap.kAttack = true;
            if (!p.isUsingItem()) {
                mc.gameMode.continueDestroyBlock(hit.getBlockPos(), hit.getDirection());
            }
            if (!hit.getBlockPos().equals(pos) && ++this.blockedTicks > 60) {
                // Something else is in the way and it keeps hitting that: fine, mine that first.
                this.blockedTicks = 0;
            }
        }
        this.breaking = pos;
        return true;
    }

    private int blockedTicks;

    private boolean reach(LocalPlayer p, BlockPos pos) {
        return p.getEyePosition().distanceTo(Vec3.atCenterOf(pos)) < 4.2;
    }

    private void selectTool(Minecraft mc, LocalPlayer p, BlockState state) {
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        int best = -1;
        float bestSpeed = 1.0F;
        for (int i = 0; i < items.size(); i++) {
            ItemStack st = items.get(i);
            float speed = st.getDestroySpeed(state);
            if (speed > bestSpeed && (!state.requiresCorrectToolForDrops() || st.isCorrectToolForDrops(state))) {
                best = i;
                bestSpeed = speed;
            }
        }
        if (best >= 0) {
            int slot = this.ap.toHotbar(mc, p, best);
            if (slot >= 0) {
                p.getInventory().setSelectedSlot(slot);
            }
        }
    }

    private Direction digDir = Direction.NORTH;
    private @Nullable BlockPos stairStep;

    /**
     * Staircase down ({@code down}) or a straight 2-high tunnel. Each step is one block forward
     * (and one down): clear the blocks the body passes through (top first), then walk onto the step.
     * Turns away from lava, water and bedrock.
     */
    private boolean digStairs(Minecraft mc, LocalPlayer p, Level level, boolean down) {
        BlockPos feet = BlockPos.containing(p.getX(), p.getY() + 0.2, p.getZ());
        if (this.stairStep == null || feet.equals(this.stairStep) || feet.distManhattan(this.stairStep) > 3) {
            if (this.stairStep == null || feet.distManhattan(this.stairStep) > 3) {
                this.digDir = p.getDirection();
            }
            this.stairStep = down ? feet.relative(this.digDir).below() : feet.relative(this.digDir);
        }
        BlockPos step = this.stairStep;
        BlockPos[] clear = {step.above(2), step.above(), step};
        for (BlockPos b : clear) {
            if (!level.getFluidState(b).isEmpty() || PathFinder.nearLava(level, b) || level.getBlockState(b).getDestroySpeed(level, b) < 0.0F) {
                this.digDir = p.getRandom().nextBoolean() ? this.digDir.getClockWise() : this.digDir.getCounterClockWise();
                this.stairStep = null;
                return true;
            }
        }
        if (down && !PathFinder.solidGround(level, step.below()) && !PathFinder.body(level, step.below())) {
            // A hole or cave under the step: fine, the walk drops into it.
            this.stairStep = null;
        }
        this.say(p, down ? "gräbt eine Treppe nach unten (y " + feet.getY() + ")" : "gräbt einen Tunnel");
        for (BlockPos b : clear) {
            if (!PathFinder.body(level, b)) {
                return this.mine(mc, p, level, b);
            }
        }
        if (this.stairStep != null && down && !PathFinder.solidGround(level, step.below())) {
            // Would fall more than one block: make sure it is not a deep drop.
            int depth = 0;
            while (depth < 5 && PathFinder.body(level, step.below(depth + 1))) {
                depth++;
            }
            if (depth >= 4) {
                this.digDir = this.digDir.getClockWise();
                this.stairStep = null;
                return true;
            }
        }
        Vec3 c = Vec3.atBottomCenterOf(step);
        this.ap.face(p, c.subtract(p.getEyePosition()).multiply(1.0, 0.0, 1.0), 30.0F);
        this.ap.kForward = true;
        return true;
    }

    /** Staircase up: clear head room, the step ahead and the space above it, then jump onto it. */
    private boolean digUp(Minecraft mc, LocalPlayer p, Level level) {
        this.say(p, "gräbt sich nach oben (y " + p.getBlockY() + ")");
        BlockPos feet = BlockPos.containing(p.getX(), p.getY() + 0.2, p.getZ());
        Direction d = p.getDirection();
        BlockPos step = feet.relative(d).above();
        for (BlockPos b : new BlockPos[]{feet.above(2), step.above(2), step.above()}) {
            if (!level.getFluidState(b).isEmpty() || PathFinder.nearLava(level, b)) {
                this.ap.lookAt(p, p.getYRot() + 90.0F, 0.0F, 90.0F);
                return true;
            }
            if (!PathFinder.body(level, b)) {
                return this.mine(mc, p, level, b);
            }
        }
        if (PathFinder.body(level, step)) {
            // Nothing to stand on: the step is air, just walk forward.
            this.ap.kForward = true;
            return true;
        }
        this.ap.face(p, Vec3.atCenterOf(step).subtract(p.getEyePosition()).multiply(1.0, 0.0, 1.0), 30.0F);
        this.ap.kForward = true;
        this.ap.kJump = p.onGround();
        return true;
    }

    // ------------------------------------------------------------------ food

    private boolean hunt(Minecraft mc, LocalPlayer p, Level level) {
        LivingEntity best = null;
        double bestDist = 48.0 * 48.0;
        for (Entity e : level.getEntities(p, new AABB(p.blockPosition()).inflate(48.0))) {
            if (e instanceof LivingEntity animal && animal.isAlive() && !animal.isBaby() && p.hasLineOfSight(animal)
                    && (e.getType() == net.minecraft.world.entity.EntityTypes.COW || e.getType() == net.minecraft.world.entity.EntityTypes.PIG
                    || e.getType() == net.minecraft.world.entity.EntityTypes.SHEEP || e.getType() == net.minecraft.world.entity.EntityTypes.CHICKEN)
                    && p.distanceToSqr(e) < bestDist) {
                best = animal;
                bestDist = p.distanceToSqr(e);
            }
        }
        if (best == null) {
            return false;
        }
        this.say(p, "jagt " + best.getName().getString() + " (Essen)");
        if (p.distanceTo(best) > 2.8) {
            return this.walkNear(mc, p, level, best.blockPosition());
        }
        this.ap.attack(mc, p, best);
        return true;
    }

    // ------------------------------------------------------------------ walking

    private @Nullable List<BlockPos> path;
    private int pathIndex;
    private @Nullable BlockPos pathGoal;
    private int pathAge;
    private @Nullable Vec3 lastPos;
    private int stillTicks;

    /** Walks until the block is in reach. */
    private boolean walkNear(Minecraft mc, LocalPlayer p, Level level, BlockPos target) {
        Vec3 c = Vec3.atCenterOf(target);
        return this.walk(mc, p, level, target, feet -> Vec3.atBottomCenterOf(feet).add(0.0, 1.62, 0.0).distanceTo(c) < 4.0);
    }

    private boolean walk(Minecraft mc, LocalPlayer p, Level level, BlockPos goal, Predicate<BlockPos> arrived) {
        BlockPos feet = BlockPos.containing(p.getX(), p.getY() + 0.2, p.getZ());
        this.pathAge++;
        // Stuck? (not moving while trying to)
        if (this.lastPos != null && p.position().distanceToSqr(this.lastPos) < 0.0025) {
            this.stillTicks++;
        } else {
            this.stillTicks = 0;
        }
        this.lastPos = p.position();
        boolean replan = this.path == null || !goal.equals(this.pathGoal) || this.pathIndex >= this.path.size()
                || this.stillTicks > 40 || this.pathAge > 400;
        if (!replan && this.pathIndex < this.path.size()) {
            BlockPos next = this.path.get(this.pathIndex);
            if (next.distSqr(feet) > 9) {
                replan = true; // knocked off the path
            }
        }
        if (replan) {
            if (this.stillTicks > 40) {
                Autopilot.LOGGER.info("[AUTOPILOT] survival: stuck at {} -> new path", feet.toShortString());
            }
            this.path = PathFinder.find(level, feet, goal, arrived, 8000, true);
            this.pathGoal = goal;
            this.pathIndex = 0;
            this.pathAge = 0;
            this.stillTicks = 0;
            if (this.path == null || this.path.isEmpty()) {
                if (++this.failures > 3) {
                    this.unreachable.add(goal.asLong());
                    this.failures = 0;
                    Autopilot.LOGGER.info("[AUTOPILOT] survival: gives up on {}", goal.toShortString());
                }
                this.path = null;
                if (this.exploring) {
                    return false;
                }
                return this.explore(mc, p, level, "sucht einen Weg");
            }
            this.failures = 0;
        }
        BlockPos next = this.path.get(this.pathIndex);
        Vec3 c = Vec3.atBottomCenterOf(next);
        double h = Math.hypot(c.x - p.getX(), c.z - p.getZ());
        if (h < 0.4 && Math.abs(p.getY() - next.getY()) < 0.8) {
            this.pathIndex++;
            if (this.pathIndex >= this.path.size()) {
                return true;
            }
            next = this.path.get(this.pathIndex);
            c = Vec3.atBottomCenterOf(next);
        }
        // Blocks in the way of this step (a dig step, or head room for a step up): mine them.
        List<BlockPos> inWay = new ArrayList<>();
        inWay.add(next.above());
        inWay.add(next);
        if (next.getY() > feet.getY()) {
            inWay.add(0, feet.above(2));
        }
        // Keep digging the block already started (switching between two blocks resets the progress).
        if (this.wayBlock != null && !PathFinder.body(level, this.wayBlock) && this.reach(p, this.wayBlock)) {
            return this.mine(mc, p, level, this.wayBlock);
        }
        this.wayBlock = null;
        for (BlockPos b : inWay) {
            if (!PathFinder.body(level, b) && level.getFluidState(b).isEmpty()) {
                this.wayBlock = b;
                return this.mine(mc, p, level, b);
            }
        }
        this.ap.face(p, c.subtract(p.getEyePosition()).multiply(1.0, 0.0, 1.0), 25.0F);
        float yawToNext = (float) (Math.atan2(c.z - p.getZ(), c.x - p.getX()) * 180.0 / Math.PI) - 90.0F;
        boolean facing = Math.abs(net.minecraft.util.Mth.wrapDegrees(yawToNext - p.getYRot())) < 35.0F;
        this.ap.kForward = facing;
        this.ap.kSprint = facing && this.path.size() - this.pathIndex > 4 && p.getFoodData().getFoodLevel() > 6;
        if (p.onGround() && (next.getY() > feet.getY() || p.horizontalCollision) || p.isInWater()) {
            this.ap.kJump = true;
        }
        return true;
    }

    private int failures;
    private @Nullable BlockPos wayBlock;
    private float exploreYaw = Float.NaN;
    private int exploreTicks;

    /** Nothing useful in sight: walk somewhere new (a few dozen blocks in one direction). */
    private boolean explore(Minecraft mc, LocalPlayer p, Level level, String what) {
        this.say(p, what);
        if (Float.isNaN(this.exploreYaw) || --this.exploreTicks <= 0 || this.stillTicks > 60) {
            this.exploreYaw = Float.isNaN(this.exploreYaw) ? p.getYRot() : this.exploreYaw + 60.0F + p.getRandom().nextFloat() * 240.0F;
            this.exploreTicks = 400;
            this.stillTicks = 0;
        }
        Vec3 dir = Vec3.directionFromRotation(0.0F, this.exploreYaw);
        BlockPos far = BlockPos.containing(p.position().add(dir.scale(24.0)));
        int y = level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, far.getX(), far.getZ());
        BlockPos goal = new BlockPos(far.getX(), y, far.getZ());
        if (this.path == null || this.pathGoal == null || this.pathGoal.distSqr(goal) > 16 * 16) {
            this.path = PathFinder.find(level, p.blockPosition(), goal, pos -> pos.distSqr(goal) < 9, 4000, false);
            this.pathGoal = goal;
            this.pathIndex = 0;
            if (this.path == null || this.path.isEmpty()) {
                this.exploreTicks = 0;
                this.path = null;
                this.ap.kForward = true;
                this.ap.kJump = p.horizontalCollision;
                return true;
            }
        }
        this.exploring = true;
        try {
            if (!this.walk(mc, p, level, this.pathGoal, pos -> pos.distSqr(goal) < 9)) {
                this.exploreTicks = 0;
            }
        } finally {
            this.exploring = false;
        }
        return true;
    }

    private boolean exploring;
}
