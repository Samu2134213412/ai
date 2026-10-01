package de.samu.pvpbot.autopilot;

import de.maxhenkel.voicechat.api.VoicechatApi;
import de.maxhenkel.voicechat.api.VoicechatPlugin;
import de.maxhenkel.voicechat.api.events.ClientReceiveSoundEvent;
import de.maxhenkel.voicechat.api.events.EventRegistration;

/** Simple Voice Chat plugin (entrypoint "voicechat" in fabric.mod.json), client side. */
public class AutopilotVoicePlugin implements VoicechatPlugin {
    @Override
    public String getPluginId() {
        return "pvpbot_autopilot";
    }

    @Override
    public void initialize(VoicechatApi api) {
    }

    @Override
    public void registerEvents(EventRegistration registration) {
        registration.registerEvent(ClientReceiveSoundEvent.EntitySound.class, e -> AutopilotVoice.heard(e.getId()));
    }
}
