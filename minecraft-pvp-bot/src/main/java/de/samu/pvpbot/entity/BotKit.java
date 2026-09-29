package de.samu.pvpbot.entity;

import de.samu.pvpbot.brain.Kit;
import de.samu.pvpbot.brain.Kit.Role;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;

/**
 * Everything the bot carries. Held and worn items are the very same stack objects as in this list,
 * so durability and stack sizes stay in sync. "Infinite" kits (the default kit, or one copied in
 * creative mode) never run out of consumables; kits given in survival are used up for real.
 */
public final class BotKit {
    public static final int SIZE = 45;

    private final List<ItemStack> items = new ArrayList<>();
    private boolean infinite = true;

    public List<ItemStack> items() {
        this.items.removeIf(ItemStack::isEmpty);
        return this.items;
    }

    public boolean isInfinite() {
        return this.infinite;
    }

    public void setInfinite(boolean infinite) {
        this.infinite = infinite;
    }

    public void clear() {
        this.items.clear();
    }

    public void add(ItemStack stack) {
        if (!stack.isEmpty() && this.items.size() < SIZE) {
            this.items.add(stack);
        }
    }

    /** Adds picked-up or crafted items, merging into existing stacks. Returns what did not fit. */
    public ItemStack insert(ItemStack stack) {
        for (ItemStack existing : this.items()) {
            if (stack.isEmpty()) {
                break;
            }
            if (ItemStack.isSameItemSameComponents(existing, stack) && existing.getCount() < existing.getMaxStackSize()) {
                int moved = Math.min(stack.getCount(), existing.getMaxStackSize() - existing.getCount());
                existing.grow(moved);
                stack.shrink(moved);
            }
        }
        if (!stack.isEmpty() && this.items.size() < SIZE) {
            this.items.add(stack.copy());
            stack.setCount(0);
        }
        return stack;
    }

    public boolean hasRoom() {
        return this.items().size() < SIZE;
    }

    public int count(java.util.function.Predicate<ItemStack> match) {
        int n = 0;
        for (ItemStack stack : this.items()) {
            if (match.test(stack)) {
                n += stack.getCount();
            }
        }
        return n;
    }

    /** Removes up to {@code amount} matching items; returns how many were removed. */
    public int remove(java.util.function.Predicate<ItemStack> match, int amount) {
        int removed = 0;
        for (ItemStack stack : this.items()) {
            if (removed >= amount) {
                break;
            }
            if (match.test(stack)) {
                int take = Math.min(amount - removed, stack.getCount());
                stack.shrink(take);
                removed += take;
            }
        }
        this.items();
        return removed;
    }

    public ItemStack find(Role role) {
        for (ItemStack stack : this.items()) {
            if (Kit.classify(stack) == role) {
                return stack;
            }
        }
        return ItemStack.EMPTY;
    }

    public boolean has(Role role) {
        return !this.find(role).isEmpty();
    }

    /** Uses up one item of that role. Returns false when there is none. */
    public boolean take(Role role) {
        ItemStack stack = this.find(role);
        if (stack.isEmpty()) {
            return false;
        }
        if (!this.infinite) {
            stack.shrink(1);
        }
        return true;
    }

    /** The strongest sword, axe or trident, or empty (fists). */
    public ItemStack bestBlade() {
        ItemStack best = ItemStack.EMPTY;
        double bestDamage = 0.0;
        for (ItemStack stack : this.items()) {
            Role role = Kit.classify(stack);
            if (role == Role.SWORD || role == Role.AXE || role == Role.TRIDENT) {
                double dmg = Kit.attackDamage(stack);
                if (dmg > bestDamage) {
                    best = stack;
                    bestDamage = dmg;
                }
            }
        }
        return best;
    }

    public ItemStack bestArmor(EquipmentSlot slot) {
        ItemStack best = ItemStack.EMPTY;
        double bestValue = -1.0;
        for (ItemStack stack : this.items()) {
            if (Kit.armorSlot(stack) == slot && Kit.classify(stack) == Role.ARMOR) {
                double value = Kit.armorValue(stack, slot);
                if (value > bestValue) {
                    best = stack;
                    bestValue = value;
                }
            }
        }
        return best;
    }

    public String signature() {
        return Kit.signature(this.items());
    }

    /** Puts on the best armor and fills the off hand with a totem (or a shield). */
    public void equipBest(LivingEntity bot, boolean wearElytra) {
        for (EquipmentSlot slot : new EquipmentSlot[]{EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET}) {
            ItemStack wanted = slot == EquipmentSlot.CHEST && wearElytra ? this.find(Role.ELYTRA) : this.bestArmor(slot);
            if (slot == EquipmentSlot.CHEST && wanted.isEmpty() && !wearElytra) {
                wanted = ItemStack.EMPTY;
            }
            if (bot.getItemBySlot(slot) != wanted) {
                bot.setItemSlot(slot, wanted);
            }
        }
        ItemStack offhand = this.find(Role.TOTEM);
        if (offhand.isEmpty()) {
            offhand = this.find(Role.SHIELD);
        }
        if (bot.getItemBySlot(EquipmentSlot.OFFHAND) != offhand) {
            bot.setItemSlot(EquipmentSlot.OFFHAND, offhand);
        }
    }
}
