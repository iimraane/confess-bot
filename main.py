# ──────────── FICHIER main.py ────────────
# Bot “Confess” – messages anonymes interactifs
# Discord.py ≥2.3 (ou Py-Cord équivalent)

import discord, asyncio, json, os, requests
from discord.ext import commands
from discord.ui import View, Select, Button
import threading
import keep_alive           # ← ajoute cette ligne


# ─────────────────────────── CONFIG
TOKEN = "MTM2NTc4Njk5Mjc3MTYwMDYxNg.GtxhSl.4g3KMLDEsEzQgvIgQYNifWaBU4C2NeziMyyPY8"                       # ← garde ton token en variable d’environnement !
CHANNEL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "db.json")

threading.Thread(target=keep_alive.run, daemon=True).start()
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True          # pour être sûr que le cache des salons se peuple vite


bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────── UTILS
def load_channel_config() -> dict:
    if os.path.exists(CHANNEL_CONFIG_PATH):
        with open(CHANNEL_CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

def save_channel_config(data: dict):
    with open(CHANNEL_CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

async def log_to_webhook(author: str, cmd: str, content: str, response: str = ""):
    """Envoie le log dans chaque salon configuré."""
    message = (
        f"Auteur : {author}\n"
        f"Commande : {cmd}\n"
        f"Contenu  : {content}\n"
        f"Réponse  : {response}"
    )

    cfg = load_channel_config()
    for gid, data in cfg.items():
        chan_id = data.get("log_channel_id")
        if not chan_id:
            continue

        channel = bot.get_channel(chan_id)
        if channel is None:                # pas dans le cache ➜ on fetch
            try:
                channel = await bot.fetch_channel(chan_id)
            except discord.NotFound:
                continue        # salon supprimé ➜ on l’ignorera poliment
            except discord.Forbidden:
                continue        # pas la permission

        try:
            await channel.send(f"```log\n{message}\n```")
        except discord.Forbidden:
            pass   # permissions retirées



# ─────────────────────────── VIEWS
class ColorSelect(View):
    def __init__(self, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.value: int | None = None

    @discord.ui.select(
        placeholder="Choisis ta couleur 🎨",
        options=[
            discord.SelectOption(label="Bleu",   emoji="💙", value="0x87CEEB"),
            discord.SelectOption(label="Rouge",  emoji="❤️", value="0xFF6347"),
            discord.SelectOption(label="Vert",   emoji="💚", value="0x32CD32"),
            discord.SelectOption(label="Jaune",  emoji="💛", value="0xFFD700"),
            discord.SelectOption(label="Rose",   emoji="💖", value="0xFF69B4"),
            discord.SelectOption(label="Violet", emoji="💜", value="0x8A2BE2"),
        ],
    )
    # ordre correct : interaction PUIS select
    async def select_callback(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select
    ):
        self.value = int(select.values[0], 16)   # ← plus d’erreur !
        await interaction.response.defer()
        self.stop()


class ConfirmView(View):
    def __init__(self, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.approved: bool | None = None

    @discord.ui.button(label="Envoyer ✅", style=discord.ButtonStyle.green)
    async def send_btn(
        self,
        interaction: discord.Interaction,     # ← interaction en premier
        button: discord.ui.Button
    ):
        self.approved = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Annuler ❌", style=discord.ButtonStyle.red)
    async def cancel_btn(
        self,
        interaction: discord.Interaction,     # ← idem ici
        button: discord.ui.Button
    ):
        self.approved = False
        await interaction.response.defer()
        self.stop()


# ─────────────────────────── SESSIONS / ANNULATION
active_sessions: dict[int, asyncio.Event] = {}  # user_id → event d’annulation

# ─────────────────────────── COMMANDE !setup
@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_ano(ctx: commands.Context, channel: discord.TextChannel):
    """Définit le salon où seront publiés les messages anonymes."""
    cfg = load_channel_config()
    gid = str(ctx.guild.id)
    cfg.setdefault(gid, {})
    cfg[gid]["anon_channel_id"] = channel.id
    cfg[gid].setdefault("banned_users", [])
    save_channel_config(cfg)

    await ctx.send(f"✅ Salon anonyme défini : {channel.mention}")
    log_to_webhook(ctx.author.name, "!setup", f"Channel = {channel.id}", "OK")

@setup_ano.error
async def setup_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Seuls les administrateurs peuvent exécuter cette commande.")
    else:
        raise error

# ─────────────────────────── COMMANDE !anoban
@bot.command(name="anoban")
@commands.has_permissions(administrator=True)
async def anoban(ctx: commands.Context, member: discord.Member):
    """Interdit un utilisateur d’utiliser !ano."""
    cfg = load_channel_config()
    gid = str(ctx.guild.id)
    cfg.setdefault(gid, {"banned_users": [], "anon_channel_id": None})
    banned = cfg[gid].setdefault("banned_users", [])

    if member.id in banned:
        await ctx.send("ℹ️ Cet utilisateur est déjà banni des messages anonymes.")
        return

    banned.append(member.id)
    save_channel_config(cfg)

    await ctx.send(f"🚫 {member.mention} est désormais banni des messages anonymes.")
    log_to_webhook(ctx.author.name, "!anoban", f"User = {member.id}", "Banni")

@anoban.error
async def anoban_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Seuls les administrateurs peuvent exécuter cette commande.")
    else:
        raise error
    
# ─────────────────────────── COMMANDE !anounban
@bot.command(name="anounban")
@commands.has_permissions(administrator=True)
async def anounban(ctx: commands.Context, member: discord.Member):
    """Réadmet un utilisateur dans les messages anonymes."""
    cfg = load_channel_config()
    gid = str(ctx.guild.id)
    banned = cfg.setdefault(gid, {}).setdefault("banned_users", [])

    if member.id not in banned:
        await ctx.send("ℹ️ Cet utilisateur n’était pas banni des messages anonymes.")
        return

    banned.remove(member.id)
    save_channel_config(cfg)

    await ctx.send(f"✅ {member.mention} est de nouveau autorisé à utiliser `!ano`.")
    log_to_webhook(ctx.author.name, "!anounban", f"User = {member.id}", "Débanni")


@anounban.error
async def anounban_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Seuls les administrateurs peuvent exécuter cette commande.")
    else:
        raise error
    
# ─────────────────────────── COMMANDE !logsetup
@bot.command(name="logsetup")
@commands.has_permissions(administrator=True)
async def logsetup(ctx: commands.Context, channel: discord.TextChannel):
    """Définit le salon où le bot enverra ses logs (en plus du webhook)."""
    cfg = load_channel_config()
    gid = str(ctx.guild.id)
    cfg.setdefault(gid, {})
    cfg[gid]["log_channel_id"] = channel.id
    save_channel_config(cfg)

    await ctx.send(f"📜 Salon de logs défini : {channel.mention}")
    log_to_webhook(ctx.author.name, "!logsetup", f"Channel = {channel.id}", "OK")


@logsetup.error
async def logsetup_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⛔ Seuls les administrateurs peuvent exécuter cette commande.")
    else:
        raise error

# ─────────────────────────── COMMANDE !aide
@bot.command(name="aide", aliases=["commands"])
async def aide(ctx: commands.Context):
    """Affiche la liste des commandes disponibles."""
    txt = (
        "🌟 **Commandes disponibles**\n"
        "• `!ano` *(DM uniquement)* : crée un message anonyme de façon interactive.\n"
        "• `!anostop` *(DM)* : annule la procédure `!ano` en cours.\n"
        "• `!setup <#salon>` *(admin)* : définit le salon où seront publiés les confessions.\n"
        "• `!logsetup #salon` – Choisir le salon de logs du bot (Admin)\n"
        "• `!anoban @membre` *(admin)* : bannit un utilisateur de `!ano`.\n"
        "• `!anounban @membre` – Débannir `!ano` (Admin)\n"
        "• `!aide` : affiche ce message.\n"
    )
    await ctx.send(txt)
    log_to_webhook(ctx.author.name, "!aide", "—", "OK")

# ─────────────────────────── COMMANDE !anostop
@bot.command()
@commands.dm_only()
async def anostop(ctx: commands.Context):
    """Annule la procédure !ano en cours."""
    if (ev := active_sessions.get(ctx.author.id)) and not ev.is_set():
        ev.set()
        await ctx.reply("Procédure interrompue 🔕. Tu peux relancer **!ano** quand tu veux.")
    else:
        await ctx.reply("Aucune procédure active à interrompre.")

# ─────────────────────────── COMMANDE INTERACTIVE !ano
@bot.command(name="ano")
@commands.dm_only()
async def ano(ctx: commands.Context):
    """Création interactive d’un message anonyme."""
    # ───── Vérifie si l’utilisateur est banni d’au moins un serveur commun
    cfg = load_channel_config()
    if any(
        str(g.id) in cfg and ctx.author.id in cfg[str(g.id)].get("banned_users", [])
        for g in ctx.author.mutual_guilds
    ):
        await ctx.send("🚫 Tu n’es pas autorisé à utiliser les messages anonymes.")
        return

    # ───── Préparation session
    cancel_event = asyncio.Event()
    active_sessions[ctx.author.id] = cancel_event

    async def prompt(question: str, timeout: int = 180) -> str:
        await ctx.send(question)

        response_task = asyncio.create_task(
            bot.wait_for(
                "message",
                timeout=timeout,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )
        )
        cancel_task = asyncio.create_task(cancel_event.wait())

        done, pending = await asyncio.wait(
            {response_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if cancel_task in done:
            raise Exception("Annulation demandée.")

        return response_task.result().content.strip()


    try:
        # 1️⃣ Titre
        title = await prompt("Quel est le **titre** de ton post ? 📝")

        # 2️⃣ Couleur
        color_view = ColorSelect()
        await ctx.send("Choisis la **couleur** de ton embed :", view=color_view)
        await color_view.wait()
        if color_view.value is None:
            raise Exception("Couleur non choisie ou temps dépassé.")
        color = color_view.value

        # 3️⃣ Corps du message
        body = await prompt("Parfait ! Tape maintenant le **contenu** de ton message ✍️")

        # 4️⃣ Aperçu + confirmation
        preview = discord.Embed(title=title, description=body, color=color)
        confirm_view = ConfirmView()
        await ctx.send("Voici un aperçu. On l’envoie ?", embed=preview, view=confirm_view)
        await confirm_view.wait()
        if not confirm_view.approved:
            raise Exception("Message annulé par l’utilisateur.")

        # 5️⃣ Envoi dans le(s) serveur(s)
        sent_somewhere = False
        for g in ctx.author.mutual_guilds:
            gid = str(g.id)
            guild_cfg = cfg.get(gid, {})
            dest_id = guild_cfg.get("anon_channel_id")
            if dest_id:
                channel = bot.get_channel(dest_id)
                if channel:
                    await channel.send(embed=preview)
                    sent_somewhere = True

        if not sent_somewhere:
            await ctx.send("⚠️ Aucun salon anonyme n’a été configuré sur tes serveurs communs.")
            return

        await ctx.send("✅ Ton message anonyme vient d’être publié !")

        log_to_webhook(
            author=ctx.author.name,
            cmd="!ano",
            content=f"Titre: {title}\nCorps: {body}",
            response="Envoyé",
        )

    except asyncio.TimeoutError:
        await ctx.send("⌛ Temps écoulé, la procédure a été annulée.")
    except Exception as e:
        await ctx.send(f"❌ {e}")
        log_to_webhook(ctx.author.name, "!ano", "—", f"Abandonné ({e})")
    finally:
        active_sessions.pop(ctx.author.id, None)

@ano.error
async def ano_error(ctx: commands.Context, error):
    if isinstance(error, commands.PrivateMessageOnly):
        await ctx.send("😅 Cette commande ne fonctionne qu’en **message privé**.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send("⏳ Doucement ! Réessaie dans quelques secondes.")
    else:
        raise error

# ─────────────────────────── READY & LANCEMENT
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} ✔️")

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("La variable d’environnement DISCORD_TOKEN est vide.")
    bot.run(TOKEN)
