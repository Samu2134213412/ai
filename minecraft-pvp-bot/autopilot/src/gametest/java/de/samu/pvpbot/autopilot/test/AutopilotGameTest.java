package de.samu.pvpbot.autopilot.test;

import de.samu.pvpbot.autopilot.Autopilot;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Path;
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
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.AABB;

/**
 * Runs the autopilot in a real client against real mobs (and against the PvP bot, if that mod is
 * loaded), logs the fights and prints small screenshots as base64 so they can be looked at later.
 */
public class AutopilotGameTest implements FabricClientGameTest {
    private static final String TAG = "[AUTOPILOT-TEST] ";
    private final List<String> results = new ArrayList<>();

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
            fight(ctx, sp, "Mace + Windladungen vs Golem", ARMOR + ";give @a minecraft:mace;give @a minecraft:wind_charge 32",
                    "summon minecraft:iron_golem 6 ~ 0 {NoAI:1b}", 600);
            fight(ctx, sp, "Speer vs Golem", ARMOR + ";give @a minecraft:netherite_spear",
                    "summon minecraft:iron_golem 9 ~ 0 {NoAI:1b}", 600);
            fight(ctx, sp, "Bogen vs Golem", ARMOR + ";give @a minecraft:bow;give @a minecraft:arrow 64",
                    "summon minecraft:iron_golem 16 ~ 0 {NoAI:1b}", 900);
            fight(ctx, sp, "Elytra + Mace vs Golem (35 Bloecke)",
                    ARMOR + ";give @a minecraft:mace;give @a minecraft:elytra;give @a minecraft:firework_rocket 64",
                    "summon minecraft:iron_golem 35 ~ 0 {NoAI:1b}", 900);
            fight(ctx, sp, "Schwert vs 3 Zombies", ARMOR + ";give @a minecraft:netherite_sword;give @a minecraft:golden_apple 4",
                    "summon minecraft:zombie 6 ~ 3;summon minecraft:zombie 7 ~ -3;summon minecraft:zombie 9 ~ 0", 900);
            if (FabricLoader.getInstance().isModLoaded("pvpbot")) {
                fight(ctx, sp, "DUELL: Autopilot vs PvP-Bot",
                        ARMOR + ";give @a minecraft:netherite_sword;give @a minecraft:mace;give @a minecraft:wind_charge 32;"
                                + "give @a minecraft:golden_apple 8;give @a minecraft:totem_of_undying",
                        "execute as @p at @p run pvpbot spawn Gegner;execute as @p run pvpbot duel", 1200);
            }

            System.out.println(TAG + "==================== SUMMARY");
            results.forEach(r -> System.out.println(TAG + r));
            System.out.println(TAG + "DONE");
        }
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
        ctx.waitTicks(10);

        boolean started = ctx.computeOnClient(mc -> {
            LivingEntity enemy = nearestEnemy(mc);
            if (enemy == null) {
                return false;
            }
            Autopilot.INSTANCE.setTarget(mc, enemy);
            Autopilot.INSTANCE.setTargetMode(mc, Autopilot.TargetMode.MOBS);
            Autopilot.INSTANCE.setTarget(mc, enemy);
            Autopilot.INSTANCE.setEnabled(mc, true);
            return true;
        });
        if (!started) {
            results.add("FAIL " + name + " (kein Gegner gefunden)");
            return;
        }

        int waited = 0;
        boolean won = false;
        boolean lost = false;
        while (waited < timeoutTicks) {
            ctx.waitTicks(20);
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
            boolean enemyLeft = ctx.computeOnClient(mc -> nearestEnemy(mc) != null);
            boolean dead = ctx.computeOnClient(mc -> mc.player == null || !mc.player.isAlive() || mc.player.getHealth() <= 0.0F);
            if (!enemyLeft) {
                won = true;
                break;
            }
            if (dead) {
                lost = true;
                break;
            }
        }
        String line = String.format("%s %-38s %s nach %.1fs", won ? "PASS" : "FAIL", name, won ? "gewonnen" : lost ? "verloren" : "Zeit abgelaufen", waited / 20.0);
        results.add(line);
        System.out.println(TAG + line);
        ctx.runOnClient(mc -> Autopilot.INSTANCE.setEnabled(mc, false));
        if (lost) {
            ctx.runOnClient(mc -> {
                if (mc.player != null) {
                    mc.player.respawn();
                }
            });
            ctx.waitTicks(40);
            ctx.runOnClient(mc -> mc.setScreen(null));
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
