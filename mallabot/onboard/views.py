from __future__ import annotations

import discord

from mallabot.config import Settings

BTN_APPLY = "malla:apply"


class ApplyModal(discord.ui.Modal, title="Aplicar a Mallanet"):
    presentacion = discord.ui.TextInput(
        label="¿Cómo te presentas?",
        style=discord.TextStyle.short,
        required=True,
        max_length=100,
        placeholder="Nombre o como te conocen",
    )
    oficio = discord.ui.TextInput(
        label="¿Qué haces?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800,
        placeholder="Oficio, skills, experiencia breve",
    )
    aporte = discord.ui.TextInput(
        label="¿Qué quieres aportar o qué idea tienes?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800,
        placeholder="Cuéntanos cómo te gustaría sumar",
    )
    linkedin = discord.ui.TextInput(
        label="LinkedIn (opcional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=200,
        placeholder="https://linkedin.com/in/...",
    )
    enlace = discord.ui.TextInput(
        label="Website o Instagram",
        style=discord.TextStyle.short,
        required=True,
        max_length=200,
        placeholder="https://...",
    )

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Solo en el server.", ephemeral=True)
            return

        # Acknowledge immediately — role + #bot-admin can exceed 3s.
        await interaction.response.defer(ephemeral=True)

        member = guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                member = None
        pendiente = guild.get_role(self.settings.role_pendiente)
        if member and pendiente and pendiente not in member.roles:
            try:
                await member.add_roles(pendiente, reason="KYC application submitted")
            except discord.HTTPException:
                pass

        embed = discord.Embed(
            title="Nueva aplicación",
            color=0xD29922,
            description=f"Solicitante: {interaction.user.mention} (`{interaction.user.id}`)",
        )
        embed.add_field(name="Presentación", value=str(self.presentacion)[:1024], inline=False)
        embed.add_field(name="Qué hace", value=str(self.oficio)[:1024], inline=False)
        embed.add_field(name="Aporte / idea", value=str(self.aporte)[:1024], inline=False)
        li = str(self.linkedin).strip()
        embed.add_field(name="LinkedIn", value=li or "_(no indicado)_", inline=False)
        embed.add_field(name="Website / Instagram", value=str(self.enlace)[:1024], inline=False)
        embed.set_footer(text="Privacidad: solo admisión/coordinación · no se vende")

        admin = guild.get_channel(self.settings.channel_bot_admin)
        if not isinstance(admin, discord.TextChannel):
            await interaction.followup.send(
                "No pude notificar a ops. Avisa a un Root.", ephemeral=True
            )
            return

        uid = interaction.user.id
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Aprobar → Verificado",
                style=discord.ButtonStyle.success,
                custom_id=f"malla:approve:{uid}",
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Rechazar",
                style=discord.ButtonStyle.danger,
                custom_id=f"malla:reject:{uid}",
            )
        )
        await admin.send(embed=embed, view=view)
        await interaction.followup.send(
            "Aplicación enviada. Quedó en revisión. Te avisamos cuando haya decisión.",
            ephemeral=True,
        )


class ApplyView(discord.ui.View):
    def __init__(self, settings: Settings):
        super().__init__(timeout=None)
        self.settings = settings

    @discord.ui.button(
        label="Aplicar",
        style=discord.ButtonStyle.primary,
        custom_id=BTN_APPLY,
        emoji="✅",
    )
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Solo en el server.", ephemeral=True)
            return
        member = guild.get_member(interaction.user.id)
        if member and any(r.id == self.settings.role_verificado for r in member.roles):
            await interaction.response.send_message(
                "Ya tienes **Verificado**. No necesitas aplicar de nuevo.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ApplyModal(self.settings))
