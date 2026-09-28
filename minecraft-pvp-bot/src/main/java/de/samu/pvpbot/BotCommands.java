package de.samu.pvpbot;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.entity.PvpBotEntity;
import java.util.Collection;
import java.util.List;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.LivingEntity;

public final class BotCommands {
    private BotCommands() {
    }

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("pvpbot")
                .then(Commands.literal("spawn")
                        .executes(ctx -> spawn(ctx, "PvP Bot"))
                        .then(Commands.argument("name", StringArgumentType.greedyString())
                                .executes(ctx -> spawn(ctx, StringArgumentType.getString(ctx, "name")))))
                .then(Commands.literal("attack")
                        .then(Commands.argument("targets", EntityArgument.entities())
                                .executes(BotCommands::attack)))
                .then(Commands.literal("stop").executes(BotCommands::stop))
                .then(Commands.literal("follow").executes(ctx -> setFollow(ctx, true)))
                .then(Commands.literal("stay").executes(ctx -> setFollow(ctx, false)))
                .then(Commands.literal("assist")
                        .then(Commands.literal("on").executes(ctx -> setAssist(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> setAssist(ctx, false))))
                .then(Commands.literal("weapon")
                        .then(Commands.literal("auto").executes(ctx -> setStyle(ctx, PvpBotEntity.Style.AUTO)))
                        .then(Commands.literal("mace").executes(ctx -> setStyle(ctx, PvpBotEntity.Style.MACE)))
                        .then(Commands.literal("spear").executes(ctx -> setStyle(ctx, PvpBotEntity.Style.SPEAR))))
                .then(Commands.literal("brain")
                        .executes(BotCommands::brain)
                        .then(Commands.literal("reset").executes(BotCommands::brainReset)))
                .then(Commands.literal("chat")
                        .then(Commands.literal("on").executes(ctx -> setTalk(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> setTalk(ctx, false))))
                .then(Commands.literal("tp").executes(BotCommands::teleport))
                .then(Commands.literal("remove").executes(BotCommands::remove))
                .then(Commands.literal("list").executes(BotCommands::list)));
    }

    private static int spawn(CommandContext<CommandSourceStack> ctx, String name) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        ServerLevel level = ctx.getSource().getLevel();
        PvpBotEntity bot = PvpBotMod.PVP_BOT.create(level, EntitySpawnReason.COMMAND);
        if (bot == null) {
            return 0;
        }
        bot.snapTo(player.getX(), player.getY(), player.getZ(), player.getYRot(), 0.0F);
        bot.setOwner(player);
        bot.setCustomName(Component.literal(name));
        bot.setCustomNameVisible(true);
        bot.equipLoadout();
        level.addFreshEntity(bot);
        ctx.getSource().sendSuccess(() -> Component.literal("§a" + name + " ist bereit! §7Sag ihm mit §f/pvpbot attack <Ziel>§7, wen er erledigen soll."), false);
        return 1;
    }

    private static List<PvpBotEntity> myBots(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        List<PvpBotEntity> bots = PvpBotEntity.botsOf(player);
        if (bots.isEmpty()) {
            ctx.getSource().sendFailure(Component.literal("Du hast keine Bots in der Nähe. Erstelle einen mit /pvpbot spawn"));
        }
        return bots;
    }

    private static int attack(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        Collection<? extends Entity> targets = EntityArgument.getEntities(ctx, "targets");
        List<PvpBotEntity> bots = myBots(ctx);
        int count = 0;
        for (Entity entity : targets) {
            if (entity instanceof LivingEntity living && !(entity instanceof PvpBotEntity) && entity != ctx.getSource().getEntity()) {
                for (PvpBotEntity bot : bots) {
                    bot.addTarget(living, true);
                }
                count++;
            }
        }
        if (bots.isEmpty()) {
            return 0;
        }
        if (count == 0) {
            ctx.getSource().sendFailure(Component.literal("Keine gültigen Ziele gefunden."));
            return 0;
        }
        final int n = count;
        ctx.getSource().sendSuccess(() -> Component.literal("§c" + bots.size() + " Bot(s) greifen " + n + " Ziel(e) an!"), false);
        return count;
    }

    private static int stop(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(PvpBotEntity::clearTargets);
        ctx.getSource().sendSuccess(() -> Component.literal("§eBots hören auf zu kämpfen."), false);
        return bots.size();
    }

    private static int setFollow(CommandContext<CommandSourceStack> ctx, boolean follow) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setFollowing(follow));
        ctx.getSource().sendSuccess(() -> Component.literal(follow ? "§aBots folgen dir." : "§eBots bleiben hier."), false);
        return bots.size();
    }

    private static int setAssist(CommandContext<CommandSourceStack> ctx, boolean assist) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setAssisting(assist));
        ctx.getSource().sendSuccess(() -> Component.literal(assist
                ? "§aBots greifen an, wen du schlägst und wer dich schlägt."
                : "§eBots greifen nur noch auf Befehl an."), false);
        return bots.size();
    }

    private static int setStyle(CommandContext<CommandSourceStack> ctx, PvpBotEntity.Style style) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setStyle(style));
        ctx.getSource().sendSuccess(() -> Component.literal("§aKampfstil: " + style.name().toLowerCase()), false);
        return bots.size();
    }

    private static int brain(CommandContext<CommandSourceStack> ctx) {
        List<String> lines = BotBrain.INSTANCE.summary(12);
        if (lines.isEmpty()) {
            ctx.getSource().sendSuccess(() -> Component.literal("§7Das Gedächtnis ist noch leer – lass deine Bots ein paar Kämpfe machen."), false);
            return 0;
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§6Was die Bots gelernt haben §7(Wert = wie gut es klappt, (n) = wie oft probiert):"), false);
        for (String line : lines) {
            ctx.getSource().sendSuccess(() -> Component.literal(line), false);
        }
        return lines.size();
    }

    private static int brainReset(CommandContext<CommandSourceStack> ctx) {
        BotBrain.INSTANCE.reset();
        ctx.getSource().sendSuccess(() -> Component.literal("§eGedächtnis gelöscht – die Bots fangen wieder von vorne an zu lernen."), false);
        return 1;
    }

    private static int setTalk(CommandContext<CommandSourceStack> ctx, boolean talk) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setTalk(talk));
        ctx.getSource().sendSuccess(() -> Component.literal(talk ? "§aBots erzählen dir, was sie lernen." : "§eBots lernen jetzt leise."), false);
        return bots.size();
    }

    private static int teleport(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.teleportTo(player.getX(), player.getY(), player.getZ()));
        return bots.size();
    }

    private static int remove(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(Entity::discard);
        ctx.getSource().sendSuccess(() -> Component.literal("§7" + bots.size() + " Bot(s) entfernt."), false);
        return bots.size();
    }

    private static int list(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        for (PvpBotEntity bot : bots) {
            ctx.getSource().sendSuccess(() -> Component.literal("§f" + bot.getName().getString()
                    + " §7- " + (int) bot.getHealth() + "/" + (int) bot.getMaxHealth() + " HP, Zustand: " + bot.describeState()), false);
        }
        return bots.size();
    }
}
