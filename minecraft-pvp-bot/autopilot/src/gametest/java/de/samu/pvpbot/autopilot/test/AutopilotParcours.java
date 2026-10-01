package de.samu.pvpbot.autopilot.test;

import de.samu.pvpbot.autopilot.Autopilot;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.gametest.v1.context.TestSingleplayerContext;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/**
 * Training course for the autopilot: the traps the survival bot got stuck in (or died in), built in
 * the flat test world. The autopilot plays on in full control from a start spot with a small kit and
 * has to get past each trap on its own - without lava, without a long fall, without dying.
 */
final class AutopilotParcours {
    private static final String TAG = "[AUTOPILOT-PARCOURS] ";

    /** Where the course is (x offset), how high the start is, how long it may take, the kit, the goal. */
    private record Course(String name, int x, int dy, int timeout, String kit, boolean noFalls, Goal goal, Builder build) {
    }

    private interface Goal {
        boolean reached(LocalPlayer p, int bx, int by, int bz);
    }

    private interface Builder {
        void build(List<String> cmds, int x, int y, int z);
    }

    private static final String PICK_FOOD = "give @a minecraft:wooden_pickaxe;give @a minecraft:cobblestone 16;give @a minecraft:cooked_beef 8";
    private static final Predicate<ItemStack> WOOD = st -> st.is(ItemTags.LOGS) || st.is(ItemTags.PLANKS);

    private static boolean has(LocalPlayer p, Predicate<ItemStack> match) {
        for (ItemStack st : p.getInventory().getNonEquipmentItems()) {
            if (match.test(st)) {
                return true;
            }
        }
        return false;
    }

    private static final List<Course> COURSES = List.of(
            // Needs sticks (no wood in the kit), the trees are outside: out of the shaft, on top or through the wall.
            new Course("Parcours 1: Grube (6 tief, 1 breit)", -90, 0, 2400, PICK_FOOD, false,
                    (p, x, y, z) -> p.getY() >= y + 7 || Math.abs(p.getX() - (x + 0.5)) > 1.5 || Math.abs(p.getZ() - (z + 0.5)) > 1.5,
                    (c, x, y, z) -> {
                        c.add(fill(x - 3, y, z - 3, x + 3, y + 6, z + 3, "stone"));
                        c.add(fill(x, y, z, x, y + 6, z, "air"));
                        tree(c, x + 8, y, z);
                    }),
            new Course("Parcours 2: im Berg eingeschlossen", -55, 0, 6000, PICK_FOOD, false,
                    (p, x, y, z) -> p.level().canSeeSky(p.blockPosition().above()),
                    (c, x, y, z) -> {
                        c.add(fill(x - 10, y, z - 10, x + 10, y + 15, z + 10, "stone"));
                        c.add(fill(x, y, z, x, y + 1, z, "air"));
                        tree(c, x + 14, y, z);
                    }),
            new Course("Parcours 3: Insel im See, Holz am Ufer", -10, 4, 6000, "", false,
                    (p, x, y, z) -> has(p, WOOD),
                    (c, x, y, z) -> {
                        c.add(fill(x - 12, y, z - 12, x + 12, y + 3, z + 12, "stone"));
                        c.add(fill(x - 11, y + 1, z - 11, x + 11, y + 3, z + 11, "water"));
                        c.add(fill(x - 1, y + 1, z - 1, x + 1, y + 3, z + 1, "dirt"));
                        c.add("setblock " + x + " " + (y + 3) + " " + z + " minecraft:grass_block");
                        tree(c, x + 16, y, z + 3);
                        tree(c, x - 16, y, z - 4);
                    }),
            new Course("Parcours 4: Eisen neben Lava", 30, 0, 3600,
                    "give @a minecraft:stone_pickaxe;give @a minecraft:stone_sword;give @a minecraft:stick 8;give @a minecraft:oak_planks 24;"
                            + "give @a minecraft:crafting_table;give @a minecraft:cooked_beef 8", false,
                    (p, x, y, z) -> has(p, st -> st.is(Items.RAW_IRON) || st.is(Items.IRON_INGOT)),
                    (c, x, y, z) -> {
                        c.add(fill(x - 8, y - 1, z - 6, x + 8, y - 1, z + 6, "stone"));
                        c.add(fill(x + 2, y - 2, z - 3, x + 7, y - 2, z + 3, "stone"));
                        c.add(fill(x + 3, y - 1, z - 2, x + 6, y - 1, z + 2, "lava"));
                        c.add("setblock " + (x + 2) + " " + y + " " + z + " minecraft:iron_ore");      // right next to the lava
                        c.add("setblock " + (x - 7) + " " + y + " " + (z + 4) + " minecraft:iron_ore"); // the safe one
                        c.add("setblock " + (x - 7) + " " + (y + 1) + " " + (z + 4) + " minecraft:stone");
                    }),
            new Course("Parcours 5: gefluteter Stollen", 60, 1, 4000, PICK_FOOD, false,
                    (p, x, y, z) -> p.level().canSeeSky(p.blockPosition().above()) && !p.isInWater(),
                    (c, x, y, z) -> {
                        c.add(fill(x - 6, y, z - 6, x + 6, y + 9, z + 6, "stone"));
                        c.add(fill(x - 4, y + 1, z, x + 4, y + 2, z, "air"));
                        c.add("setblock " + (x + 4) + " " + (y + 3) + " " + z + " minecraft:water");
                        c.add("setblock " + (x - 4) + " " + (y + 3) + " " + z + " minecraft:water");
                    }),
            new Course("Parcours 6: Holz ohne Werkzeug im Fels", 90, 0, 7200, "", false,
                    (p, x, y, z) -> has(p, WOOD),
                    (c, x, y, z) -> {
                        c.add(fill(x - 4, y, z - 4, x + 4, y + 6, z + 4, "stone"));
                        c.add(fill(x, y, z, x, y + 1, z, "air"));
                        tree(c, x + 7, y, z + 2);
                        tree(c, x - 7, y, z - 2);
                    }),
            // A hidden hollow under the top of a tower: down (it looks for iron) without falling into it.
            new Course("Parcours 7: Hoehlensturz (Treppe runter)", 125, 20, 4800,
                    "give @a minecraft:stone_pickaxe 2;give @a minecraft:stone_sword;give @a minecraft:stick 8;give @a minecraft:oak_planks 24;"
                            + "give @a minecraft:crafting_table;give @a minecraft:cooked_beef 8;give @a minecraft:cobblestone 16", true,
                    (p, x, y, z) -> p.getY() <= y + 10,
                    (c, x, y, z) -> {
                        c.add(fill(x - 4, y, z - 4, x + 4, y + 19, z + 4, "stone"));
                        c.add(fill(x - 2, y + 12, z - 2, x + 2, y + 17, z + 2, "air"));
                    }));

    private static String fill(int x1, int y1, int z1, int x2, int y2, int z2, String block) {
        return "fill " + x1 + " " + y1 + " " + z1 + " " + x2 + " " + y2 + " " + z2 + " minecraft:" + block;
    }

    private static void tree(List<String> c, int x, int y, int z) {
        c.add(fill(x, y, z, x, y + 4, z, "oak_log"));
        c.add(fill(x - 1, y + 4, z - 1, x + 1, y + 5, z + 1, "oak_leaves[persistent=true]"));
        c.add("setblock " + x + " " + (y + 4) + " " + z + " minecraft:oak_log");
    }

    private static void run(TestSingleplayerContext sp, String commands) {
        for (String command : commands.split(";")) {
            if (!command.isBlank()) {
                sp.getServer().runCommand(command.trim());
            }
        }
    }

    static void run(ClientGameTestContext ctx) {
        List<String> results = new ArrayList<>();
        int passed = 0;
        try (TestSingleplayerContext sp = ctx.worldBuilder().create()) {
            ctx.waitTicks(60);
            run(sp, "difficulty peaceful;gamemode survival @a;time set day");
            int[] base = new int[3];
            ctx.runOnClient(mc -> {
                base[0] = mc.player.getBlockX();
                base[1] = mc.player.getBlockY();
                base[2] = mc.player.getBlockZ();
            });
            int bz = base[2] + 64;
            System.out.println(TAG + "Boden y=" + base[1] + ", Kurse bei z=" + bz);
            run(sp, "forceload add " + (base[0] - 110) + " " + (bz - 20) + " " + (base[0] + 180) + " " + (bz + 20));
            ctx.waitTicks(40);
            for (Course c : COURSES) {
                List<String> cmds = new ArrayList<>();
                c.build().build(cmds, base[0] + c.x(), base[1], bz);
                cmds.forEach(cmd -> sp.getServer().runCommand(cmd));
            }
            ctx.waitTicks(20);
            for (Course c : COURSES) {
                int cx = base[0] + c.x();
                int cy = base[1];
                String result = runCourse(ctx, sp, c, cx, cy, bz);
                if (result.startsWith("PASS")) {
                    passed++;
                }
                results.add(result + " - " + c.name());
            }
            String odds = runOverpowered(ctx, sp, base[0] + 160, base[1], bz);
            if (odds.startsWith("PASS")) {
                passed++;
            }
            results.add(odds + " - Parcours 8: Uebermacht (nicht angreifen)");
            ctx.runOnClient(mc -> Autopilot.INSTANCE.setFullControl(mc, false));
        }
        System.out.println(TAG + "==================== ERGEBNIS");
        results.forEach(r -> System.out.println(TAG + r));
        System.out.println(TAG + passed + "/" + (COURSES.size() + 1) + " bestanden");
        System.out.println("[AUTOPILOT-TEST] DONE");
    }

    private static String runCourse(ClientGameTestContext ctx, TestSingleplayerContext sp, Course c, int x, int y, int z) {
        System.out.println(TAG + "==================== " + c.name());
        ctx.runOnClient(mc -> {
            Autopilot.INSTANCE.setFullControl(mc, false);
            Autopilot.INSTANCE.resetSurvival();
        });
        run(sp, "clear @a;kill @e[type=item];effect clear @a;effect give @a minecraft:instant_health 1 10;effect give @a minecraft:saturation 1 20");
        run(sp, "tp @a " + x + ".5 " + (y + c.dy()) + " " + z + ".5 0 0");
        run(sp, c.kit());
        ctx.waitTicks(20);
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setFullControl(mc, true));
        int[] st = new int[4]; // lava ticks, falls, deaths, reached
        double[] fall = new double[1];
        boolean[] dead = new boolean[1];
        String[] info = new String[1];
        int t = 0;
        while (t < c.timeout()) {
            ctx.waitTicks(2);
            t += 2;
            boolean logNow = t % 200 == 0;
            ctx.runOnClient(mc -> {
                LocalPlayer p = mc.player;
                if (p == null) {
                    return;
                }
                if (p.isInLava() || p.isOnFire()) {
                    st[0]++;
                }
                if (p.onGround() || p.isInWater()) {
                    if (fall[0] > 3.5 && !p.isInWater()) {
                        st[1]++;
                        System.out.println(TAG + "STURZ " + String.format("%.1f", fall[0]) + " Bloecke bei " + p.blockPosition().toShortString());
                    }
                    fall[0] = 0.0;
                } else {
                    fall[0] = Math.max(fall[0], p.fallDistance);
                }
                if (p.isDeadOrDying() && !dead[0]) {
                    st[2]++;
                }
                dead[0] = p.isDeadOrDying();
                if (c.goal().reached(p, x, y, z)) {
                    st[3] = 1;
                }
                info[0] = String.format("hp=%.1f pos=%s | %s", p.getHealth(), p.blockPosition().toShortString(),
                        Autopilot.INSTANCE.status().replaceAll("§.", ""));
            });
            if (logNow) {
                System.out.println(TAG + "t=" + t / 20 + "s " + info[0]);
            }
            if (st[3] == 1 || st[2] > 0) {
                break;
            }
        }
        int[] stucks = new int[1];
        ctx.runOnClient(mc -> {
            stucks[0] = Autopilot.INSTANCE.survivalStucks();
            Autopilot.INSTANCE.setFullControl(mc, false);
        });
        boolean ok = st[3] == 1 && st[0] == 0 && st[2] == 0 && (!c.noFalls() || st[1] == 0);
        String result = (ok ? "PASS" : "FAIL") + " nach " + t / 20 + "s (Ziel " + (st[3] == 1 ? "erreicht" : "NICHT erreicht")
                + ", Lava/Feuer " + st[0] + ", Stuerze " + st[1] + ", Tode " + st[2] + ", Sicherheitsnetz " + stucks[0] + ")";
        System.out.println(TAG + result + " | " + info[0]);
        return result;
    }

    /**
     * A zombie in diamond armor with a netherite sword, the autopilot with a wooden sword: it must
     * not pick that fight (full control would fight monsters it can beat) and get away from it.
     */
    private static String runOverpowered(ClientGameTestContext ctx, TestSingleplayerContext sp, int x, int y, int z) {
        System.out.println(TAG + "==================== Parcours 8: Uebermacht (nicht angreifen)");
        ctx.runOnClient(mc -> {
            Autopilot.INSTANCE.setFullControl(mc, false);
            Autopilot.INSTANCE.resetSurvival();
        });
        run(sp, "clear @a;kill @e[type=item];effect clear @a;effect give @a minecraft:instant_health 1 10;effect give @a minecraft:saturation 1 20");
        run(sp, "tp @a " + x + ".5 " + y + " " + z + ".5 -90 0");
        run(sp, "give @a minecraft:wooden_sword;give @a minecraft:cooked_beef 8");
        run(sp, "difficulty easy");
        run(sp, "summon minecraft:zombie " + (x + 7) + " " + y + " " + z + " {PersistenceRequired:1b,Tags:[\"uebermacht\"],equipment:{"
                + "mainhand:{id:\"minecraft:netherite_sword\",count:1},head:{id:\"minecraft:diamond_helmet\",count:1},"
                + "chest:{id:\"minecraft:diamond_chestplate\",count:1},legs:{id:\"minecraft:diamond_leggings\",count:1},"
                + "feet:{id:\"minecraft:diamond_boots\",count:1}}}");
        ctx.waitTicks(10);
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setFullControl(mc, true));
        boolean[] hit = new boolean[1];
        boolean[] dead = new boolean[1];
        double[] far = new double[1];
        String[] info = new String[1];
        for (int t = 0; t < 600; t += 2) {
            ctx.waitTicks(2);
            int tt = t;
            ctx.runOnClient(mc -> {
                LocalPlayer p = mc.player;
                if (p == null) {
                    return;
                }
                dead[0] |= p.isDeadOrDying();
                for (var e : mc.level.entitiesForRendering()) {
                    if (e.getType() == net.minecraft.world.entity.EntityTypes.ZOMBIE && e instanceof net.minecraft.world.entity.LivingEntity zombie
                            && zombie.distanceTo(p) < 64.0F) {
                        hit[0] |= zombie.getHealth() < zombie.getMaxHealth();
                        far[0] = Math.max(far[0], zombie.distanceTo(p));
                    }
                }
                info[0] = String.format("hp=%.1f pos=%s | %s", p.getHealth(), p.blockPosition().toShortString(),
                        Autopilot.INSTANCE.status().replaceAll("§.", ""));
            });
            if (tt % 200 == 0) {
                System.out.println(TAG + "t=" + tt / 20 + "s " + info[0]);
            }
        }
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setFullControl(mc, false));
        run(sp, "kill @e[tag=uebermacht];difficulty peaceful");
        boolean ok = !hit[0] && !dead[0];
        String result = (ok ? "PASS" : "FAIL") + " nach 30s (Zombie angegriffen: " + (hit[0] ? "JA" : "nein") + ", Tod: " + (dead[0] ? "JA" : "nein")
                + ", groesster Abstand " + (int) far[0] + " Bloecke)";
        System.out.println(TAG + result + " | " + info[0]);
        return result;
    }

    private AutopilotParcours() {
    }
}
