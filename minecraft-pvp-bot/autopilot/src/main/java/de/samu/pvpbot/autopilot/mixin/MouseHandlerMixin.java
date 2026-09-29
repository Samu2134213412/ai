package de.samu.pvpbot.autopilot.mixin;

import de.samu.pvpbot.autopilot.Autopilot;
import net.minecraft.client.Minecraft;
import net.minecraft.client.MouseHandler;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * While the autopilot plays and no menu is open, the game acts as if the window had mouse focus -
 * otherwise Minecraft cancels block breaking every tick (a released mouse button), which is what
 * stalled mining whenever the window was in the background.
 */
@Mixin(MouseHandler.class)
public class MouseHandlerMixin {
    @Inject(method = "isMouseGrabbed", at = @At("HEAD"), cancellable = true)
    private void pvpbot$grabbedWhileAutopilot(CallbackInfoReturnable<Boolean> cir) {
        Minecraft mc = Minecraft.getInstance();
        if (Autopilot.INSTANCE.isEnabled() && mc.player != null && mc.gui.screen() == null) {
            cir.setReturnValue(true);
        }
    }
}
