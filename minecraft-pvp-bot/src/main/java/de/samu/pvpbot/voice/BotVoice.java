package de.samu.pvpbot.voice;

import de.maxhenkel.voicechat.api.VoicechatServerApi;
import de.maxhenkel.voicechat.api.audiochannel.AudioPlayer;
import de.maxhenkel.voicechat.api.audiochannel.LocationalAudioChannel;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import net.minecraft.server.level.ServerLevel;
import org.jspecify.annotations.Nullable;

/**
 * The bot in Simple Voice Chat: when it answers in chat you also hear it "talk" (a babble the length of
 * its sentence, from where it stands), and when its owner talks into the microphone nearby it turns
 * round to listen.
 */
public final class BotVoice {
    private static volatile @Nullable VoicechatServerApi api;
    /** Players who spoke recently (game time is not known on the voice thread: wall clock). */
    private static final Map<UUID, Long> SPEAKING = new ConcurrentHashMap<>();

    private BotVoice() {
    }

    static void started(VoicechatServerApi serverApi) {
        api = serverApi;
    }

    static void stopped() {
        api = null;
        SPEAKING.clear();
    }

    static void heard(UUID player) {
        SPEAKING.put(player, System.currentTimeMillis());
    }

    /** True while this player is talking into their microphone (last packet under half a second ago). */
    public static boolean isSpeaking(UUID player) {
        Long t = SPEAKING.get(player);
        return t != null && System.currentTimeMillis() - t < 500L;
    }

    public static boolean available() {
        return api != null;
    }

    /** Plays a short babble for this sentence at the bot's position (server thread). */
    public static void speak(PvpBotEntity bot, String sentence) {
        VoicechatServerApi a = api;
        if (a == null || !(bot.level() instanceof ServerLevel level)) {
            return;
        }
        try {
            LocationalAudioChannel channel = a.createLocationalAudioChannel(UUID.randomUUID(),
                    a.fromServerLevel(level), a.createPosition(bot.getX(), bot.getEyeY(), bot.getZ()));
            if (channel == null) {
                return;
            }
            channel.setDistance(32.0F);
            AudioPlayer player = a.createAudioPlayer(channel, a.createEncoder(), babble(sentence, bot.getUUID().hashCode()));
            player.startPlaying();
        } catch (Throwable t) {
            // (Voice is a nice extra: the chat answer is already there.)
        }
    }

    /** 48 kHz mono: one little "syllable" per few letters, pitch varying like speech. */
    public static short[] babble(String sentence, int voiceSeed) {
        int syllables = Math.max(2, Math.min(40, sentence.length() / 3));
        int rate = 48000;
        int per = rate / 9; // ~110 ms per syllable
        short[] out = new short[syllables * per];
        java.util.Random random = new java.util.Random(sentence.hashCode() ^ voiceSeed);
        double base = 170.0 + Math.floorMod(voiceSeed, 90);
        double phase = 0.0;
        for (int s = 0; s < syllables; s++) {
            char c = sentence.charAt(Math.min(sentence.length() - 1, s * 3));
            if (c == ' ' || c == ',' || c == '.') {
                continue; // a short pause
            }
            double pitch = base * (0.85 + random.nextDouble() * 0.4);
            for (int i = 0; i < per; i++) {
                double env = Math.sin(Math.PI * i / per);
                phase += 2 * Math.PI * pitch / rate;
                double v = Math.sin(phase) * 0.6 + Math.sin(phase * 2) * 0.25 + Math.sin(phase * 3) * 0.1;
                out[s * per + i] = (short) (v * env * 9000);
            }
        }
        return out;
    }
}
