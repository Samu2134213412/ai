package de.samu.pvpbot;

import com.mojang.authlib.GameProfile;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.UUID;
import net.fabricmc.fabric.api.entity.FakePlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.GameType;
import org.jspecify.annotations.Nullable;

/**
 * Test only: an invisible creative player that stays with the bot, like the owner watching it play.
 * The game does its usual things around a player by itself - loads and ticks the chunks, runs mob
 * spawners and natural spawning, starts the dragon fight - so the test never has to change the
 * world. It never touches anything; creative players are ignored by mobs.
 */
final class TestWatcher {
    private static final GameProfile PROFILE = new GameProfile(UUID.fromString("5e1f7e57-0b5e-4e7e-8000-00000000c0de"), "Zuschauer");
    private static @Nullable ServerPlayer watcher;

    private TestWatcher() {
    }

    static void follow(PvpBotEntity bot) {
        if (!(bot.level() instanceof ServerLevel level) || bot.isRemoved()) {
            return;
        }
        if (watcher == null || watcher.isRemoved() || watcher.level() != level) {
            remove();
            ServerPlayer p = new FakePlayer(level, PROFILE) {
                @Override
                public boolean isPushable() {
                    return false; // stands in the bot without shoving it around
                }
            };
            p.setGameMode(GameType.CREATIVE);
            p.setInvisible(true);
            p.setNoGravity(true);
            p.getAbilities().flying = true;
            p.snapTo(bot.getX(), bot.getY(), bot.getZ(), 0.0F, 0.0F);
            level.addNewPlayer(p);
            watcher = p;
            bot.setOwner(p);
            bot.setFollowing(false); // the owner only watches: the bot plays on its own
            PvpBotMod.LOGGER.info("[SELFTEST]   (test) watcher (creative, invisible) now with the bot in " + level.dimension());
        }
        watcher.snapTo(bot.getX(), bot.getY(), bot.getZ(), bot.getYRot(), 0.0F);
        level.getChunkSource().move(watcher);
    }

    static void remove() {
        if (watcher != null) {
            if (!watcher.isRemoved() && watcher.level() instanceof ServerLevel level) {
                level.removePlayerImmediately(watcher, Entity.RemovalReason.CHANGED_DIMENSION);
            }
            watcher = null;
        }
    }
}
