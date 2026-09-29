package de.samu.pvpbot.autopilot;

import de.samu.pvpbot.autopilot.brain.BotBrain;
import de.samu.pvpbot.autopilot.brain.BotBrain.Pattern;
import de.samu.pvpbot.autopilot.brain.Kit;
import de.samu.pvpbot.autopilot.brain.Kit.Role;
import de.samu.pvpbot.autopilot.mixin.MinecraftInvoker;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Options;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Turns the local player into a PvP bot: it moves, aims, switches items and attacks through the
 * normal game controls, using only what is in the player's inventory. It chooses between attack
 * patterns with the same learning brain as the bot mod (own memory file).
 */
public final class Autopilot {
    public static final Autopilot INSTANCE = new Autopilot();
    static final Logger LOGGER = LoggerFactory.getLogger("pvpbot-autopilot");

    public enum TargetMode { MANUAL, NEAREST_PLAYER, MOBS }

    private boolean enabled;
    private TargetMode targetMode = TargetMode.MANUAL;
    private @Nullable Entity target;

    // Current attempt.
    private @Nullable Pattern pattern;
    private BotBrain.@Nullable Context attemptContext;
    private @Nullable LivingEntity attemptTarget;
    private float attemptTargetHp;
    private float attemptTaken;
    private float lastHealth = -1.0F;
    private int attemptTicks;
    private int phase;
    private int phaseTicks;
    private int shots;
    private final Map<Pattern, Long> tabuUntil = new EnumMap<>(Pattern.class);
    private long ticks;

    // Cooldowns (ticks).
    private int windCooldown;
    private int rocketCooldown;
    private int spearCooldown;
    private int flightCooldown;
    private int eatTicks;

    // Getting unstuck.
    private @Nullable Vec3 stuckAnchor;
    private int stuckTicks;
    private int unstuckTicks;
    private int unstuckMode;

    // Desired key states for this tick.
    private boolean kForward, kBack, kLeft, kRight, kJump, kSprint, kSneak, kUse, kAttack;
    private boolean wasJump;
    private boolean keysHeld;
    private float strafe = 1.0F;
    private String lastStatus = "";

    private Autopilot() {
    }

    // ------------------------------------------------------------------ public control

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(Minecraft mc, boolean enabled) {
        this.enabled = enabled;
        if (!enabled) {
            this.finishAttempt(mc);
            this.releaseKeys(mc);
        }
        this.say(mc, enabled ? "§aAutopilot AN §7– Ziel: " + this.describeTarget() : "§eAutopilot AUS");
    }

    public void setTarget(Minecraft mc, @Nullable Entity entity) {
        this.targetMode = TargetMode.MANUAL;
        this.target = entity;
        this.finishAttempt(mc);
        if (entity != null) {
            this.say(mc, "§cZiel: §f" + entity.getName().getString());
        }
    }

    public void setTargetMode(Minecraft mc, TargetMode mode) {
        this.targetMode = mode;
        this.target = null;
        this.finishAttempt(mc);
        this.say(mc, "§cZiel: §f" + this.describeTarget());
    }

    public @Nullable Entity getTarget() {
        return this.target;
    }

    public String describeTarget() {
        return switch (this.targetMode) {
            case NEAREST_PLAYER -> "nächster Spieler";
            case MOBS -> "Monster in der Nähe";
            case MANUAL -> this.target == null ? "keins" : this.target.getName().getString();
        };
    }

    public String status() {
        return this.lastStatus;
    }

    // ------------------------------------------------------------------ main loop

    public void tick(Minecraft mc) {
        LocalPlayer p = mc.player;
        if (!this.enabled || p == null || mc.level == null || mc.gameMode == null) {
            if (this.keysHeld) {
                this.releaseKeys(mc);
            }
            return;
        }
        this.ticks++;
        if (mc.gui.screen() != null || !p.isAlive()) {
            // Menu or chat open, or dead: hands off.
            this.releaseKeys(mc);
            return;
        }
        this.clearKeys();
        if (this.windCooldown > 0) this.windCooldown--;
        if (this.rocketCooldown > 0) this.rocketCooldown--;
        if (this.spearCooldown > 0) this.spearCooldown--;
        if (this.flightCooldown > 0) this.flightCooldown--;

        float health = p.getHealth() + p.getAbsorptionAmount();
        if (this.pattern != null && this.lastHealth >= 0.0F && health < this.lastHealth) {
            this.attemptTaken += this.lastHealth - health;
        }
        this.lastHealth = health;

        this.refreshTarget(mc, p);
        this.keepTotemInOffhand(mc, p);

        LivingEntity t = this.target instanceof LivingEntity living ? living : null;
        if (this.eatIfLow(mc, p, t)) {
            this.applyKeys(mc);
            return;
        }
        if (t == null) {
            this.finishAttempt(mc);
            this.landIfFlying(mc, p);
            if (this.eatWhenHungry(mc, p)) {
                this.status(p, "§7isst");
                this.applyKeys(mc);
                return;
            }
            if (this.collectLoot(mc, p)) {
                this.status(p, "§7sammelt Beute ein");
                this.applyKeys(mc);
                return;
            }
            this.status(p, "§7wartet auf ein Ziel");
            this.applyKeys(mc);
            return;
        }

        if (this.pattern != null) {
            this.attemptTicks++;
            this.phaseTicks++;
            if (this.attemptTarget != t || this.attemptTicks > 500) {
                this.finishAttempt(mc);
            }
        }
        if (this.pattern == null) {
            this.choosePattern(mc, p, t);
        }
        if (this.pattern != null) {
            this.tickPattern(mc, p, t);
        }
        this.tickStuck(mc, p);
        this.status(p, "§c⚔ " + t.getName().getString() + " §7| " + (this.pattern == null ? "-" : this.pattern.label)
                + " §7| Kit " + Kit.describeSignature(this.kitSignature(p)));
        this.applyKeys(mc);
    }

    private void refreshTarget(Minecraft mc, LocalPlayer p) {
        if (this.target != null && (!this.target.isAlive() || this.target.isRemoved() || this.target.level() != p.level()
                || p.distanceToSqr(this.target) > 160.0 * 160.0)) {
            if (!this.target.isAlive()) {
                this.say(mc, "§a✔ " + this.target.getName().getString() + " erledigt.");
            }
            this.target = null;
        }
        if (this.target == null && this.targetMode != TargetMode.MANUAL) {
            AABB box = p.getBoundingBox().inflate(this.targetMode == TargetMode.MOBS ? 24.0 : 96.0);
            Entity best = null;
            double bestDist = Double.MAX_VALUE;
            for (Entity e : mc.level.getEntities(p, box)) {
                boolean fits = this.targetMode == TargetMode.MOBS
                        ? e instanceof Enemy && e instanceof LivingEntity
                        : e instanceof Player other && !other.isSpectator() && !other.isCreative();
                if (fits && e.isAlive() && p.distanceToSqr(e) < bestDist) {
                    best = e;
                    bestDist = p.distanceToSqr(e);
                }
            }
            this.target = best;
        }
    }

    // ------------------------------------------------------------------ choosing

    private String kitSignature(LocalPlayer p) {
        List<ItemStack> items = new ArrayList<>(p.getInventory().getNonEquipmentItems());
        items.add(p.getItemBySlot(EquipmentSlot.CHEST));
        items.add(p.getItemBySlot(EquipmentSlot.OFFHAND));
        return Kit.signature(items);
    }

    private BotBrain.Context context(LocalPlayer p, LivingEntity t) {
        BotBrain.Env env = p.isInWater() ? BotBrain.Env.WATER : this.ceiling(p, 12) <= 10 ? BotBrain.Env.CAVE : BotBrain.Env.OPEN;
        double hDist = p.position().subtract(t.position()).horizontalDistance();
        boolean inAir = t.isFallFlying() || !t.onGround() && t.getY() - p.getY() > 4.0;
        return new BotBrain.Context(env, BotBrain.Range.of(hDist), inAir, t instanceof Player, this.kitSignature(p));
    }

    private int ceiling(LocalPlayer p, int max) {
        BlockPos pos = p.blockPosition();
        for (int i = 2; i <= max; i++) {
            if (!p.level().getBlockState(pos.above(i)).getCollisionShape(p.level(), pos.above(i)).isEmpty()) {
                return i;
            }
        }
        return max + 1;
    }

    private boolean canFlyHere(LocalPlayer p) {
        return this.has(p, Role.ELYTRA) && this.has(p, Role.ROCKET) && !p.isInWater()
                && p.level().canSeeSky(p.blockPosition().above()) && this.flightCooldown == 0;
    }

    private List<Pattern> feasible(LocalPlayer p, LivingEntity t) {
        double hDist = p.position().subtract(t.position()).horizontalDistance();
        double dy = t.getY() - p.getY();
        boolean sees = p.hasLineOfSight(t);
        boolean flying = p.isFallFlying();
        List<Pattern> out = new ArrayList<>();
        boolean mace = this.has(p, Role.MACE);
        boolean spear = this.has(p, Role.SPEAR);
        if (mace) {
            out.add(Pattern.MACE_MELEE);
        }
        if (spear) {
            out.add(Pattern.SPEAR_KITE);
        }
        if (this.has(p, Role.SWORD) || this.has(p, Role.AXE) || this.has(p, Role.TRIDENT) || out.isEmpty()) {
            out.add(Pattern.BLADE_MELEE);
        }
        if ((this.has(p, Role.BOW) || this.has(p, Role.CROSSBOW)) && this.has(p, Role.ARROW) && sees && hDist > 2.5) {
            out.add(Pattern.BOW_SNIPE);
        }
        if (!flying && mace && this.has(p, Role.WIND_CHARGE) && p.onGround() && this.windCooldown == 0 && sees
                && hDist > 1.0 && hDist < 8.0 && dy < 3.0 && dy > -4.0 && this.ceiling(p, 8) > 7) {
            out.add(Pattern.WIND_SMASH);
        }
        if (!flying && spear && p.onGround() && this.spearCooldown == 0 && sees && hDist > 4.0 && hDist < 18.0) {
            out.add(Pattern.SPEAR_CHARGE);
        }
        if (flying || this.canFlyHere(p) && p.onGround() && hDist > 5.0) {
            if (mace && this.hasChestArmor(p)) {
                out.add(Pattern.ELYTRA_DIVE);
            }
            if (spear) {
                out.add(Pattern.ELYTRA_LANCE);
            }
        }
        List<Pattern> allowed = new ArrayList<>(out);
        allowed.removeIf(x -> this.tabuUntil.getOrDefault(x, 0L) > this.ticks);
        return allowed.isEmpty() ? out : allowed;
    }

    private void choosePattern(Minecraft mc, LocalPlayer p, LivingEntity t) {
        BotBrain.Context ctx = this.context(p, t);
        List<Pattern> options = this.feasible(p, t);
        if (options.isEmpty()) {
            return;
        }
        Pattern chosen = BotBrain.INSTANCE.choose(ctx, options, p.getRandom());
        if (p.isFallFlying() && !chosen.aerial()) {
            // Fighting on foot now: glide down first.
            this.landIfFlying(mc, p);
            if (p.isFallFlying()) {
                return;
            }
        }
        this.pattern = chosen;
        this.attemptContext = ctx;
        this.attemptTarget = t;
        this.attemptTargetHp = t.getHealth() + t.getAbsorptionAmount();
        this.attemptTaken = 0.0F;
        this.attemptTicks = 0;
        this.phase = p.isFallFlying() && chosen.aerial() ? 3 : 0;
        this.phaseTicks = 0;
        this.shots = 0;
        LOGGER.info("[AUTOPILOT] try {} ({})", chosen.label, ctx.describe());
    }

    private void finishAttempt(Minecraft mc) {
        Pattern done = this.pattern;
        BotBrain.Context ctx = this.attemptContext;
        this.pattern = null;
        this.kUse = false;
        if (done == null || ctx == null) {
            return;
        }
        LivingEntity t = this.attemptTarget;
        boolean killed = t != null && (!t.isAlive() || t.isRemoved() && t.getHealth() <= 0.0F);
        float hpNow = t == null ? this.attemptTargetHp : killed ? 0.0F : t.getHealth() + t.getAbsorptionAmount();
        double dealt = Math.max(0.0, this.attemptTargetHp - hpNow);
        double seconds = this.attemptTicks / 20.0;
        double score = (dealt + (killed ? 8.0 : 0.0) - 0.8 * this.attemptTaken) / (seconds + 1.5);
        BotBrain.Lesson lesson = BotBrain.INSTANCE.learn(ctx, done, score);
        if (lesson.flop()) {
            this.tabuUntil.put(done, this.ticks + 200L);
        }
        LOGGER.info(String.format("[AUTOPILOT] learned %s: dealt=%.1f taken=%.1f time=%.1fs -> score=%.1f value=%.1f%s",
                done.label, dealt, this.attemptTaken, seconds, score, lesson.value(), lesson.newFavourite() ? " NEW FAVOURITE" : ""));
        if (lesson.newFavourite()) {
            this.say(mc, String.format("§bGelernt: §f%s§7 → §a%s§7 (Wert %.1f)", ctx.describe(), done.label, lesson.value()));
        }
    }

    // ------------------------------------------------------------------ patterns

    private void tickPattern(Minecraft mc, LocalPlayer p, LivingEntity t) {
        switch (this.pattern) {
            case MACE_MELEE, BLADE_MELEE -> this.tickMelee(mc, p, t);
            case SPEAR_KITE -> this.tickSpearKite(mc, p, t);
            case SPEAR_CHARGE -> this.tickSpearCharge(mc, p, t);
            case WIND_SMASH -> this.tickWindSmash(mc, p, t);
            case ELYTRA_DIVE, ELYTRA_LANCE -> this.tickFlight(mc, p, t);
            case BOW_SNIPE -> this.tickBow(mc, p, t);
        }
    }

    private void tickMelee(Minecraft mc, LocalPlayer p, LivingEntity t) {
        if (this.pattern == Pattern.MACE_MELEE) {
            this.select(mc, p, Role.MACE);
        } else {
            this.selectBestBlade(mc, p);
        }
        this.faceEntity(p, t, 40.0F);
        double dist = p.distanceTo(t);
        if (dist > 2.7) {
            this.kForward = true;
            this.kSprint = true;
            if (p.horizontalCollision || t.getY() - p.getY() > 0.6) {
                this.kJump = p.onGround();
            }
        } else {
            this.strafeAround(p, dist < 1.6);
        }
        boolean ready = p.getAttackStrengthScale(0.5F) >= 0.93F;
        if (ready && dist <= 3.0 && p.hasLineOfSight(t)) {
            if (p.onGround() && !p.isInWater()) {
                // Jump first so the hit lands as a critical hit on the way down.
                this.kJump = true;
            } else if (p.getDeltaMovement().y < -0.05 || p.isInWater()) {
                this.attack(mc, p, t);
            }
        }
        if (this.attemptTicks > 50) {
            this.finishAttempt(mc);
        }
    }

    private void tickSpearKite(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.select(mc, p, Role.SPEAR);
        this.faceEntity(p, t, 40.0F);
        double dist = p.distanceTo(t);
        if (dist > 4.0) {
            this.kForward = true;
            this.kSprint = true;
        } else {
            this.strafeAround(p, dist < 2.8);
        }
        if (p.getAttackStrengthScale(0.5F) >= 0.9F && dist <= 4.5 && p.hasLineOfSight(t)) {
            this.attack(mc, p, t);
        }
        if (this.attemptTicks > 50) {
            this.finishAttempt(mc);
        }
    }

    private void tickSpearCharge(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.select(mc, p, Role.SPEAR);
        this.faceEntity(p, t, 30.0F);
        double dist = p.distanceTo(t);
        if (this.phase == 0) {
            // Get a run-up.
            if (dist < 8.0 && this.phaseTicks < 30) {
                this.kBack = true;
            } else {
                this.nextPhase();
            }
        } else {
            this.kUse = true;
            this.kForward = true;
            this.kSprint = true;
            if (p.horizontalCollision) {
                this.kJump = true;
            }
            if (this.phaseTicks > 60 || dist < 1.2) {
                this.kUse = false;
                this.spearCooldown = 40;
                this.finishAttempt(mc);
            }
        }
    }

    private void tickWindSmash(Minecraft mc, LocalPlayer p, LivingEntity t) {
        switch (this.phase) {
            case 0 -> {
                if (!this.select(mc, p, Role.WIND_CHARGE)) {
                    this.finishAttempt(mc);
                    return;
                }
                this.lookAt(p, p.getYRot(), 90.0F, 180.0F);
                this.kJump = true;
                this.nextPhase();
            }
            case 1 -> {
                this.lookAt(p, p.getYRot(), 90.0F, 180.0F);
                if (!p.onGround() || this.phaseTicks > 3) {
                    // Throw the wind charge at our own feet: it launches us up.
                    this.useItemOnce(mc);
                    this.windCooldown = 30;
                    this.nextPhase();
                }
            }
            default -> {
                this.select(mc, p, Role.MACE);
                this.faceEntity(p, t, 60.0F);
                double hDist = p.position().subtract(t.position()).horizontalDistance();
                this.kForward = hDist > 0.8;
                if (!p.onGround() && p.getDeltaMovement().y < 0.0 && p.fallDistance > 1.5 && p.distanceTo(t) <= 3.3) {
                    this.attack(mc, p, t);
                }
                if (p.onGround() && this.phaseTicks > 5 || this.phaseTicks > 80) {
                    this.finishAttempt(mc);
                }
            }
        }
    }

    private void tickFlight(Minecraft mc, LocalPlayer p, LivingEntity t) {
        boolean lance = this.pattern == Pattern.ELYTRA_LANCE;
        Vec3 toTarget = t.position().subtract(p.position());
        double hDist = toTarget.horizontalDistance();
        double speed = p.getDeltaMovement().length();
        switch (this.phase) {
            case 0 -> {
                // Put the elytra on and jump.
                if (!this.wearChest(mc, p, Role.ELYTRA)) {
                    this.finishAttempt(mc);
                    return;
                }
                this.kJump = true;
                this.nextPhase();
            }
            case 1 -> this.nextPhase(); // release jump for a tick
            case 2 -> {
                this.kJump = true; // second jump in the air opens the elytra
                if (p.isFallFlying()) {
                    this.nextPhase();
                } else if (this.phaseTicks > 12) {
                    this.wearChest(mc, p, Role.ARMOR);
                    this.flightCooldown = 100;
                    this.finishAttempt(mc);
                }
            }
            case 3 -> {
                // Climb above the target.
                this.select(mc, p, lance ? Role.SPEAR : Role.MACE);
                double wantY = t.getY() + (lance ? 10.0 : 24.0);
                Vec3 dir = hDist < 14.0 ? toTarget.multiply(-1.0, 0.0, -1.0) : toTarget.multiply(1.0, 0.0, 1.0);
                this.face(p, dir.normalize().scale(10.0).add(0.0, Mth.clamp(wantY - p.getY(), -5.0, 9.0), 0.0), 15.0F);
                this.boost(mc, p, speed < 1.3 || p.getXRot() < -15.0F);
                if (p.getY() >= wantY - 3.0 && hDist >= 14.0 || p.getY() >= wantY + 6.0) {
                    this.nextPhase();
                }
                this.checkLanded(mc, p);
            }
            case 4 -> {
                if (lance) {
                    this.select(mc, p, Role.SPEAR);
                    double dist = p.distanceTo(t);
                    Vec3 aim = t.getBoundingBox().getCenter().add(t.getDeltaMovement().scale(Math.min(10.0, dist / Math.max(0.8, speed))));
                    double wantY = hDist > 14.0 ? t.getY() + 1.5 + (hDist - 14.0) * 0.35 : aim.y;
                    this.face(p, new Vec3(aim.x - p.getX(), wantY - p.getEyeY(), aim.z - p.getZ()), 25.0F);
                    this.boost(mc, p, speed < 1.6);
                    this.kUse = dist < 24.0;
                    if (dist < 2.5) {
                        this.nextPhase();
                    }
                } else {
                    this.select(mc, p, Role.MACE);
                    Vec3 lead = t.getDeltaMovement().multiply(1.0, 0.0, 1.0).scale(hDist / Math.max(0.8, speed));
                    Vec3 above = t.position().add(lead).add(0.0, 24.0, 0.0).subtract(p.position());
                    this.face(p, new Vec3(above.x, Mth.clamp(above.y, -4.0, 4.0), above.z), 15.0F);
                    this.boost(mc, p, speed < 1.0 && hDist > 20.0);
                    if (hDist < 2.0 + p.getDeltaMovement().horizontalDistance() * 5.0) {
                        // Take the elytra off mid-air: we fall straight onto the target and smash.
                        this.wearChest(mc, p, Role.ARMOR);
                        this.nextPhase();
                    }
                }
                this.checkLanded(mc, p);
            }
            default -> {
                if (lance) {
                    // Passed through: pull up, then decide again.
                    this.face(p, p.getDeltaMovement().multiply(1.0, 0.0, 1.0).add(0.0, 0.7, 0.0), 25.0F);
                    this.boost(mc, p, true);
                    if (this.phaseTicks > 20) {
                        this.finishAttempt(mc);
                    }
                } else {
                    this.select(mc, p, Role.MACE);
                    this.faceEntity(p, t, 60.0F);
                    this.kForward = hDist > 0.8;
                    if (p.getDeltaMovement().y < 0.0 && p.fallDistance > 1.5 && p.distanceTo(t) <= 3.3) {
                        this.attack(mc, p, t);
                    }
                    if (p.onGround() && this.phaseTicks > 3 || this.phaseTicks > 160) {
                        this.finishAttempt(mc);
                    }
                }
            }
        }
    }

    private void checkLanded(Minecraft mc, LocalPlayer p) {
        if (!p.isFallFlying() && p.onGround() && this.phaseTicks > 5) {
            this.wearChest(mc, p, Role.ARMOR);
            this.flightCooldown = 60;
            this.finishAttempt(mc);
        }
    }

    private void tickBow(Minecraft mc, LocalPlayer p, LivingEntity t) {
        if (!this.select(mc, p, Role.BOW) && !this.select(mc, p, Role.CROSSBOW)) {
            this.finishAttempt(mc);
            return;
        }
        double dist = p.distanceTo(t);
        // Aim with lead and arrow drop.
        Vec3 aim = t.getBoundingBox().getCenter().add(t.getDeltaMovement().multiply(1.0, 0.0, 1.0).scale(dist / 3.0));
        Vec3 dir = aim.subtract(p.getEyePosition());
        double h = dir.horizontalDistance();
        this.face(p, new Vec3(dir.x, dir.y + h * h / 330.0, dir.z), 30.0F);
        if (dist < 7.0) {
            this.kBack = true;
        } else if (dist > 24.0 || !p.hasLineOfSight(t)) {
            this.kForward = true;
        } else {
            this.strafeAround(p, false);
        }
        if (p.isUsingItem() && p.getTicksUsingItem() >= 22) {
            this.kUse = false; // release: shoot
            if (++this.shots >= 3) {
                this.finishAttempt(mc);
            }
        } else {
            this.kUse = true;
        }
        if (this.attemptTicks > 100) {
            this.finishAttempt(mc);
        }
    }

    // ------------------------------------------------------------------ survival helpers

    private boolean eatIfLow(Minecraft mc, LocalPlayer p, @Nullable LivingEntity t) {
        if (this.eatTicks > 0) {
            this.eatTicks--;
            if (this.select(mc, p, Role.GAPPLE)) {
                this.kUse = true;
                this.kBack = t != null && p.distanceTo(t) < 6.0;
                if (t != null) {
                    this.faceEntity(p, t, 30.0F);
                }
                return true;
            }
            this.eatTicks = 0;
        }
        if (p.getHealth() < 9.0F && !p.isFallFlying() && this.has(p, Role.GAPPLE) && !p.hasEffect(net.minecraft.world.effect.MobEffects.REGENERATION)) {
            this.eatTicks = 36;
            this.finishAttempt(mc);
        }
        return false;
    }

    private int hungerEatTicks;

    /** Out of combat: eat normal food when hungry, so health keeps regenerating. */
    private boolean eatWhenHungry(Minecraft mc, LocalPlayer p) {
        if (this.hungerEatTicks > 0) {
            this.hungerEatTicks--;
            this.kUse = true;
            return true;
        }
        if (p.getFoodData().getFoodLevel() >= 14) {
            return false;
        }
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        for (int i = 0; i < items.size(); i++) {
            ItemStack stack = items.get(i);
            if (stack.has(net.minecraft.core.component.DataComponents.FOOD) && Kit.classify(stack) != Role.GAPPLE) {
                int slot = this.toHotbar(mc, p, i);
                if (slot >= 0) {
                    p.getInventory().setSelectedSlot(slot);
                    this.hungerEatTicks = 36;
                    this.kUse = true;
                    return true;
                }
            }
        }
        return false;
    }

    /** Out of combat: walk over dropped items nearby (loot of kills) to pick them up. */
    private boolean collectLoot(Minecraft mc, LocalPlayer p) {
        net.minecraft.world.entity.item.ItemEntity closest = null;
        double best = 12.0 * 12.0;
        for (net.minecraft.world.entity.item.ItemEntity item : p.level().getEntitiesOfClass(net.minecraft.world.entity.item.ItemEntity.class,
                p.getBoundingBox().inflate(12.0))) {
            double d = p.distanceToSqr(item);
            if (item.isAlive() && d < best && Math.abs(item.getY() - p.getY()) < 3.0) {
                closest = item;
                best = d;
            }
        }
        if (closest == null) {
            return false;
        }
        this.face(p, closest.position().subtract(p.getEyePosition()).multiply(1.0, 0.0, 1.0), 30.0F);
        this.kForward = true;
        this.kSprint = best > 16.0;
        if (p.horizontalCollision) {
            this.kJump = true;
        }
        return true;
    }

    private void keepTotemInOffhand(Minecraft mc, LocalPlayer p) {
        if (this.ticks % 10 != 0 || Kit.classify(p.getItemBySlot(EquipmentSlot.OFFHAND)) == Role.TOTEM) {
            return;
        }
        int slot = this.findInventory(p, Role.TOTEM);
        if (slot >= 0) {
            // Button 40 = swap with off hand, like pressing F in the inventory.
            this.click(mc, p, menuSlot(slot), 40);
        }
    }

    private void landIfFlying(Minecraft mc, LocalPlayer p) {
        if (!p.isFallFlying()) {
            return;
        }
        // Glide down gently; landing closes the elytra.
        this.lookAt(p, p.getYRot(), 25.0F, 10.0F);
        if (p.onGround()) {
            this.wearChest(mc, p, Role.ARMOR);
        }
    }

    // ------------------------------------------------------------------ getting unstuck

    private void tickStuck(Minecraft mc, LocalPlayer p) {
        if (this.unstuckTicks > 0) {
            this.unstuckTicks--;
            if (this.unstuckMode == 1) {
                this.kJump = true;
                this.kForward = true;
                if (this.strafe > 0) this.kLeft = true; else this.kRight = true;
            } else {
                this.digForward(mc, p);
            }
            return;
        }
        boolean wantsToMove = this.kForward || p.isFallFlying();
        if (!wantsToMove) {
            this.stuckTicks = 0;
            this.stuckAnchor = null;
            return;
        }
        if (this.stuckAnchor == null || p.position().distanceToSqr(this.stuckAnchor) > 0.5) {
            this.stuckAnchor = p.position();
            this.stuckTicks = 0;
            return;
        }
        if (++this.stuckTicks > (p.isFallFlying() ? 15 : 30)) {
            this.stuckTicks = 0;
            this.attemptTaken += 3.0F;
            if (p.isFallFlying()) {
                this.wearChest(mc, p, Role.ARMOR);
                this.flightCooldown = 100;
                this.finishAttempt(mc);
            }
            this.unstuckMode = this.unstuckMode == 1 ? 2 : 1;
            this.unstuckTicks = this.unstuckMode == 1 ? 12 : 40;
            this.strafe = -this.strafe;
            LOGGER.info("[AUTOPILOT] stuck -> {}", this.unstuckMode == 1 ? "jump aside" : "dig");
        }
    }

    private void digForward(Minecraft mc, LocalPlayer p) {
        // Look at the block in front (feet or head height) and hold attack to mine it.
        Vec3 look = Vec3.directionFromRotation(0.0F, p.getYRot());
        BlockPos feet = BlockPos.containing(p.position().add(look.scale(0.8)));
        BlockPos head = feet.above();
        BlockPos block = !p.level().getBlockState(head).isAir() ? head : feet;
        Vec3 center = Vec3.atCenterOf(block);
        this.face(p, center.subtract(p.getEyePosition()), 45.0F);
        if (mc.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
            this.kAttack = true;
        }
        this.kForward = true;
    }

    // ------------------------------------------------------------------ inventory

    private static int menuSlot(int inventoryIndex) {
        // Inventory menu: hotbar 0-8 are slots 36-44, the rest 9-35 keep their index.
        return inventoryIndex < 9 ? 36 + inventoryIndex : inventoryIndex;
    }

    private void click(Minecraft mc, LocalPlayer p, int slot, int button) {
        mc.gameMode.handleContainerInput(p.inventoryMenu.containerId, slot, button, ContainerInput.SWAP, p);
    }

    private int findInventory(LocalPlayer p, Role role) {
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        for (int i = 0; i < items.size(); i++) {
            if (Kit.classify(items.get(i)) == role) {
                return i;
            }
        }
        return -1;
    }

    private boolean has(LocalPlayer p, Role role) {
        return this.findInventory(p, role) >= 0 || role == Role.ELYTRA && Kit.classify(p.getItemBySlot(EquipmentSlot.CHEST)) == Role.ELYTRA;
    }

    private boolean hasChestArmor(LocalPlayer p) {
        for (ItemStack stack : p.getInventory().getNonEquipmentItems()) {
            if (Kit.armorSlot(stack) == EquipmentSlot.CHEST && Kit.classify(stack) == Role.ARMOR) {
                return true;
            }
        }
        return Kit.classify(p.getItemBySlot(EquipmentSlot.CHEST)) == Role.ARMOR;
    }

    /** Makes sure an item of that role is in the hotbar and returns its hotbar slot (or -1). */
    private int toHotbar(Minecraft mc, LocalPlayer p, int inventoryIndex) {
        if (inventoryIndex < 0) {
            return -1;
        }
        if (inventoryIndex < 9) {
            return inventoryIndex;
        }
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        int free = 8;
        for (int i = 0; i < 9; i++) {
            if (items.get(i).isEmpty()) {
                free = i;
                break;
            }
        }
        this.click(mc, p, menuSlot(inventoryIndex), free);
        return free;
    }

    private boolean select(Minecraft mc, LocalPlayer p, Role role) {
        int slot = this.toHotbar(mc, p, this.findInventory(p, role));
        if (slot < 0) {
            return false;
        }
        if (p.getInventory().getSelectedSlot() != slot) {
            this.kUse = false;
            p.getInventory().setSelectedSlot(slot);
        }
        return true;
    }

    private void selectBestBlade(Minecraft mc, LocalPlayer p) {
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        int best = -1;
        double bestDamage = 0.0;
        for (int i = 0; i < items.size(); i++) {
            Role role = Kit.classify(items.get(i));
            if ((role == Role.SWORD || role == Role.AXE || role == Role.TRIDENT) && Kit.attackDamage(items.get(i)) > bestDamage) {
                best = i;
                bestDamage = Kit.attackDamage(items.get(i));
            }
        }
        int slot = this.toHotbar(mc, p, best);
        if (slot >= 0 && p.getInventory().getSelectedSlot() != slot) {
            p.getInventory().setSelectedSlot(slot);
        }
    }

    /** Swaps the chest slot to an elytra (ELYTRA) or the best chestplate (ARMOR). */
    private boolean wearChest(Minecraft mc, LocalPlayer p, Role role) {
        ItemStack worn = p.getItemBySlot(EquipmentSlot.CHEST);
        if (role == Role.ELYTRA ? Kit.classify(worn) == Role.ELYTRA : Kit.classify(worn) == Role.ARMOR) {
            return true;
        }
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        int index = -1;
        double best = -1.0;
        for (int i = 0; i < items.size(); i++) {
            ItemStack stack = items.get(i);
            if (role == Role.ELYTRA ? Kit.classify(stack) == Role.ELYTRA
                    : Kit.classify(stack) == Role.ARMOR && Kit.armorSlot(stack) == EquipmentSlot.CHEST && Kit.armorValue(stack, EquipmentSlot.CHEST) > best) {
                index = i;
                best = Kit.armorValue(stack, EquipmentSlot.CHEST);
                if (role == Role.ELYTRA) {
                    break;
                }
            }
        }
        int hotbar = this.toHotbar(mc, p, index);
        if (hotbar < 0) {
            return false;
        }
        // Menu slot 6 is the chest armor slot.
        this.click(mc, p, 6, hotbar);
        return true;
    }

    // ------------------------------------------------------------------ actions

    private void attack(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.faceEntity(p, t, 180.0F);
        mc.hitResult = p.raycastHitResult(1.0F, p);
        ((MinecraftInvoker) mc).pvpbot$startAttack();
    }

    private void useItemOnce(Minecraft mc) {
        if (mc.player != null) {
            mc.hitResult = mc.player.raycastHitResult(1.0F, mc.player);
        }
        ((MinecraftInvoker) mc).pvpbot$startUseItem();
    }

    private void boost(Minecraft mc, LocalPlayer p, boolean wanted) {
        if (!wanted || this.rocketCooldown > 0 || !p.isFallFlying()) {
            return;
        }
        int previous = p.getInventory().getSelectedSlot();
        if (this.select(mc, p, Role.ROCKET)) {
            this.useItemOnce(mc);
            p.getInventory().setSelectedSlot(previous);
            this.rocketCooldown = 25;
        }
    }

    private void nextPhase() {
        this.phase++;
        this.phaseTicks = 0;
    }

    private void strafeAround(LocalPlayer p, boolean backOff) {
        if (p.getRandom().nextInt(25) == 0) {
            this.strafe = -this.strafe;
        }
        if (this.strafe > 0) this.kLeft = true; else this.kRight = true;
        this.kBack = backOff;
    }

    private void faceEntity(LocalPlayer p, LivingEntity t, float maxTurn) {
        Vec3 aim = new Vec3(t.getX(), t.getY() + t.getBbHeight() * 0.6, t.getZ());
        this.face(p, aim.subtract(p.getEyePosition()), maxTurn);
    }

    private void face(LocalPlayer p, Vec3 dir, float maxTurn) {
        if (dir.lengthSqr() < 1.0E-6) {
            return;
        }
        float yaw = (float) (Mth.atan2(dir.z, dir.x) * (180.0 / Math.PI)) - 90.0F;
        float pitch = (float) -(Mth.atan2(dir.y, dir.horizontalDistance()) * (180.0 / Math.PI));
        this.lookAt(p, yaw, pitch, maxTurn);
    }

    private void lookAt(LocalPlayer p, float yaw, float pitch, float maxTurn) {
        float dy = Mth.wrapDegrees(yaw - p.getYRot());
        float dp = Mth.clamp(pitch, -90.0F, 90.0F) - p.getXRot();
        p.setYRot(p.getYRot() + Mth.clamp(dy, -maxTurn, maxTurn));
        p.setXRot(Mth.clamp(p.getXRot() + Mth.clamp(dp, -maxTurn, maxTurn), -90.0F, 90.0F));
    }

    // ------------------------------------------------------------------ keys

    private void clearKeys() {
        this.kForward = this.kBack = this.kLeft = this.kRight = this.kJump = this.kSprint = this.kSneak = this.kAttack = false;
        // kUse is kept between ticks: patterns release it explicitly (bow, spear, eating).
    }

    private void applyKeys(Minecraft mc) {
        Options o = mc.options;
        o.keyUp.setDown(this.kForward);
        o.keyDown.setDown(this.kBack);
        o.keyLeft.setDown(this.kLeft);
        o.keyRight.setDown(this.kRight);
        // A fresh press is needed to open the elytra, so never hold jump two ticks in a row mid-air.
        boolean jump = this.kJump && !(this.wasJump && mc.player != null && !mc.player.onGround() && !mc.player.isFallFlying());
        o.keyJump.setDown(jump);
        this.wasJump = jump;
        o.keySprint.setDown(this.kSprint);
        o.keyShift.setDown(this.kSneak);
        o.keyUse.setDown(this.kUse);
        o.keyAttack.setDown(this.kAttack);
        this.keysHeld = true;
    }

    private void releaseKeys(Minecraft mc) {
        Options o = mc.options;
        o.keyUp.setDown(false);
        o.keyDown.setDown(false);
        o.keyLeft.setDown(false);
        o.keyRight.setDown(false);
        o.keyJump.setDown(false);
        o.keySprint.setDown(false);
        o.keyShift.setDown(false);
        o.keyUse.setDown(false);
        o.keyAttack.setDown(false);
        this.kUse = false;
        this.keysHeld = false;
    }

    private void status(LocalPlayer p, String text) {
        this.lastStatus = text;
        if (this.ticks % 10 == 0) {
            p.sendOverlayMessage(Component.literal(text));
        }
    }

    void say(Minecraft mc, String text) {
        if (mc.player != null) {
            mc.player.sendSystemMessage(Component.literal("§6[Autopilot] §r" + text));
        }
    }
}
