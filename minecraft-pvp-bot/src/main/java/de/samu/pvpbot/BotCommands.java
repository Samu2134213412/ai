package de.samu.pvpbot;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import de.samu.pvpbot.ai.BotAi;
import de.samu.pvpbot.brain.BotBrain;
import de.samu.pvpbot.voice.BotVoice;
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
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;

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
                .then(Commands.literal("survival")
                        .executes(ctx -> spawnSurvival(ctx, "Survival-Bot"))
                        .then(Commands.argument("name", StringArgumentType.greedyString())
                                .executes(ctx -> spawnSurvival(ctx, StringArgumentType.getString(ctx, "name")))))
                .then(Commands.literal("gather")
                        .then(Commands.literal("on").executes(ctx -> setGather(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> setGather(ctx, false))))
                .then(Commands.literal("needs").executes(BotCommands::needs))
                .then(Commands.literal("durchspielen")
                        .executes(ctx -> setSpeedrun(ctx, true))
                        .then(Commands.literal("stop").executes(ctx -> setSpeedrun(ctx, false))))
                .then(Commands.literal("autonom")
                        .executes(ctx -> setAutonomous(ctx, true))
                        .then(Commands.literal("on").executes(ctx -> setAutonomous(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> setAutonomous(ctx, false))))
                .then(Commands.literal("home")
                        .executes(BotCommands::homeInfo)
                        .then(Commands.literal("set").executes(BotCommands::homeSet))
                        .then(Commands.literal("go").executes(BotCommands::homeGo))
                        .then(Commands.literal("clear").executes(BotCommands::homeClear)))
                .then(Commands.literal("duel").executes(BotCommands::duel))
                .then(Commands.literal("kit")
                        .executes(BotCommands::kitShow)
                        .then(Commands.literal("default").executes(BotCommands::kitDefault))
                        .then(Commands.literal("copy").executes(BotCommands::kitCopy))
                        .then(Commands.literal("give").executes(BotCommands::kitGive))
                        .then(Commands.literal("take").executes(BotCommands::kitTake)))
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
                .then(Commands.literal("trick")
                        .then(Commands.argument("name", StringArgumentType.word())
                                .suggests((c, b) -> {
                                    for (BotBrain.Pattern p : BotBrain.Pattern.values()) {
                                        b.suggest(p.trickName());
                                    }
                                    return b.buildFuture();
                                })
                                .executes(BotCommands::trick)))
                .then(Commands.literal("brain")
                        .executes(BotCommands::brain)
                        .then(Commands.literal("reset").executes(BotCommands::brainReset)))
                .then(Commands.literal("chat")
                        .then(Commands.literal("on").executes(ctx -> setTalk(ctx, true)))
                        .then(Commands.literal("off").executes(ctx -> setTalk(ctx, false))))
                .then(Commands.literal("ki")
                        .executes(BotCommands::aiInfo)
                        .then(Commands.literal("key")
                                .then(Commands.argument("key", StringArgumentType.greedyString())
                                        .executes(BotCommands::aiKey)))
                        .then(Commands.literal("aus").executes(BotCommands::aiOff)))
                .then(Commands.literal("sag")
                        .then(Commands.argument("text", StringArgumentType.greedyString())
                                .executes(BotCommands::aiSay)))
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

    private static int spawnSurvival(CommandContext<CommandSourceStack> ctx, String name) throws CommandSyntaxException {
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
        bot.setKit(List.of(), false);
        bot.setGathering(true);
        level.addFreshEntity(bot);
        ctx.getSource().sendSuccess(() -> Component.literal("§a" + name + " startet mit leeren Händen und besorgt sich seine Ausrüstung selbst: "
                + "Holz → Spitzhacke → Stein → Eisen → Schwert, Rüstung, Schild, Essen. §7Status: §f/pvpbot needs"), false);
        return 1;
    }

    private static int setGather(CommandContext<CommandSourceStack> ctx, boolean gather) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setGathering(gather));
        ctx.getSource().sendSuccess(() -> Component.literal(gather
                ? "§aBots mit Survival-Kit besorgen sich fehlende Ausrüstung selbst."
                : "§eBots sammeln nichts mehr."), false);
        return bots.size();
    }

    private static int needs(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        for (PvpBotEntity bot : bots) {
            ctx.getSource().sendSuccess(() -> Component.literal("§f" + bot.getName().getString() + " §7" + bot.describeNeeds()
                    + " §8| Kit: " + bot.describeKit()), false);
        }
        return bots.size();
    }

    private static int setSpeedrun(CommandContext<CommandSourceStack> ctx, boolean on) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        int count = 0;
        for (PvpBotEntity bot : bots) {
            if (on && bot.getKit().isInfinite()) {
                continue;
            }
            bot.setSpeedrun(on);
            count++;
        }
        if (on && count == 0 && !bots.isEmpty()) {
            ctx.getSource().sendFailure(Component.literal("Dein Bot hat ein unendliches Kit. Nimm einen Survival-Bot: /pvpbot survival"));
            return 0;
        }
        ctx.getSource().sendSuccess(() -> Component.literal(on
                ? "§5Durchspielen – Etappe 1: §fWassereimer → Diamantspitzhacke (Treppe runter, Strip-Mining) → 10 Obsidian (Wasser auf Lava) → Feuerzeug → Netherportal. §7Status: /pvpbot needs"
                : "§eDurchspielen gestoppt."), false);
        return count;
    }

    private static int setAutonomous(CommandContext<CommandSourceStack> ctx, boolean on) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        int count = 0;
        boolean homeless = false;
        for (PvpBotEntity bot : bots) {
            if (on && bot.getKit().isInfinite()) {
                continue;
            }
            bot.setAutonomous(on);
            homeless |= on && bot.getHome() == null;
            count++;
        }
        if (on && count == 0 && !bots.isEmpty()) {
            ctx.getSource().sendFailure(Component.literal("Dein Bot hat ein unendliches Kit. Nimm einen Survival-Bot: /pvpbot survival"));
            return 0;
        }
        boolean noHome = homeless;
        ctx.getSource().sendSuccess(() -> Component.literal(on
                ? "§6Autonom: §fverbessert seine Ausrüstung bis Diamant, sammelt Ersatz-Rüstungssets (1× Eisen, 2× Diamant) und lagert sie in Kisten im Umkreis von 10 Blöcken um sein Zuhause (vorhandene Kisten benutzt er, sonst stellt er selbst welche auf). Wenn nichts zu tun ist, wartet er zu Hause."
                        + (noHome ? " §cSetz ihm noch ein Zuhause (Menü O → Zuhause oder /pvpbot home set), sonst kann er nichts einlagern." : "")
                : "§eAutonom aus."), false);
        return count;
    }

    private static int homeSet(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        net.minecraft.core.BlockPos pos = net.minecraft.core.BlockPos.containing(ctx.getSource().getPosition());
        for (PvpBotEntity bot : bots) {
            if (bot.level() == ctx.getSource().getLevel()) {
                bot.setHome(pos);
            }
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§6Zuhause gesetzt: §f" + pos.getX() + " " + pos.getY() + " " + pos.getZ()
                + " §7– hier stellt er seine Kisten auf und hierhin kommt er zurück."), false);
        return bots.size();
    }

    private static int homeClear(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.setHome(null));
        ctx.getSource().sendSuccess(() -> Component.literal("§eZuhause gelöscht."), false);
        return bots.size();
    }

    private static int homeGo(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        int count = 0;
        for (PvpBotEntity bot : bots) {
            if (bot.getHome() != null) {
                bot.setFollowing(false);
                bot.clearTargets();
                bot.goHome();
                count++;
            }
        }
        int n = count;
        ctx.getSource().sendSuccess(() -> Component.literal(n > 0 ? "§6Ab nach Hause." : "§cKein Zuhause gesetzt: /pvpbot home set"), false);
        return count;
    }

    private static int homeInfo(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        for (PvpBotEntity bot : myBots(ctx)) {
            var home = bot.getHome();
            ctx.getSource().sendSuccess(() -> Component.literal("§6" + bot.getName().getString() + "§7: Zuhause "
                    + (home == null ? "§ckeins" : "§f" + home.getX() + " " + home.getY() + " " + home.getZ())
                    + " §7· Kisten: §f" + bot.homeChests().size() + " §7· Autonom: " + (bot.isAutonomous() ? "§aan" : "§caus")), false);
        }
        return 1;
    }

    private static int trick(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        String name = StringArgumentType.getString(ctx, "name");
        BotBrain.Pattern pattern = BotBrain.Pattern.byTrickName(name);
        if (pattern == null) {
            ctx.getSource().sendFailure(Component.literal("Unbekannter Trick. Möglich: kombo, smash, ansturm, stiche, sturzflug, speerflug, mace, schwert, bogen"));
            return 0;
        }
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.forcePattern(pattern));
        ctx.getSource().sendSuccess(() -> Component.literal("§aNächster Angriff: §f" + pattern.label), false);
        return bots.size();
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
            if (entity == ctx.getSource().getEntity()) {
                // "@s": the player wants to fight the bots themselves.
                return duel(ctx);
            }
            if (entity instanceof LivingEntity living && !(entity instanceof PvpBotEntity)) {
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

    private static int duel(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        if (player.isCreative() || player.isSpectator()) {
            ctx.getSource().sendFailure(Component.literal("Im Kreativmodus kann dir der Bot nichts tun. Wechsle mit /gamemode survival in den Überlebensmodus."));
            return 0;
        }
        List<PvpBotEntity> bots = myBots(ctx);
        bots.forEach(b -> b.startDuel(player));
        if (!bots.isEmpty()) {
            ctx.getSource().sendSuccess(() -> Component.literal("§c⚔ Duell! §7" + bots.size() + " Bot(s) kämpfen gegen dich. Aufgeben mit §f/pvpbot stop§7."), false);
        }
        return bots.size();
    }

    private static @org.jspecify.annotations.Nullable PvpBotEntity nearestBot(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        return myBots(ctx).stream().min(java.util.Comparator.comparingDouble(b -> b.distanceToSqr(player))).orElse(null);
    }

    private static int kitShow(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        for (PvpBotEntity bot : myBots(ctx)) {
            ctx.getSource().sendSuccess(() -> Component.literal("§f" + bot.getName().getString() + "§7: Kit " + bot.describeKit()), false);
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§7Ändern: §f/pvpbot kit default§7 (Mace/Speer/Elytra), §fcopy§7 (Kopie deines Inventars, nur Kreativ), §fgive§7 (gibt ihm deine Rüstung + Hotbar, Survival), §ftake§7 (zurückholen)"), false);
        return 1;
    }

    private static int kitDefault(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        List<PvpBotEntity> bots = myBots(ctx);
        for (PvpBotEntity bot : bots) {
            if (!bot.getKit().isInfinite()) {
                ctx.getSource().sendFailure(Component.literal(bot.getName().getString() + " hat noch dein Survival-Kit – hol es erst mit /pvpbot kit take zurück."));
                continue;
            }
            bot.equipLoadout();
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§aStandard-Kit: Mace, Speer, Elytra."), false);
        return bots.size();
    }

    private static List<ItemStack> playerKitItems(ServerPlayer player, boolean hotbarOnly) {
        List<ItemStack> items = new java.util.ArrayList<>();
        for (EquipmentSlot slot : new EquipmentSlot[]{EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET, EquipmentSlot.OFFHAND}) {
            items.add(player.getItemBySlot(slot));
        }
        var inventory = player.getInventory().getNonEquipmentItems();
        for (int i = 0; i < (hotbarOnly ? 9 : inventory.size()); i++) {
            items.add(inventory.get(i));
        }
        items.removeIf(ItemStack::isEmpty);
        return items;
    }

    private static int kitCopy(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        if (!player.isCreative()) {
            ctx.getSource().sendFailure(Component.literal("Kopieren geht nur im Kreativmodus. Im Survival nimm /pvpbot kit give – dann bekommt er deine echten Sachen."));
            return 0;
        }
        List<PvpBotEntity> bots = myBots(ctx);
        for (PvpBotEntity bot : bots) {
            if (!bot.getKit().isInfinite()) {
                continue;
            }
            bot.setKit(playerKitItems(player, false).stream().map(ItemStack::copy).toList(), true);
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§aDeine Bots haben jetzt eine Kopie deines Kits. Sie lernen selbst, wie man damit kämpft."), false);
        return bots.size();
    }

    private static int kitGive(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        PvpBotEntity bot = nearestBot(ctx);
        if (bot == null) {
            return 0;
        }
        if (!bot.getKit().isInfinite()) {
            ctx.getSource().sendFailure(Component.literal(bot.getName().getString() + " hat schon ein Survival-Kit von dir."));
            return 0;
        }
        List<ItemStack> items = playerKitItems(player, true);
        if (items.isEmpty()) {
            ctx.getSource().sendFailure(Component.literal("Du hast nichts in Rüstung, Hotbar oder Zweithand."));
            return 0;
        }
        // Move (not copy) the items: survival friendly, nothing gets duplicated.
        for (EquipmentSlot slot : new EquipmentSlot[]{EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET, EquipmentSlot.OFFHAND}) {
            player.setItemSlot(slot, ItemStack.EMPTY);
        }
        var inventory = player.getInventory().getNonEquipmentItems();
        for (int i = 0; i < 9; i++) {
            inventory.set(i, ItemStack.EMPTY);
        }
        bot.setKit(items, false);
        ctx.getSource().sendSuccess(() -> Component.literal("§a" + bot.getName().getString() + " kämpft jetzt mit deinem Kit (" + bot.describeKit()
                + "§a). Stirbt er, lässt er alles fallen. Zurück mit §f/pvpbot kit take§a."), false);
        return 1;
    }

    private static int kitTake(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        PvpBotEntity bot = nearestBot(ctx);
        if (bot == null) {
            return 0;
        }
        if (bot.getKit().isInfinite()) {
            ctx.getSource().sendFailure(Component.literal(bot.getName().getString() + " hat kein Kit von dir."));
            return 0;
        }
        for (ItemStack stack : bot.removeKit()) {
            if (!player.getInventory().add(stack)) {
                player.spawnAtLocation(ctx.getSource().getLevel(), stack);
            }
        }
        ctx.getSource().sendSuccess(() -> Component.literal("§aDu hast dein Kit zurück. Der Bot kämpft jetzt mit den Fäusten – /pvpbot kit default gibt ihm wieder seine Ausrüstung."), false);
        return 1;
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

    private static int aiInfo(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        boolean key = BotAi.INSTANCE.hasKey(player.getUUID());
        ctx.getSource().sendSuccess(() -> Component.literal("§6KI-Chat: " + (key ? "§aan" : "§caus – §f/pvpbot ki key <dein-anthropic-key>")
                + "\n§7Schreib im Chat §f@bot <text>§7 (oder §f@Name§7 / §fName, <text>§7) oder §f/pvpbot sag <text>§7. "
                + "Die KI antwortet für deinen Bot und legt seine Ziele fest (Durchspielen, Aufträge, Kämpfen …). Modell: §f"
                + BotAi.INSTANCE.model() + (BotVoice.available() ? "§7 · Voice Chat: §aan" : "§7 · Voice Chat: §caus")), false);
        return key ? 1 : 0;
    }

    private static int aiKey(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        String key = StringArgumentType.getString(ctx, "key").strip();
        if (!key.startsWith("sk-")) {
            ctx.getSource().sendFailure(Component.literal("Das sieht nicht wie ein Anthropic-API-Key aus (beginnt mit sk-)."));
            return 0;
        }
        BotAi.INSTANCE.setKey(player.getUUID(), key);
        // (The key is never shown again or written to the log.)
        ctx.getSource().sendSuccess(() -> Component.literal("§aAPI-Key gespeichert. §7Schreib jetzt im Chat §f@bot hallo"), false);
        return 1;
    }

    private static int aiOff(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        BotAi.INSTANCE.setKey(player.getUUID(), null);
        ctx.getSource().sendSuccess(() -> Component.literal("§eAPI-Key gelöscht, KI-Chat aus."), false);
        return 1;
    }

    private static int aiSay(CommandContext<CommandSourceStack> ctx) throws CommandSyntaxException {
        ServerPlayer player = ctx.getSource().getPlayerOrException();
        PvpBotEntity bot = nearestBot(ctx);
        if (bot == null) {
            ctx.getSource().sendFailure(Component.literal("Du hast keine Bots in der Nähe. Erstelle einen mit /pvpbot survival"));
            return 0;
        }
        String text = StringArgumentType.getString(ctx, "text");
        player.sendSystemMessage(Component.literal("§7<" + player.getName().getString() + " → " + bot.getName().getString() + "> " + text));
        BotAi.INSTANCE.ask(player, bot, text);
        return 1;
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
