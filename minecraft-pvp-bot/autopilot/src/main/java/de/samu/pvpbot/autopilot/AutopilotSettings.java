package de.samu.pvpbot.autopilot;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/** Which tactics the autopilot may use. Stored in config/pvpbot-autopilot.properties. */
public final class AutopilotSettings {
    public static final AutopilotSettings INSTANCE = new AutopilotSettings();

    public boolean elytra = true;
    public boolean windCharges = true;
    public boolean spear = true;
    public boolean bow = true;
    public boolean attributeSwap = true;
    public boolean shield = true;
    public boolean wTap = true;
    public boolean pearls = true;
    public boolean waterClutch = true;
    public boolean potions = true;
    public boolean autoEat = true;
    public boolean lootPickup = true;
    public boolean chat = true;

    private Path file;

    private AutopilotSettings() {
    }

    public void load(Path file) {
        this.file = file;
        if (!Files.exists(file)) {
            return;
        }
        Properties p = new Properties();
        try (Reader r = Files.newBufferedReader(file)) {
            p.load(r);
        } catch (IOException e) {
            Autopilot.LOGGER.warn("Could not read {}", file, e);
            return;
        }
        this.elytra = get(p, "elytra", this.elytra);
        this.windCharges = get(p, "windCharges", this.windCharges);
        this.spear = get(p, "spear", this.spear);
        this.bow = get(p, "bow", this.bow);
        this.attributeSwap = get(p, "attributeSwap", this.attributeSwap);
        this.shield = get(p, "shield", this.shield);
        this.wTap = get(p, "wTap", this.wTap);
        this.pearls = get(p, "pearls", this.pearls);
        this.waterClutch = get(p, "waterClutch", this.waterClutch);
        this.potions = get(p, "potions", this.potions);
        this.autoEat = get(p, "autoEat", this.autoEat);
        this.lootPickup = get(p, "lootPickup", this.lootPickup);
        this.chat = get(p, "chat", this.chat);
    }

    public void save() {
        if (this.file == null) {
            return;
        }
        Properties p = new Properties();
        p.setProperty("elytra", Boolean.toString(this.elytra));
        p.setProperty("windCharges", Boolean.toString(this.windCharges));
        p.setProperty("spear", Boolean.toString(this.spear));
        p.setProperty("bow", Boolean.toString(this.bow));
        p.setProperty("attributeSwap", Boolean.toString(this.attributeSwap));
        p.setProperty("shield", Boolean.toString(this.shield));
        p.setProperty("wTap", Boolean.toString(this.wTap));
        p.setProperty("pearls", Boolean.toString(this.pearls));
        p.setProperty("waterClutch", Boolean.toString(this.waterClutch));
        p.setProperty("potions", Boolean.toString(this.potions));
        p.setProperty("autoEat", Boolean.toString(this.autoEat));
        p.setProperty("lootPickup", Boolean.toString(this.lootPickup));
        p.setProperty("chat", Boolean.toString(this.chat));
        try {
            Files.createDirectories(this.file.getParent());
            try (Writer w = Files.newBufferedWriter(this.file)) {
                p.store(w, "PvP-Autopilot settings");
            }
        } catch (IOException e) {
            Autopilot.LOGGER.warn("Could not write {}", this.file, e);
        }
    }

    private static boolean get(Properties p, String key, boolean fallback) {
        String v = p.getProperty(key);
        return v == null ? fallback : Boolean.parseBoolean(v);
    }
}
