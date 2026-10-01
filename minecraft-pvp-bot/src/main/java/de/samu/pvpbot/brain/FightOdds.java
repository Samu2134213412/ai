package de.samu.pvpbot.brain;

import java.util.List;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.BowItem;
import net.minecraft.world.item.CrossbowItem;
import net.minecraft.world.item.ItemStack;

/**
 * Would it win? A rough guess like a player makes before a fight, only from what can be seen:
 * health, the armor someone wears and the weapon in their hand. Strength = how much it can take
 * (health, more with armor) times how hard it hits; against a group the strengths add up.
 */
public final class FightOdds {
    /** Start a fight only with at least this share of the enemy's strength. */
    public static final double START = 0.75;
    /** Mid-fight below this share: get out. */
    public static final double GIVE_UP = 0.45;

    private FightOdds() {
    }

    /** Armor points worn (from the items, so it also works for other players seen from a client). */
    public static double armor(LivingEntity e) {
        double a = e.getAttributes().hasAttribute(Attributes.ARMOR) ? e.getAttributeBaseValue(Attributes.ARMOR) : 0.0;
        for (EquipmentSlot slot : new EquipmentSlot[]{EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET}) {
            ItemStack st = e.getItemBySlot(slot);
            if (!st.isEmpty()) {
                a += Kit.armorValue(st, slot);
            }
        }
        return Math.min(a, 30.0);
    }

    /** Damage per hit of what it holds (a bow counts like a good sword: it hits from afar). */
    public static double weapon(ItemStack held) {
        if (held.isEmpty()) {
            return 1.0;
        }
        if (held.getItem() instanceof BowItem || held.getItem() instanceof CrossbowItem) {
            return 6.0;
        }
        return Math.max(1.0, Kit.attackDamage(held));
    }

    /** Damage per hit someone else can do, from what is seen (their hand, or a monster's own attack). */
    public static double damageOf(LivingEntity e) {
        double d = weapon(e.getMainHandItem());
        if (!(e instanceof Player)) {
            if (e.getAttributes().hasAttribute(Attributes.ATTACK_DAMAGE)) {
                d = Math.max(d, e.getAttributeBaseValue(Attributes.ATTACK_DAMAGE) + (e.getMainHandItem().isEmpty() ? 0.0 : d - 1.0));
            }
            var type = e.getType();
            if (type == EntityTypes.CREEPER) d = 15.0;            // the explosion
            else if (type == EntityTypes.SKELETON || type == EntityTypes.STRAY || type == EntityTypes.BOGGED) d = Math.max(d, 4.0);
            else if (type == EntityTypes.BLAZE || type == EntityTypes.GHAST || type == EntityTypes.WITCH) d = Math.max(d, 6.0);
            else if (type == EntityTypes.WARDEN) d = 30.0;
        }
        return d;
    }

    /** Strength: what it can take times what it deals. */
    public static double strength(LivingEntity e, double damage) {
        double hp = e.getHealth() + e.getAbsorptionAmount();
        double protection = Math.min(0.8, armor(e) * 0.04);
        return hp / (1.0 - protection) * damage;
    }

    public static double strength(LivingEntity e) {
        return strength(e, damageOf(e));
    }

    /** Its share of the enemies' strength (above 1: stronger than all of them together). */
    public static double odds(LivingEntity self, double ownDamage, List<? extends LivingEntity> enemies) {
        double them = 0.0;
        for (LivingEntity e : enemies) {
            them += strength(e);
        }
        return them <= 0.0 ? 99.0 : strength(self, ownDamage) / them;
    }

    /** The enemy and the monsters it can see right next to it (they join in). */
    public static List<LivingEntity> group(LivingEntity self, LivingEntity enemy) {
        List<LivingEntity> list = new java.util.ArrayList<>();
        list.add(enemy);
        if (enemy instanceof Enemy) {
            for (LivingEntity other : enemy.level().getEntitiesOfClass(LivingEntity.class, enemy.getBoundingBox().inflate(6.0),
                    o -> o != enemy && o != self && o.isAlive() && o instanceof Enemy && self.hasLineOfSight(o))) {
                list.add(other);
            }
        }
        return list;
    }
}
