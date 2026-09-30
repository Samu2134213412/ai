package de.samu.pvpbot;

import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.function.Supplier;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/**
 * Training course: the traps the bot got stuck in (or died in) during full runs, built as hard tests
 * in the flat test world. Each has a start kit, a start spot and a goal; the bot plays through as
 * usual (speedrun mode) and has to get past the trap on its own. Only the test world is built on -
 * never a world the bot plays in.
 */
final class Parcours {
    /** One course: where it is (x offset, z is always {@link #Z}), how the bot starts, what counts as done. */
    record Course(String name, int x, int dy, int timeout, Supplier<List<ItemStack>> kit, Predicate<PvpBotEntity> goal,
                  Builder build) {
    }

    interface Builder {
        void build(ServerLevel level, BlockPos c);
    }

    static final int Z = 64;
    static final Map<String, Course> COURSES = new LinkedHashMap<>();
    /** Damage the course forbids (lava, fire, falls) - counted by the self test. */
    static int lavaHits;
    static int fallHits;

    private static BlockPos base;

    private Parcours() {
    }

    static {
        add(new Course("Parcours 1: Grube (6 tief, 1 breit)", -90, 0, 3000,
                () -> List.of(new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.OAK_PLANKS, 8)),
                bot -> bot.getY() >= base.getY() + 7, Parcours::pit));
        add(new Course("Parcours 2: im Berg eingeschlossen", -55, 0, 6000,
                () -> List.of(new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.OAK_PLANKS, 8)),
                bot -> bot.level().canSeeSky(bot.blockPosition().above()), Parcours::mountain));
        add(new Course("Parcours 3: Insel im See, Holz am Ufer", -10, 4, 6000,
                List::of,
                bot -> bot.getKit().count(s -> s.is(net.minecraft.tags.ItemTags.LOGS) || s.is(net.minecraft.tags.ItemTags.PLANKS)) > 0,
                Parcours::island));
        add(new Course("Parcours 4: Eisen neben Lava", 30, 0, 3000,
                () -> List.of(new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.STONE_SWORD), new ItemStack(Items.STICK, 4),
                        new ItemStack(Items.OAK_PLANKS, 8), new ItemStack(Items.CRAFTING_TABLE)),
                bot -> bot.getKit().count(s -> s.is(Items.RAW_IRON) || s.is(Items.IRON_INGOT)) > 0, Parcours::lavaIron));
        add(new Course("Parcours 5: gefluteter Stollen", 60, 1, 4000,
                () -> List.of(new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.COBBLESTONE, 16), new ItemStack(Items.OAK_PLANKS, 8)),
                bot -> bot.level().canSeeSky(bot.blockPosition().above()) && !bot.isInWater(), Parcours::flooded));
        add(new Course("Parcours 6: Holz ohne Werkzeug im Fels", 90, 0, 9000,
                List::of,
                bot -> bot.getKit().count(s -> s.is(net.minecraft.tags.ItemTags.LOGS) || s.is(net.minecraft.tags.ItemTags.PLANKS)) > 0,
                Parcours::rockNoTools));
        add(new Course("Parcours 7: Hoehlensturz (Treppe runter)", 125, 20, 5000,
                () -> List.of(new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.STONE_PICKAXE), new ItemStack(Items.STONE_SWORD),
                        new ItemStack(Items.STICK, 8), new ItemStack(Items.OAK_PLANKS, 16), new ItemStack(Items.COOKED_BEEF, 8)),
                bot -> bot.getY() <= base.getY() + 2, Parcours::caveTower));
    }

    private static void add(Course c) {
        COURSES.put(c.name(), c);
    }

    /** Builds every course (flat test world, next to the other test areas). */
    static void buildAll(ServerLevel level, BlockPos origin) {
        base = origin;
        for (Course c : COURSES.values()) {
            BlockPos at = new BlockPos(origin.getX() + c.x(), origin.getY(), Z);
            for (int cx = (at.getX() - 16) >> 4; cx <= (at.getX() + 16) >> 4; cx++) {
                for (int cz = (Z - 16) >> 4; cz <= (Z + 16) >> 4; cz++) {
                    level.setChunkForced(cx, cz, true);
                }
            }
            c.build().build(level, at);
        }
    }

    static BlockPos start(Course c) {
        return new BlockPos(base.getX() + c.x(), base.getY() + c.dy(), Z);
    }

    // ------------------------------------------------------------------ builders

    private static void box(ServerLevel level, BlockPos from, BlockPos to, BlockState state) {
        for (BlockPos p : BlockPos.betweenClosed(from, to)) {
            level.setBlock(p, state, 2);
        }
    }

    private static void tree(ServerLevel level, BlockPos foot) {
        box(level, foot, foot.above(4), Blocks.OAK_LOG.defaultBlockState());
        box(level, foot.offset(-1, 4, -1), foot.offset(1, 5, 1), Blocks.OAK_LEAVES.defaultBlockState());
        level.setBlock(foot.above(4), Blocks.OAK_LOG.defaultBlockState(), 2);
    }

    /** A 1x1 shaft 6 deep in a 7x7 stone block: out on top (no ladder, no stairs). */
    private static void pit(ServerLevel level, BlockPos c) {
        BlockState stone = Blocks.STONE.defaultBlockState();
        box(level, c.offset(-3, 0, -3), c.offset(3, 6, 3), stone);
        box(level, c, c.above(6), Blocks.AIR.defaultBlockState());
        tree(level, c.offset(8, 0, 0));
    }

    /** A 21x21x16 stone block with a 1x2 hollow in the middle at the bottom: dig out (the flank is nearer than the top). */
    private static void mountain(ServerLevel level, BlockPos c) {
        box(level, c.offset(-10, 0, -10), c.offset(10, 15, 10), Blocks.STONE.defaultBlockState());
        box(level, c, c.above(), Blocks.AIR.defaultBlockState());
        tree(level, c.offset(14, 0, 0));
    }

    /** A walled lake (3 deep) with a small island in the middle; trees only on the shore outside. */
    private static void island(ServerLevel level, BlockPos c) {
        BlockState stone = Blocks.STONE.defaultBlockState();
        box(level, c.offset(-12, 0, -12), c.offset(12, 3, 12), stone);             // floor + rim
        box(level, c.offset(-11, 1, -11), c.offset(11, 3, 11), Blocks.WATER.defaultBlockState());
        box(level, c.offset(-1, 1, -1), c.offset(1, 3, 1), Blocks.DIRT.defaultBlockState()); // the island
        level.setBlock(c.offset(0, 3, 0), Blocks.GRASS_BLOCK.defaultBlockState(), 2);
        tree(level, c.offset(16, 0, 3));
        tree(level, c.offset(-16, 0, -4));
    }

    /** Iron ore at the edge of a lava pool, and more iron a few blocks away in safe rock. */
    private static void lavaIron(ServerLevel level, BlockPos c) {
        BlockState stone = Blocks.STONE.defaultBlockState();
        box(level, c.offset(-8, -1, -6), c.offset(8, -1, 6), stone);
        box(level, c.offset(3, -1, -2), c.offset(6, -1, 2), Blocks.LAVA.defaultBlockState());
        box(level, c.offset(2, -2, -3), c.offset(7, -2, 3), stone);
        level.setBlock(c.offset(2, 0, 0), Blocks.IRON_ORE.defaultBlockState(), 2); // right next to the lava
        level.setBlock(c.offset(-7, 0, 4), Blocks.IRON_ORE.defaultBlockState(), 2); // the safe one
        level.setBlock(c.offset(-7, 1, 4), Blocks.STONE.defaultBlockState(), 2);
    }

    /** A stone block with a tunnel inside; a water source over its end floods it. Out into the open. */
    private static void flooded(ServerLevel level, BlockPos c) {
        box(level, c.offset(-6, 0, -6), c.offset(6, 9, 6), Blocks.STONE.defaultBlockState());
        box(level, c.offset(-4, 1, 0), c.offset(4, 2, 0), Blocks.AIR.defaultBlockState());
        level.setBlock(c.offset(4, 3, 0), Blocks.WATER.defaultBlockState(), 3);
        level.setBlock(c.offset(-4, 3, 0), Blocks.WATER.defaultBlockState(), 3);
    }

    /** Shut in rock with empty hands; trees outside. Out by hand (slow) and get wood. */
    private static void rockNoTools(ServerLevel level, BlockPos c) {
        box(level, c.offset(-4, 0, -4), c.offset(4, 6, 4), Blocks.STONE.defaultBlockState());
        box(level, c, c.above(), Blocks.AIR.defaultBlockState());
        tree(level, c.offset(7, 0, 2));
        tree(level, c.offset(-7, 0, -2));
    }

    /** A 9x9 stone tower, 20 high, with a hidden 5x5x6 hollow half-way down: dig down without falling in. */
    private static void caveTower(ServerLevel level, BlockPos c) {
        box(level, c.offset(-4, 0, -4), c.offset(4, 19, 4), Blocks.STONE.defaultBlockState());
        box(level, c.offset(-2, 5, -2), c.offset(2, 10, 2), Blocks.AIR.defaultBlockState());
    }
}
