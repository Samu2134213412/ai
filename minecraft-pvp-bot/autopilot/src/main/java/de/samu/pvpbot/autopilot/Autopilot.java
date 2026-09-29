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
import net.minecraft.core.component.DataComponents;
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
import net.minecraft.world.item.component.KineticWeapon;
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
    private int useTicks;
    /** Trick asked for with /autopilot trick: used as soon as it is possible. */
    private @Nullable Pattern forcedPattern;
    private int forcedTicks;
    /** The smash of this attempt was already swung (no more attribute swaps back and forth). */
    private boolean smashed;
    // Extra tactics.
    private int wtapTicks;
    private int pearlCooldown;
    private int waterPickupTicks;
    private int drinkTicks;
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

    public void forcePattern(Pattern pattern) {
        this.forcedPattern = pattern;
        this.forcedTicks = 0;
    }

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
        if (this.pearlCooldown > 0) this.pearlCooldown--;
        if (this.waterClutch(mc, p, t)) {
            this.status(p, "§bWassereimer-Clutch");
            this.applyKeys(mc);
            return;
        }
        if (this.drinkPotion(mc, p, t)) {
            this.status(p, "§dtrinkt");
            this.applyKeys(mc);
            return;
        }
        if (this.eatIfLow(mc, p, t)) {
            this.applyKeys(mc);
            return;
        }
        if (t == null) {
            this.finishAttempt(mc);
            this.landIfFlying(mc, p);
            if (AutopilotSettings.INSTANCE.autoEat && this.eatWhenHungry(mc, p)) {
                this.status(p, "§7isst");
                this.applyKeys(mc);
                return;
            }
            if (AutopilotSettings.INSTANCE.lootPickup && this.collectLoot(mc, p)) {
                this.status(p, "§7sammelt Beute ein");
                this.applyKeys(mc);
                return;
            }
            this.status(p, "§7wartet auf ein Ziel");
            this.applyKeys(mc);
            return;
        }

        if (this.trackSight(mc, p, t)) {
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
        if (this.pattern == null && this.hungerEatTicks > 0
                || this.pattern == null && p.getFoodData().getFoodLevel() <= 6 && p.onGround() && p.distanceTo(t) > 7.0) {
            // Too hungry to sprint or lunge: eat quickly while the enemy is not right here.
            if (AutopilotSettings.INSTANCE.autoEat && this.eatWhenHungry(mc, p)) {
                this.status(p, "§7isst (für Sprint/Lunge)");
                this.applyKeys(mc);
                return;
            }
        }
        if (this.pattern == null && this.throwPearl(mc, p, t)) {
            this.applyKeys(mc);
            return;
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

    private @Nullable Vec3 lastSeen;
    private int unseenTicks;
    private @Nullable Entity sightOf;

    /**
     * No wallhacks: we only know where the target is while we see it. Out of sight we walk to where
     * it was last seen, and give up if it is not there. Returns true while searching.
     */
    private boolean trackSight(Minecraft mc, LocalPlayer p, LivingEntity t) {
        if (this.sightOf != t) {
            this.sightOf = t;
            this.lastSeen = null;
            this.unseenTicks = 0;
        }
        if (p.hasLineOfSight(t)) {
            this.lastSeen = t.position();
            this.unseenTicks = 0;
            return false;
        }
        this.unseenTicks++;
        if (p.isFallFlying() || this.unseenTicks <= 40 && this.lastSeen != null) {
            return false;
        }
        boolean there = this.lastSeen != null && p.position().distanceToSqr(this.lastSeen) < 2.5;
        if (this.lastSeen == null || this.unseenTicks > 300 || there && this.unseenTicks > 120) {
            this.say(mc, "§7" + t.getName().getString() + (this.lastSeen == null ? " ist nicht in Sicht." : " aus den Augen verloren."));
            this.finishAttempt(mc);
            this.target = null;
            this.sightOf = null;
            return true;
        }
        this.finishAttempt(mc);
        this.face(p, this.lastSeen.subtract(p.getEyePosition()).multiply(1.0, 0.0, 1.0), 25.0F);
        this.kForward = !there;
        this.kSprint = !there;
        if (p.horizontalCollision && p.onGround()) {
            this.kJump = true;
        }
        this.status(p, "§7sucht " + t.getName().getString() + " (zuletzt gesehen)");
        return true;
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
            AABB box = p.getBoundingBox().inflate(this.targetMode == TargetMode.MOBS ? 24.0 : 64.0);
            Entity best = null;
            double bestDist = Double.MAX_VALUE;
            for (Entity e : mc.level.getEntities(p, box)) {
                boolean fits = this.targetMode == TargetMode.MOBS
                        ? e instanceof Enemy && e instanceof LivingEntity
                        : e instanceof Player other && !other.isSpectator() && !other.isCreative();
                // Only what we can actually see: no finding players through walls.
                if (fits && e.isAlive() && p.distanceToSqr(e) < bestDist && p.hasLineOfSight(e)) {
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
        return AutopilotSettings.INSTANCE.elytra && this.has(p, Role.ELYTRA) && this.has(p, Role.ROCKET) && !p.isInWater()
                && p.level().canSeeSky(p.blockPosition().above()) && this.flightCooldown == 0;
    }

    private List<Pattern> feasible(LocalPlayer p, LivingEntity t) {
        double hDist = p.position().subtract(t.position()).horizontalDistance();
        double dy = t.getY() - p.getY();
        boolean sees = p.hasLineOfSight(t);
        boolean flying = p.isFallFlying();
        List<Pattern> out = new ArrayList<>();
        boolean mace = this.has(p, Role.MACE);
        boolean spear = AutopilotSettings.INSTANCE.spear && this.has(p, Role.SPEAR);
        if (mace) {
            out.add(Pattern.MACE_MELEE);
        }
        if (spear) {
            out.add(Pattern.SPEAR_KITE);
        }
        if (this.has(p, Role.SWORD) || this.has(p, Role.AXE) || this.has(p, Role.TRIDENT) || out.isEmpty()) {
            out.add(Pattern.BLADE_MELEE);
        }
        if (AutopilotSettings.INSTANCE.bow && (this.has(p, Role.BOW) || this.has(p, Role.CROSSBOW)) && this.has(p, Role.ARROW) && sees && hDist > 2.5) {
            out.add(Pattern.BOW_SNIPE);
        }
        if (!flying && mace && AutopilotSettings.INSTANCE.windCharges && this.has(p, Role.WIND_CHARGE) && p.onGround() && this.windCooldown == 0 && sees
                && hDist > 1.0 && hDist < 8.0 && dy < 3.0 && dy > -4.0 && this.ceiling(p, 8) > 7) {
            out.add(Pattern.WIND_SMASH);
        }
        if (!flying && spear && p.onGround() && this.spearCooldown == 0 && sees && hDist < 18.0) {
            out.add(Pattern.SPEAR_CHARGE);
        }
        if (!flying && mace && spear && AutopilotSettings.INSTANCE.windCharges && this.spearLunge(p) > 0 && this.has(p, Role.WIND_CHARGE) && p.onGround() && this.windCooldown == 0
                && sees && hDist > 3.0 && hDist < 12.0 && dy < 3.0 && dy > -4.0 && this.ceiling(p, 8) > 7
                && p.getFoodData().getFoodLevel() > 6) {
            out.add(Pattern.WIND_LUNGE_SMASH);
        }
        if (flying || this.canFlyHere(p) && p.onGround() && hDist > 5.0) {
            if (mace && this.hasChestArmor(p)) {
                out.add(Pattern.ELYTRA_DIVE);
            }
            if (spear) {
                out.add(Pattern.ELYTRA_LANCE);
            }
        }
        if (this.forcedPattern == Pattern.WIND_LUNGE_SMASH && !out.contains(Pattern.WIND_LUNGE_SMASH) && this.ticks % 20 == 0) {
            int spearIndex = this.findInventory(p, Role.SPEAR);
            LOGGER.info("[AUTOPILOT] combo not possible: mace={} spear={} lunge={} ench={} wind={} ground={} windCd={} sees={} hDist={} dy={} ceiling={} food={}",
                    mace, spear, this.spearLunge(p), spearIndex < 0 ? "-" : p.getInventory().getItem(spearIndex).getEnchantments(),
                    this.has(p, Role.WIND_CHARGE), p.onGround(), this.windCooldown, sees, String.format("%.1f", hDist),
                    String.format("%.1f", dy), this.ceiling(p, 8), p.getFoodData().getFoodLevel());
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
        if (this.forcedPattern != null) {
            if (options.contains(this.forcedPattern)) {
                chosen = this.forcedPattern;
                this.forcedPattern = null;
            } else if (++this.forcedTicks > 200) {
                this.say(mc, "§e" + this.forcedPattern.label + " geht gerade nicht (möglich: "
                        + options.stream().map(x -> x.label).toList() + ")");
                this.forcedPattern = null;
            }
        }
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
        this.smashed = false;
        LOGGER.info("[AUTOPILOT] try {} ({})", chosen.label, ctx.describe());
    }

    private void finishAttempt(Minecraft mc) {
        Pattern done = this.pattern;
        BotBrain.Context ctx = this.attemptContext;
        if (done != null && mc.player != null) {
            LOGGER.info("[AUTOPILOT] finish {} in phase {} (fly={}, y={}, caller {})", done.label, this.phase, mc.player.isFallFlying(),
                    String.format("%.1f", mc.player.getY()), StackWalker.getInstance().walk(f -> f.skip(1).findFirst().map(x -> x.getMethodName() + ":" + x.getLineNumber()).orElse("?")));
        }
        this.pattern = null;
        this.kUse = false;
        if (done == null || ctx == null) {
            return;
        }
        LivingEntity t = this.attemptTarget;
        boolean selfDead = mc.player == null || !mc.player.isAlive() || mc.player.getHealth() <= 0.0F;
        if (selfDead) {
            // Our own death: the target vanishing from view says nothing about it being dead.
            this.attemptTaken += 20.0F;
            t = null;
        }
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
            case WIND_SMASH, WIND_LUNGE_SMASH -> this.tickWindSmash(mc, p, t);
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
                Role held = Kit.classify(p.getMainHandItem());
                if (t.isBlocking() && this.has(p, Role.AXE) && held != Role.AXE) {
                    // Attribute swap onto the axe for this hit: it knocks the shield out of their hands.
                    this.swapAttack(mc, p, t, Role.AXE);
                } else if ((held == Role.SWORD || held == Role.AXE) && t.getArmorValue() >= 8 && this.maceBreach(p) > 0) {
                    // Breach swap: the blade's damage with the mace's Breach (ignores part of the armor).
                    this.swapAttack(mc, p, t, Role.MACE);
                } else {
                    this.attack(mc, p, t);
                }
                this.wtapTicks = AutopilotSettings.INSTANCE.wTap ? 2 : 0;
            }
        }
        if (this.wtapTicks > 0) {
            // W-tap: let go of forward/sprint for a moment after a hit, so the next hit is a sprint hit
            // again (extra knockback keeps the enemy from hitting back).
            this.wtapTicks--;
            this.kForward = false;
            this.kSprint = false;
        }
        this.kUse = this.shouldBlock(p, t, ready);
        if (this.attemptTicks > 50) {
            this.finishAttempt(mc);
        }
    }

    // Spear facts (26.3): a jab only hits between 2 and 4.5 blocks and needs a full attack charge.
    // The charge (holding use) deals base damage + closing speed x multiplier, so speed is damage.
    // Lunge throws the wielder forward on every jab (not in water, not while gliding, costs hunger).
    private static final double JAB_MIN = 2.0;
    private static final double JAB_MAX = 4.4;

    /** Hit and run: sprint in, jab at the edge of the reach, run past the target, curve around, repeat. */
    private void tickSpearKite(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.select(mc, p, Role.SPEAR);
        double dist = p.distanceTo(t);
        int lunge = Kit.lungeLevel(p.getMainHandItem());
        boolean canLunge = lunge > 0 && p.onGround() && !p.isInWater() && p.getFoodData().getFoodLevel() > 6;
        boolean ready = p.getAttackStrengthScale(0.5F) >= 1.0F;
        this.kForward = true;
        this.kSprint = true;
        switch (this.phase) {
            case 0 -> {
                // Run in. Sprint-jump on long straight stretches for extra speed.
                this.faceEntity(p, t, 35.0F);
                if (p.onGround() && (dist > 7.0 || p.horizontalCollision)) {
                    this.kJump = true;
                }
                if (ready && dist >= JAB_MIN && dist <= JAB_MAX && p.hasLineOfSight(t)) {
                    this.attack(mc, p, t);
                    this.nextPhase();
                } else if (ready && canLunge && dist > 5.0 && dist < 5.0 + 1.4 * lunge && p.hasLineOfSight(t)) {
                    // Lunge as a gap closer: the jab throws us right into striking distance.
                    this.attack(mc, p, t);
                } else if (dist < JAB_MIN) {
                    // Too close for the spear: keep moving and swing around.
                    this.nextPhase();
                }
            }
            case 1 -> {
                // Run past the target, a little to the side, instead of stopping in front of it.
                Vec3 toT = t.position().subtract(p.position()).multiply(1.0, 0.0, 1.0);
                Vec3 side = new Vec3(-toT.z, 0.0, toT.x).normalize().scale(this.strafe * 2.5);
                this.face(p, toT.add(side), 30.0F);
                this.kLeft = this.strafe < 0;
                this.kRight = this.strafe > 0;
                boolean passed = toT.dot(p.getLookAngle().multiply(1.0, 0.0, 1.0)) < 0.0;
                if (passed && dist > 2.5 || this.phaseTicks > 12) {
                    this.nextPhase();
                }
            }
            default -> {
                // Curve around to get a fresh run-up, then go again.
                Vec3 toT = t.position().subtract(p.position()).multiply(1.0, 0.0, 1.0);
                Vec3 away = toT.scale(-1.0);
                Vec3 side = new Vec3(-toT.z, 0.0, toT.x).normalize().scale(this.strafe * toT.length());
                this.face(p, away.add(side), 35.0F);
                if (p.horizontalCollision) {
                    this.kJump = true;
                }
                // Turn back in as soon as the spear is (almost) recharged and we are in reach again.
                boolean almost = p.getAttackStrengthScale(0.5F) >= 0.8F;
                if (almost && dist >= 3.0 && this.phaseTicks > 3 || dist >= 6.0 || this.phaseTicks > 30) {
                    if (p.getRandom().nextInt(3) == 0) {
                        this.strafe = -this.strafe;
                    }
                    this.phase = 0;
                    this.phaseTicks = 0;
                }
            }
        }
        if (this.attemptTicks > 80) {
            this.finishAttempt(mc);
        }
    }

    /** Couched charge: get a run-up, then sprint(-jump) straight through the target holding the spear. */
    private void tickSpearCharge(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.select(mc, p, Role.SPEAR);
        double dist = p.distanceTo(t);
        switch (this.phase) {
            case 0 -> {
                // Run-up: sprint away until there is room to build up speed.
                this.kUse = false;
                Vec3 away = p.position().subtract(t.position()).multiply(1.0, 0.0, 1.0);
                this.face(p, away, 40.0F);
                this.kForward = true;
                this.kSprint = true;
                if (p.horizontalCollision) {
                    this.kJump = true;
                }
                if (dist >= 7.5 || this.phaseTicks > 30) {
                    this.nextPhase();
                }
            }
            case 1 -> {
                // Turn around.
                this.faceEntity(p, t, 45.0F);
                Vec3 toT = t.getEyePosition().subtract(p.getEyePosition()).normalize();
                if (toT.dot(p.getLookAngle()) > 0.95 || this.phaseTicks > 8) {
                    this.nextPhase();
                }
            }
            case 2 -> {
                // Charge. The damage counts the speed along the look direction, so look straight at the target.
                this.faceEntity(p, t, 25.0F);
                this.kForward = true;
                this.kSprint = true;
                if (p.onGround()) {
                    this.kJump = true;
                }
                KineticWeapon kinetic = p.getMainHandItem().get(DataComponents.KINETIC_WEAPON);
                int delay = kinetic == null ? 0 : kinetic.delayTicks();
                int window = kinetic == null ? 60 : kinetic.computeDamageUseDuration();
                double speed = Math.max(0.15, p.getDeltaMovement().multiply(1.0, 0.0, 1.0).length());
                double eta = Math.max(0.0, dist - 3.0) / speed;
                if (!this.kUse && eta <= window - 4) {
                    this.kUse = true;
                    this.useTicks = 0;
                }
                if (this.kUse) {
                    this.useTicks++;
                }
                boolean hit = t.hurtTime > 0 && this.useTicks > delay;
                if (hit || dist < 1.5 || this.useTicks > window + 2 || this.phaseTicks > 100) {
                    this.nextPhase();
                }
            }
            default -> {
                // Run through and away, then let go.
                Vec3 toT = t.position().subtract(p.position()).multiply(1.0, 0.0, 1.0);
                if (dist < 5.0) {
                    this.face(p, toT.scale(-1.0), 20.0F);
                }
                this.kForward = true;
                this.kSprint = true;
                if (this.phaseTicks > 8) {
                    this.kUse = false;
                    this.spearCooldown = 10;
                    this.finishAttempt(mc);
                }
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
            case 2 -> {
                if (this.pattern != Pattern.WIND_LUNGE_SMASH) {
                    this.nextPhase();
                    return;
                }
                // Combo: keep a charged weapon in hand on the way up and swap to the spear only in the
                // tick of the jab (lunge swap): the jab uses the old weapon's charge, so it is allowed
                // right away, and Lunge throws us across.
                this.holdSmashCarrier(mc, p);
                Vec3 toT = t.position().subtract(p.position());
                this.face(p, new Vec3(toT.x, 0.0, toT.z), 60.0F);
                boolean top = p.getDeltaMovement().y < 0.15;
                if (top) {
                    this.swapAttack(mc, p, t, Role.SPEAR);
                    LOGGER.info("[AUTOPILOT] lunge swap at the top of the wind jump");
                    this.nextPhase();
                } else if (p.getDeltaMovement().y < -0.4 || p.onGround() && this.phaseTicks > 5) {
                    this.nextPhase(); // too late for the lunge, just smash
                }
            }
            default -> {
                this.holdSmashCarrier(mc, p);
                this.faceEntity(p, t, 60.0F);
                double hDist = p.position().subtract(t.position()).horizontalDistance();
                this.kForward = hDist > 0.8;
                double reach = Math.sqrt(t.getBoundingBox().distanceToSqr(p.getEyePosition()));
                if (!p.onGround() && p.getDeltaMovement().y < 0.0 && p.fallDistance > 1.5 && (reach <= 3.0 || p.distanceTo(t) <= 3.3)) {
                    this.smashHit(mc, p, t);
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
                    double height = p.getY() - (t.getY() + t.getBbHeight());
                    Vec3 hVel = p.getDeltaMovement().multiply(1.0, 0.0, 1.0);
                    boolean heading = hVel.dot(toTarget.multiply(1.0, 0.0, 1.0).normalize()) > 0.3 * Math.max(0.1, hVel.length());
                    // Start braking early enough: we keep drifting forward for a while.
                    if (hDist < 3.0 + hVel.length() * 6.0 && heading && height > 8.0) {
                        // Tip over into a steep dive with the elytra still on: while diving the fall
                        // distance keeps growing (smash damage), and a miss just means pulling up.
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
                } else if (this.phase >= 20) {
                    // Pull up after the smash (or a miss) and glide on; landing is handled later.
                    this.face(p, p.getDeltaMovement().multiply(1.0, 0.0, 1.0).normalize().add(0.0, 0.6, 0.0), 45.0F);
                    this.boost(mc, p, speed < 0.9 || this.phaseTicks < 3);
                    if (this.phaseTicks > 20 && p.isFallFlying() && this.shots < 2 && this.attemptTarget != null
                            && this.attemptTarget.isAlive() && this.attemptTarget.hurtTime == 0) {
                        // Missed: climb again and have another go.
                        this.shots++;
                        this.phase = 3;
                        this.phaseTicks = 0;
                    } else if (this.phaseTicks > 20 || !p.isFallFlying()) {
                        this.flightCooldown = 40;
                        this.finishAttempt(mc);
                    }
                } else if (p.isFallFlying() && this.phase < 10) {
                    // Right above the target: pull up hard to bleed off speed, then drop the elytra and
                    // fall straight down onto it (a fast diagonal dive tends to overshoot or arrive too
                    // late for the hit to register).
                    this.select(mc, p, Role.MACE);
                    float yaw = (float) (Mth.atan2(toTarget.z, toTarget.x) * (180.0 / Math.PI)) - 90.0F;
                    this.lookAt(p, yaw, -55.0F, 30.0F);
                    double hSpeed = p.getDeltaMovement().horizontalDistance();
                    if ((hSpeed < 0.3 || this.phaseTicks > 30) && hDist > 3.0 && this.shots < 3) {
                        // Not above the target after braking: go round again instead of dropping beside it.
                        LOGGER.info("[AUTOPILOT] brake missed (hDist={}), going round", String.format("%.1f", hDist));
                        this.shots++;
                        this.phase = 4;
                        this.phaseTicks = 0;
                    } else if (hSpeed < 0.3 || this.phaseTicks > 30) {
                        LOGGER.info("[AUTOPILOT] drop: hSpeed={} hDist={} height={}", String.format("%.2f", hSpeed),
                                String.format("%.1f", hDist), String.format("%.1f", p.getY() - t.getY()));
                        this.wearChest(mc, p, Role.ARMOR);
                        this.phase = 6;
                        this.phaseTicks = 0;
                    }
                } else if (this.phase >= 10) {
                    // Rescue: the smash is going to miss, open the elytra again before hitting the ground.
                    if (this.phase == 10) {
                        this.wearChest(mc, p, Role.ELYTRA);
                        this.nextPhase();
                    } else if (this.phase == 11) {
                        this.nextPhase(); // jump key released for a tick
                    } else if (!p.isFallFlying() && !p.onGround()) {
                        this.kJump = true;
                    } else {
                        this.face(p, p.getDeltaMovement().multiply(1.0, 0.0, 1.0).add(0.0, 0.3, 0.0), 25.0F);
                        this.boost(mc, p, this.phaseTicks > 4);
                    }
                    if (p.onGround() || this.phaseTicks > 40) {
                        this.wearChest(mc, p, Role.ARMOR);
                        this.flightCooldown = 60;
                        this.finishAttempt(mc);
                    }
                } else {
                    this.holdSmashCarrier(mc, p);
                    this.faceEntity(p, t, 60.0F);
                    this.kForward = hDist > 0.8;
                    double reach = Math.sqrt(t.getBoundingBox().distanceToSqr(p.getEyePosition()));
                    if (p.getDeltaMovement().y < 0.0 && p.fallDistance > 1.5 && (reach <= 3.0 || p.distanceTo(t) <= 3.3)) {
                        this.smashHit(mc, p, t);
                    }
                    double above = p.getY() - (t.getY() + t.getBbHeight());
                    boolean missing = hDist > 2.5 && above < 22.0 && above > 1.0;
                    if (missing && p.fallDistance > 4.0 && p.getDeltaMovement().y < -0.4 && this.has(p, Role.ELYTRA)) {
                        this.phase = 10;
                        this.phaseTicks = 0;
                    } else if (p.onGround() && this.phaseTicks > 3 || this.phaseTicks > 160) {
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

    /** Falling hard without elytra: pour water right before the ground, then pick it up again. */
    private boolean waterClutch(Minecraft mc, LocalPlayer p, @Nullable LivingEntity t) {
        if (!AutopilotSettings.INSTANCE.waterClutch && this.waterPickupTicks == 0) {
            return false;
        }
        if (this.waterPickupTicks > 0) {
            this.waterPickupTicks--;
            if (p.onGround() || p.isInWater()) {
                this.lookAt(p, p.getYRot(), 90.0F, 90.0F);
                if (this.selectItem(mc, p, s -> s.is(net.minecraft.world.item.Items.BUCKET)) && this.waterPickupTicks % 3 == 0) {
                    this.useItemOnce(mc); // scoop the water back up
                }
                if (this.has(p, Role.WATER_BUCKET)) {
                    this.waterPickupTicks = 0;
                }
                return this.waterPickupTicks > 0;
            }
            return false;
        }
        boolean smashComing = t != null && p.position().subtract(t.position()).horizontalDistance() < 3.0
                && (this.pattern == Pattern.WIND_SMASH || this.pattern == Pattern.WIND_LUNGE_SMASH || this.pattern == Pattern.ELYTRA_DIVE);
        if (p.isFallFlying() || smashComing || p.fallDistance < 10.0 || p.getDeltaMovement().y > -0.5
                || !this.has(p, Role.WATER_BUCKET) || this.heightAboveGround(p) > 3) {
            return false;
        }
        this.select(mc, p, Role.WATER_BUCKET);
        this.lookAt(p, p.getYRot(), 90.0F, 180.0F);
        this.useItemOnce(mc);
        this.waterPickupTicks = 20;
        this.say(mc, "§bWassereimer-Clutch!");
        return true;
    }

    /**
     * Potions: buffs (strength, speed, fire resistance ...) before the fight while the enemy is still
     * away, healing when low.
     */
    private boolean drinkPotion(Minecraft mc, LocalPlayer p, @Nullable LivingEntity t) {
        if (!AutopilotSettings.INSTANCE.potions && this.drinkTicks == 0) {
            return false;
        }
        if (this.drinkTicks > 0) {
            this.drinkTicks--;
            this.kUse = true;
            if (t != null && p.distanceTo(t) < 6.0) {
                this.kBack = true;
            }
            if (this.drinkTicks == 0) {
                this.kUse = false;
            }
            return true;
        }
        if (t == null || p.isFallFlying() || !p.onGround()) {
            return false;
        }
        boolean low = p.getHealth() < 8.0F;
        boolean calm = p.distanceTo(t) > 10.0 && this.pattern == null;
        if (!low && !calm) {
            return false;
        }
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        for (int i = 0; i < items.size(); i++) {
            ItemStack stack = items.get(i);
            if (Kit.classify(stack) != Role.POTION) {
                continue;
            }
            var contents = stack.get(net.minecraft.core.component.DataComponents.POTION_CONTENTS);
            if (contents == null) {
                continue;
            }
            boolean heals = false;
            boolean missing = false;
            for (var effect : contents.getAllEffects()) {
                var type = effect.getEffect();
                if (type.equals(net.minecraft.world.effect.MobEffects.INSTANT_HEALTH) || type.equals(net.minecraft.world.effect.MobEffects.REGENERATION)) {
                    heals = true;
                } else if (!p.hasEffect(type)) {
                    missing = true;
                }
            }
            if (low && heals || calm && missing) {
                int slot = this.toHotbar(mc, p, i);
                if (slot >= 0) {
                    p.getInventory().setSelectedSlot(slot);
                    this.finishAttempt(mc);
                    this.drinkTicks = 34;
                    this.kUse = true;
                    this.say(mc, "§dTrinkt " + stack.getHoverName().getString());
                    return true;
                }
            }
        }
        return false;
    }

    /** Ender pearls: chase a far target on foot, or get away when low and without a totem. */
    private boolean throwPearl(Minecraft mc, LocalPlayer p, LivingEntity t) {
        if (!AutopilotSettings.INSTANCE.pearls) {
            return false;
        }
        if (this.pearlCooldown > 0 || !p.onGround() || !this.has(p, Role.PEARL)) {
            return false;
        }
        double dist = p.distanceTo(t);
        boolean flee = p.getHealth() < 7.0F && !this.has(p, Role.TOTEM) && Kit.classify(p.getItemBySlot(EquipmentSlot.OFFHAND)) != Role.TOTEM
                && dist < 8.0;
        boolean chase = dist > 22.0 && dist < 60.0 && p.hasLineOfSight(t) && !this.canFlyHere(p);
        if (!flee && !chase) {
            return false;
        }
        Vec3 dir = flee ? p.position().subtract(t.position()) : t.position().subtract(p.position());
        double h = Math.min(dir.horizontalDistance(), flee ? 25.0 : dist);
        Vec3 horizontal = dir.multiply(1.0, 0.0, 1.0).normalize().scale(h);
        // A pearl flies at about 1.5 blocks per tick and drops fast: aim higher the further it goes.
        double up = (flee ? 0.0 : t.getY() - p.getY()) + h * h / 80.0;
        if (!this.select(mc, p, Role.PEARL)) {
            return false;
        }
        this.face(p, new Vec3(horizontal.x, up, horizontal.z), 180.0F);
        this.useItemOnce(mc);
        this.pearlCooldown = 40;
        this.say(mc, flee ? "§ePerle weg vom Gegner!" : "§ePerle hinterher!");
        return true;
    }

    private boolean selectItem(Minecraft mc, LocalPlayer p, java.util.function.Predicate<ItemStack> match) {
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        for (int i = 0; i < items.size(); i++) {
            if (match.test(items.get(i))) {
                int slot = this.toHotbar(mc, p, i);
                if (slot >= 0) {
                    p.getInventory().setSelectedSlot(slot);
                    return true;
                }
            }
        }
        return false;
    }

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
            if (stack.has(net.minecraft.core.component.DataComponents.FOOD) && Kit.classify(stack) != Role.GAPPLE
                    && !stack.is(net.minecraft.world.item.Items.ROTTEN_FLESH) && !stack.is(net.minecraft.world.item.Items.SPIDER_EYE)
                    && !stack.is(net.minecraft.world.item.Items.POISONOUS_POTATO)) {
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
            if (item.isAlive() && d < best && Math.abs(item.getY() - p.getY()) < 3.0 && p.hasLineOfSight(item)) {
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
        } else if (p.getItemBySlot(EquipmentSlot.OFFHAND).isEmpty() && (slot = this.findInventory(p, Role.SHIELD)) >= 0) {
            // No totem: a shield in the off hand for blocking.
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
                if (this.heightAboveGround(p) > 3) {
                    // Stalled in the air: never take the elytra off up here, dive to pick up speed.
                    this.lookAt(p, p.getYRot(), 35.0F, 90.0F);
                    this.boost(mc, p, true);
                    LOGGER.info("[AUTOPILOT] stalled in flight -> dive");
                    return;
                }
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

    private int heightAboveGround(LocalPlayer p) {
        BlockPos pos = p.blockPosition();
        for (int i = 1; i <= 8; i++) {
            if (!p.level().getBlockState(pos.below(i)).isAir()) {
                return i - 1;
            }
        }
        return 8;
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

    private int maceBreach(LocalPlayer p) {
        int index = this.findInventory(p, Role.MACE);
        return index < 0 ? 0 : Kit.enchantLevel(p.getInventory().getItem(index), "breach");
    }

    /**
     * Raise the shield (off hand) while our own weapon is recharging and the enemy is in reach, or
     * when they draw a bow. Never with a usable item in the main hand (that would be used instead).
     */
    private boolean shouldBlock(LocalPlayer p, LivingEntity t, boolean ready) {
        if (!AutopilotSettings.INSTANCE.shield) {
            return false;
        }
        if (Kit.classify(p.getItemBySlot(EquipmentSlot.OFFHAND)) != Role.SHIELD || !p.onGround()) {
            return false;
        }
        Role held = Kit.classify(p.getMainHandItem());
        if (held != Role.SWORD && held != Role.AXE && held != Role.MACE) {
            return false;
        }
        double dist = p.distanceTo(t);
        boolean aiming = t.isUsingItem() && (Kit.classify(t.getUseItem()) == Role.BOW || Kit.classify(t.getUseItem()) == Role.CROSSBOW);
        return !ready && p.getAttackStrengthScale(0.5F) < 0.6F && dist < 4.0 || aiming && dist > 5.0;
    }

    private int spearLunge(LocalPlayer p) {
        int index = this.findInventory(p, Role.SPEAR);
        return index < 0 ? 0 : Kit.lungeLevel(p.getInventory().getItem(index));
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

    /**
     * Turns towards the target at a human speed and only swings when the crosshair is really on it
     * (spear jabs: when looking straight at it). No snapping, no hits around corners.
     */
    private void attack(Minecraft mc, LocalPlayer p, LivingEntity t) {
        this.faceEntity(p, t, 40.0F);
        HitResult hit = p.raycastHitResult(1.0F, p);
        boolean piercing = p.getMainHandItem().has(DataComponents.PIERCING_WEAPON);
        Vec3 toT = t.getBoundingBox().getCenter().subtract(p.getEyePosition()).normalize();
        boolean aimed = piercing ? p.getLookAngle().dot(toT) > 0.97
                : hit instanceof net.minecraft.world.phys.EntityHitResult entityHit && entityHit.getEntity() == t;
        if (!aimed) {
            return;
        }
        mc.hitResult = hit;
        ((MinecraftInvoker) mc).pvpbot$startAttack();
    }

    /**
     * Attribute swap: switch to another weapon and attack in the same tick. The server still uses the
     * attack damage attribute and the attack charge of the weapon held until now (they only update on
     * its next tick), but the new weapon's enchantments, mace smash bonus and shield breaking.
     */
    private void swapAttack(Minecraft mc, LocalPlayer p, LivingEntity t, Role role) {
        ItemStack before = p.getMainHandItem();
        if (role == Role.MACE) {
            this.smashed = true;
        }
        if (!AutopilotSettings.INSTANCE.attributeSwap && Kit.classify(before) != role) {
            // Without attribute swapping: switch now, hit next tick.
            this.select(mc, p, role);
            return;
        }
        if (Kit.classify(before) != role && this.select(mc, p, role)) {
            LOGGER.info("[AUTOPILOT] attribute swap {} -> {}", before.getItem(), p.getMainHandItem().getItem());
            this.say(mc, "§dAttribute-Swap: §f" + before.getHoverName().getString() + " §7→ §f" + p.getMainHandItem().getHoverName().getString());
        }
        this.attack(mc, p, t);
    }

    /**
     * The mace smash. Against a raised shield it becomes a stun slam: an axe hit (knocks the shield
     * out) and the smash in the same tick. The second hit has no attack charge, but the mace's fall
     * bonus is not scaled by the charge.
     */
    private void smashHit(Minecraft mc, LocalPlayer p, LivingEntity t) {
        if (AutopilotSettings.INSTANCE.attributeSwap && t.isBlocking() && this.has(p, Role.AXE)) {
            this.swapAttack(mc, p, t, Role.AXE);
            this.say(mc, "§dStun-Slam!");
        }
        this.swapAttack(mc, p, t, Role.MACE);
    }

    /** While falling towards a mace smash: hold the weapon with the highest attack damage (usually an axe). */
    private void holdSmashCarrier(Minecraft mc, LocalPlayer p) {
        if (this.smashed || !AutopilotSettings.INSTANCE.attributeSwap) {
            this.select(mc, p, Role.MACE);
            return;
        }
        int mace = this.findInventory(p, Role.MACE);
        double maceDamage = mace < 0 ? 0.0 : Kit.attackDamage(p.getInventory().getItem(mace));
        List<ItemStack> items = p.getInventory().getNonEquipmentItems();
        double best = 0.0;
        for (ItemStack stack : items) {
            Role role = Kit.classify(stack);
            if (role == Role.SWORD || role == Role.AXE) {
                best = Math.max(best, Kit.attackDamage(stack));
            }
        }
        if (best > maceDamage) {
            this.selectBestBlade(mc, p);
        } else {
            this.select(mc, p, Role.MACE);
        }
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
        LOGGER.info("[AUTOPILOT] {} -> phase {}", this.pattern == null ? "-" : this.pattern.label, this.phase);
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
        if (mc.player != null && AutopilotSettings.INSTANCE.chat) {
            mc.player.sendSystemMessage(Component.literal("§6[Autopilot] §r" + text));
        }
    }
}
