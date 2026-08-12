from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from mallabot.config import Settings, onboard_token
from mallabot.onboard.views import ApplyView

log = logging.getLogger("malla.onboard")


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
    # Avoid duplicate Estado if re-clicked
    if emb.fields and emb.fields[0].name == "Estado":
        emb.set_field_at(0, name="Estado", value=status, inline=False)
    else:
        emb.insert_field_at(0, name="Estado", value=status, inline=False)
    disabled = discord.ui.View()
    if interaction.message:
        await interaction.message.edit(embed=emb, view=disabled)
    await interaction.followup.send("Hecho." if approve else "Rechazado.", ephemeral=True)


async def post_apply_panel(bot: commands.Bot, settings: Settings) -> None:
    channel = bot.get_channel(settings.channel_verificacion)
    if not isinstance(channel, discord.TextChannel):
        log.error("CHANNEL_VERIFICACION invalid")
        return
    # Avoid duplicate panels: look at last 20 messages from us with the button
    async for msg in channel.history(limit=20):
        if msg.author.id == bot.user.id and msg.components:
            log.info("Apply panel already present: %s", msg.id)
            return
    embed = discord.Embed(
        title="Verificación — únete a Mallanet",
        description=(
            "Lee <#{}> y pulsa **Aplicar**.\n"
            "Pedimos presentación, qué haces, qué quieres aportar, "
            "LinkedIn _(opcional)_ y un **website o Instagram** _(obligatorio)_.\n\n"
            "Un humano revisa y, si encaja, te damos **Verificado**."
        ).format(settings.channel_reglas),
        color=0x1F6FEB,
    )
    await channel.send(embed=embed, view=ApplyView(settings))
    log.info("Posted apply panel")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    bot.add_view(ApplyView(settings))

    @bot.event
    async def on_ready() -> None:
        log.info("onboard ready as %s", bot.user)
        await post_apply_panel(bot, settings)

    @bot.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        if cid.startswith("malla:approve:"):
            await handle_review(interaction, settings, approve=True, applicant_id=int(cid.rsplit(":", 1)[1]))
        elif cid.startswith("malla:reject:"):
            await handle_review(interaction, settings, approve=False, applicant_id=int(cid.rsplit(":", 1)[1]))

    bot.run(onboard_token(), log_handler=None)


if __name__ == "__main__":
    main()
