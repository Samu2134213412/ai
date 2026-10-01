package de.samu.pvpbot.autopilot;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * What the autopilot hears in Simple Voice Chat: who is talking right now (the voice chat client
 * plays their audio anyway - it only notes the speaker, it does not record or understand words).
 */
public final class AutopilotVoice {
    private static final Map<UUID, Long> LAST_HEARD = new ConcurrentHashMap<>();

    private AutopilotVoice() {
    }

    /** Called from the voice chat thread for every audio packet of a player. */
    static void heard(UUID speaker) {
        LAST_HEARD.put(speaker, System.currentTimeMillis());
    }

    /** True while the player has been heard within the last half second. */
    public static boolean isSpeaking(UUID player) {
        Long t = LAST_HEARD.get(player);
        return t != null && System.currentTimeMillis() - t < 500L;
    }
}
