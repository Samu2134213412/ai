package de.samu.pvpbot.brain;

import net.minecraft.core.component.DataComponents;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.MaceItem;
import net.minecraft.world.item.component.ItemAttributeModifiers;
import net.minecraft.world.item.enchantment.Enchantments;

/** Sorts items into combat roles, so both bots can work with whatever PvP kit they have. */
public final class Kit {

    public enum Role {
        MACE, SPEAR, SWORD, AXE, TRIDENT, BOW, CROSSBOW, ARROW, ELYTRA, ROCKET, WIND_CHARGE,
        GAPPLE, TOTEM, SHIELD, ARMOR, OTHER
    }

    private Kit() {
    }

    public static Role classify(ItemStack stack) {
        if (stack.isEmpty()) {
            return Role.OTHER;
        }
        if (stack.getItem() instanceof MaceItem) {
            return Role.MACE;
        }
        if (stack.has(DataComponents.KINETIC_WEAPON)) {
            return Role.SPEAR;
        }
        if (stack.is(ItemTags.SWORDS)) {
            return Role.SWORD;
        }
        if (stack.is(ItemTags.AXES)) {
            return Role.AXE;
        }
        if (stack.is(Items.TRIDENT)) {
            return Role.TRIDENT;
        }
        if (stack.is(Items.BOW)) {
            return Role.BOW;
        }
        if (stack.is(Items.CROSSBOW)) {
            return Role.CROSSBOW;
        }
        if (stack.is(ItemTags.ARROWS)) {
            return Role.ARROW;
        }
        if (stack.has(DataComponents.GLIDER)) {
            return Role.ELYTRA;
        }
        if (stack.is(Items.FIREWORK_ROCKET)) {
            return Role.ROCKET;
        }
        if (stack.is(Items.WIND_CHARGE)) {
            return Role.WIND_CHARGE;
        }
        if (stack.is(Items.GOLDEN_APPLE) || stack.is(Items.ENCHANTED_GOLDEN_APPLE)) {
            return Role.GAPPLE;
        }
        if (stack.is(Items.TOTEM_OF_UNDYING)) {
            return Role.TOTEM;
        }
        if (stack.is(Items.SHIELD)) {
            return Role.SHIELD;
        }
        if (armorSlot(stack) != null) {
            return Role.ARMOR;
        }
        return Role.OTHER;
    }

    /** The armor slot an item goes into, or null for non-armor. Elytras count as armor only for the chest swap. */
    public static EquipmentSlot armorSlot(ItemStack stack) {
        var equippable = stack.get(DataComponents.EQUIPPABLE);
        if (equippable == null) {
            return null;
        }
        EquipmentSlot slot = equippable.slot();
        return slot.getType() == EquipmentSlot.Type.HUMANOID_ARMOR ? slot : null;
    }

    public static double attackDamage(ItemStack stack) {
        ItemAttributeModifiers mods = stack.getOrDefault(DataComponents.ATTRIBUTE_MODIFIERS, ItemAttributeModifiers.EMPTY);
        return mods.compute(Attributes.ATTACK_DAMAGE, 1.0, EquipmentSlot.MAINHAND);
    }

    /** Attacks per second with this item in the main hand (4 = fists). */
    /** Level of the Lunge enchantment (spear jabs throw the wielder forward), 0 if none. */
    public static int lungeLevel(ItemStack stack) {
        for (var entry : stack.getEnchantments().entrySet()) {
            if (entry.getKey().is(Enchantments.LUNGE)) {
                return entry.getIntValue();
            }
        }
        return 0;
    }

    public static double attackSpeed(ItemStack stack) {
        ItemAttributeModifiers mods = stack.getOrDefault(DataComponents.ATTRIBUTE_MODIFIERS, ItemAttributeModifiers.EMPTY);
        return mods.compute(Attributes.ATTACK_SPEED, 4.0, EquipmentSlot.MAINHAND);
    }

    public static double armorValue(ItemStack stack, EquipmentSlot slot) {
        ItemAttributeModifiers mods = stack.getOrDefault(DataComponents.ATTRIBUTE_MODIFIERS, ItemAttributeModifiers.EMPTY);
        return mods.compute(Attributes.ARMOR, 0.0, slot) + mods.compute(Attributes.ARMOR_TOUGHNESS, 0.0, slot) * 0.5;
    }

    /**
     * Short signature of what a kit can do, used to learn separately per kit:
     * M=Mace S=Speer W=Schwert A=Axt T=Dreizack B=Bogen E=Elytra+Raketen C=Windladungen.
     */
    public static String signature(Iterable<ItemStack> items) {
        boolean m = false, s = false, w = false, a = false, t = false, b = false, e = false, r = false, c = false, arrows = false;
        for (ItemStack stack : items) {
            switch (classify(stack)) {
                case MACE -> m = true;
                case SPEAR -> s = true;
                case SWORD -> w = true;
                case AXE -> a = true;
                case TRIDENT -> t = true;
                case BOW, CROSSBOW -> b = true;
                case ARROW -> arrows = true;
                case ELYTRA -> e = true;
                case ROCKET -> r = true;
                case WIND_CHARGE -> c = true;
                default -> {
                }
            }
        }
        StringBuilder sb = new StringBuilder();
        if (m) sb.append('M');
        if (s) sb.append('S');
        if (w) sb.append('W');
        if (a) sb.append('A');
        if (t) sb.append('T');
        if (b && arrows) sb.append('B');
        if (e && r) sb.append('E');
        if (c) sb.append('C');
        return sb.isEmpty() ? "-" : sb.toString();
    }

    public static String describeSignature(String signature) {
        if (signature.equals("-")) {
            return "Fäuste";
        }
        StringBuilder sb = new StringBuilder();
        for (char ch : signature.toCharArray()) {
            if (!sb.isEmpty()) {
                sb.append('+');
            }
            sb.append(switch (ch) {
                case 'M' -> "Mace";
                case 'S' -> "Speer";
                case 'W' -> "Schwert";
                case 'A' -> "Axt";
                case 'T' -> "Dreizack";
                case 'B' -> "Bogen";
                case 'E' -> "Elytra";
                case 'C' -> "Windladung";
                default -> "?";
            });
        }
        return sb.toString();
    }
}
