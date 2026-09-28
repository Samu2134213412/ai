package de.samu.pvpbot.autopilot.mixin;

import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** Lets the autopilot press "attack" and "use" exactly like the mouse buttons do. */
@Mixin(Minecraft.class)
public interface MinecraftInvoker {
    @Invoker("startAttack")
    boolean pvpbot$startAttack();

    @Invoker("startUseItem")
    void pvpbot$startUseItem();
}
