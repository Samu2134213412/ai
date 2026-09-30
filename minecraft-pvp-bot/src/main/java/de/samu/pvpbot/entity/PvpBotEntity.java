package de.samu.pvpbot.entity;

import de.samu.pvpbot.PvpBotMod;
import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.brain.BotBrain.Pattern;
import de.samu.pvpbot.brain.Kit;
import de.samu.pvpbot.brain.Kit.Role;
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
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
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
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.entity.projectile.ProjectileUtil;
import net.minecraft.world.entity.projectile.arrow.AbstractArrow;
import net.minecraft.world.item.BowItem;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.gamerules.GameRules;
import net.minecraft.world.level.levelgen.Heightmap;
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
    static final boolean DEBUG = Boolean.getBoolean("pvpbot.selftest");
    private static final int WIND_COOLDOWN = 45;
    private static final int SPEAR_COOLDOWN = 50;
    private static final int FLIGHT_COOLDOWN = 60;
    private static final int MAX_GAPPLES = 8;

    private @Nullable UUID ownerId;
    private boolean following = true;
    private boolean assisting = true;
    private Style style = Style.AUTO;
    private final Deque<UUID> targetQueue = new ArrayDeque<>();
    // No wallhacks: the bot only knows where a target is while it can see it.
    private @Nullable Vec3 lastSeenPos;
    private int unseenTicks;

    private final BotKit kit = new BotKit();
    private @Nullable BlockPos clutchWater;
    private int clutchTicks;
    final Gatherer gatherer = new Gatherer(this);
    private int foodCooldown;
    private boolean duelOwner;

    // Getting unstuck.
    private @Nullable Vec3 stuckAnchor;
    private int stuckTicks;
    private int unstuckStage;
    private long lastUnstuckTime;
    private int bowShots;

    private Mode mode = Mode.IDLE;
    private int modeTicks;
    private boolean lancePlan;
    private boolean lancePassed;
    private @Nullable Vec3 retreatPos;
    /** Retreating only to get a run-up for a spear charge. */
    private boolean chargeAfterRetreat;
    /** Wind-lunge-smash combo: lunge with the spear at the top of the wind jump. */
    private boolean lungePlanned;
    /** A trick the owner asked for (/pvpbot trick): used as soon as it is possible. */
    private @Nullable Pattern forcedPattern;
    private int forcedTicks;
    // Extra tactics: ender pearls and potions.
    private int pearlCooldown;
    private @Nullable Projectile thrownPearl;
    private @Nullable Vec3 pearlPos;
    private int potionCooldown;
    /** Ticks left of running past the target after a jab (hit and run). */
    private int spearRunTicks;
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
        for (EquipmentSlot slot : EquipmentSlot.values()) {
            this.setDropChance(slot, 0.0F);
        }
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
        this.goalSelector.addGoal(2, new GatherGoal());
        this.goalSelector.addGoal(3, new FollowOwnerGoal());
        this.goalSelector.addGoal(4, new LookAtPlayerGoal(this, Player.class, 10.0F));
        this.goalSelector.addGoal(5, new RandomLookAroundGoal(this));
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
        this.duelOwner = false;
        this.setTarget(null);
    }

    /** Sparring: the bot fights its own owner until one of them is down. */
    public void startDuel(Player owner) {
        this.setOwner(owner);
        this.targetQueue.clear();
        this.duelOwner = true;
        this.setTarget(owner);
    }

    public boolean isInDuel() {
        return this.duelOwner;
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
        if (this.isAlliedTo(target) || target instanceof net.minecraft.world.entity.boss.enderdragon.EnderDragon) {
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
                return !this.duelOwner;
            }
            if (other instanceof PvpBotEntity bot && this.ownerId.equals(bot.ownerId)) {
                return true;
            }
        }
        return super.considersEntityAsAlly(other);
    }

    @Override
    public boolean canUsePortal(boolean allowPassengers) {
        return super.canUsePortal(allowPassengers) && this.gatherer.mayUsePortal();
    }

    @Override
    public boolean hurtServer(ServerLevel level, DamageSource source, float amount) {
        float before = this.getHealth() + this.getAbsorptionAmount();
        boolean hurt = super.hurtServer(level, source, amount);
        if (this.pattern != null) {
            this.attemptTaken += Math.max(0.0F, before - (this.getHealth() + this.getAbsorptionAmount()));
        }
        // The dragon is fought with its own tactic (hit it while it sits), not like a normal enemy.
        if (hurt && source.getEntity() instanceof LivingEntity attacker && attacker != this && !this.isAlliedTo(attacker)
                && !(attacker instanceof net.minecraft.world.entity.boss.enderdragon.EnderDragon)) {
            this.addTarget(attacker, false);
        }
        return hurt;
    }

    @Override
    public boolean removeWhenFarAway(double distance) {
        return false;
    }

    // ------------------------------------------------------------------ equipment

    /** The original mace/spear/elytra loadout. Consumables never run out. */
    public void equipLoadout() {
        List<ItemStack> items = new ArrayList<>();
        items.add(enchanted(new ItemStack(Items.MACE),
                Enchantments.DENSITY, 5, Enchantments.WIND_BURST, 3, Enchantments.FIRE_ASPECT, 2, Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.NETHERITE_SPEAR), Enchantments.SHARPNESS, 5, Enchantments.UNBREAKING, 3, Enchantments.LUNGE, 3));
        // The axe is for attribute swapping: its damage for mace smashes, and shield breaking.
        items.add(enchanted(new ItemStack(Items.NETHERITE_AXE), Enchantments.SHARPNESS, 5, Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.ELYTRA), Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.NETHERITE_HELMET), Enchantments.PROTECTION, 4, Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.NETHERITE_CHESTPLATE), Enchantments.PROTECTION, 4, Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.NETHERITE_LEGGINGS), Enchantments.BLAST_PROTECTION, 4, Enchantments.UNBREAKING, 3));
        items.add(enchanted(new ItemStack(Items.NETHERITE_BOOTS),
                Enchantments.PROTECTION, 4, Enchantments.FEATHER_FALLING, 4, Enchantments.UNBREAKING, 3));
        items.add(new ItemStack(Items.TOTEM_OF_UNDYING));
        items.add(new ItemStack(Items.WIND_CHARGE, 64));
        ItemStack rockets = new ItemStack(Items.FIREWORK_ROCKET, 64);
        rockets.set(DataComponents.FIREWORKS, new Fireworks(1, List.of()));
        items.add(rockets);
        items.add(new ItemStack(Items.GOLDEN_APPLE, MAX_GAPPLES));
        this.setKit(items, true);
    }

    /** Replaces everything the bot carries. The bot works out itself how to fight with it. */
    public void setKit(List<ItemStack> items, boolean infinite) {
        for (EquipmentSlot slot : EquipmentSlot.values()) {
            this.setItemSlot(slot, ItemStack.EMPTY);
        }
        this.kit.clear();
        items.forEach(this.kit::add);
        this.kit.setInfinite(infinite);
        this.gapples = MAX_GAPPLES;
        this.kit.equipBest(this, false);
        ItemStack weapon = this.style == Style.SPEAR && !this.spear().isEmpty() ? this.spear()
                : !this.mace().isEmpty() ? this.mace() : !this.spear().isEmpty() ? this.spear() : this.kit.bestBlade();
        this.holdItem(weapon);
    }

    /** Takes all items away from the bot (e.g. to give a survival kit back to its owner). */
    public List<ItemStack> removeKit() {
        List<ItemStack> items = new ArrayList<>(this.kit.items());
        this.setKit(List.of(), true);
        return items;
    }

    /** "Beat the game" mode (stage 1: diamonds, obsidian, nether portal). */
    public void setSpeedrun(boolean speedrun) {
        this.gatherer.setSpeedrun(speedrun);
    }

    public boolean isSpeedrun() {
        return this.gatherer.isSpeedrun();
    }

    public boolean portalBuilt() {
        return this.gatherer.portalBuilt();
    }

    public boolean stage2Done() {
        return this.gatherer.stage2Done();
    }

    /** For tests: start stage 2 next to an existing, lit portal. */
    public void startAtStage2(net.minecraft.core.BlockPos portal) {
        this.gatherer.setSpeedrun(true);
        this.gatherer.setPortalBuilt(true);
        this.gatherer.setPortals(portal, null);
    }

    /** Autonomous mode: upgrade its own gear, collect spare armor sets, store them at home. */
    public void setAutonomous(boolean autonomous) {
        this.gatherer.setAutonomous(autonomous);
    }

    public boolean isAutonomous() {
        return this.gatherer.isAutonomous();
    }

    public void setHome(net.minecraft.core.@org.jspecify.annotations.Nullable BlockPos home) {
        this.gatherer.setHome(home, home == null ? null : this.level().dimension());
    }

    public net.minecraft.core.@org.jspecify.annotations.Nullable BlockPos getHome() {
        return this.gatherer.home();
    }

    /** Walk home now (and wait there). */
    public void goHome() {
        this.gatherer.goHome();
    }

    public List<net.minecraft.core.BlockPos> homeChests() {
        return this.gatherer.homeChests();
    }

    /** For tests: start stage 3 with the eyes of ender already crafted. */
    public void startAtStage3() {
        this.startAtStage2(null);
        this.gatherer.setStage2Done(true);
    }

    public boolean inEnd() {
        return this.level().dimension() == net.minecraft.world.level.Level.END;
    }

    public boolean gameBeaten() {
        return this.gatherer.gameBeaten();
    }

    @Override
    public void remove(Entity.RemovalReason reason) {
        this.gatherer.releaseChunks();
        super.remove(reason);
    }

    public boolean isGathering() {
        return this.gatherer.isEnabled();
    }

    public void setGathering(boolean gathering) {
        this.gatherer.setEnabled(gathering);
    }

    public String describeNeeds() {
        return this.gatherer.describe();
    }

    /** An order from the AI chat: fetch this. Returns null when accepted, else why not. */
    public @Nullable String order(String what, int count) {
        return this.gatherer.order(what, count);
    }

    public void cancelOrder() {
        this.gatherer.cancelOrder();
    }

    public @Nullable String currentOrder() {
        return this.gatherer.currentOrder();
    }

    public static String orderOptions() {
        return Gatherer.orderOptions();
    }

    private @Nullable Vec3 hardPos;
    private int hardKit;
    private int hardSeconds;

    public boolean isTalking() {
        return this.talk;
    }

    /** Called after crafting or picking something up: wear the best armor, keep a weapon in hand. */
    void onKitChanged() {
        this.kit.equipBest(this, this.isFallFlying());
        ItemStack hand = this.getMainHandItem();
        if (hand.isEmpty() || !this.kit.items().contains(hand)) {
            ItemStack weapon = !this.mace().isEmpty() ? this.mace() : !this.spear().isEmpty() ? this.spear() : this.kit.bestBlade();
            this.holdItem(weapon);
        }
    }

    void holdTool(ItemStack tool) {
        this.holdItem(tool);
    }

    void lookAtBlock(BlockPos pos) {
        this.manualRotation = false;
        this.getLookControl().setLookAt(pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5);
    }

    void huntTarget(LivingEntity prey) {
        this.addTarget(prey, true);
    }

    public BotKit getKit() {
        return this.kit;
    }

    public String describeKit() {
        StringBuilder sb = new StringBuilder(Kit.describeSignature(this.kit.signature()));
        sb.append(this.kit.isInfinite() ? " §8(unendlich)" : " §8(verbraucht sich)");
        return sb.toString();
    }

    private ItemStack mace() {
        return this.kit.find(Role.MACE);
    }

    private ItemStack spear() {
        return this.kit.find(Role.SPEAR);
    }

    private ItemStack bow() {
        ItemStack bow = this.kit.find(Role.BOW);
        return bow.isEmpty() ? this.kit.find(Role.CROSSBOW) : bow;
    }

    private boolean hasArrows() {
        return this.kit.has(Role.ARROW) || this.kit.isInfinite() && !this.bow().isEmpty();
    }

    @Override
    protected void dropCustomDeathLoot(ServerLevel level, DamageSource source, boolean killedByPlayer) {
        super.dropCustomDeathLoot(level, source, killedByPlayer);
        if (!this.kit.isInfinite()) {
            // A kit given in survival is real loot.
            for (ItemStack stack : new ArrayList<>(this.kit.items())) {
                this.spawnAtLocation(level, stack.copy());
            }
            this.kit.clear();
        }
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

    /** Like holdWeapon, but also allows an empty hand (fists). */
    private void holdItem(ItemStack item) {
        if (this.getMainHandItem() != item) {
            if (this.isUsingItem()) {
                this.stopUsingItem();
            }
            this.setItemSlot(EquipmentSlot.MAINHAND, item);
        }
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
        ItemStack spear = this.spear();
        return !spear.isEmpty() && this.getMainHandItem() == spear;
    }

    private void wearElytra(boolean wantElytra) {
        ItemStack wanted = wantElytra ? this.kit.find(Role.ELYTRA) : this.kit.bestArmor(EquipmentSlot.CHEST);
        if ((wantElytra ? !wanted.isEmpty() : true) && this.getItemBySlot(EquipmentSlot.CHEST) != wanted) {
            this.setItemSlot(EquipmentSlot.CHEST, wanted);
        }
    }

    private boolean wantsMace() {
        return this.style != Style.SPEAR && !this.mace().isEmpty();
    }

    private boolean wantsSpear() {
        return this.style != Style.MACE && !this.spear().isEmpty();
    }

    // ------------------------------------------------------------------ server tick

    private int retreatUntil;

    public boolean isRetreating() {
        return this.tickCount < this.retreatUntil;
    }

    /**
     * Several monsters on it and low on health (a blaze spawner): back off like a player, eat, and
     * only go on once it is healthy again - one at a time instead of all of them at once.
     */
    private void tickRetreat(ServerLevel level) {
        if (!this.gatherer.isSpeedrun() && !this.gatherer.isAutonomousMode()) {
            return;
        }
        List<net.minecraft.world.entity.monster.Monster> near = level.getEntitiesOfClass(net.minecraft.world.entity.monster.Monster.class,
                this.getBoundingBox().inflate(14.0), m -> m.isAlive() && m.getTarget() == this);
        if (!this.isRetreating()) {
            if (this.getHealth() >= 8.0F || near.size() < 2) {
                return;
            }
            this.retreatUntil = this.tickCount + 200;
            this.tellOwner("§6Zu viele auf einmal – ich ziehe mich zurück und esse.", false);
            if (DEBUG) {
                PvpBotMod.LOGGER.info("[SELFTEST]   retreat: hp {} with {} monsters on it", this.getHealth(), near.size());
            }
        }
        if (near.isEmpty() && this.getHealth() >= 14.0F || this.getHealth() >= 17.0F) {
            this.retreatUntil = 0;
            return;
        }
        this.setTarget(null);
        if (near.isEmpty()) {
            return;
        }
        Vec3 center = Vec3.ZERO;
        for (var m : near) {
            center = center.add(m.position());
        }
        center = center.scale(1.0 / near.size());
        Vec3 away = this.position().subtract(center).multiply(1.0, 0.0, 1.0);
        if (away.lengthSqr() < 1.0E-4) {
            away = new Vec3(1.0, 0.0, 0.0);
        }
        Vec3 goal = this.position().add(away.normalize().scale(8.0));
        if (this.getNavigation().isDone() || this.tickCount % 20 == 0) {
            this.getNavigation().moveTo(goal.x, goal.y, goal.z, 1.3);
        }
    }

    /**
     * While fighting, and always in the nether and the End: never step off a ledge into a deep drop
     * or lava (a fortress bridge over the lava sea). Like a player who sneaks at the edge: stop.
     */
    private void guardLedge(ServerLevel level) {
        boolean dangerous = this.level().dimension() != net.minecraft.world.level.Level.OVERWORLD; // (lava seas, the void)
        if (this.getTarget() == null && !dangerous || !this.onGround() || this.isFallFlying()
                || !this.gatherer.isAutonomousMode() && !this.gatherer.isSpeedrun()) {
            return;
        }
        Vec3 v = this.getDeltaMovement();
        Vec3 dir = new Vec3(v.x, 0.0, v.z);
        if (dir.lengthSqr() < 1.0E-4) {
            return;
        }
        Vec3 ahead = this.position().add(dir.normalize().scale(0.8));
        BlockPos col = BlockPos.containing(ahead.x, this.getY() - 0.5, ahead.z);
        int depth = 0;
        while (depth < 4 && level.getBlockState(col.below(depth)).getCollisionShape(level, col.below(depth)).isEmpty()
                && level.getFluidState(col.below(depth)).isEmpty()) {
            depth++;
        }
        boolean lava = level.getFluidState(col.below(depth)).is(net.minecraft.tags.FluidTags.LAVA)
                || level.getFluidState(col.below(Math.max(0, depth - 1))).is(net.minecraft.tags.FluidTags.LAVA);
        if (depth >= 4 || lava) {
            this.setDeltaMovement(0.0, v.y, 0.0);
            this.getNavigation().stop();
            this.getMoveControl().setWantedPosition(this.getX(), this.getY(), this.getZ(), 0.0);
        }
    }

    @Override
    protected void customServerAiStep(ServerLevel level) {
        super.customServerAiStep(level);
        this.refreshTarget(level);

        this.gatherer.keepChunksLoaded();
        this.gatherer.reflexActive = this.gatherer.reflexes();
        if ((this.gatherer.isSpeedrun() || this.gatherer.isAutonomousMode()) && this.tickCount % 20 == 0) {
            int kitCount = 0;
            for (ItemStack st : this.getKit().items()) {
                kitCount += st.getCount() * 31 + net.minecraft.core.registries.BuiltInRegistries.ITEM.getId(st.getItem());
            }
            if (this.hardPos == null || this.position().distanceTo(this.hardPos) > 6.0 || kitCount != this.hardKit
                    || this.getTarget() != null || this.gatherer.gameBeaten() || this.inEnd()) {
                this.hardPos = this.position();
                this.hardKit = kitCount;
                this.hardSeconds = 0;
            } else if (++this.hardSeconds >= 180) {
                this.hardSeconds = 0;
                this.gatherer.forceFree();
            }
        }
        if (this.getTarget() == null && this.getOwner() instanceof ServerPlayer talker && talker.level() == this.level()
                && this.distanceToSqr(talker) < 16.0 * 16.0 && de.samu.pvpbot.voice.BotVoice.isSpeaking(talker.getUUID())) {
            // Its owner talks (Simple Voice Chat): it turns round and listens.
            this.getLookControl().setLookAt(talker, 30.0F, 30.0F);
        }
        this.guardLedge(level);
        this.tickRetreat(level);
        if (this.windCooldown > 0) this.windCooldown--;
        if (this.pearlCooldown > 0) this.pearlCooldown--;
        if (this.potionCooldown > 0) this.potionCooldown--;
        this.tickPearl();
        if (this.spearCooldown > 0) this.spearCooldown--;
        if (this.meleeCooldown > 0) this.meleeCooldown--;
        if (this.rocketCooldown > 0) this.rocketCooldown--;
        if (this.flightCooldown > 0) this.flightCooldown--;
        if (this.gappleCooldown > 0) this.gappleCooldown--;

        // Eat a golden apple when low.
        if (this.getHealth() < 10.0F && this.gappleCooldown == 0
                && (this.kit.isInfinite() ? this.gapples > 0 && this.kit.has(Role.GAPPLE) : this.kit.take(Role.GAPPLE))) {
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
                if (this.kit.isInfinite()) {
                    this.gapples = MAX_GAPPLES;
                    if (!this.kit.has(Role.TOTEM) && this.kit.signature().length() > 0) {
                        this.kit.add(new ItemStack(Items.TOTEM_OF_UNDYING));
                    }
                }
                this.kit.equipBest(this, false);
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
                && this.groundDistance(3) <= 2 && !(this.getTarget() != null && this.inSmashReach(this.getTarget()))
                && this.kit.take(Role.WIND_CHARGE)) {
            this.windBurst(level, new Vec3(v.x * 0.5, 0.55, v.z * 0.5));
            this.resetFallDistance();
        } else if (!this.onGround() && !this.isFallFlying() && v.y < -0.5 && this.fallDistance > 5.0 && this.clutchWater == null
                && level.dimension() != net.minecraft.world.level.Level.NETHER && this.groundDistance(3) <= 3
                && this.kit.count(st -> st.is(Items.WATER_BUCKET)) > 0) {
            // Water bucket clutch, like a player: water on the ground right before landing.
            BlockPos feet = this.blockPosition();
            for (int i = 1; i <= 4; i++) {
                BlockPos p = feet.below(i);
                if (!level.getBlockState(p).getCollisionShape(level, p).isEmpty()) {
                    BlockPos spot = p.above();
                    if (level.getBlockState(spot).canBeReplaced() && level.getFluidState(spot).isEmpty()) {
                        level.setBlock(spot, net.minecraft.world.level.block.Blocks.WATER.defaultBlockState(), 3);
                        level.playSound(null, spot, net.minecraft.sounds.SoundEvents.BUCKET_EMPTY, this.getSoundSource(), 1.0F, 1.0F);
                        if (!this.kit.isInfinite()) {
                            this.kit.remove(st -> st.is(Items.WATER_BUCKET), 1);
                            this.kit.insert(new ItemStack(Items.BUCKET));
                        }
                        this.clutchWater = spot;
                        this.clutchTicks = 0;
                    }
                    break;
                }
            }
        }
        if (this.clutchWater != null && ++this.clutchTicks > 10 && (this.onGround() || this.isInWater())) {
            // Landed: scoop the water up again.
            if (level.getFluidState(this.clutchWater).isSource() && level.getFluidState(this.clutchWater).is(net.minecraft.tags.FluidTags.WATER)) {
                level.setBlock(this.clutchWater, net.minecraft.world.level.block.Blocks.AIR.defaultBlockState(), 3);
                level.playSound(null, this.clutchWater, net.minecraft.sounds.SoundEvents.BUCKET_FILL, this.getSoundSource(), 1.0F, 1.0F);
                if (!this.kit.isInfinite()) {
                    this.kit.remove(st -> st.is(Items.BUCKET), 1);
                    this.kit.insert(new ItemStack(Items.WATER_BUCKET));
                }
            }
            this.clutchWater = null;
        }

        // Keep the off hand stocked (a popped totem is gone) and never stay stuck somewhere.
        if (this.tickCount % 20 == 0 && this.getOffhandItem().isEmpty()) {
            this.kit.equipBest(this, this.isFallFlying());
        }
        this.tickStuck(level);
        this.trackDragonArrows(level);
        if (!this.kit.isInfinite()) {
            this.pickUpItems(level);
            this.eatFood(level);
        }
    }

    /** Its arrows in flight: in the game only players (and explosions) can hurt the dragon. */
    private final List<AbstractArrow> dragonArrows = new ArrayList<>();
    private final java.util.Map<AbstractArrow, Vec3> arrowTargets = new java.util.HashMap<>();
    private int arrowLogs;

    /**
     * Arrows the bot shot hit the dragon like a player's arrows would (same damage as the game gives
     * an arrow: speed times base damage, a quarter plus one on the body, full on the head).
     */
    private void trackDragonArrows(ServerLevel level) {
        if (this.dragonArrows.isEmpty()) {
            return;
        }
        for (java.util.Iterator<AbstractArrow> it = this.dragonArrows.iterator(); it.hasNext(); ) {
            AbstractArrow arrow = it.next();
            Vec3 motion = arrow.getDeltaMovement();
            if (arrow.isRemoved() || arrow.tickCount > 200 || motion.lengthSqr() < 0.01) {
                Vec3 aimed = this.arrowTargets.remove(arrow);
                if (DEBUG && aimed != null && ++this.arrowLogs < 60) {
                    Vec3 d = arrow.position().subtract(aimed);
                    PvpBotMod.LOGGER.info("[SELFTEST]   arrow landed off by dx {} dy {} dz {} (aimed {} from {}, age {}, removed {})",
                            String.format("%.1f", d.x), String.format("%.1f", d.y), String.format("%.1f", d.z),
                            BlockPos.containing(aimed).toShortString(), this.blockPosition().toShortString(), arrow.tickCount, arrow.isRemoved());
                }
                it.remove();
                continue;
            }
            Vec3 from = arrow.position();
            Vec3 to = from.add(motion);
            AABB sweep = new AABB(from, to).inflate(0.5);
            for (var crystal : level.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EndCrystal.class, sweep.inflate(2.0))) {
                AABB box = crystal.getBoundingBox().inflate(0.3);
                if (crystal.isAlive() && (box.contains(from) || box.clip(from, to).isPresent())) {
                    var type = level.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.DAMAGE_TYPE).getOrThrow(BOT_ATTACK);
                    boolean hurt = crystal.hurtServer(level, new net.minecraft.world.damagesource.DamageSource(type, arrow, this), 5.0F);
                    if (DEBUG) {
                        PvpBotMod.LOGGER.info("[SELFTEST]   arrow hit crystal at {} -> destroyed={} (invulnerable {})", crystal.blockPosition().toShortString(),
                                hurt, crystal.isInvulnerable());
                    }
                    this.arrowTargets.remove(arrow);
                    arrow.discard();
                    it.remove();
                    return;
                }
            }
            for (var dragon : level.getEntitiesOfClass(net.minecraft.world.entity.boss.enderdragon.EnderDragon.class, sweep.inflate(24.0))) {
                for (var part : dragon.getSubEntities()) {
                    AABB box = part.getBoundingBox().inflate(0.3);
                    if (box.contains(from) || box.clip(from, to).isPresent()) {
                        float damage = (float) Math.ceil(motion.length() * 2.0); // 2 = an arrow's base damage
                        var type = level.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.DAMAGE_TYPE).getOrThrow(BOT_ATTACK);
                        boolean hurt = part.hurtServer(level, new net.minecraft.world.damagesource.DamageSource(type, arrow, this), damage);
                        if (DEBUG) {
                            PvpBotMod.LOGGER.info("[SELFTEST]   arrow hit dragon {} for {} -> hurt={} (dragon hp {})", part == dragon.head ? "head" : "body",
                                    damage, hurt, (int) dragon.getHealth());
                        }
                        arrow.discard();
                        it.remove();
                        return;
                    }
                }
            }
        }
    }

    /** Survival kits: pick up useful drops (materials, loot of kills). */
    private void pickUpItems(ServerLevel level) {
        if (this.tickCount % 4 != 0) {
            return;
        }
        boolean changed = false;
        for (net.minecraft.world.entity.item.ItemEntity item : level.getEntitiesOfClass(net.minecraft.world.entity.item.ItemEntity.class,
                this.getBoundingBox().inflate(2.5, 1.0, 2.5))) {
            if (!item.isAlive() || item.hasPickUpDelay() || !Gatherer.isUseful(item.getItem())) {
                continue;
            }
            if (this.gatherer.enoughOf(item.getItem())) {
                continue; // plenty of building blocks already: the room is for what it came for
            }
            if (!this.gatherer.makeRoomFor(item.getItem())) {
                continue; // inventory full of things that matter more
            }
            ItemStack stack = item.getItem().copy();
            int before = stack.getCount();
            ItemStack rest = this.kit.insert(stack);
            int taken = before - rest.getCount();
            if (taken > 0) {
                this.take(item, taken);
                changed = true;
                if (rest.isEmpty()) {
                    item.discard();
                } else {
                    item.setItem(rest);
                }
            }
        }
        if (changed) {
            this.onKitChanged();
        }
    }

    /** Survival kits: eat food to heal outside of fights. */
    private void eatFood(ServerLevel level) {
        if (this.foodCooldown > 0) {
            this.foodCooldown--;
            return;
        }
        // (A player gets about 8 hearts' worth of healing out of a steak through natural regeneration;
        // the bot has no hunger bar, so a steak heals it directly - 8 points, a bit less than that.)
        // (Fighting a monster and low on health: eat in between anyway.)
        boolean lowVsMob = this.getTarget() != null && !(this.getTarget() instanceof Player) && this.getHealth() < 8.0F;
        if ((this.getTarget() == null && this.getHealth() < this.getMaxHealth() - 6.0F || lowVsMob)
                && this.kit.remove(Gatherer.Res.COOKED_MEAT.match, 1) == 1) {
            this.heal(8.0F);
            this.foodCooldown = 40;
            level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.GENERIC_EAT, this.getSoundSource(), 1.0F, 1.0F);
        }
    }

    // ------------------------------------------------------------------ getting unstuck

    private void tickStuck(ServerLevel level) {
        LivingEntity target = this.getTarget();
        Player owner = this.getOwner();
        boolean wantsToMove = this.isFallFlying()
                || target != null && this.pattern != Pattern.BOW_SNIPE && this.distanceTo(target) > 4.0
                || target == null && this.following && owner != null && this.distanceToSqr(owner) > 36.0;
        if (this.isInWall()) {
            this.stuckTicks += 5;
        } else if (!wantsToMove) {
            this.stuckTicks = 0;
            this.stuckAnchor = null;
            return;
        }
        if (this.stuckAnchor == null || this.position().distanceToSqr(this.stuckAnchor) > 2.25) {
            this.stuckAnchor = this.position();
            this.stuckTicks = 0;
            if (level.getGameTime() - this.lastUnstuckTime > 200L) {
                this.unstuckStage = 0;
            }
            return;
        }
        this.stuckTicks++;
        if (this.stuckTicks >= (this.isFallFlying() ? 15 : 40)) {
            this.stuckTicks = 0;
            this.unstuck(level);
        }
    }

    /** A direction to hop to with ground under it and no lava near; NaN if there is none. */
    private double safeHopAngle(ServerLevel level) {
        double start = this.random.nextDouble() * Math.PI * 2.0;
        for (int k = 0; k < 8; k++) {
            double a = start + k * Math.PI / 4.0;
            BlockPos land = BlockPos.containing(this.getX() + Math.cos(a) * 1.6, this.getY(), this.getZ() + Math.sin(a) * 1.6);
            boolean ground = false;
            boolean lava = false;
            for (int dy = -3; dy <= 1; dy++) {
                BlockPos p = land.above(dy);
                lava |= level.getFluidState(p).is(net.minecraft.tags.FluidTags.LAVA);
                if (dy < 0 && dy >= -2 && !level.getBlockState(p).getCollisionShape(level, p).isEmpty()) {
                    ground = true;
                }
            }
            if (ground && !lava) {
                return a;
            }
        }
        return Double.NaN;
    }

    /** Tries ever stronger ways out: hop aside, wind charge, dig free, teleport. */
    private void unstuck(ServerLevel level) {
        this.unstuckStage++;
        this.lastUnstuckTime = level.getGameTime();
        if (this.pattern != null) {
            // Getting stuck is a bad outcome for whatever the bot was trying.
            this.attemptTaken += 3.0F;
        }
        boolean wasFlying = this.isFallFlying();
        if (wasFlying) {
            this.stopFallFlying();
            this.flightCooldown = 100;
        }
        if (this.mode != Mode.GROUND && this.mode != Mode.IDLE) {
            this.stopUsingItem();
            this.setMode(Mode.GROUND);
        }
        this.getNavigation().stop();
        double angle = this.safeHopAngle(level);
        if (Double.isNaN(angle) && this.unstuckStage <= 2) {
            this.unstuckStage = 2; // (no safe side to hop to - lava or a drop all round: dig free instead)
            angle = 0.0;
        }
        String how;
        switch (this.unstuckStage) {
            case 1 -> {
                this.setDeltaMovement(Math.cos(angle) * 0.35, 0.45, Math.sin(angle) * 0.35);
                this.needsSync = true;
                how = "springe zur Seite";
            }
            case 2 -> {
                if (this.kit.take(Role.WIND_CHARGE)) {
                    this.windBurst(level, new Vec3(Math.cos(angle) * 0.4, 1.0, Math.sin(angle) * 0.4));
                    how = "Windladung";
                } else {
                    this.setDeltaMovement(Math.cos(angle) * 0.5, 0.5, Math.sin(angle) * 0.5);
                    this.needsSync = true;
                    how = "springe weg";
                }
            }
            case 3 -> {
                if (this.breakFree(level)) {
                    how = "baue mich frei";
                } else {
                    this.teleportFree(level);
                    how = "teleportiere mich raus";
                    this.unstuckStage = 0;
                }
            }
            default -> {
                this.teleportFree(level);
                how = "teleportiere mich raus";
                this.unstuckStage = 0;
            }
        }
        if (DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   stuck -> {}", how);
        }
        this.tellOwner("§7Ich stecke fest – " + how + ".", false);
    }

    /** Breaks the blocks around feet and head (never bedrock, obsidian or containers). */
    private boolean breakFree(ServerLevel level) {
        if (!level.getGameRules().get(GameRules.MOB_GRIEFING)) {
            return false;
        }
        boolean broke = false;
        BlockPos base = this.blockPosition();
        for (int dy = 0; dy <= 2; dy++) {
            for (int dx = -1; dx <= 1; dx++) {
                for (int dz = -1; dz <= 1; dz++) {
                    BlockPos p = base.offset(dx, dy, dz);
                    BlockState state = level.getBlockState(p);
                    if (state.isAir() || state.hasBlockEntity() || state.getCollisionShape(level, p).isEmpty()) {
                        continue;
                    }
                    float hardness = state.getDestroySpeed(level, p);
                    if (hardness >= 0.0F && hardness <= 25.0F) {
                        broke |= level.destroyBlock(p, true, this, 512);
                    }
                }
            }
        }
        if (broke) {
            this.swingMainHand();
        }
        return broke;
    }

    private boolean isStandable(ServerLevel level, BlockPos p) {
        return level.getBlockState(p).getCollisionShape(level, p).isEmpty()
                && level.getBlockState(p.above()).getCollisionShape(level, p.above()).isEmpty()
                && !level.getBlockState(p.below()).getCollisionShape(level, p.below()).isEmpty()
                && level.getFluidState(p).isEmpty();
    }

    private void teleportFree(ServerLevel level) {
        if (this.gatherer.isSpeedrun() || this.gatherer.isAutonomousMode()) {
            // Playing the game on its own: no teleporting (a player cannot) - hop and try again.
            this.getJumpControl().jump();
            this.setDeltaMovement(this.getDeltaMovement().add((this.random.nextDouble() - 0.5) * 0.4, 0.0, (this.random.nextDouble() - 0.5) * 0.4));
            return;
        }
        BlockPos base = this.blockPosition();
        BlockPos dest = null;
        for (int i = 0; i < 40 && dest == null; i++) {
            BlockPos p = base.offset(this.random.nextInt(13) - 6, this.random.nextInt(9) - 2, this.random.nextInt(13) - 6);
            if (this.isStandable(level, p)) {
                dest = p;
            }
        }
        if (dest == null) {
            dest = new BlockPos(base.getX(), level.getHeight(Heightmap.Types.MOTION_BLOCKING, base.getX(), base.getZ()), base.getZ());
        }
        level.sendParticles(ParticleTypes.PORTAL, this.getX(), this.getY() + 1.0, this.getZ(), 30, 0.3, 0.8, 0.3, 0.2);
        this.teleportTo(dest.getX() + 0.5, dest.getY(), dest.getZ() + 0.5);
        this.setDeltaMovement(Vec3.ZERO);
        this.resetFallDistance();
        level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.ENDERMAN_TELEPORT, this.getSoundSource(), 1.0F, 1.0F);
    }

    void tellOwner(String message, boolean important) {
        long now = this.level().getGameTime();
        if (this.talk && (important || now - this.lastMessageTime > 300L) && this.getOwner() instanceof ServerPlayer owner) {
            this.lastMessageTime = now;
            owner.sendSystemMessage(Component.literal("§b[" + this.getName().getString() + "] " + message));
        }
    }

    private void refreshTarget(ServerLevel level) {
        if (this.isRetreating()) {
            this.setTarget(null);
            return;
        }
        LivingEntity current = this.getTarget();
        if (current != null && !this.isValidTarget(current)) {
            if (this.duelOwner && this.isOwnedBy(current)) {
                this.duelOwner = false;
                this.tellOwner(current.isAlive() ? "§7Duell beendet." : "§6GG! §7Das Duell geht an mich.", true);
            }
            this.setTarget(null);
            current = null;
        }
        if (current == null && !this.targetQueue.isEmpty() && this.tickCount % 10 == 0) {
            // Take the next target it can actually see (or hear right next to it), like a player would.
            for (java.util.Iterator<UUID> it = this.targetQueue.iterator(); it.hasNext(); ) {
                Entity next = level.getEntity(it.next());
                if (!(next instanceof LivingEntity living) || !this.isValidTarget(living)) {
                    it.remove();
                    continue;
                }
                if (this.getSensing().hasLineOfSight(living) || this.distanceTo(living) < 5.0) {
                    it.remove();
                    this.setTarget(living);
                    current = living;
                    break;
                }
            }
        }
        if (current == null) {
            this.lastSeenPos = null;
            this.unseenTicks = 0;
        } else if (this.getSensing().hasLineOfSight(current)) {
            this.lastSeenPos = current.position();
            this.unseenTicks = 0;
        } else {
            this.unseenTicks++;
            boolean reachedLastSeen = this.lastSeenPos != null && this.position().distanceToSqr(this.lastSeenPos) < 4.0;
            if (this.lastSeenPos == null || this.unseenTicks > 400 || reachedLastSeen && this.unseenTicks > 160) {
                this.tellOwner("§7Ich habe " + current.getName().getString() + " aus den Augen verloren.", true);
                if (this.duelOwner && this.isOwnedBy(current)) {
                    this.duelOwner = false;
                }
                this.setTarget(null);
                this.lastSeenPos = null;
                this.unseenTicks = 0;
            }
        }
    }

    /** Out of sight for a while: go where it was last seen instead of knowing where it is. */
    private boolean searchLastSeen() {
        if (this.unseenTicks <= 60 || this.lastSeenPos == null || this.isFallFlying()) {
            return false;
        }
        this.manualRotation = false;
        this.setSprinting(true);
        this.getNavigation().moveTo(this.lastSeenPos.x, this.lastSeenPos.y, this.lastSeenPos.z, 1.2);
        this.getLookControl().setLookAt(this.lastSeenPos.x, this.lastSeenPos.y + 1.5, this.lastSeenPos.z);
        return true;
    }

    // ------------------------------------------------------------------ movement helpers

    private void setMode(Mode mode) {
        this.mode = mode;
        this.modeTicks = 0;
        if (mode == Mode.GROUND) {
            this.lungePlanned = false;
        }
        if (mode == Mode.GROUND && this.pattern != null && !this.pattern.melee) {
            this.finishAttempt();
        }
    }

    private void startGliding() {
        this.setSharedFlag(7, true);
    }

    private void fireRocket(ServerLevel level) {
        if (this.rocketCooldown > 0 || !this.kit.take(Role.ROCKET)) {
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
        return this.kit.has(Role.ELYTRA) && this.kit.has(Role.ROCKET) && !this.isInWater()
                && this.level().canSeeSky(this.blockPosition().above());
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
        if (!this.mace().isEmpty() && MaceItem.canSmashAttack(this) && this.inSmashReach(target)) {
            this.faceEntity(target, 180.0F);
            ItemStack axe = this.kit.find(Role.AXE);
            if (target.isBlocking() && !axe.isEmpty()) {
                // Stun slam: an axe hit knocks the shield out, the smash lands in the same tick.
                this.holdWeapon(axe);
                this.swingMainHand();
                this.doHurtTarget(level, target);
                this.tellOwner("§dStun-Slam!", false);
            }
            if (this.getMainHandItem() != this.mace()) {
                // Attribute swap: the attack damage attribute still belongs to the weapon held until
                // now (equipment attributes only update on the next tick), the mace adds its smash
                // bonus and enchantments.
                if (DEBUG) {
                    PvpBotMod.LOGGER.info("[PvPBot] attribute swap {} -> mace", this.getMainHandItem().getItem());
                }
                this.holdWeapon(this.mace());
            }
            this.swingMainHand();
            this.doHurtTarget(level, target);
            return true;
        }
        return false;
    }

    /** What to hold while falling towards a mace smash: the weapon with the highest attack damage. */
    /** Raise the shield while the weapon recharges and the enemy is close, or when they draw a bow. */
    private void tickShield(LivingEntity target, double dist) {
        if (Kit.classify(this.getItemBySlot(EquipmentSlot.OFFHAND)) != Role.SHIELD) {
            return;
        }
        boolean aiming = target.isUsingItem() && (Kit.classify(target.getUseItem()) == Role.BOW || Kit.classify(target.getUseItem()) == Role.CROSSBOW);
        boolean melee = this.pattern != null && this.pattern.melee && this.pattern != Pattern.SPEAR_KITE && this.pattern != Pattern.BOW_SNIPE;
        boolean block = melee && this.meleeCooldown > 3 && dist < 4.5 || aiming && dist > 5.0;
        if (block && !this.isUsingItem()) {
            this.startUsingItem(InteractionHand.OFF_HAND);
        } else if (!block && this.isUsingItem() && this.getUsedItemHand() == InteractionHand.OFF_HAND) {
            this.stopUsingItem();
        }
    }

    /** Potions from the kit: buffs at the start of a fight, healing when low. */
    private void usePotions(LivingEntity target, double dist) {
        if (this.potionCooldown > 0) {
            return;
        }
        boolean low = this.getHealth() < 8.0F;
        for (ItemStack stack : this.kit.items()) {
            if (Kit.classify(stack) != Role.POTION) {
                continue;
            }
            var contents = stack.get(DataComponents.POTION_CONTENTS);
            if (contents == null) {
                continue;
            }
            boolean heals = false;
            boolean missing = false;
            for (MobEffectInstance effect : contents.getAllEffects()) {
                if (effect.getEffect().equals(MobEffects.INSTANT_HEALTH) || effect.getEffect().equals(MobEffects.REGENERATION)) {
                    heals = true;
                } else if (!this.hasEffect(effect.getEffect())) {
                    missing = true;
                }
            }
            if (low && heals || missing && dist > 6.0) {
                for (MobEffectInstance effect : contents.getAllEffects()) {
                    if (effect.getDuration() <= 1) {
                        this.heal(effect.getAmplifier() >= 1 ? 8.0F : 4.0F);
                    } else {
                        this.addEffect(new MobEffectInstance(effect));
                    }
                }
                this.tellOwner("§dTrinkt " + stack.getHoverName().getString(), false);
                if (!this.kit.isInfinite()) {
                    stack.shrink(1);
                }
                this.potionCooldown = 40;
                return;
            }
        }
    }

    /** Ender pearls: chase a target that is far away on foot, or escape when low without a totem. */
    private boolean tryPearl(ServerLevel level, LivingEntity target, double dist, boolean sees) {
        if (this.pearlCooldown > 0 || !this.onGround() || !this.kit.has(Role.PEARL) || this.thrownPearl != null || this.isSpeedrun()) {
            return false;
        }
        boolean flee = this.getHealth() < 7.0F && !this.kit.has(Role.TOTEM) && dist < 8.0;
        boolean chase = sees && dist > 22.0 && dist < 60.0 && !this.canFlyHere();
        if (!flee && !chase) {
            return false;
        }
        Vec3 dir = flee ? this.position().subtract(target.position()) : target.position().subtract(this.position());
        double h = Math.min(dir.horizontalDistance(), flee ? 25.0 : dist);
        double up = (flee ? 0.0 : target.getY() - this.getY()) + h * h / 80.0;
        float yaw = (float) (Mth.atan2(dir.z, dir.x) * Mth.RAD_TO_DEG) - 90.0F;
        float pitch = (float) -(Mth.atan2(up, h) * Mth.RAD_TO_DEG);
        if (!(EntityTypes.ENDER_PEARL.create(level, EntitySpawnReason.COMMAND) instanceof Projectile pearl)) {
            return false;
        }
        pearl.setOwner(this);
        pearl.setPos(this.getX(), this.getEyeY() - 0.1, this.getZ());
        pearl.shootFromRotation(this, pitch, yaw, 0.0F, 1.5F, 0.5F);
        level.addFreshEntity(pearl);
        this.kit.take(Role.PEARL);
        this.swingMainHand();
        this.thrownPearl = pearl;
        this.pearlCooldown = 40;
        this.tellOwner(flee ? "§ePerle weg vom Gegner!" : "§ePerle hinterher!", false);
        return true;
    }

    /** Where our pearl lands, we land (also works if the game only teleports players). */
    private void tickPearl() {
        if (this.thrownPearl == null) {
            return;
        }
        if (!this.thrownPearl.isRemoved()) {
            this.pearlPos = this.thrownPearl.position();
            if (this.thrownPearl.tickCount > 200) {
                this.thrownPearl.discard();
                this.thrownPearl = null;
            }
            return;
        }
        if (this.pearlPos != null && this.pearlPos.distanceToSqr(this.position()) > 4.0) {
            this.teleportTo(this.pearlPos.x, this.pearlPos.y, this.pearlPos.z);
            this.resetFallDistance();
        }
        this.thrownPearl = null;
        this.pearlPos = null;
    }

    public void forcePattern(Pattern pattern) {
        this.forcedPattern = pattern;
        this.forcedTicks = 0;
    }

    private ItemStack smashCarrier() {
        ItemStack blade = this.kit.bestBlade();
        return !blade.isEmpty() && Kit.attackDamage(blade) > Kit.attackDamage(this.mace()) ? blade : this.mace();
    }

    // ------------------------------------------------------------------ combat

    private void tickCombat(ServerLevel level, LivingEntity target) {
        if (this.searchLastSeen()) {
            return;
        }
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
        this.usePotions(target, dist);
        if (this.pattern == null && this.tryPearl(level, target, dist, sees)) {
            return;
        }
        this.tickShield(target, dist);

        // Decide what to do next: the brain picks an attack pattern for this situation.
        if (this.pattern == null) {
            List<Pattern> options = this.feasiblePatterns(target, false);
            if (options.isEmpty()) {
                return;
            }
            BotBrain.Context ctx = this.currentContext(target);
            Pattern chosen = BotBrain.INSTANCE.choose(ctx, options, this.random);
            if (this.forcedPattern != null) {
                if (options.contains(this.forcedPattern)) {
                    chosen = this.forcedPattern;
                    this.forcedPattern = null;
                } else if (++this.forcedTicks > 200) {
                    this.tellOwner("§e" + this.forcedPattern.label + " geht gerade nicht (möglich: "
                            + options.stream().map(p -> p.label).toList() + ")", true);
                    this.forcedPattern = null;
                }
            }
            this.beginAttempt(chosen, target, ctx);
            if (!chosen.melee) {
                this.startPattern(level, target, chosen);
                return;
            }
        }
        if (this.attemptTicks > (this.pattern == Pattern.BOW_SNIPE ? 90 : 40)) {
            // Melee rounds are short so the bot re-evaluates often.
            this.finishAttempt();
            return;
        }

        if (this.pattern == Pattern.BOW_SNIPE) {
            this.tickBow(level, target, dist, sees);
            return;
        }
        boolean useSpear = this.pattern == Pattern.SPEAR_KITE;
        this.holdItem(switch (this.pattern) {
            case SPEAR_KITE -> this.spear();
            case MACE_MELEE -> this.mace();
            default -> this.kit.bestBlade();
        });

        if (this.random.nextInt(30) == 0) {
            this.strafeDir = -this.strafeDir;
        }
        if (useSpear) {
            // Hit and run: never stand still in front of the target. Run in, jab at the edge of the
            // reach (2 - 4.5 blocks), run past it, curve around and come again.
            this.setSprinting(true);
            Vec3 toT = target.position().subtract(this.position()).multiply(1.0, 0.0, 1.0);
            Vec3 dir = toT.lengthSqr() > 1.0E-4 ? toT.normalize() : this.getLookAngle();
            Vec3 side = new Vec3(-dir.z, 0.0, dir.x).scale(this.strafeDir);
            if (this.spearRunTicks > 0) {
                this.spearRunTicks--;
                Vec3 goal = this.spearRunTicks > 10
                        ? target.position().add(dir.scale(4.0)).add(side.scale(2.5))
                        : this.position().add(side.scale(4.0)).subtract(dir.scale(3.0));
                this.getNavigation().stop();
                this.getMoveControl().setWantedPosition(goal.x, this.getY(), goal.z, 1.5);
            } else if (dist < 2.0) {
                this.spearRunTicks = 14;
            } else if (sees) {
                this.getNavigation().stop();
                this.getMoveControl().setWantedPosition(target.getX(), target.getY(), target.getZ(), 1.5);
            } else {
                this.getNavigation().moveTo(target, 1.4);
            }
            if (this.horizontalCollision && this.onGround()) {
                this.getJumpControl().jump();
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
            int lunge = Kit.lungeLevel(this.spear());
            if (this.holdingSpear() && dist >= 2.0 && dist <= 4.4) {
                this.jab(target);
                this.meleeCooldown = 12;
                this.spearRunTicks = 22;
            } else if (this.holdingSpear() && lunge > 0 && dist > 5.0 && dist < 5.0 + 1.4 * lunge && this.onGround() && !this.isInWater()) {
                // Lunge as a gap closer: the jab throws the bot right into striking distance.
                this.jab(target);
                this.meleeCooldown = 10;
            } else if (!this.holdingSpear() && dist <= 3.2) {
                this.faceEntity(target, 180.0F);
                ItemStack axe = this.kit.find(Role.AXE);
                ItemStack main = this.getMainHandItem();
                if (target.isBlocking() && !axe.isEmpty() && main != axe) {
                    // Stun: an axe hit knocks the shield out, the real weapon hits in the same tick.
                    this.holdWeapon(axe);
                    this.swingMainHand();
                    this.doHurtTarget(level, target);
                    this.holdWeapon(main);
                    this.tellOwner("§7Schild weg!", false);
                } else if (Kit.classify(main) != Role.MACE && Kit.enchantLevel(this.mace(), "breach") > 0 && target.getArmorValue() >= 8) {
                    // Breach swap: this weapon's damage with the mace's Breach.
                    this.holdWeapon(this.mace());
                }
                boolean fast = this.getDeltaMovement().horizontalDistance() > 0.12;
                this.swingMainHand();
                this.doHurtTarget(level, target);
                if (fast) {
                    // Like a player's sprint hit (w-tap): extra knockback.
                    target.push(-Mth.sin(this.getYRot() * Mth.DEG_TO_RAD) * 0.4, 0.1, Mth.cos(this.getYRot() * Mth.DEG_TO_RAD) * 0.4);
                    target.needsSync = true;
                }
                // Same attack cooldown a player has with this weapon.
                double speed = Kit.attackSpeed(this.getMainHandItem());
                this.meleeCooldown = Math.max(8, (int) Math.round(20.0 / Math.max(0.5, speed)));
            }
        }
    }

    /** Bow/crossbow: keep a comfortable distance, draw fully and shoot with a bit of lead. */
    private void tickBow(ServerLevel level, LivingEntity target, double dist, boolean sees) {
        ItemStack bow = this.bow();
        if (bow.isEmpty() || !this.hasArrows()) {
            this.finishAttempt();
            return;
        }
        this.holdWeapon(bow);
        this.faceEntity(target, 30.0F);
        if (dist < 7.0) {
            this.setSprinting(true);
            this.getNavigation().stop();
            this.getMoveControl().strafe(-0.8F, this.strafeDir * 0.4F);
        } else if (dist > 24.0 || !sees) {
            this.getNavigation().moveTo(target, 1.1);
        } else {
            this.setSprinting(false);
            this.getNavigation().stop();
            this.getMoveControl().strafe(0.0F, this.strafeDir * 0.6F);
        }
        if (!this.isUsingItem()) {
            this.startUsingItem(InteractionHand.MAIN_HAND);
        } else if (this.getTicksUsingItem() >= 20 && sees && !this.bystanderInLine(level, target)) {
            this.shootArrow(level, target, bow);
            this.stopUsingItem();
            if (++this.bowShots >= 3) {
                this.bowShots = 0;
                this.finishAttempt();
            }
        }
    }

    /**
     * A neutral mob (zombified piglin, piglin, enderman) in the line of fire or right behind the
     * target: a miss would turn the whole group against it - hold the shot, like a careful player.
     */
    private boolean bystanderInLine(ServerLevel level, LivingEntity target) {
        Vec3 from = this.getEyePosition();
        Vec3 to = target.position().add(0.0, target.getBbHeight() * 0.5, 0.0);
        Vec3 dir = to.subtract(from);
        double len = dir.length();
        if (len < 1.0E-3) {
            return false;
        }
        Vec3 unit = dir.scale(1.0 / len);
        Vec3 end = to.add(unit.scale(12.0)); // (a miss flies on)
        AABB box = new AABB(from, end).inflate(2.0);
        for (LivingEntity e : level.getEntitiesOfClass(LivingEntity.class, box, e -> e != this && e != target && e.isAlive())) {
            boolean neutral = e.getType() == EntityTypes.ZOMBIFIED_PIGLIN || e.getType() == EntityTypes.PIGLIN
                    || e.getType() == EntityTypes.ENDERMAN || e.getType() == EntityTypes.PIGLIN_BRUTE;
            if (!neutral || e instanceof Mob m && m.getTarget() == this) {
                continue;
            }
            Vec3 c = e.position().add(0.0, e.getBbHeight() * 0.5, 0.0);
            double t = Math.max(0.0, Math.min(len + 12.0, c.subtract(from).dot(unit)));
            if (from.add(unit.scale(t)).distanceTo(c) < 1.3) {
                return true;
            }
        }
        return false;
    }

    private void shootArrow(ServerLevel level, LivingEntity target, ItemStack bow) {
        ItemStack arrowItem = this.kit.find(Role.ARROW);
        ItemStack ammo = arrowItem.isEmpty() ? new ItemStack(Items.ARROW) : arrowItem.copyWithCount(1);
        if (!this.kit.isInfinite() && !arrowItem.isEmpty()) {
            arrowItem.shrink(1);
        }
        AbstractArrow arrow = ProjectileUtil.getMobArrow(this, ammo, BowItem.getPowerForTime(20), bow);
        Vec3 lead = target.getDeltaMovement().multiply(1.0, 0.0, 1.0).scale(this.distanceTo(target) / 3.0);
        double xd = target.getX() + lead.x - this.getX();
        double zd = target.getZ() + lead.z - this.getZ();
        double yd = target.getY(0.5) - arrow.getY();
        double horizontal = Math.sqrt(xd * xd + zd * zd);
        Projectile.spawnProjectileUsingShoot(arrow, level, ammo, xd, yd + horizontal * horizontal / 330.0, zd, 3.0F, 1.0F);
        this.swingMainHand();
        level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.ARROW_SHOOT, this.getSoundSource(), 1.0F, 1.0F);
    }

    /** Shoots one arrow at a point (end crystals). Returns false without bow or arrows. */
    boolean shootAt(Vec3 point) {
        ItemStack bow = this.bow();
        if (bow.isEmpty() || !this.hasArrows() || !(this.level() instanceof ServerLevel level)) {
            return false;
        }
        this.holdWeapon(bow);
        ItemStack arrowItem = this.kit.find(Role.ARROW);
        ItemStack ammo = arrowItem.isEmpty() ? new ItemStack(Items.ARROW) : arrowItem.copyWithCount(1);
        if (!this.kit.isInfinite() && !arrowItem.isEmpty()) {
            arrowItem.shrink(1);
        }
        AbstractArrow arrow = ProjectileUtil.getMobArrow(this, ammo, BowItem.getPowerForTime(20), bow);
        double xd = point.x - this.getX();
        double zd = point.z - this.getZ();
        double yd = point.y - arrow.getY();
        double horizontal = Math.sqrt(xd * xd + zd * zd);
        double pitch = ballisticPitch(horizontal, yd);
        this.getLookControl().setLookAt(point.x, point.y, point.z);
        Projectile.spawnProjectileUsingShoot(arrow, level, ammo, xd, Math.tan(pitch) * horizontal, zd, 3.0F, 0.5F);
        if (this.dragonArrows.size() < 32) {
            this.dragonArrows.add(arrow);
            this.arrowTargets.put(arrow, point);
        }
        this.swingMainHand();
        level.playSound(null, this.getX(), this.getY(), this.getZ(), SoundEvents.ARROW_SHOOT, this.getSoundSource(), 1.0F, 1.0F);
        return true;
    }

    /**
     * The flattest bow angle (radians) that reaches a point {@code h} blocks away and {@code dy} higher,
     * by flying a full-power arrow tick by tick (speed 3, drag 0.99, gravity 0.05) - a player learns
     * the same arc by feel.
     */
    static double ballisticPitch(double h, double dy) {
        double best = Math.atan2(dy, h);
        double bestErr = Double.MAX_VALUE;
        for (double a = -0.6; a < 1.45; a += 0.005) {
            double vx = Math.cos(a) * 3.0;
            double vy = Math.sin(a) * 3.0;
            double x = 0.0;
            double y = 0.0;
            for (int t = 0; t < 200 && x < h; t++) {
                double px = x;
                double py = y;
                x += vx;
                y += vy;
                vx *= 0.99;
                vy = vy * 0.99 - 0.05;
                if (x >= h) {
                    double yAt = py + (y - py) * (h - px) / (x - px);
                    double err = Math.abs(yAt - dy);
                    if (err < bestErr) {
                        bestErr = err;
                        best = a;
                    }
                }
            }
            if (bestErr < 0.3) {
                break;
            }
        }
        return best;
    }

    /**
     * Melee hit on a part of the ender dragon. Vanilla only lets players (and explosions) hurt the
     * dragon, so the bot's hit uses its own damage type from the always_hurts_ender_dragons tag; the
     * damage is the plain weapon damage, the head takes it in full, the other parts a quarter.
     */
    void hitDragonPart(ServerLevel level, Entity part) {
        ItemStack blade = this.kit.find(Role.SWORD);
        if (blade.isEmpty()) {
            blade = this.kit.find(Role.AXE);
        }
        if (!blade.isEmpty()) {
            this.holdWeapon(blade);
        }
        float damage = (float) this.getAttributeValue(Attributes.ATTACK_DAMAGE);
        var type = level.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.DAMAGE_TYPE).getOrThrow(BOT_ATTACK);
        this.swingMainHand();
        boolean hurt = part.hurtServer(level, new net.minecraft.world.damagesource.DamageSource(type, this), damage);
        if (DEBUG) {
            PvpBotMod.LOGGER.info("[SELFTEST]   dragon hit {} for {} -> hurt={}", part, damage, hurt);
        }
    }

    private static final net.minecraft.resources.ResourceKey<net.minecraft.world.damagesource.DamageType> BOT_ATTACK = net.minecraft.resources.ResourceKey.create(
            net.minecraft.core.registries.Registries.DAMAGE_TYPE, net.minecraft.resources.Identifier.fromNamespaceAndPath("pvpbot", "bot_attack"));

    private void jab(LivingEntity target) {
        this.faceEntity(target, 180.0F);
        PiercingWeapon piercing = this.spear().get(DataComponents.PIERCING_WEAPON);
        if (piercing != null) {
            piercing.attack(this, EquipmentSlot.MAINHAND);
        } else if (this.level() instanceof ServerLevel level) {
            this.swingMainHand();
            this.doHurtTarget(level, target);
        }
    }

    // --- mace: wind charge jump

    private void startWindJump(ServerLevel level, LivingEntity target) {
        this.holdWeapon(this.mace());
        this.getNavigation().stop();
        Vec3 horizontal = target.position().subtract(this.position()).multiply(1.0, 0.0, 1.0);
        Vec3 push = horizontal.lengthSqr() > 1.0E-4 ? horizontal.normalize().scale(this.lungePlanned ? 0.05 : 0.15) : Vec3.ZERO;
        this.kit.take(Role.WIND_CHARGE);
        this.windBurst(level, new Vec3(push.x, 1.15, push.z));
        this.windCooldown = WIND_COOLDOWN;
        this.setMode(Mode.WIND_JUMP);
    }

    /** Airborne after a wind jump or a dive: steer onto the target and smash it on the way down. */
    private void tickAirSmash(ServerLevel level, LivingEntity target) {
        if (this.lungePlanned && this.mode == Mode.WIND_JUMP && this.modeTicks > 3 && this.getDeltaMovement().y < 0.15) {
            // Top of the jump: jab with the Lunge spear to shoot across towards the target, then
            // straight back to the mace for the smash.
            this.lungePlanned = false;
            this.holdWeapon(this.spear());
            this.jab(target);
            this.tellOwner("§7Lunge!", false);
        }
        this.holdWeapon(this.smashCarrier());
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
        this.holdWeapon(this.spear());
        this.setSprinting(true);
        if (this.distanceTo(target) < 9.0) {
            // Too close to build up speed: run away first, then turn and charge.
            Vec3 away = this.position().subtract(target.position()).multiply(1.0, 0.0, 1.0);
            away = away.lengthSqr() > 1.0E-4 ? away.normalize() : this.getLookAngle().scale(-1.0);
            this.retreatPos = target.position().add(away.scale(12.0));
            this.chargeAfterRetreat = true;
            this.setMode(Mode.SPEAR_RETREAT);
            return;
        }
        this.beginCharge();
    }

    private void beginCharge() {
        this.chargeAfterRetreat = false;
        this.getNavigation().stop();
        this.setSprinting(true);
        this.setMode(Mode.SPEAR_CHARGE);
    }

    private int spearUseDuration() {
        KineticWeapon kinetic = this.spear().get(DataComponents.KINETIC_WEAPON);
        return kinetic != null ? Math.max(20, kinetic.computeDamageUseDuration()) : 60;
    }

    /**
     * The charge deals base damage plus closing speed times a multiplier, so the bot sprints (and
     * jumps) straight at the target and only lowers the spear when it will arrive in time.
     */
    private void tickSpearCharge(ServerLevel level, LivingEntity target) {
        this.holdWeapon(this.spear());
        this.faceEntity(target, 30.0F);
        this.setSprinting(true);
        this.getMoveControl().setWantedPosition(target.getX(), target.getY(), target.getZ(), 1.9);
        if (this.onGround() && (this.horizontalCollision || this.modeTicks % 12 == 6)) {
            this.getJumpControl().jump();
        }
        double dist = this.distanceTo(target);
        double speed = Math.max(0.15, this.getDeltaMovement().multiply(1.0, 0.0, 1.0).length());
        double eta = Math.max(0.0, dist - 3.0) / speed;
        if (!this.isUsingItem()) {
            if (eta <= this.spearUseDuration() - 4 || this.modeTicks > 60) {
                this.startUsingItem(InteractionHand.MAIN_HAND);
            }
            if (this.modeTicks > 80) {
                this.finishCharge(target);
            }
            return;
        }
        boolean hit = target.hurtTime > 0 && this.getTicksUsingItem() > 4;
        if (hit || this.getTicksUsingItem() > this.spearUseDuration() || dist < 1.3) {
            this.finishCharge(target);
        }
    }

    /** Run straight through and past the target, then turn around. */
    private void finishCharge(LivingEntity target) {
        this.stopUsingItem();
        this.spearCooldown = SPEAR_COOLDOWN;
        Vec3 dir = target.position().subtract(this.position()).multiply(1.0, 0.0, 1.0);
        dir = dir.lengthSqr() > 1.0E-4 ? dir.normalize() : this.getLookAngle();
        this.retreatPos = target.position().add(dir.scale(7.0));
        this.chargeAfterRetreat = false;
        this.setMode(Mode.SPEAR_RETREAT);
    }

    private void tickSpearRetreat(LivingEntity target) {
        this.manualRotation = false;
        this.getLookControl().setLookAt(target, 60.0F, 60.0F);
        double dist = this.distanceTo(target);
        if (this.chargeAfterRetreat && (dist >= 10.0 || this.modeTicks > 40)) {
            this.beginCharge();
            return;
        }
        if (this.retreatPos == null || this.modeTicks > 40 || !this.chargeAfterRetreat && dist > 12.0) {
            this.setMode(Mode.GROUND);
            return;
        }
        this.setSprinting(true);
        this.getNavigation().moveTo(this.retreatPos.x, this.retreatPos.y, this.retreatPos.z, 1.5);
        if (this.modeTicks > 5 && this.getNavigation().isDone()) {
            if (this.chargeAfterRetreat) {
                this.beginCharge();
            } else {
                this.setMode(Mode.GROUND);
            }
        }
    }

    // --- elytra: take off, climb, then mace dive or spear lance

    private void startTakeoff(ServerLevel level, LivingEntity target) {
        this.getNavigation().stop();
        this.wearElytra(true);
        this.holdWeapon(this.lancePlan ? this.spear() : this.mace());
        Vec3 v = this.getDeltaMovement();
        if (this.kit.take(Role.WIND_CHARGE)) {
            this.windBurst(level, new Vec3(v.x, 1.0, v.z));
        } else {
            // No wind charge: jump and get going with a rocket.
            this.setDeltaMovement(v.x, 0.6, v.z);
            this.needsSync = true;
        }
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
        if (this.horizontalCollision) {
            // Flew into a wall: turn away, pull up and boost out instead of hugging the block.
            Vec3 away = this.getLookAngle().multiply(-1.0, 0.0, -1.0);
            this.face(away.add(0.0, 1.2, 0.0), 60.0F);
            this.fireRocket(level);
            return;
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
                this.holdWeapon(this.mace());
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
                this.holdWeapon(this.spear());
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
        return new BotBrain.Context(env, BotBrain.Range.of(hDist), inAir, target instanceof Player, this.kit.signature());
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
        if (!this.kit.bestBlade().isEmpty() || out.isEmpty()) {
            // Sword, axe, trident – or fists when nothing else is left.
            out.add(Pattern.BLADE_MELEE);
        }
        // (Arrows never hit an enderman: it teleports away from them.)
        if (!this.bow().isEmpty() && this.hasArrows() && sees && hDist > 2.5 && target.getType() != EntityTypes.ENDERMAN) {
            out.add(Pattern.BOW_SNIPE);
        }
        if (!flying && this.wantsMace() && this.kit.has(Role.WIND_CHARGE) && this.onGround() && this.windCooldown == 0 && sees
                && hDist > 1.0 && hDist < 8.0 && dy < 3.0 && dy > -4.0) {
            out.add(Pattern.WIND_SMASH);
        }
        if (!flying && this.wantsSpear() && this.onGround() && this.spearCooldown == 0 && sees && hDist < 18.0) {
            out.add(Pattern.SPEAR_CHARGE);
        }
        if (!flying && this.wantsMace() && this.wantsSpear() && Kit.lungeLevel(this.spear()) > 0 && this.kit.has(Role.WIND_CHARGE)
                && this.onGround() && this.windCooldown == 0 && sees && hDist > 3.0 && hDist < 12.0 && dy < 3.0 && dy > -4.0) {
            // Combo: wind charge up, lunge across with the spear at the top, smash down with the mace.
            out.add(Pattern.WIND_LUNGE_SMASH);
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
            case WIND_LUNGE_SMASH -> {
                this.lungePlanned = true;
                this.startWindJump(level, target);
            }
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

    private class GatherGoal extends Goal {
        GatherGoal() {
            this.setFlags(EnumSet.of(Goal.Flag.MOVE, Goal.Flag.LOOK));
        }

        @Override
        public boolean canUse() {
            return PvpBotEntity.this.gatherer.wantsToWork();
        }

        @Override
        public boolean requiresUpdateEveryTick() {
            return true;
        }

        @Override
        public void stop() {
            PvpBotEntity.this.gatherer.reset();
            PvpBotEntity.this.getNavigation().stop();
            PvpBotEntity.this.onKitChanged();
        }

        @Override
        public void tick() {
            PvpBotEntity.this.manualRotation = false;
            PvpBotEntity.this.gatherer.tick();
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
        output.store("PvpBotKit", ItemStack.OPTIONAL_CODEC.listOf(), new ArrayList<>(this.kit.items()));
        output.putBoolean("PvpBotKitInfinite", this.kit.isInfinite());
        output.putBoolean("PvpBotDuel", this.duelOwner);
        output.putBoolean("PvpBotGather", this.gatherer.isEnabled());
        output.putBoolean("PvpBotSpeedrun", this.gatherer.isSpeedrun());
        output.putBoolean("PvpBotPortal", this.gatherer.portalBuilt());
        output.putBoolean("PvpBotStage2", this.gatherer.stage2Done());
        if (this.gatherer.overworldPortal() != null) {
            output.putLong("PvpBotOverworldPortal", this.gatherer.overworldPortal().asLong());
        }
        if (this.gatherer.netherPortal() != null) {
            output.putLong("PvpBotNetherPortal", this.gatherer.netherPortal().asLong());
        }
        output.putInt("PvpBotFuel", this.gatherer.fuel());
        output.putBoolean("PvpBotAutonom", this.gatherer.isAutonomous());
        if (this.gatherer.home() != null && this.gatherer.homeLevel() != null) {
            output.putLong("PvpBotHome", this.gatherer.home().asLong());
            output.store("PvpBotHomeDim", net.minecraft.world.level.Level.RESOURCE_KEY_CODEC, this.gatherer.homeLevel());
        }
        output.store("PvpBotChests", net.minecraft.core.BlockPos.CODEC.listOf(), List.copyOf(this.gatherer.homeChests()));
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
        this.duelOwner = input.getBooleanOr("PvpBotDuel", false);
        this.gatherer.setEnabled(input.getBooleanOr("PvpBotGather", true));
        if (input.getBooleanOr("PvpBotSpeedrun", false)) {
            this.gatherer.setSpeedrun(true);
        }
        this.gatherer.setPortalBuilt(input.getBooleanOr("PvpBotPortal", false));
        this.gatherer.setStage2Done(input.getBooleanOr("PvpBotStage2", false));
        long ow = input.getLongOr("PvpBotOverworldPortal", Long.MIN_VALUE);
        long ne = input.getLongOr("PvpBotNetherPortal", Long.MIN_VALUE);
        this.gatherer.setPortals(ow == Long.MIN_VALUE ? null : net.minecraft.core.BlockPos.of(ow),
                ne == Long.MIN_VALUE ? null : net.minecraft.core.BlockPos.of(ne));
        this.gatherer.setFuel(input.getIntOr("PvpBotFuel", 0));
        long home = input.getLongOr("PvpBotHome", Long.MIN_VALUE);
        if (home != Long.MIN_VALUE) {
            this.gatherer.setHome(net.minecraft.core.BlockPos.of(home),
                    input.read("PvpBotHomeDim", net.minecraft.world.level.Level.RESOURCE_KEY_CODEC).orElse(net.minecraft.world.level.Level.OVERWORLD));
        }
        this.gatherer.homeChests().clear();
        this.gatherer.homeChests().addAll(input.read("PvpBotChests", net.minecraft.core.BlockPos.CODEC.listOf()).orElse(List.of()));
        if (input.getBooleanOr("PvpBotAutonom", false)) {
            this.gatherer.setAutonomous(true);
        }
        List<ItemStack> saved = input.read("PvpBotKit", ItemStack.OPTIONAL_CODEC.listOf()).orElse(null);
        this.kit.clear();
        if (saved == null) {
            // Saved before kits existed: give it the default loadout again.
            this.equipLoadout();
        } else {
            saved.forEach(this.kit::add);
            this.kit.setInfinite(input.getBooleanOr("PvpBotKitInfinite", true));
            // Re-link worn and held items with the kit's stacks so swapping keeps working.
            for (EquipmentSlot slot : EquipmentSlot.values()) {
                ItemStack worn = this.getItemBySlot(slot);
                for (ItemStack stack : this.kit.items()) {
                    if (!worn.isEmpty() && ItemStack.matches(worn, stack)) {
                        this.setItemSlot(slot, stack);
                        break;
                    }
                }
            }
        }
    }
}
