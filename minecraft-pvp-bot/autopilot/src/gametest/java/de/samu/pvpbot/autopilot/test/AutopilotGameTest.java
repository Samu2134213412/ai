package de.samu.pvpbot.autopilot.test;

import de.samu.pvpbot.autopilot.Autopilot;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import javax.imageio.ImageIO;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.gametest.v1.context.TestSingleplayerContext;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.AABB;

/**
 * Runs the autopilot in a real client against real mobs (and against the PvP bot, if that mod is
 * loaded), logs the fights and prints small screenshots as base64 so they can be looked at later.
 * Some scenes are also recorded frame by frame into {@code pvpbot-frames/<clip>/} (CI turns them into videos).
 */
public class AutopilotGameTest implements FabricClientGameTest {
    private static final String TAG = "[AUTOPILOT-TEST] ";
    private final List<String> results = new ArrayList<>();
    private static final Path FRAMES = Path.of("pvpbot-frames").toAbsolutePath();
    /** Name of the clip being recorded, or null. */
    private String clip;
    private String recordNext;
    private int frame;

    private static final String ARMOR = "item replace entity @a armor.head with minecraft:netherite_helmet;"
            + "item replace entity @a armor.chest with minecraft:netherite_chestplate;"
            + "item replace entity @a armor.legs with minecraft:netherite_leggings;"
            + "item replace entity @a armor.feet with minecraft:netherite_boots";

    @Override
    public void runTest(ClientGameTestContext ctx) {
        try (TestSingleplayerContext sp = ctx.worldBuilder().create()) {
            ctx.waitTicks(60);
            run(sp, "difficulty normal");
            run(sp, "gamemode survival @a");
            run(sp, "time set day");
            logWorld(ctx, sp);

            fight(ctx, sp, "Schwert vs Golem", ARMOR + ";give @a minecraft:netherite_sword",
                    "summon minecraft:iron_golem 5 ~ 0 {NoAI:1b}", 600);
            recordNext = "02_mace_windladungen";
            fight(ctx, sp, "Mace + Windladungen vs Golem", ARMOR + ";give @a minecraft:mace;give @a minecraft:wind_charge 32",
                    "summon minecraft:iron_golem 6 ~ 0 {NoAI:1b}", 600);
            recordNext = "03_speer";
            fight(ctx, sp, "Speer (Lunge III) vs Golem", ARMOR + ";give @a minecraft:netherite_spear[enchantments={lunge:3}]",
                    "summon minecraft:iron_golem 9 ~ 0 {NoAI:1b}", 900);
            recordNext = "03b_speer_zombies";
            fight(ctx, sp, "Speer (Lunge III) vs 3 Zombies", ARMOR + ";give @a minecraft:netherite_spear[enchantments={lunge:3}];give @a minecraft:golden_apple 4",
                    "summon minecraft:zombie 10 ~ 4 {equipment:{head:{id:\"minecraft:iron_helmet\",count:1}}};summon minecraft:zombie 12 ~ -4 {equipment:{head:{id:\"minecraft:iron_helmet\",count:1}}};summon minecraft:zombie 14 ~ 0 {equipment:{head:{id:\"minecraft:iron_helmet\",count:1}}}", 900, true);
            fight(ctx, sp, "Bogen vs Golem", ARMOR + ";give @a minecraft:bow;give @a minecraft:arrow 64",
                    "summon minecraft:iron_golem 16 ~ 0 {NoAI:1b}", 900);
            recordNext = "04_elytra_mace_sturzflug";
            fight(ctx, sp, "Elytra + Mace vs Golem (35 Bloecke)",
                    ARMOR + ";give @a minecraft:mace;give @a minecraft:elytra;give @a minecraft:firework_rocket 64",
                    "summon minecraft:iron_golem 35 ~ 0 {NoAI:1b}", 900);
            fight(ctx, sp, "Schwert vs 3 Zombies", ARMOR + ";give @a minecraft:netherite_sword;give @a minecraft:golden_apple 4",
                    "summon minecraft:zombie 6 ~ 3;summon minecraft:zombie 7 ~ -3;summon minecraft:zombie 9 ~ 0", 900, true);
            if (FabricLoader.getInstance().isModLoaded("pvpbot")) {
                survivalScene(ctx, sp);
                botSpearScene(ctx, sp);
                botCloseUp(ctx, sp);
                // Fair mirror match: the bot gets an exact copy of the player's kit.
                String duelKit = ARMOR + ";give @a minecraft:netherite_sword;give @a minecraft:mace;give @a minecraft:wind_charge 16;"
                        + "give @a minecraft:golden_apple 4;give @a minecraft:totem_of_undying";
                for (int round = 1; round <= 2; round++) {
                    if (round == 1) {
                        recordNext = "05_duell_autopilot_vs_bot";
                    }
                    fight(ctx, sp, "DUELL " + round + ": Autopilot vs PvP-Bot (gleiches Kit)", duelKit,
                            "execute as @p at @p run pvpbot spawn Gegner;gamemode creative @a;execute as @p run pvpbot kit copy;"
                                    + "gamemode survival @a;execute as @p run pvpbot duel", 1200);
                }
            }

            System.out.println(TAG + "==================== SUMMARY");
            results.forEach(r -> System.out.println(TAG + r));
            System.out.println(TAG + "DONE");
        }
    }

    /**
     * A survival bot starts with empty hands next to a few trees, stone, coal and iron and has to
     * equip itself. The camera (the player, in spectator mode) slowly circles around the bot.
     */
    private void survivalScene(ClientGameTestContext ctx, TestSingleplayerContext sp) {
        System.out.println(TAG + "==================== Survival-Bot besorgt sich Ausruestung");
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setEnabled(mc, false));
        run(sp, "kill @e[type=!minecraft:player]");
        run(sp, "clear @a");
        run(sp, "tp @a 100 -60 0 0 20");
        ctx.waitTicks(60);
        run(sp, "fill 104 -60 5 104 -55 5 minecraft:oak_log;fill 95 -60 5 95 -55 5 minecraft:oak_log;"
                + "fill 103 -54 4 105 -53 6 minecraft:oak_leaves[persistent=true];fill 94 -54 4 96 -53 6 minecraft:oak_leaves[persistent=true];"
                + "fill 106 -60 -5 108 -59 -3 minecraft:stone;fill 99 -60 -8 102 -60 -8 minecraft:coal_ore;"
                + "fill 91 -60 -5 95 -59 -3 minecraft:iron_ore;fill 98 -62 9 100 -62 9 minecraft:iron_ore;"
                + "summon minecraft:cow 108 -60 8;summon minecraft:cow 109 -60 9;summon minecraft:cow 110 -60 8");
        run(sp, "execute as @p at @p run pvpbot survival Sammler");
        run(sp, "gamemode spectator @a");
        ctx.waitTicks(5);
        startClip("01_survival_bot_sammelt", 20);
        int waited = 0;
        boolean geared = false;
        while (waited < 4800 && !geared) {
            for (int i = 0; i < 5; i++) {
                ctx.waitTicks(4);
                waited += 4;
                orbitCamera(sp, waited * 0.0015, 7.0, 4.0);
                capture(ctx);
            }
            geared = ctx.computeOnClient(mc -> {
                LivingEntity bot = pvpBot(mc);
                return bot != null && bot.getItemBySlot(EquipmentSlot.HEAD).is(Items.IRON_HELMET)
                        && bot.getItemBySlot(EquipmentSlot.CHEST).is(Items.IRON_CHESTPLATE)
                        && bot.getItemBySlot(EquipmentSlot.LEGS).is(Items.IRON_LEGGINGS)
                        && bot.getItemBySlot(EquipmentSlot.FEET).is(Items.IRON_BOOTS)
                        && bot.getItemBySlot(EquipmentSlot.OFFHAND).is(Items.SHIELD);
            });
            if (waited % 400 == 0) {
                String state = ctx.computeOnClient(mc -> {
                    LivingEntity bot = pvpBot(mc);
                    return bot == null ? "kein Bot" : "Bot bei " + bot.blockPosition() + " haelt " + bot.getMainHandItem().getItem();
                });
                System.out.println(TAG + String.format("t=%3ds %s", waited / 20, state));
            }
        }
        for (int i = 0; i < 15; i++) {
            ctx.waitTicks(4);
            capture(ctx);
        }
        clip = null;
        String line = String.format("INFO Survival-Bot %s nach %.1fs", geared ? "komplett ausgeruestet" : "noch nicht fertig", waited / 20.0);
        results.add(line);
        System.out.println(TAG + line);
        run(sp, "kill @e[type=pvpbot:pvp_bot]");
        run(sp, "gamemode survival @a");
        run(sp, "tp @a 0 -60 0 -90 0");
        ctx.waitTicks(40);
    }

    /** Puts the (spectating) player at a point circling the bot, looking at it. */
    private static void orbitCamera(TestSingleplayerContext sp, double angle, double radius, double height) {
        String dx = String.format(java.util.Locale.ROOT, "%.2f", -radius * Math.cos(angle));
        String dz = String.format(java.util.Locale.ROOT, "%.2f", -radius * Math.sin(angle));
        sp.getServer().runCommand("execute as @a at @e[type=pvpbot:pvp_bot,limit=1] run tp @s ~" + dx + " ~" + height + " ~" + dz
                + " facing entity @e[type=pvpbot:pvp_bot,limit=1] feet");
    }

    /** The PvP bot with only its spear (Lunge III) against zombies, filmed from outside. */
    private void botSpearScene(ClientGameTestContext ctx, TestSingleplayerContext sp) {
        System.out.println(TAG + "==================== PvP-Bot mit Speer vs Zombies");
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setEnabled(mc, false));
        run(sp, "kill @e[type=!minecraft:player]");
        run(sp, "gamemode survival @a");
        run(sp, "tp @a 0 -60 60 0 0");
        ctx.waitTicks(40);
        run(sp, "execute as @p at @p run pvpbot spawn Lanze");
        run(sp, "execute as @p run pvpbot weapon spear");
        run(sp, "execute as @p run pvpbot assist off");
        for (int[] z : new int[][]{{12, 5}, {14, -4}, {16, 1}, {20, 8}, {22, -7}, {25, 0}}) {
            run(sp, "execute at @p run summon minecraft:zombie ~" + z[0] + " ~ ~" + z[1] + " {equipment:{head:{id:\"minecraft:iron_helmet\",count:1}}}");
        }
        run(sp, "effect give @e[type=minecraft:zombie] minecraft:fire_resistance infinite 0 true");
        run(sp, "execute as @p run pvpbot attack @e[type=minecraft:zombie]");
        run(sp, "gamemode spectator @a");
        ctx.waitTicks(4);
        startClip("06_pvpbot_speer", 10);
        int waited = 0;
        boolean zombiesLeft = true;
        while (waited < 900 && zombiesLeft) {
            for (int i = 0; i < 10; i++) {
                ctx.waitTicks(2);
                waited += 2;
                orbitCamera(sp, 0.6 + waited * 0.003, 5.0, 2.5);
                capture(ctx);
            }
            zombiesLeft = ctx.computeOnClient(mc -> {
                for (Entity e : mc.level.getEntities(mc.player, new AABB(mc.player.blockPosition()).inflate(80.0))) {
                    if (e.getType().toString().contains("zombie") && e.isAlive()) {
                        return true;
                    }
                }
                return false;
            });
        }
        for (int i = 0; i < 15; i++) {
            ctx.waitTicks(2);
            orbitCamera(sp, 0.6 + (waited + 2 * i) * 0.003, 5.0, 2.5);
            capture(ctx);
        }
        clip = null;
        String line = String.format("INFO PvP-Bot Speer vs 6 Zombies: %s nach %.1fs", zombiesLeft ? "Zeit abgelaufen" : "alle erledigt", waited / 20.0);
        results.add(line);
        System.out.println(TAG + line);
        run(sp, "kill @e[type=pvpbot:pvp_bot]");
        run(sp, "kill @e[type=minecraft:zombie]");
        run(sp, "gamemode survival @a");
        run(sp, "tp @a 0 -60 0 -90 0");
        ctx.waitTicks(40);
    }

    private static LivingEntity pvpBot(Minecraft mc) {
        if (mc.level == null || mc.player == null) {
            return null;
        }
        for (Entity e : mc.level.getEntities(mc.player, new AABB(mc.player.blockPosition()).inflate(100.0))) {
            if (e instanceof LivingEntity living && e.getType().toString().contains("pvp_bot")) {
                return living;
            }
        }
        return null;
    }

    private void startClip(String name, int fps) {
        this.clip = name;
        this.frame = 0;
        try {
            Path dir = FRAMES.resolve(name);
            Files.createDirectories(dir);
            Files.writeString(dir.resolve("fps"), Integer.toString(fps));
        } catch (Exception e) {
            System.out.println(TAG + "recording failed: " + e);
            this.clip = null;
        }
    }

    /** Saves one video frame of the current clip. */
    private void capture(ClientGameTestContext ctx) {
        if (clip == null) {
            return;
        }
        try {
            Path shot = ctx.takeScreenshot("frame");
            Files.move(shot, FRAMES.resolve(clip).resolve(String.format("%05d.png", frame++)), StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception e) {
            System.out.println(TAG + "frame failed: " + e);
            clip = null;
        }
    }

    /** A still picture of the bot right in front of the camera, to check how it looks. */
    private void botCloseUp(ClientGameTestContext ctx, TestSingleplayerContext sp) {
        run(sp, "kill @e[type=!minecraft:player]");
        run(sp, "tp @a 0 ~ 0 -90 10");
        ctx.waitTicks(5);
        sp.getServer().runCommand("execute as @p at @p run pvpbot spawn Modell");
        sp.getServer().runCommand("execute as @p run pvpbot stay");
        sp.getServer().runCommand("execute at @p run tp @e[type=pvpbot:pvp_bot] ~3 ~ ~ 90 0");
        ctx.waitTicks(30);
        screenshot(ctx, "Bot_Nahaufnahme");
        run(sp, "kill @e[type=pvpbot:pvp_bot]");
    }

    private static void run(TestSingleplayerContext sp, String commands) {
        for (String command : commands.split(";")) {
            if (!command.isBlank()) {
                sp.getServer().runCommand(command.trim());
            }
        }
    }

    private void logWorld(ClientGameTestContext ctx, TestSingleplayerContext sp) {
        String info = ctx.computeOnClient(mc -> "player at " + mc.player.blockPosition() + " standing on "
                + mc.level.getBlockState(mc.player.blockPosition().below()).getBlock());
        System.out.println(TAG + info);
    }

    private void fight(ClientGameTestContext ctx, TestSingleplayerContext sp, String name, String kit, String enemies, int timeoutTicks) {
        fight(ctx, sp, name, kit, enemies, timeoutTicks, false);
    }

    private void fight(ClientGameTestContext ctx, TestSingleplayerContext sp, String name, String kit, String enemies, int timeoutTicks, boolean mobsMode) {
        System.out.println(TAG + "==================== " + name);
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setEnabled(mc, false));
        run(sp, "kill @e[type=!minecraft:player]");
        run(sp, "clear @a");
        run(sp, "effect clear @a");
        run(sp, "effect give @a minecraft:instant_health 1 10");
        run(sp, "tp @a 0 ~ 0 -90 0");
        ctx.waitTicks(10);
        run(sp, kit);
        // Summons are run as the player so "~" means the player's height.
        for (String enemy : enemies.split(";")) {
            String command = enemy.trim().startsWith("execute") ? enemy.trim() : "execute at @p run " + enemy.trim();
            sp.getServer().runCommand(command);
        }
        run(sp, "effect give @e[type=minecraft:zombie] minecraft:fire_resistance infinite 0 true");
        ctx.waitTicks(10);

        // Remember exactly which enemies were summoned: the fight is won when all of them are dead
        // on the server (not merely out of sight).
        List<java.util.UUID> enemyIds = ctx.computeOnClient(mc -> {
            List<java.util.UUID> ids = new ArrayList<>();
            for (Entity e : mc.level.getEntities(mc.player, new AABB(mc.player.blockPosition()).inflate(80.0))) {
                if (e instanceof LivingEntity && !(e instanceof Player) && !e.getType().toString().contains("item")) {
                    ids.add(e.getUUID());
                }
            }
            return ids;
        });
        java.util.Map<java.util.UUID, net.minecraft.world.phys.Vec3> lastSeen = new java.util.HashMap<>();
        boolean started = ctx.computeOnClient(mc -> {
            LivingEntity enemy = nearestEnemy(mc);
            if (enemy == null) {
                return false;
            }
            if (mobsMode) {
                Autopilot.INSTANCE.setTargetMode(mc, Autopilot.TargetMode.MOBS);
            } else {
                Autopilot.INSTANCE.setTarget(mc, enemy);
            }
            Autopilot.INSTANCE.setEnabled(mc, true);
            return true;
        });
        if (!started) {
            results.add("FAIL " + name + " (kein Gegner gefunden)");
            recordNext = null;
            return;
        }
        if (recordNext != null) {
            startClip(recordNext, 10);
            recordNext = null;
        }

        int waited = 0;
        boolean won = false;
        boolean lost = false;
        while (waited < timeoutTicks) {
            if (clip != null) {
                for (int i = 0; i < 10; i++) {
                    ctx.waitTicks(2);
                    capture(ctx);
                }
            } else {
                ctx.waitTicks(20);
            }
            waited += 20;
            if (waited == 60 || waited == 200) {
                screenshot(ctx, name.replaceAll("[^A-Za-z]", "") + "_" + waited);
            }
            String state = ctx.computeOnClient(mc -> {
                LivingEntity enemy = nearestEnemy(mc);
                return String.format("t=%3ds hp=%4.1f y=%+5.1f fly=%s hand=%s enemy=%s | %s", 0, mc.player.getHealth(),
                        mc.player.getY(), mc.player.isFallFlying(), mc.player.getMainHandItem().getItem(),
                        enemy == null ? "-" : String.format("%s %.1f hp %.1fm", enemy.getName().getString(), enemy.getHealth(), enemy.distanceTo(mc.player)),
                        Autopilot.INSTANCE.status().replaceAll("§.", ""));
            });
            System.out.println(TAG + state.replace("t=  0s", String.format("t=%3ds", waited / 20)));
            boolean enemyLeft = sp.getServer().computeOnServer(server -> {
                // An enemy only counts as dead when it died near the player; far away it may just be unloaded.
                var player = server.getPlayerList().getPlayers().get(0);
                for (java.util.UUID id : enemyIds) {
                    Entity e = server.overworld().getEntity(id);
                    if (e != null) {
                        lastSeen.put(id, e.position());
                        if (e.isAlive()) {
                            return true;
                        }
                    } else if (lastSeen.containsKey(id) && lastSeen.get(id).distanceTo(player.position()) > 40.0) {
                        return true;
                    }
                }
                return false;
            });
            boolean dead = ctx.computeOnClient(mc -> mc.player == null || !mc.player.isAlive() || mc.player.getHealth() <= 0.0F);
            if (dead) {
                lost = true;
                break;
            }
            if (!enemyLeft) {
                won = true;
                break;
            }
        }
        boolean duel = name.startsWith("DUELL");
        String verdict = duel ? (won ? "INFO Autopilot gewinnt" : lost ? "INFO Bot gewinnt" : "INFO unentschieden")
                : (won ? "PASS" : "FAIL");
        String line = String.format("%s %-38s %s nach %.1fs", verdict, name, won ? "gewonnen" : lost ? "verloren" : "Zeit abgelaufen", waited / 20.0);
        results.add(line);
        System.out.println(TAG + line);
        if (clip != null) {
            for (int i = 0; i < 15; i++) {
                ctx.waitTicks(2);
                capture(ctx);
            }
            clip = null;
        }
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setEnabled(mc, false));
        if (lost) {
            ctx.runOnClient(mc -> {
                if (mc.player != null) {
                    mc.player.respawn();
                }
            });
            ctx.waitTicks(40);
            ctx.runOnClient(mc -> mc.gui.setScreen(null));
        }
    }

    private static LivingEntity nearestEnemy(Minecraft mc) {
        if (mc.player == null || mc.level == null) {
            return null;
        }
        LivingEntity best = null;
        for (Entity e : mc.level.getEntities(mc.player, new AABB(mc.player.blockPosition()).inflate(80.0))) {
            if (e instanceof LivingEntity living && !(e instanceof Player) && living.isAlive() && living.getHealth() > 0.0F
                    && !e.getType().toString().contains("item")) {
                if (best == null || living.distanceTo(mc.player) < best.distanceTo(mc.player)) {
                    best = living;
                }
            }
        }
        return best;
    }

    private void screenshot(ClientGameTestContext ctx, String name) {
        try {
            Path path = ctx.takeScreenshot(name);
            BufferedImage img = ImageIO.read(path.toFile());
            int w = 480;
            int h = img.getHeight() * w / img.getWidth();
            BufferedImage small = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = small.createGraphics();
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.drawImage(img, 0, 0, w, h, null);
            g.dispose();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            ImageIO.write(small, "jpg", out);
            String data = Base64.getEncoder().encodeToString(out.toByteArray());
            int chunks = (data.length() + 3999) / 4000;
            for (int i = 0; i < chunks; i++) {
                System.out.println("[SHOT " + name + " " + (i + 1) + "/" + chunks + "] "
                        + data.substring(i * 4000, Math.min(data.length(), (i + 1) * 4000)));
            }
        } catch (Exception e) {
            System.out.println(TAG + "screenshot failed: " + e);
        }
    }
}
