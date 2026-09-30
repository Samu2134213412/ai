package de.samu.pvpbot.voice;

import de.maxhenkel.voicechat.api.VoicechatApi;
import de.maxhenkel.voicechat.api.VoicechatPlugin;
import de.maxhenkel.voicechat.api.events.EventRegistration;
import de.maxhenkel.voicechat.api.events.MicrophonePacketEvent;
import de.maxhenkel.voicechat.api.events.VoicechatServerStartedEvent;
import de.maxhenkel.voicechat.api.events.VoicechatServerStoppedEvent;

/** Simple Voice Chat plugin (entrypoint "voicechat" in fabric.mod.json). */
public class BotVoicePlugin implements VoicechatPlugin {
    @Override
    public String getPluginId() {
        return "pvpbot";
    }

    @Override
    public void initialize(VoicechatApi api) {
    }

    @Override
    public void registerEvents(EventRegistration registration) {
        registration.registerEvent(VoicechatServerStartedEvent.class, e -> BotVoice.started(e.getVoicechat()));
        registration.registerEvent(VoicechatServerStoppedEvent.class, e -> BotVoice.stopped());
        registration.registerEvent(MicrophonePacketEvent.class, e -> {
            if (e.getSenderConnection() != null) {
                BotVoice.heard(e.getSenderConnection().getPlayer().getUuid());
            }
        });
    }
}
