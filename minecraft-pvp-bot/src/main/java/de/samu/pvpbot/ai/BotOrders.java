package de.samu.pvpbot.ai;

import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.Locale;
import net.minecraft.server.level.ServerPlayer;
import org.jspecify.annotations.Nullable;

/**
 * Plain orders in the chat ("@bot komm", "@bot greif den zombie an", "@bot hol 10 eisen") that
 * work without any AI key. The bot's owner and the players the owner trusts may give them.
 * What is not understood here goes on to the AI chat, if the speaker has set a key.
 */
public final class BotOrders {
    public static final String HELP = "komm · bleib · stopp · heim · greif <ziel> an · hol [anzahl] <"
            + PvpBotEntity.orderOptions() + "> · status · (nur Besitzer: allein an/aus, durchspielen)";

    private BotOrders() {
    }

    /** Carries out the order and returns the bot's answer, or null if it was not understood. */
    public static @Nullable String run(PvpBotEntity bot, ServerPlayer sender, String words) {
        String w = words.toLowerCase(Locale.ROOT).replaceAll("[.!?]+$", "").strip();
        boolean owner = bot.isOwnedBy(sender);
        if (w.isEmpty()) {
            return null;
        }
        if (w.equals("hilfe") || w.equals("befehle") || w.equals("help")) {
            return "Ich verstehe: " + HELP;
        }
        if (w.equals("status") || w.startsWith("was machst")) {
            return (bot.isSolo() ? "Ich spiele allein. " : "") + "Gerade: " + bot.describeState() + ". " + bot.describeNeeds()
                    + " Leben " + (int) bot.getHealth() + "/" + (int) bot.getMaxHealth() + ".";
        }
        if (w.startsWith("allein") || w.startsWith("spiel allein")) {
            if (!owner) {
                return "Das darf nur mein Besitzer entscheiden.";
            }
            boolean on = !w.endsWith(" aus") && !w.endsWith(" off");
            bot.setSolo(on);
            return on ? "Alles klar, ich spiele allein und melde mich, wenn etwas ist." : "Allein-Modus aus. Ich warte auf Befehle.";
        }
        if (w.startsWith("durchspielen") || w.contains("spiel minecraft durch") || w.contains("spiel durch")) {
            if (!owner) {
                return "Das darf nur mein Besitzer entscheiden.";
            }
            if (bot.getKit().isInfinite()) {
                return "Das kann nur ein Survival-Bot (/pvpbot survival).";
            }
            bot.setSpeedrun(true);
            return "Ich spiele Minecraft durch.";
        }
        if (w.equals("stopp") || w.equals("stop") || w.startsWith("hör auf") || w.startsWith("hoer auf")) {
            bot.clearTargets();
            bot.cancelOrder();
            return "Ich höre auf.";
        }
        if (w.startsWith("komm") || w.startsWith("folg")) {
            // Coming along is a full-time job: playing on its own pauses.
            if (bot.isSolo()) {
                bot.setSolo(false);
            }
            bot.setSpeedrun(false);
            bot.setLeader(sender);
            bot.setFollowing(true);
            return "Ich komme mit dir, " + sender.getName().getString() + ".";
        }
        if (w.startsWith("bleib") || w.startsWith("warte")) {
            bot.setFollowing(false);
            return "Ich bleibe hier.";
        }
        if (w.equals("heim") || w.contains("nach hause") || w.equals("zuhause") || w.startsWith("geh heim")) {
            if (bot.getHome() == null) {
                return "Ich habe kein Zuhause (/pvpbot home set).";
            }
            bot.setFollowing(false);
            bot.clearTargets();
            bot.goHome();
            return "Ich gehe nach Hause.";
        }
        for (String verb : new String[]{"greif ", "angriff ", "töte ", "toete ", "kill ", "attackier "}) {
            if (w.startsWith(verb)) {
                String what = w.substring(verb.length()).replaceFirst("\\s+an$", "")
                        .replaceFirst("^(den|die|das|einen|eine|ein)\\s+", "").strip();
                return what.isEmpty() ? "Wen denn?" : BotAi.INSTANCE.attack(bot, sender, what);
            }
        }
        for (String verb : new String[]{"hol ", "besorg ", "bring ", "sammel "}) {
            if (w.startsWith(verb)) {
                String rest = w.substring(verb.length()).replaceFirst("^mir\\s+", "").strip();
                int count = 1;
                String[] parts = rest.split("\\s+", 2);
                if (parts.length == 2 && parts[0].matches("\\d{1,3}")) {
                    count = Integer.parseInt(parts[0]);
                    rest = parts[1];
                }
                String err = bot.order(rest, count);
                return err == null ? "Mache ich: " + bot.currentOrder() + "." : err;
            }
        }
        return null;
    }
}
