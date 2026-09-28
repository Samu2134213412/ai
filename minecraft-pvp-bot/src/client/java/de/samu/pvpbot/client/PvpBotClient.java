package de.samu.pvpbot.client;

import de.samu.pvpbot.PvpBotMod;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;

public class PvpBotClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        EntityRendererRegistry.register(PvpBotMod.PVP_BOT, PvpBotRenderer::new);
    }
}
