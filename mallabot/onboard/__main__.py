from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from mallabot.config import Settings, onboard_token
from mallabot.onboard.views import BTN_APPLY, ApplyModal, ApplyView

log = logging.getLogger("malla.onboard")

# DM cooldown after deleting chatter in #verificacion (seconds).
_DM_COOLDOWN_S = 3600
_dm_cooldown: dict[int, float] = {}
_panel_lock = asyncio.Lock()


def _is_approver(member: discord.Member, settings: Settings) -> bool:
    return bool(settings.approver_role_ids.intersection({r.id for r in member.roles}))


async def _fetch_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


async def handle_apply(interaction: discord.Interaction, settings: Settings) -> None:
    if interaction.response.is_done():
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Solo en el server.", ephemeral=True)
        return
    # Cache-only check. Never fetch_member before responding (causes Discord timeout).
    member = guild.get_member(interaction.user.id)
    if member and any(r.id == settings.role_verificado for r in member.roles):
        await interaction.response.send_message(
            "Ya tienes **Verificado**. No necesitas aplicar de nuevo.",
            ephemeral=True,
        )
        return
    await interaction.response.send_modal(ApplyModal(settings))


async def handle_review(
    interaction: discord.Interaction, settings: Settings, *, approve: bool, applicant_id: int
) -> None:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Solo en el server.", ephemeral=True)
        return
    if not _is_approver(interaction.user, settings):
        await interaction.response.send_message("Sin permiso.", ephemeral=True)
        return

    # Discord interactions expire in ~3s — defer before role/DM work.
    await interaction.response.defer(ephemeral=True)

    member = await _fetch_member(interaction.guild, applicant_id)
    ver = interaction.guild.get_role(settings.role_verificado)
    pend = interaction.guild.get_role(settings.role_pendiente)

    if approve:
        if not member or not ver:
            await interaction.followup.send("No pude aprobar (miembro/rol).", ephemeral=True)
            return
        try:
            await member.add_roles(ver, reason=f"KYC approved by {interaction.user}")
            if pend and pend in member.roles:
                await member.remove_roles(pend, reason="KYC approved")
        except discord.HTTPException as e:
            await interaction.followup.send(f"Error de roles: {e}", ephemeral=True)
            return
        try:
            await member.send(
                "Listo: ya eres **Verificado** en Mallanet.org. "
                "Mira #informacion y #general. Bienvenido/a."
            )
        except discord.HTTPException:
            pass
        color = 0x238636
        status = f"Aprobada por {interaction.user.mention}"
    else:
        if member and pend and pend in member.roles:
            try:
                await member.remove_roles(pend, reason=f"KYC rejected by {interaction.user}")
            except discord.HTTPException:
                pass
        if member:
            try:
                await member.send(
                    "Tu aplicación a Mallanet.org no fue aprobada esta vez. "
                    "Si crees que fue un error, escribe a un Root o a contacto@mallanet.org."
                )
            except discord.HTTPException:
                pass
        color = 0xDA3633
        status = f"Rechazada por {interaction.user.mention}"

    emb = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
    emb.color = color
    if emb.fields and emb.fields[0].name == "Estado":
        emb.set_field_at(0, name="Estado", value=status, inline=False)
    else:
        emb.insert_field_at(0, name="Estado", value=status, inline=False)
    disabled = discord.ui.View()
    if interaction.message:
        await interaction.message.edit(embed=emb, view=disabled)
    await interaction.followup.send("Hecho." if approve else "Rechazado.", ephemeral=True)


def _is_apply_panel(msg: discord.Message, bot_user_id: int) -> bool:
    return msg.author.id == bot_user_id and bool(msg.components)


async def post_apply_panel(bot: commands.Bot, settings: Settings) -> None:
    channel = bot.get_channel(settings.channel_verificacion)
    if not isinstance(channel, discord.TextChannel):
        log.error("CHANNEL_VERIFICACION invalid")
        return
    if bot.user is None:
        return

    embed = discord.Embed(
        title="Verificación — únete a Mallanet",
        description=(
            "Lee <#{}> y pulsa **Aplicar**.\n"
            "Pedimos presentación, qué haces, qué quieres aportar, "
            "**ciudad**, y un **website / Instagram / LinkedIn** _(obligatorio)_.\n\n"
            "Un humano revisa y, si encaja, te damos **Verificado**."
        ).format(settings.channel_reglas),
        color=0x1F6FEB,
    )
    view = ApplyView(settings)

    async with _panel_lock:
        # Refresh panel: remove old bot panels so the button is bound to this process.
        async for msg in channel.history(limit=30):
            if _is_apply_panel(msg, bot.user.id):
                try:
                    await msg.delete()
                    log.info("Removed old apply panel: %s", msg.id)
                except discord.HTTPException as e:
                    log.warning("Could not delete old panel %s: %s", msg.id, e)

        sent = await channel.send(embed=embed, view=view)
        bot.add_view(view, message_id=sent.id)
        log.info("Posted apply panel: %s", sent.id)


async def ensure_panel_at_bottom(bot: commands.Bot, settings: Settings) -> None:
    """Exactly one apply panel, and it must be the newest message. No-op if already ok."""
    channel = bot.get_channel(settings.channel_verificacion)
    if not isinstance(channel, discord.TextChannel) or bot.user is None:
        return

    # Avoid overlapping with an in-flight post_apply_panel.
    if _panel_lock.locked():
        return

    try:
        messages = [m async for m in channel.history(limit=25)]
    except discord.HTTPException as e:
        log.warning("No pude leer #verificacion: %s", e)
        return

    panels = [m for m in messages if _is_apply_panel(m, bot.user.id)]
    last = messages[0] if messages else None

    if last is not None and len(panels) == 1 and last.id == panels[0].id:
        return

    log.info(
        "Panel hygiene: panels=%s last_is_panel=%s → refresh",
        len(panels),
        bool(last and panels and last.id == panels[0].id),
    )
    await post_apply_panel(bot, settings)


async def _maybe_dm_hygiene(user: discord.abc.User) -> None:
    now = time.monotonic()
    last = _dm_cooldown.get(user.id, 0.0)
    if now - last < _DM_COOLDOWN_S:
        return
    _dm_cooldown[user.id] = now
    try:
        await user.send("En #verificacion solo usa el botón Aplicar ✅")
    except discord.HTTPException:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    # Default intents only (+ members). message_content may be OFF — delete needs no content.
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Persistent fallback (also rebound with message_id in on_ready).
    bot.add_view(ApplyView(settings))

    @tasks.loop(minutes=3)
    async def panel_hygiene() -> None:
        await ensure_panel_at_bottom(bot, settings)

    @panel_hygiene.before_loop
    async def _wait_ready() -> None:
        await bot.wait_until_ready()

    @bot.event
    async def on_ready() -> None:
        log.info("onboard ready as %s", bot.user)
        await post_apply_panel(bot, settings)
        if not panel_hygiene.is_running():
            panel_hygiene.start()
        log.info("cleaner active (#verificacion hygiene)")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        # Channel hygiene: strip human chatter; keep only the Aplicar panel.
        if message.author.bot:
            return
        if message.channel.id != settings.channel_verificacion:
            return
        try:
            await message.delete()
            log.info("Deleted chatter in #verificacion from %s", message.author.id)
        except discord.Forbidden:
            log.warning("Sin Manage Messages en #verificacion — no pude borrar %s", message.id)
            return
        except discord.HTTPException as e:
            log.warning("No pude borrar mensaje %s: %s", message.id, e)
            return

        await _maybe_dm_hygiene(message.author)
        await ensure_panel_at_bottom(bot, settings)

    @bot.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        # Fallback if persistent View dispatch misses the component (prevents Discord timeout).
        if interaction.type is not discord.InteractionType.component:
            return
        if interaction.response.is_done():
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        if cid == BTN_APPLY:
            log.info("apply click user=%s", interaction.user.id)
            await handle_apply(interaction, settings)
        elif cid.startswith("malla:approve:"):
            await handle_review(interaction, settings, approve=True, applicant_id=int(cid.rsplit(":", 1)[1]))
        elif cid.startswith("malla:reject:"):
            await handle_review(interaction, settings, approve=False, applicant_id=int(cid.rsplit(":", 1)[1]))

    bot.run(onboard_token(), log_handler=None)


if __name__ == "__main__":
    main()
