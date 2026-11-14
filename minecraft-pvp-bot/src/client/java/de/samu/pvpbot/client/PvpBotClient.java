package de.samu.pvpbot.client;

import de.samu.pvpbot.PvpBotMod;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.hud.VanillaHudElements;
import net.minecraft.client.KeyMapping;
import net.minecraft.resources.Identifier;

public class PvpBotClient implements ClientModInitializer {
    // Key codes are SDL scancodes in this Minecraft version (A = 4 ... O = 18).
    private static final int KEY_O = 18;
    private static KeyMapping menuKey;

    @Override
    public void onInitializeClient() {
        EntityRendererRegistry.register(PvpBotMod.PVP_BOT, PvpBotRenderer::new);
        KeyMapping.Category category = KeyMapping.Category.register(Identifier.fromNamespaceAndPath("pvpbot", "pvpbot"));
        menuKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.pvpbot.menu", KEY_O, category));
        PvpBotHud.load();
        HudElementRegistry.attachElementBefore(VanillaHudElements.CHAT, Identifier.fromNamespaceAndPath("pvpbot", "status"), new PvpBotHud());
        ClientTickEvents.END_CLIENT_TICK.register(mc -> {
            PvpBotHud.tick(mc);
            while (menuKey.consumeClick()) {
                if (mc.player != null && mc.gui.screen() == null) {
                    mc.gui.setScreen(new PvpBotScreen());
                }
            }
        });
    }
}
