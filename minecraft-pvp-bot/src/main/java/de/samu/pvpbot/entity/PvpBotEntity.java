package de.samu.pvpbot.entity;

import de.samu.pvpbot.PvpBotMod;
import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.brain.BotBrain.Pattern;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.util.Mth;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.ai.control.LookControl;
import net.minecraft.world.entity.ai.goal.FloatGoal;
import net.minecraft.world.entity.ai.goal.Goal;
import net.minecraft.world.entity.ai.goal.LookAtPlayerGoal;
import net.minecraft.world.entity.ai.goal.RandomLookAroundGoal;
import net.minecraft.world.entity.ai.util.LandRandomPos;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.FireworkRocketEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.MaceItem;
import net.minecraft.world.item.component.Fireworks;
import net.minecraft.world.item.component.KineticWeapon;
import net.minecraft.world.item.component.PiercingWeapon;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.Enchantments;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.storage.ValueInput;
import net.minecraft.world.level.storage.ValueOutput;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

/**
 * A player-like PvP bot. It fights with a mace (wind-charge jumps and elytra dives for smash attacks)
 * and a spear (sprint charges, jabs and elytra lance passes), and kills whatever its owner tells it to.
 */
public class PvpBotEntity extends PathfinderMob {

    public enum Style { AUTO, MACE, SPEAR }

    private enum Mode {
        IDLE("bereit"),
        GROUND("Nahkampf"),
        WIND_JUMP("Mace-Sprung"),
        SPEAR_CHARGE("Speer-Ansturm"),
        SPEAR_RETREAT("Anlauf holen"),
        TAKEOFF("Start"),
        CLIMB("steigt auf"),
        APPROACH("Anflug"),
        DIVE("Mace-Sturzflug"),
        LANCE("Speer-Flugangriff");

        final String label;

        Mode(String label) {
            this.label = label;
        }
    }

    private static final double CRUISE_HEIGHT = 26.0;
    private static final double LANCE_HEIGHT = 12.0;
    private static final boolean DEBUG = Boolean.getBoolean("pvpbot.selftest");
    private static final int WIND_COOLDOWN = 45;
    private static final int SPEAR_COOLDOWN = 50;
    private static final int FLIGHT_COOLDOWN = 60;
    private static final int MAX_GAPPLES = 8;

    private @Nullable UUID ownerId;
    private boolean following = true;
    private boolean assisting = true;
    private Style style = Style.AUTO;
    private final Deque<UUID> targetQueue = new ArrayDeque<>();

    private ItemStack mace = ItemStack.EMPTY;
    private ItemStack spear = ItemStack.EMPTY;
    private ItemStack elytra = ItemStack.EMPTY;
    private ItemStack chestplate = ItemStack.EMPTY;

    private Mode mode = Mode.IDLE;
    private int modeTicks;
    private boolean lancePlan;
    private boolean lancePassed;
    private @Nullable Vec3 retreatPos;
    private int windCooldown;
    private int spearCooldown;
    private int meleeCooldown;
    private int rocketCooldown;
    private int flightCooldown;
    private int gappleCooldown;
    private int gapples = MAX_GAPPLES;
    private int idleTicks;
    private boolean talk = true;

    // Learning: the attack pattern currently being tried and how it is going.
    private @Nullable Pattern pattern;
    private BotBrain.@Nullable Context attemptContext;
    private @Nullable LivingEntity attemptTarget;
    private float attemptTargetHp;
    private float attemptTaken;
    private int attemptTicks;
    private final Map<Pattern, Long> tabuUntil = new EnumMap<>(Pattern.class);
    private long lastMessageTime;
    private float strafeDir = 1.0F;
    boolean manualRotation;

    public PvpBotEntity(EntityType<? extends PvpBotEntity> type, Level level) {
        super(type, level);
        this.lookControl = new BotLookControl(this);
        this.setPersistenceRequired();
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Mob.createMobAttributes()
                .add(Attributes.MAX_HEALTH, 20.0)
                .add(Attributes.MOVEMENT_SPEED, 0.32)
                .add(Attributes.ATTACK_DAMAGE, 2.0)
                .add(Attributes.ATTACK_KNOCKBACK, 0.0)
                .add(Attributes.FOLLOW_RANGE, 96.0);
    }

    @Override
    protected void registerGoals() {
        this.goalSelector.addGoal(0, new FloatGoal(this));
        this.goalSelector.addGoal(1, new CombatGoal());
        this.goalSelector.addGoal(2, new FollowOwnerGoal());
        this.goalSelector.addGoal(3, new LookAtPlayerGoal(this, Player.class, 10.0F));
        this.goalSelector.addGoal(4, new RandomLookAroundGoal(this));
    }

    // ------------------------------------------------------------------ owner / orders

    public static List<PvpBotEntity> botsOf(Player player) {
        if (!(player.level() instanceof ServerLevel level)) {
            return List.of();
        }
        List<PvpBotEntity> bots = new ArrayList<>(level.getEntitiesOfClass(PvpBotEntity.class,
                player.getBoundingBox().inflate(512.0),
                bot -> bot.isAlive() && (bot.isOwnedBy(player) || bot.ownerId == null && bot.distanceToSqr(player) < 64.0 * 64.0)));
        for (PvpBotEntity bot : bots) {
            if (bot.ownerId == null) {
                bot.setOwner(player);
            }
        }
        return bots;
    }

    public void setOwner(Player player) {
        this.ownerId = player.getUUID();
    }

    public boolean isOwnedBy(Entity entity) {
        return this.ownerId != null && this.ownerId.equals(entity.getUUID());
    }

    public @Nullable Player getOwner() {
        return this.ownerId == null ? null : this.level().getPlayerByUUID(this.ownerId);
    }

    public boolean isAssisting() {
        return this.assisting;
    }

    public void setAssisting(boolean assisting) {
        this.assisting = assisting;
    }

    public void setFollowing(boolean following) {
        this.following = following;
        this.getNavigation().stop();
    }

    public void setTalk(boolean talk) {
        this.talk = talk;
    }

    public void setStyle(Style style) {
        this.style = style;
    }

    public void addTarget(LivingEntity target, boolean ordered) {
        if (target == this || !this.isValidTarget(target)) {
            return;
        }
        UUID id = target.getUUID();
        LivingEntity current = this.getTarget();
        if (current != null && current.getUUID().equals(id) || this.targetQueue.contains(id)) {
            return;
        }
        if (current == null) {
            this.setTarget(target);
        } else if (ordered) {
            this.targetQueue.addLast(id);
        } else {
            // Someone attacking us or the owner is more urgent than the order list.
            this.targetQueue.addFirst(id);
        }
    }

    public void clearTargets() {
        this.targetQueue.clear();
        this.setTarget(null);
    }

    public String describeState() {
        LivingEntity target = this.getTarget();
        String s = this.pattern != null ? this.pattern.label + " (" + this.mode.label + ")" : this.mode.label;
        if (target != null) {
            s += " gegen " + target.getName().getString();
        }
        if (!this.targetQueue.isEmpty()) {
            s += " (+" + this.targetQueue.size() + " weitere)";
        }
        return s;
    }

    private boolean isValidTarget(LivingEntity target) {
        if (!target.isAlive() || target.isRemoved() || target.level() != this.level()) {
            return false;
        }
        if (this.isAlliedTo(target)) {
            return false;
        }
        if (target instanceof Player player && (player.isCreative() || player.isSpectator())) {
            return false;
        }
        return this.distanceToSqr(target) < 256.0 * 256.0;
    }

    @Override
    protected boolean considersEntityAsAlly(Entity other) {
        if (this.ownerId != null) {
            if (this.ownerId.equals(other.getUUID())) {
                return true;
            }
            if (other instanceof PvpBotEntity bot && this.ownerId.equals(bot.ownerId)) {
                return true;
            }
        }
        return super.considersEntityAsAlly(other);
    }

    @Override
    public boolean hurtServer(ServerLevel level, DamageSource source, float amount) {
        float before = this.getHealth() + this.getAbsorptionAmount();
        boolean hurt = super.hurtServer(level, source, amount);
        if (this.pattern != null) {
            this.attemptTaken += Math.max(0.0F, before - (this.getHealth() + this.getAbsorptionAmount()));
        }
        if (hurt && source.getEntity() instanceof LivingEntity attacker && attacker != this && !this.isAlliedTo(attacker)) {
            this.addTarget(attacker, false);
        }
        return hurt;
    }

    @Override
    public boolean removeWhenFarAway(double distance) {
        return false;
    }

    // ------------------------------------------------------------------ equipment

    public void equipLoadout() {
        this.mace = enchanted(new ItemStack(Items.MACE),
                Enchantments.DENSITY, 5, Enchantments.WIND_BURST, 3, Enchantments.FIRE_ASPECT, 2, Enchantments.UNBREAKING, 3);
        this.spear = enchanted(new ItemStack(Items.NETHERITE_SPEAR),
                Enchantments.SHARPNESS, 5, Enchantments.UNBREAKING, 3);
        this.elytra = enchanted(new ItemStack(Items.ELYTRA), Enchantments.UNBREAKING, 3);
        this.chestplate = enchanted(new ItemStack(Items.NETHERITE_CHESTPLATE),
                Enchantments.PROTECTION, 4, Enchantments.UNBREAKING, 3);

        this.setItemSlot(EquipmentSlot.HEAD, enchanted(new ItemStack(Items.NETHERITE_HELMET),
                Enchantments.PROTECTION, 4, Enchantments.UNBREAKING, 3));
        this.setItemSlot(EquipmentSlot.CHEST, this.chestplate);
        this.setItemSlot(EquipmentSlot.LEGS, enchanted(new ItemStack(Items.NETHERITE_LEGGINGS),
                Enchantments.BLAST_PROTECTION, 4, Enchantments.UNBREAKING, 3));
        this.setItemSlot(EquipmentSlot.FEET, enchanted(new ItemStack(Items.NETHERITE_BOOTS),
                Enchantments.PROTECTION, 4, Enchantments.FEATHER_FALLING, 4, Enchantments.UNBREAKING, 3));
        this.setItemSlot(EquipmentSlot.MAINHAND, this.style == Style.SPEAR ? this.spear : this.mace);
        this.setItemSlot(EquipmentSlot.OFFHAND, new ItemStack(Items.TOTEM_OF_UNDYING));
        for (EquipmentSlot slot : EquipmentSlot.values()) {
            this.setDropChance(slot, 0.0F);
        }
        this.gapples = MAX_GAPPLES;
    }

    private ItemStack enchanted(ItemStack stack, Object... enchantsAndLevels) {
        var registry = this.level().registryAccess().lookupOrThrow(Registries.ENCHANTMENT);
        for (int i = 0; i + 1 < enchantsAndLevels.length; i += 2) {
            @SuppressWarnings("unchecked")
            ResourceKey<Enchantment> key = (ResourceKey<Enchantment>) enchantsAndLevels[i];
            int lvl = (Integer) enchantsAndLevels[i + 1];
            registry.get(key).ifPresent(holder -> stack.enchant(holder, lvl));
        }
        return stack;
    }

    private void holdWeapon(ItemStack weapon) {
        if (!weapon.isEmpty() && this.getMainHandItem() != weapon) {
            if (this.isUsingItem()) {
                this.stopUsingItem();
            }
            this.setItemSlot(EquipmentSlot.MAINHAND, weapon);
        }
    }

    private boolean holdingSpear() {
        return !this.spear.isEmpty() && this.getMainHandItem() == this.spear;
    }

    private void wearElytra(boolean wantElytra) {
        ItemStack wanted = wantElytra ? this.elytra : this.chestplate;
        if (!wanted.isEmpty() && this.getItemBySlot(EquipmentSlot.CHEST) != wanted) {
            this.setItemSlot(EquipmentSlot.CHEST, wanted);
        }
    }

    private boolean wantsMace() {
        return this.style != Style.SPEAR && !this.mace.isEmpty();
    }

    private boolean wantsSpear() {
        return this.style != Style.MACE && !this.spear.isEmpty();
    }

    // ------------------------------------------------------------------ server tick

    @Override
    protected void customServerAiStep(ServerLevel level) {
        super.customServerAiStep(level);
        this.refreshTarget(level);

        if (this.windCooldown > 0) this.windCooldown--;
        if (this.spearCooldown > 0) this.spearCooldown--;
        if (this.meleeCooldown > 0) this.meleeCooldown--;
        if (this.rocketCooldown > 0) this.rocketCooldown--;
        if (this.flightCooldown > 0) this.flightCooldown--;
        if (this.gappleCooldown > 0) this.gappleCooldown--;

        // Eat a golden apple when low.
        if (this.getHealth() < 10.0F && this.gapples > 0 && this.gappleCooldown == 0) {
            this.gapples--;
            this.gappleCooldown = 80;
            this.addEffect(new MobEffectInstance(MobEffects.REGENERATION, 100, 1));
            this.addEffect(new MobEffectInstance(MobEffects.ABSORPTION, 2400, 0));
            level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.GENERIC_EAT, this.getSoundSource(), 1.0F, 1.0F);
        }

        // Restock consumables after a while out of combat.
        if (this.getTarget() == null) {
            if (++this.idleTicks > 600) {
                this.idleTicks = 0;
                this.gapples = MAX_GAPPLES;
                if (this.getOffhandItem().isEmpty()) {
                    this.setItemSlot(EquipmentSlot.OFFHAND, new ItemStack(Items.TOTEM_OF_UNDYING));
                }
            }
        } else {
            this.idleTicks = 0;
        }

        // Swap the elytra back for the chestplate once we are on the ground.
        if (this.onGround() && !this.isFallFlying() && this.mode != Mode.TAKEOFF) {
            this.wearElytra(false);
        }

        // Out of combat and still gliding: just drop and land safely.
        if (this.getTarget() == null && this.isFallFlying()) {
            this.stopFallFlying();
        }

        // Wind-charge clutch: never die of fall damage when a smash is not about to land.
        Vec3 v = this.getDeltaMovement();
        if (!this.onGround() && !this.isFallFlying() && v.y < -0.65 && this.fallDistance > 3.0
                && this.groundDistance(3) <= 2 && !(this.getTarget() != null && this.inSmashReach(this.getTarget()))) {
            this.windBurst(level, new Vec3(v.x * 0.5, 0.55, v.z * 0.5));
            this.resetFallDistance();
        }
    }

    private void refreshTarget(ServerLevel level) {
        LivingEntity current = this.getTarget();
        if (current != null && !this.isValidTarget(current)) {
            this.setTarget(null);
            current = null;
        }
        while (current == null && !this.targetQueue.isEmpty()) {
            Entity next = level.getEntity(this.targetQueue.pollFirst());
            if (next instanceof LivingEntity living && this.isValidTarget(living)) {
                this.setTarget(living);
                current = living;
            }
        }
    }

    // ------------------------------------------------------------------ movement helpers

    private void setMode(Mode mode) {
        this.mode = mode;
        this.modeTicks = 0;
        if (mode == Mode.GROUND && this.pattern != null && !this.pattern.melee) {
            this.finishAttempt();
        }
    }

    private void startGliding() {
        this.setSharedFlag(7, true);
    }

    private void fireRocket(ServerLevel level) {
        if (this.rocketCooldown > 0) {
            return;
        }
        ItemStack rocket = new ItemStack(Items.FIREWORK_ROCKET);
        rocket.set(DataComponents.FIREWORKS, new Fireworks(1, List.of()));
        level.addFreshEntity(new FireworkRocketEntity(level, rocket, this));
        this.rocketCooldown = 24;
    }

    private void windBurst(ServerLevel level, Vec3 motion) {
        this.setDeltaMovement(motion);
        this.needsSync = true;
        level.sendParticles(ParticleTypes.GUST_EMITTER_SMALL, this.getX(), this.getY(), this.getZ(), 1, 0.0, 0.0, 0.0, 0.0);
        level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.WIND_CHARGE_BURST, this.getSoundSource(), 1.0F, 1.0F);
    }

    /** Number of air blocks below the feet, up to {@code max}. */
    private int groundDistance(int max) {
        BlockPos pos = this.blockPosition();
        for (int i = 0; i <= max; i++) {
            BlockPos p = pos.below(i);
            if (!this.level().getBlockState(p).getCollisionShape(this.level(), p).isEmpty()) {
                return i;
            }
        }
        return max + 1;
    }

    private boolean canFlyHere() {
        return !this.elytra.isEmpty() && !this.isInWater() && this.level().canSeeSky(this.blockPosition().above());
    }

    private static float yawTo(Vec3 dir) {
        return (float) (Mth.atan2(dir.z, dir.x) * (180.0 / Math.PI)) - 90.0F;
    }

    private static float pitchTo(Vec3 dir) {
        return (float) -(Mth.atan2(dir.y, dir.horizontalDistance()) * (180.0 / Math.PI));
    }

    private static float approachAngle(float from, float to, float max) {
        float diff = Mth.wrapDegrees(to - from);
        return from + Mth.clamp(diff, -max, max);
    }

    /** Rotate body, head and look direction towards {@code dir}, turning at most {@code maxTurn} degrees per tick. */
    private void face(Vec3 dir, float maxTurn) {
        this.manualRotation = true;
        float yaw = approachAngle(this.getYRot(), yawTo(dir), maxTurn);
        float pitch = approachAngle(this.getXRot(), Mth.clamp(pitchTo(dir), -89.0F, 89.0F), maxTurn);
        this.setYRot(yaw);
        this.setXRot(pitch);
        this.setYHeadRot(yaw);
        this.setYBodyRot(yaw);
    }

    private void faceEntity(LivingEntity target, float maxTurn) {
        this.face(target.getEyePosition().subtract(this.getEyePosition()), maxTurn);
    }

    boolean inSmashReach(LivingEntity target) {
        double vy = Math.min(0.0, this.getDeltaMovement().y);
        AABB reach = this.getBoundingBox().expandTowards(0.0, vy, 0.0).inflate(1.7, 0.6, 1.7);
        return reach.intersects(target.getBoundingBox());
    }

    private void swingMainHand() {
        this.swing(InteractionHand.MAIN_HAND, this.getMainHandItem().getAttackAnimation());
    }

    private boolean trySmash(ServerLevel level, LivingEntity target) {
        if (this.getMainHandItem() == this.mace && MaceItem.canSmashAttack(this) && this.inSmashReach(target)) {
            this.faceEntity(target, 180.0F);
            this.swingMainHand();
            this.doHurtTarget(level, target);
            return true;
        }
        return false;
    }

    // ------------------------------------------------------------------ combat

    private void tickCombat(ServerLevel level, LivingEntity target) {
        this.modeTicks++;
        if (this.pattern != null) {
            this.attemptTicks++;
            if (this.attemptTarget != target || this.attemptTicks > 500) {
                this.finishAttempt();
            }
        }
        switch (this.mode) {
            case IDLE, GROUND -> this.tickGround(level, target);
            case WIND_JUMP, DIVE -> this.tickAirSmash(level, target);
            case SPEAR_CHARGE -> this.tickSpearCharge(level, target);
            case SPEAR_RETREAT -> this.tickSpearRetreat(target);
            case TAKEOFF -> this.tickTakeoff(level, target);
            case CLIMB, APPROACH, LANCE -> this.tickFlight(level, target);
        }
    }

    private void tickGround(ServerLevel level, LivingEntity target) {
        if (this.mode != Mode.GROUND) {
            this.setMode(Mode.GROUND);
        }
        this.manualRotation = false;
        this.getLookControl().setLookAt(target, 60.0F, 60.0F);

        double dist = this.distanceTo(target);
        double hDist = this.position().subtract(target.position()).horizontalDistance();
        double dy = target.getY() - this.getY();
        boolean sees = this.getSensing().hasLineOfSight(target);

        // Decide what to do next: the brain picks an attack pattern for this situation.
        if (this.pattern == null) {
            List<Pattern> options = this.feasiblePatterns(target, false);
            if (options.isEmpty()) {
                return;
            }
            BotBrain.Context ctx = this.currentContext(target);
            Pattern chosen = BotBrain.INSTANCE.choose(ctx, options, this.random);
            this.beginAttempt(chosen, target, ctx);
            if (!chosen.melee) {
                this.startPattern(level, target, chosen);
                return;
            }
        }
        if (this.attemptTicks > 40) {
            // Melee rounds are short so the bot re-evaluates often.
            this.finishAttempt();
            return;
        }

        boolean useSpear = this.pattern == Pattern.SPEAR_KITE;
        this.holdWeapon(useSpear ? this.spear : this.mace);

        if (this.random.nextInt(30) == 0) {
            this.strafeDir = -this.strafeDir;
        }
        if (useSpear) {
            // Kite at the edge of the spear's reach.
            if (dist > 4.0) {
                this.setSprinting(true);
                this.getNavigation().moveTo(target, 1.25);
            } else {
                this.setSprinting(false);
                this.getNavigation().stop();
                this.getMoveControl().strafe(dist < 2.8 ? -0.7F : 0.1F, this.strafeDir * 0.5F);
            }
        } else if (dist > 2.6) {
            this.setSprinting(true);
            this.getNavigation().moveTo(target, 1.25);
        } else {
            this.setSprinting(false);
            this.getNavigation().stop();
            this.getMoveControl().strafe(-0.2F, this.strafeDir * 0.5F);
        }

        if (this.meleeCooldown == 0 && sees) {
            if (this.holdingSpear() && dist <= 4.4) {
                this.jab(target);
                this.meleeCooldown = 12;
            } else if (!this.holdingSpear() && dist <= 3.2) {
                this.faceEntity(target, 180.0F);
                this.swingMainHand();
                this.doHurtTarget(level, target);
                this.meleeCooldown = 16;
            }
        }
    }

    private void jab(LivingEntity target) {
        this.faceEntity(target, 180.0F);
        PiercingWeapon piercing = this.spear.get(DataComponents.PIERCING_WEAPON);
        if (piercing != null) {
            piercing.attack(this, EquipmentSlot.MAINHAND);
        } else if (this.level() instanceof ServerLevel level) {
            this.swingMainHand();
            this.doHurtTarget(level, target);
        }
    }

    // --- mace: wind charge jump

    private void startWindJump(ServerLevel level, LivingEntity target) {
        this.holdWeapon(this.mace);
        this.getNavigation().stop();
        Vec3 horizontal = target.position().subtract(this.position()).multiply(1.0, 0.0, 1.0);
        Vec3 push = horizontal.lengthSqr() > 1.0E-4 ? horizontal.normalize().scale(0.15) : Vec3.ZERO;
        this.windBurst(level, new Vec3(push.x, 1.15, push.z));
        this.windCooldown = WIND_COOLDOWN;
        this.setMode(Mode.WIND_JUMP);
    }

    /** Airborne after a wind jump or a dive: steer onto the target and smash it on the way down. */
    private void tickAirSmash(ServerLevel level, LivingEntity target) {
        this.holdWeapon(this.mace);
        this.faceEntity(target, 40.0F);
        this.getNavigation().stop();

        Vec3 v = this.getDeltaMovement();
        double fallTicks = v.y < 0 ? Math.max(1.0, (this.getY() - target.getY()) / Math.max(0.3, -v.y)) : 8.0;
        Vec3 aim = target.position().add(target.getDeltaMovement().multiply(1.0, 0.0, 1.0).scale(Math.min(fallTicks, 10.0)));
        Vec3 toAim = aim.subtract(this.position()).multiply(1.0, 0.0, 1.0);
        double maxH = this.mode == Mode.DIVE ? 0.7 : 0.38;
        Vec3 wantH = toAim.scale(0.25);
        if (wantH.length() > maxH) {
            wantH = wantH.normalize().scale(maxH);
        }
        this.setDeltaMovement(v.x * 0.5 + wantH.x * 0.5, v.y, v.z * 0.5 + wantH.z * 0.5);
        this.needsSync = true;

        this.trySmash(level, target);

        if (this.modeTicks > 3 && (this.onGround() || this.isInWater())) {
            this.setMode(Mode.GROUND);
        } else if (this.modeTicks > 200) {
            this.setMode(Mode.GROUND);
        }
    }

    // --- spear: ground charge

    private void startSpearCharge(LivingEntity target) {
        this.holdWeapon(this.spear);
        this.getNavigation().stop();
        this.setSprinting(true);
        this.startUsingItem(InteractionHand.MAIN_HAND);
        this.setMode(Mode.SPEAR_CHARGE);
    }

    private int spearUseDuration() {
        KineticWeapon kinetic = this.spear.get(DataComponents.KINETIC_WEAPON);
        return kinetic != null ? Math.max(20, kinetic.computeDamageUseDuration()) : 60;
    }

    private void tickSpearCharge(ServerLevel level, LivingEntity target) {
        this.faceEntity(target, 30.0F);
        this.setSprinting(true);
        this.getMoveControl().setWantedPosition(target.getX(), target.getY(), target.getZ(), 1.9);
        if (this.horizontalCollision && this.onGround()) {
            this.getJumpControl().jump();
        }

        double dist = this.distanceTo(target);
        if (!this.isUsingItem() && this.modeTicks < 4) {
            // Weapon swaps can cancel the use on the same tick; just try again.
            this.startUsingItem(InteractionHand.MAIN_HAND);
            return;
        }
        if (!this.isUsingItem() || this.modeTicks > this.spearUseDuration() || dist < 1.3) {
            this.stopUsingItem();
            this.spearCooldown = SPEAR_COOLDOWN;
            this.retreatPos = LandRandomPos.getPosAway(this, 6, 10, 7, target.position());
            this.setMode(Mode.SPEAR_RETREAT);
        }
    }

    private void tickSpearRetreat(LivingEntity target) {
        this.manualRotation = false;
        this.getLookControl().setLookAt(target, 60.0F, 60.0F);
        if (this.retreatPos == null || this.modeTicks > 40 || this.distanceTo(target) > 12.0) {
            this.setMode(Mode.GROUND);
            return;
        }
        this.setSprinting(true);
        this.getNavigation().moveTo(this.retreatPos.x, this.retreatPos.y, this.retreatPos.z, 1.4);
        if (this.modeTicks > 5 && this.getNavigation().isDone()) {
            this.setMode(Mode.GROUND);
        }
    }

    // --- elytra: take off, climb, then mace dive or spear lance

    private void startTakeoff(ServerLevel level, LivingEntity target) {
        this.getNavigation().stop();
        this.wearElytra(true);
        this.holdWeapon(this.lancePlan ? this.spear : this.mace);
        Vec3 v = this.getDeltaMovement();
        this.windBurst(level, new Vec3(v.x, 1.0, v.z));
        this.setMode(Mode.TAKEOFF);
    }

    private void tickTakeoff(ServerLevel level, LivingEntity target) {
        this.face(target.position().subtract(this.position()).multiply(1.0, 0.0, 1.0).add(0.0, 8.0, 0.0), 30.0F);
        if (this.modeTicks >= 4 && !this.onGround()) {
            this.startGliding();
            this.fireRocket(level);
            this.setMode(Mode.CLIMB);
        } else if (this.modeTicks > 20) {
            this.flightCooldown = FLIGHT_COOLDOWN;
            this.setMode(Mode.GROUND);
        }
    }

    private void endFlight() {
        this.stopUsingItem();
        this.flightCooldown = FLIGHT_COOLDOWN;
        this.setMode(Mode.GROUND);
    }

    private void tickFlight(ServerLevel level, LivingEntity target) {
        this.getNavigation().stop();
        if (this.pattern == null) {
            this.continueFlightOrLand(level, target);
            if (this.mode == Mode.GROUND) {
                return;
            }
        }
        if (!this.isFallFlying()) {
            if (this.onGround() || this.isInWater()) {
                this.endFlight();
                return;
            }
            this.startGliding();
        }

        Vec3 pos = this.position();
        Vec3 v = this.getDeltaMovement();
        double speed = v.length();
        Vec3 toTarget = target.position().subtract(pos);
        double hDist = toTarget.horizontalDistance();
        double cruiseY = target.getY() + (this.lancePlan ? LANCE_HEIGHT : CRUISE_HEIGHT);

        switch (this.mode) {
            case CLIMB -> {
                // Head for a point high above the target (or circle away from it while too close).
                Vec3 flat = toTarget.multiply(1.0, 0.0, 1.0);
                Vec3 dir = flat.lengthSqr() < 1.0E-4 ? this.getLookAngle().multiply(1.0, 0.0, 1.0) : flat.normalize();
                if (hDist < 14.0) {
                    dir = dir.scale(-1.0);
                }
                Vec3 aim = dir.scale(12.0).add(0.0, Mth.clamp(cruiseY - this.getY(), -6.0, 9.0), 0.0);
                this.face(aim, 12.0F);
                if (speed < 1.3 || this.getXRot() < -15.0F) {
                    this.fireRocket(level);
                }
                if (this.getY() >= cruiseY - 3.0 && hDist >= 14.0 || this.getY() >= cruiseY + 6.0) {
                    this.lancePassed = false;
                    this.setMode(this.lancePlan ? Mode.LANCE : Mode.APPROACH);
                }
            }
            case APPROACH -> {
                this.holdWeapon(this.mace);
                Vec3 lead = target.getDeltaMovement().multiply(1.0, 0.0, 1.0).scale(hDist / Math.max(0.8, speed));
                Vec3 above = target.position().add(lead).add(0.0, CRUISE_HEIGHT, 0.0).subtract(pos);
                this.face(new Vec3(above.x, Mth.clamp(above.y, -4.0, 4.0), above.z), 15.0F);
                if (speed < 1.0 && hDist > 20.0) {
                    this.fireRocket(level);
                }
                // Release the glide early enough that momentum carries us onto the target.
                double releaseDist = 2.0 + v.horizontalDistance() * 5.0;
                if (hDist < releaseDist) {
                    this.stopFallFlying();
                    this.setDeltaMovement(v.x * 0.6, Math.min(v.y, -0.6), v.z * 0.6);
                    this.needsSync = true;
                    this.setMode(Mode.DIVE);
                } else if (this.getY() < target.getY() + 12.0 || this.modeTicks > 400) {
                    this.setMode(Mode.CLIMB);
                }
            }
            case LANCE -> {
                this.holdWeapon(this.spear);
                double dist = this.distanceTo(target);
                Vec3 lead = target.getDeltaMovement().scale(Math.min(10.0, dist / Math.max(0.8, speed)));
                Vec3 aimPoint = target.getBoundingBox().getCenter().add(lead);
                // Glide path: come down gradually while far away, then fly level straight through the target.
                double wantY = hDist > 14.0 ? target.getY() + 1.5 + (hDist - 14.0) * 0.35 : aimPoint.y;
                Vec3 aim = new Vec3(aimPoint.x - this.getX(), wantY - this.getEyeY(), aimPoint.z - this.getZ());
                if (this.groundDistance(3) <= 2 && aim.y < 0.0 && hDist > 2.0) {
                    aim = new Vec3(aim.x, 0.4, aim.z);
                }
                if (this.lancePassed) {
                    // Went through the target: pull up and away, then loop around for the next pass.
                    Vec3 flat = v.multiply(1.0, 0.0, 1.0);
                    aim = (flat.lengthSqr() < 1.0E-3 ? this.getLookAngle().multiply(1.0, 0.0, 1.0) : flat.normalize()).add(0.0, 0.7, 0.0);
                }
                this.face(aim, 25.0F);
                if (speed < 1.6 || this.lancePassed && this.groundDistance(3) <= 2) {
                    this.fireRocket(level);
                }
                if (dist < 24.0 && !this.isUsingItem() && !this.lancePassed) {
                    this.startUsingItem(InteractionHand.MAIN_HAND);
                }
                if (DEBUG && dist < 4.0) {
                    PvpBotMod.LOGGER.info(String.format("[SELFTEST]   lance dist=%.1f using=%s ticks=%d speed=%.2f pitch=%.0f ground=%d",
                            dist, this.isUsingItem(), this.getTicksUsingItem(), speed, this.getXRot(), this.groundDistance(6)));
                }
                if (dist < 2.5) {
                    this.lancePassed = true;
                }
                if (this.lancePassed && dist > 8.0 || this.modeTicks > 240) {
                    this.stopUsingItem();
                    this.finishAttempt();
                    this.continueFlightOrLand(level, target);
                }
            }
            default -> {
            }
        }
    }

    // ------------------------------------------------------------------ learning

    private BotBrain.Context currentContext(LivingEntity target) {
        BotBrain.Env env = this.isInWater() ? BotBrain.Env.WATER
                : this.ceilingHeight(12) <= 10 ? BotBrain.Env.CAVE : BotBrain.Env.OPEN;
        double hDist = this.position().subtract(target.position()).horizontalDistance();
        boolean inAir = target.isFallFlying() || !target.onGround() && target.getY() - this.getY() > 4.0;
        return new BotBrain.Context(env, BotBrain.Range.of(hDist), inAir, target instanceof Player);
    }

    /** Height of the first solid block above the head, up to {@code max}. */
    private int ceilingHeight(int max) {
        BlockPos pos = this.blockPosition();
        for (int i = 2; i <= max; i++) {
            BlockPos p = pos.above(i);
            if (!this.level().getBlockState(p).getCollisionShape(this.level(), p).isEmpty()) {
                return i;
            }
        }
        return max + 1;
    }

    /** Patterns that can actually be executed right now (weapons, cooldowns, space, recent flops). */
    private List<Pattern> feasiblePatterns(LivingEntity target, boolean flying) {
        double hDist = this.position().subtract(target.position()).horizontalDistance();
        double dy = target.getY() - this.getY();
        boolean sees = this.getSensing().hasLineOfSight(target);
        List<Pattern> out = new ArrayList<>();
        if (this.wantsMace()) {
            out.add(Pattern.MACE_MELEE);
        }
        if (this.wantsSpear()) {
            out.add(Pattern.SPEAR_KITE);
        }
        if (!flying && this.wantsMace() && this.onGround() && this.windCooldown == 0 && sees
                && hDist > 1.0 && hDist < 8.0 && dy < 3.0 && dy > -4.0) {
            out.add(Pattern.WIND_SMASH);
        }
        if (!flying && this.wantsSpear() && this.onGround() && this.spearCooldown == 0 && sees && hDist > 4.0 && hDist < 18.0) {
            out.add(Pattern.SPEAR_CHARGE);
        }
        boolean canFly = flying || this.onGround() && this.flightCooldown == 0 && this.canFlyHere() && hDist > 5.0;
        if (canFly) {
            if (this.wantsMace()) {
                out.add(Pattern.ELYTRA_DIVE);
            }
            if (this.wantsSpear()) {
                out.add(Pattern.ELYTRA_LANCE);
            }
        }
        long now = this.level().getGameTime();
        List<Pattern> allowed = new ArrayList<>(out);
        allowed.removeIf(p -> this.tabuUntil.getOrDefault(p, 0L) > now);
        return allowed.isEmpty() ? out : allowed;
    }

    private void beginAttempt(Pattern chosen, LivingEntity target, BotBrain.Context ctx) {
        this.pattern = chosen;
        this.attemptContext = ctx;
        this.attemptTarget = target;
        this.attemptTargetHp = target.getHealth() + target.getAbsorptionAmount();
        this.attemptTaken = 0.0F;
        this.attemptTicks = 0;
        if (DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   try {} ({})", chosen.label, ctx.describe());
        }
    }

    private void startPattern(ServerLevel level, LivingEntity target, Pattern chosen) {
        switch (chosen) {
            case WIND_SMASH -> this.startWindJump(level, target);
            case SPEAR_CHARGE -> this.startSpearCharge(target);
            case ELYTRA_DIVE, ELYTRA_LANCE -> {
                this.lancePlan = chosen == Pattern.ELYTRA_LANCE;
                this.startTakeoff(level, target);
            }
            default -> {
            }
        }
    }

    /** While airborne: pick the next pattern, keep flying for aerial ones, otherwise land and fight on foot. */
    private void continueFlightOrLand(ServerLevel level, LivingEntity target) {
        BotBrain.Context ctx = this.currentContext(target);
        Pattern next = BotBrain.INSTANCE.choose(ctx, this.feasiblePatterns(target, true), this.random);
        this.beginAttempt(next, target, ctx);
        if (next.aerial()) {
            this.lancePlan = next == Pattern.ELYTRA_LANCE;
            this.lancePassed = false;
            this.setMode(Mode.CLIMB);
        } else {
            this.stopUsingItem();
            this.stopFallFlying();
            this.flightCooldown = FLIGHT_COOLDOWN;
            this.setMode(Mode.GROUND);
        }
    }

    /** Scores the finished attempt (damage dealt vs. taken, per time) and teaches the brain. */
    private void finishAttempt() {
        Pattern done = this.pattern;
        BotBrain.Context ctx = this.attemptContext;
        this.pattern = null;
        if (done == null || ctx == null) {
            return;
        }
        LivingEntity target = this.attemptTarget;
        this.attemptTarget = null;
        boolean killed = target != null && !target.isAlive();
        float hpNow = target == null ? this.attemptTargetHp : killed ? 0.0F : target.getHealth() + target.getAbsorptionAmount();
        double dealt = Math.max(0.0, this.attemptTargetHp - hpNow);
        double seconds = this.attemptTicks / 20.0;
        double score = (dealt + (killed ? 8.0 : 0.0) - 0.8 * this.attemptTaken) / (seconds + 1.5);
        BotBrain.Lesson lesson = BotBrain.INSTANCE.learn(ctx, done, score);
        long now = this.level().getGameTime();
        if (lesson.flop()) {
            this.tabuUntil.put(done, now + 200L);
        }
        if (DEBUG) {
            PvpBotMod.LOGGER.info(String.format("[SELFTEST]   learned %s: dealt=%.1f taken=%.1f time=%.1fs -> score=%.1f value=%.1f%s%s",
                    done.label, dealt, this.attemptTaken, seconds, score, lesson.value(),
                    lesson.newFavourite() ? " NEW FAVOURITE" : "", lesson.flop() ? " FLOP" : ""));
        }
        if (this.talk && (lesson.newFavourite() || lesson.flop()) && now - this.lastMessageTime > 300L
                && this.getOwner() instanceof ServerPlayer owner) {
            this.lastMessageTime = now;
            String name = this.getName().getString();
            owner.sendSystemMessage(Component.literal(lesson.newFavourite()
                    ? String.format("§b[%s] §7Gelernt: §f%s§7 → §a%s§7 klappt am besten (Wert %.1f)", name, ctx.describe(), done.label, lesson.value())
                    : String.format("§b[%s] §c%s§7 hat nicht funktioniert (%s) – ich probiere was anderes.", name, done.label, ctx.describe())));
        }
    }

    // ------------------------------------------------------------------ goals

    private class CombatGoal extends Goal {
        CombatGoal() {
            this.setFlags(EnumSet.of(Goal.Flag.MOVE, Goal.Flag.LOOK, Goal.Flag.JUMP));
        }

        @Override
        public boolean canUse() {
            LivingEntity target = PvpBotEntity.this.getTarget();
            return target != null && target.isAlive();
        }

        @Override
        public boolean requiresUpdateEveryTick() {
            return true;
        }

        @Override
        public void start() {
            PvpBotEntity.this.setAggressive(true);
            PvpBotEntity.this.setMode(Mode.GROUND);
        }

        @Override
        public void stop() {
            PvpBotEntity bot = PvpBotEntity.this;
            bot.finishAttempt();
            bot.setAggressive(false);
            bot.setSprinting(false);
            bot.stopUsingItem();
            bot.manualRotation = false;
            bot.getNavigation().stop();
            bot.setMode(Mode.IDLE);
        }

        @Override
        public void tick() {
            LivingEntity target = PvpBotEntity.this.getTarget();
            if (target != null && PvpBotEntity.this.level() instanceof ServerLevel level) {
                PvpBotEntity.this.tickCombat(level, target);
            }
        }
    }

    private class FollowOwnerGoal extends Goal {
        FollowOwnerGoal() {
            this.setFlags(EnumSet.of(Goal.Flag.MOVE, Goal.Flag.LOOK));
        }

        @Override
        public boolean canUse() {
            Player owner = PvpBotEntity.this.getOwner();
            return PvpBotEntity.this.following && owner != null && PvpBotEntity.this.getTarget() == null
                    && !owner.isSpectator() && PvpBotEntity.this.distanceToSqr(owner) > 36.0;
        }

        @Override
        public boolean canContinueToUse() {
            Player owner = PvpBotEntity.this.getOwner();
            return PvpBotEntity.this.following && owner != null && PvpBotEntity.this.getTarget() == null
                    && PvpBotEntity.this.distanceToSqr(owner) > 9.0;
        }

        @Override
        public void stop() {
            PvpBotEntity.this.getNavigation().stop();
            PvpBotEntity.this.setSprinting(false);
        }

        @Override
        public void tick() {
            PvpBotEntity bot = PvpBotEntity.this;
            Player owner = bot.getOwner();
            if (owner == null) {
                return;
            }
            bot.manualRotation = false;
            bot.getLookControl().setLookAt(owner, 30.0F, 30.0F);
            double distSq = bot.distanceToSqr(owner);
            if (distSq > 40.0 * 40.0 && owner.onGround()) {
                bot.teleportTo(owner.getX(), owner.getY(), owner.getZ());
                bot.getNavigation().stop();
            } else {
                bot.setSprinting(distSq > 12.0 * 12.0);
                bot.getNavigation().moveTo(owner, distSq > 12.0 * 12.0 ? 1.3 : 1.0);
            }
        }
    }

    private static class BotLookControl extends LookControl {
        private final PvpBotEntity bot;

        BotLookControl(PvpBotEntity bot) {
            super(bot);
            this.bot = bot;
        }

        @Override
        public void tick() {
            if (!this.bot.manualRotation) {
                super.tick();
            }
        }
    }

    // ------------------------------------------------------------------ save data

    @Override
    protected void addAdditionalSaveData(ValueOutput output) {
        super.addAdditionalSaveData(output);
        if (this.ownerId != null) {
            output.putString("PvpBotOwner", this.ownerId.toString());
        }
        output.putBoolean("PvpBotFollowing", this.following);
        output.putBoolean("PvpBotAssisting", this.assisting);
        output.putString("PvpBotStyle", this.style.name());
        output.putInt("PvpBotGapples", this.gapples);
        output.putBoolean("PvpBotTalk", this.talk);
        output.store("PvpBotMace", ItemStack.OPTIONAL_CODEC, this.mace);
        output.store("PvpBotSpear", ItemStack.OPTIONAL_CODEC, this.spear);
        output.store("PvpBotElytra", ItemStack.OPTIONAL_CODEC, this.elytra);
        output.store("PvpBotChestplate", ItemStack.OPTIONAL_CODEC, this.chestplate);
    }

    @Override
    protected void readAdditionalSaveData(ValueInput input) {
        super.readAdditionalSaveData(input);
        this.ownerId = input.getString("PvpBotOwner").map(s -> {
            try {
                return UUID.fromString(s);
            } catch (IllegalArgumentException e) {
                return null;
            }
        }).orElse(null);
        this.following = input.getBooleanOr("PvpBotFollowing", true);
        this.assisting = input.getBooleanOr("PvpBotAssisting", true);
        try {
            this.style = Style.valueOf(input.getStringOr("PvpBotStyle", "AUTO"));
        } catch (IllegalArgumentException e) {
            this.style = Style.AUTO;
        }
        this.gapples = input.getIntOr("PvpBotGapples", MAX_GAPPLES);
        this.talk = input.getBooleanOr("PvpBotTalk", true);
        this.mace = input.read("PvpBotMace", ItemStack.OPTIONAL_CODEC).orElse(ItemStack.EMPTY);
        this.spear = input.read("PvpBotSpear", ItemStack.OPTIONAL_CODEC).orElse(ItemStack.EMPTY);
        this.elytra = input.read("PvpBotElytra", ItemStack.OPTIONAL_CODEC).orElse(ItemStack.EMPTY);
        this.chestplate = input.read("PvpBotChestplate", ItemStack.OPTIONAL_CODEC).orElse(ItemStack.EMPTY);
        // Re-link worn/held items with our stored copies so swapping keeps working after a reload.
        if (ItemStack.isSameItemSameComponents(this.getMainHandItem(), this.mace)) {
            this.setItemSlot(EquipmentSlot.MAINHAND, this.mace);
        } else if (ItemStack.isSameItemSameComponents(this.getMainHandItem(), this.spear)) {
            this.setItemSlot(EquipmentSlot.MAINHAND, this.spear);
        }
        this.setItemSlot(EquipmentSlot.CHEST, this.chestplate.isEmpty() ? this.getItemBySlot(EquipmentSlot.CHEST) : this.chestplate);
    }
}
