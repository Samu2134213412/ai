package de.samu.pvpbot.autopilot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import org.jspecify.annotations.Nullable;

/**
 * A* over the blocks the player can see in the client world: walk, step up one block, drop down up
 * to three, swim, and - only when there is no other way - dig through a block. Positions are feet
 * positions. Lava, fire, cactus and magma are never walked into.
 */
final class PathFinder {
    private PathFinder() {
    }

    private record Node(BlockPos pos, double g, double f, @Nullable Node parent) {
    }

    /** Returns the positions to walk through (without the start), or null when nothing was found. */
    static @Nullable List<BlockPos> find(Level level, BlockPos start, BlockPos target, Predicate<BlockPos> arrived, int maxNodes, boolean dig) {
        PriorityQueue<Node> open = new PriorityQueue<>((a, b) -> Double.compare(a.f, b.f));
        Map<Long, Double> best = new HashMap<>();
        Node first = new Node(start, 0.0, h(start, target), null);
        open.add(first);
        best.put(start.asLong(), 0.0);
        Node closest = first;
        int expanded = 0;
        while (!open.isEmpty() && expanded++ < maxNodes) {
            Node n = open.poll();
            if (n.g > best.getOrDefault(n.pos.asLong(), Double.MAX_VALUE)) {
                continue;
            }
            if (arrived.test(n.pos)) {
                return build(n);
            }
            if (h(n.pos, target) < h(closest.pos, target)) {
                closest = n;
            }
            for (Direction d : Direction.Plane.HORIZONTAL) {
                BlockPos side = n.pos.relative(d);
                // Same level.
                if (standable(level, side)) {
                    push(open, best, n, side, 1.0 + (level.getFluidState(side).is(FluidTags.WATER) ? 2.0 : 0.0), target);
                } else if (passable(level, side) && passable(level, side.above())) {
                    // Drop down (up to three blocks).
                    for (int k = 1; k <= 3; k++) {
                        BlockPos low = side.below(k);
                        if (!passable(level, low)) {
                            break;
                        }
                        if (standable(level, low)) {
                            push(open, best, n, low, 1.0 + 0.5 * k, target);
                            break;
                        }
                    }
                }
                // Step up one block.
                BlockPos up = side.above();
                if (standable(level, up) && passable(level, n.pos.above(2))) {
                    push(open, best, n, up, 2.0, target);
                }
                // Dig through (feet and head), only on solid ground, never next to lava.
                // (Not while swimming: digging in water takes ages - swim round or climb out.)
                if (dig && !standable(level, side) && solidGround(level, side.below()) && !level.getFluidState(n.pos).is(FluidTags.WATER) && diggable(level, side) && diggable(level, side.above())
                        && !nearLava(level, side) && !nearLava(level, side.above())) {
                    int blocks = (passable(level, side) ? 0 : 1) + (passable(level, side.above()) ? 0 : 1);
                    push(open, best, n, side, 1.0 + 4.0 * blocks, target);
                }
            }
            // Diagonals, only when both sides are free (no corner clipping).
            for (int[] dd : new int[][]{{1, 1}, {1, -1}, {-1, 1}, {-1, -1}}) {
                BlockPos diag = n.pos.offset(dd[0], 0, dd[1]);
                if (standable(level, diag) && body(level, n.pos.offset(dd[0], 0, 0)) && body(level, n.pos.offset(0, 0, dd[1]))) {
                    push(open, best, n, diag, 1.414, target);
                }
            }
            // Swim up in water.
            if (level.getFluidState(n.pos).is(FluidTags.WATER) && body(level, n.pos.above())) {
                push(open, best, n, n.pos.above(), 1.5, target);
            }
        }
        // No full path: get as close as possible (the caller walks there and tries again).
        return closest == first ? null : build(closest);
    }

    private static void push(PriorityQueue<Node> open, Map<Long, Double> best, Node from, BlockPos to, double cost, BlockPos target) {
        double g = from.g + cost;
        long key = to.asLong();
        if (g < best.getOrDefault(key, Double.MAX_VALUE)) {
            best.put(key, g);
            open.add(new Node(to, g, g + h(to, target), from));
        }
    }

    private static double h(BlockPos a, BlockPos b) {
        double dx = a.getX() - b.getX();
        double dy = a.getY() - b.getY();
        double dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dy * dy * 1.5 + dz * dz);
    }

    private static List<BlockPos> build(Node n) {
        List<BlockPos> path = new ArrayList<>();
        while (n.parent != null) {
            path.add(n.pos);
            n = n.parent;
        }
        Collections.reverse(path);
        return path;
    }

    /** The player can stand here: feet and head free and safe, something solid below (or water). */
    static boolean standable(Level level, BlockPos feet) {
        if (!body(level, feet) || !body(level, feet.above())) {
            return false;
        }
        BlockState below = level.getBlockState(feet.below());
        if (dangerous(below)) {
            return false;
        }
        return solidGround(level, feet.below()) || level.getFluidState(feet).is(FluidTags.WATER);
    }

    static boolean solidGround(Level level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        return !state.getCollisionShape(level, pos).isEmpty() && !dangerous(state);
    }

    /** Free for the body: no collision, no lava, nothing that hurts. */
    static boolean body(Level level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        return state.getCollisionShape(level, pos).isEmpty() && !level.getFluidState(pos).is(FluidTags.LAVA) && !dangerous(state);
    }

    static boolean passable(Level level, BlockPos pos) {
        return body(level, pos);
    }

    static boolean dangerous(BlockState state) {
        return state.is(Blocks.LAVA) || state.is(Blocks.FIRE) || state.is(Blocks.SOUL_FIRE) || state.is(Blocks.CACTUS)
                || state.is(Blocks.MAGMA_BLOCK) || state.is(Blocks.SWEET_BERRY_BUSH) || state.is(Blocks.POWDER_SNOW)
                || state.is(Blocks.CAMPFIRE) || state.is(Blocks.WITHER_ROSE);
    }

    static boolean diggable(Level level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        if (state.isAir() || state.getCollisionShape(level, pos).isEmpty()) {
            return level.getFluidState(pos).isEmpty();
        }
        float hardness = state.getDestroySpeed(level, pos);
        return hardness >= 0.0F && hardness < 20.0F && level.getFluidState(pos).isEmpty();
    }

    static boolean nearLava(Level level, BlockPos pos) {
        for (Direction d : Direction.values()) {
            if (level.getFluidState(pos.relative(d)).is(FluidTags.LAVA)) {
                return true;
            }
        }
        return false;
    }
}
