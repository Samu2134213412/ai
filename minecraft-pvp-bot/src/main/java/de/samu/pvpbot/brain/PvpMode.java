package de.samu.pvpbot.brain;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;
import net.minecraft.world.item.component.Fireworks;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.Enchantments;
import org.jspecify.annotations.Nullable;

/**
 * PvP game modes, like on PvP servers. A mode decides three things:
 * <ul>
 *   <li>the kit (every round starts with a fresh one),</li>
 *   <li>which attack patterns are allowed (Sumo: fists only, Bow: bow only ...),</li>
 *   <li>special rules: no damage + a hit limit (Boxing), knock the other one off the platform (Sumo).</li>
 * </ul>
 * Every mode has its own memory: what the bot learns in Sumo does not mix with what it learns in UHC.
 * Shared by the bot and the autopilot (copied into the autopilot's package when building).
 */
public enum PvpMode {
    FREI("frei", "Frei", "Alles erlaubt, mit dem Kit, das er gerade hat", null, false, 0, false),
    KLASSIK("klassik", "Klassik", "Diamant-Schwert, Bogen, Diamant-Rüstung, 3 goldene Äpfel",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE, BotBrain.Pattern.BOW_SNIPE), false, 0, false),
    NODEBUFF("nodebuff", "NoDebuff", "Schwert, Heiltränke zum Werfen, Speed-Tränke, Enderperlen",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE), false, 0, false),
    UHC("uhc", "UHC", "Schwert, Axt, Bogen, Schild, goldene Äpfel, Wassereimer",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE, BotBrain.Pattern.BOW_SNIPE), false, 0, false),
    AXT("axt", "Axt & Schild", "Netherite-Axt, Schild, Netherite-Rüstung, goldene Äpfel",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE), false, 0, false),
    MACE("mace", "Mace", "Mace, Windladungen, Axt zum Attribut-Tausch, Totems",
            EnumSet.of(BotBrain.Pattern.MACE_MELEE, BotBrain.Pattern.WIND_SMASH, BotBrain.Pattern.BLADE_MELEE), false, 0, false),
    SPEER("speer", "Speer", "Netherite-Speer mit Lunge, Schwert, goldene Äpfel",
            EnumSet.of(BotBrain.Pattern.SPEAR_KITE, BotBrain.Pattern.SPEAR_CHARGE, BotBrain.Pattern.BLADE_MELEE), false, 0, false),
    ELYTRA("elytra", "Elytra", "Mace + Speer aus der Luft: Elytra, Raketen, Windladungen",
            null, false, 0, false),
    BOGEN("bogen", "Bogen", "Nur Bogen und Pfeile, Leder-Rüstung",
            EnumSet.of(BotBrain.Pattern.BOW_SNIPE), false, 0, false),
    SUMO("sumo", "Sumo", "Keine Waffen, kein Schaden: wer von der Plattform fällt, verliert",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE), true, 0, true),
    BOXEN("boxen", "Boxen", "Kein Schaden, keine Rüstung: wer zuerst 100 Treffer landet, gewinnt",
            EnumSet.of(BotBrain.Pattern.BLADE_MELEE), true, 100, false);

    public final String id;
    public final String label;
    public final String description;
    private final @Nullable EnumSet<BotBrain.Pattern> patterns;
    /** Hits do no damage (only knockback): Sumo and Boxing. */
    public final boolean noDamage;
    /** Hits needed to win (0 = no hit limit). */
    public final int hitsToWin;
    /** Whoever falls off the platform (or into water) loses. */
    public final boolean sumo;

    PvpMode(String id, String label, String description, @Nullable EnumSet<BotBrain.Pattern> patterns, boolean noDamage, int hitsToWin, boolean sumo) {
        this.id = id;
        this.label = label;
        this.description = description;
        this.patterns = patterns;
        this.noDamage = noDamage;
        this.hitsToWin = hitsToWin;
        this.sumo = sumo;
    }

    public static @Nullable PvpMode byId(String id) {
        String wanted = id.toLowerCase(Locale.ROOT);
        for (PvpMode m : values()) {
            if (m.id.equals(wanted)) {
                return m;
            }
        }
        return null;
    }

    public boolean allows(BotBrain.Pattern p) {
        return this.patterns == null || this.patterns.contains(p.base());
    }

    /** The attacks this mode allows, for the menu ("alle" if there is no limit). */
    public String describeAttacks() {
        if (this.patterns == null) {
            return "alle";
        }
        if (this.sumo) {
            return "Fäuste";
        }
        StringBuilder sb = new StringBuilder();
        for (BotBrain.Pattern p : this.patterns) {
            if (!sb.isEmpty()) {
                sb.append(", ");
            }
            sb.append(p.label);
        }
        return sb.toString();
    }

    /** The special rule of this mode, for the menu (empty if it is a normal fight). */
    public String describeRules() {
        if (this.sumo) {
            return "Kein Schaden. Wer von der Plattform fällt, verliert.";
        }
        if (this.hitsToWin > 0) {
            return "Kein Schaden. Wer zuerst " + this.hitsToWin + " Treffer landet, gewinnt.";
        }
        return this == FREI ? "" : "Normaler Kampf, jede Runde mit frischem Kit.";
    }

    /**
     * Only the patterns this mode allows. If none is left (a bow fighter with the enemy right in its
     * face), it falls back to plain melee - with whatever it holds, fists in the worst case.
     */
    public List<BotBrain.Pattern> filter(List<BotBrain.Pattern> options) {
        if (this.patterns == null) {
            return options;
        }
        List<BotBrain.Pattern> out = new ArrayList<>(options);
        out.removeIf(p -> !this.patterns.contains(p.base()));
        if (out.isEmpty()) {
            out.add(BotBrain.Pattern.BLADE_MELEE);
        }
        return out;
    }

    /** The kit part of the learning key: each mode learns on its own. */
    public String learnKey(String kitSignature) {
        return this == FREI ? kitSignature : this.id + ":" + kitSignature;
    }

    /** Label for a learning key made by {@link #learnKey}, e.g. "Sumo" or "UHC (Schwert+Bogen)". */
    public static String describeKey(String key) {
        int colon = key.indexOf(':');
        if (colon < 0) {
            return Kit.describeSignature(key);
        }
        PvpMode mode = byId(key.substring(0, colon));
        String sig = key.substring(colon + 1);
        String name = mode != null ? mode.label : key.substring(0, colon);
        return sig.equals("-") ? name : name + " (" + Kit.describeSignature(sig) + ")";
    }

    // ------------------------------------------------------------------ kits

    /**
     * A fresh kit for this mode (empty for Sumo: fists only). {@code FREI} has no kit of its own and
     * returns null - the bot keeps what it has.
     */
    public @Nullable List<ItemStack> kit(HolderLookup.Provider registries) {
        KitBuilder k = new KitBuilder(registries);
        switch (this) {
            case FREI -> {
                return null;
            }
            case KLASSIK -> {
                k.armor(Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS);
                k.add(Items.DIAMOND_SWORD);
                k.add(Items.BOW);
                k.add(Items.ARROW, 16);
                k.add(Items.GOLDEN_APPLE, 3);
            }
            case NODEBUFF -> {
                k.armorEnchanted(Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS,
                        Enchantments.PROTECTION, 2, Enchantments.UNBREAKING, 3);
                k.add(Items.DIAMOND_SWORD, 1, Enchantments.SHARPNESS, 3, Enchantments.FIRE_ASPECT, 2, Enchantments.UNBREAKING, 3);
                k.add(Items.ENDER_PEARL, 16);
                k.add(Items.COOKED_BEEF, 64);
                k.potion(Items.POTION, Potions.STRONG_SWIFTNESS, 2);
                k.potion(Items.SPLASH_POTION, Potions.STRONG_HEALING, 28);
            }
            case UHC -> {
                k.armorEnchanted(Items.DIAMOND_HELMET, Items.DIAMOND_CHESTPLATE, Items.DIAMOND_LEGGINGS, Items.DIAMOND_BOOTS,
                        Enchantments.PROTECTION, 2);
                k.add(Items.DIAMOND_SWORD, 1, Enchantments.SHARPNESS, 3);
                k.add(Items.DIAMOND_AXE, 1, Enchantments.SHARPNESS, 1);
                k.add(Items.BOW, 1, Enchantments.POWER, 2);
                k.add(Items.ARROW, 32);
                k.add(Items.SHIELD);
                k.add(Items.GOLDEN_APPLE, 6);
                k.add(Items.WATER_BUCKET);
                k.add(Items.COBBLESTONE, 64);
            }
            case AXT -> {
                k.armorEnchanted(Items.NETHERITE_HELMET, Items.NETHERITE_CHESTPLATE, Items.NETHERITE_LEGGINGS, Items.NETHERITE_BOOTS,
                        Enchantments.PROTECTION, 3);
                k.add(Items.NETHERITE_AXE, 1, Enchantments.SHARPNESS, 3);
                k.add(Items.SHIELD);
                k.add(Items.GOLDEN_APPLE, 4);
            }
            case MACE -> {
                k.armorEnchanted(Items.NETHERITE_HELMET, Items.NETHERITE_CHESTPLATE, Items.NETHERITE_LEGGINGS, Items.NETHERITE_BOOTS,
                        Enchantments.PROTECTION, 4);
                k.add(Items.MACE, 1, Enchantments.DENSITY, 5, Enchantments.WIND_BURST, 1);
                k.add(Items.NETHERITE_AXE, 1, Enchantments.SHARPNESS, 5);
                k.add(Items.WIND_CHARGE, 64);
                k.add(Items.TOTEM_OF_UNDYING);
                k.add(Items.GOLDEN_APPLE, 8);
            }
            case SPEER -> {
                k.armorEnchanted(Items.NETHERITE_HELMET, Items.NETHERITE_CHESTPLATE, Items.NETHERITE_LEGGINGS, Items.NETHERITE_BOOTS,
                        Enchantments.PROTECTION, 4);
                k.add(Items.NETHERITE_SPEAR, 1, Enchantments.SHARPNESS, 5, Enchantments.LUNGE, 3);
                k.add(Items.NETHERITE_SWORD, 1, Enchantments.SHARPNESS, 5);
                k.add(Items.GOLDEN_APPLE, 8);
            }
            case ELYTRA -> {
                k.armorEnchanted(Items.NETHERITE_HELMET, Items.NETHERITE_CHESTPLATE, Items.NETHERITE_LEGGINGS, Items.NETHERITE_BOOTS,
                        Enchantments.PROTECTION, 4);
                k.add(Items.MACE, 1, Enchantments.DENSITY, 5, Enchantments.WIND_BURST, 3);
                k.add(Items.NETHERITE_SPEAR, 1, Enchantments.SHARPNESS, 5, Enchantments.LUNGE, 3);
                k.add(Items.ELYTRA, 1, Enchantments.UNBREAKING, 3);
                ItemStack rockets = new ItemStack(Items.FIREWORK_ROCKET, 64);
                rockets.set(DataComponents.FIREWORKS, new Fireworks(1, List.of()));
                k.items.add(rockets);
                k.add(Items.WIND_CHARGE, 64);
                k.add(Items.TOTEM_OF_UNDYING);
                k.add(Items.GOLDEN_APPLE, 8);
            }
            case BOGEN -> {
                k.armor(Items.LEATHER_HELMET, Items.LEATHER_CHESTPLATE, Items.LEATHER_LEGGINGS, Items.LEATHER_BOOTS);
                k.add(Items.BOW, 1, Enchantments.POWER, 3, Enchantments.PUNCH, 1);
                k.add(Items.ARROW, 64);
            }
            case SUMO -> {
                // fists only
            }
            case BOXEN -> k.add(Items.DIAMOND_SWORD);
        }
        return k.items;
    }

    private static final class KitBuilder {
        final List<ItemStack> items = new ArrayList<>();
        private final HolderLookup.RegistryLookup<Enchantment> enchantments;

        KitBuilder(HolderLookup.Provider registries) {
            this.enchantments = registries.lookupOrThrow(Registries.ENCHANTMENT);
        }

        void add(Item item) {
            this.add(item, 1);
        }

        @SuppressWarnings("unchecked")
        void add(Item item, int count, Object... enchantsAndLevels) {
            ItemStack stack = new ItemStack(item, count);
            for (int i = 0; i + 1 < enchantsAndLevels.length; i += 2) {
                ResourceKey<Enchantment> key = (ResourceKey<Enchantment>) enchantsAndLevels[i];
                int lvl = (Integer) enchantsAndLevels[i + 1];
                this.enchantments.get(key).ifPresent(holder -> stack.enchant(holder, lvl));
            }
            this.items.add(stack);
        }

        void armor(Item... pieces) {
            for (Item piece : pieces) {
                this.add(piece);
            }
        }

        void armorEnchanted(Item head, Item chest, Item legs, Item feet, Object... enchantsAndLevels) {
            for (Item piece : new Item[]{head, chest, legs, feet}) {
                this.add(piece, 1, enchantsAndLevels);
            }
        }

        void potion(Item bottle, net.minecraft.core.Holder<net.minecraft.world.item.alchemy.Potion> potion, int count) {
            for (int i = 0; i < count; i++) {
                this.items.add(PotionContents.createItemStack(bottle, potion));
            }
        }
    }
}
