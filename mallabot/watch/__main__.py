from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from mallabot.config import Settings, watch_token

log = logging.getLogger("malla.watch")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class WatchBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.moderation = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings

    async def setup_hook(self) -> None:
        log.info("watch setup")

    async def log_embed(self, embed: discord.Embed) -> None:
        ch = self.get_channel(self.settings.channel_logs)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=embed)
            except discord.HTTPException as e:
                log.warning("log send failed: %s", e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    bot = WatchBot(settings)

    @bot.event
    async def on_ready() -> None:
        log.info("watch ready as %s", bot.user)

    @bot.event
    async def on_member_join(member: discord.Member) -> None:
        if member.guild.id != settings.guild_id:
            return
        emb = discord.Embed(title="Join", color=0x238636, timestamp=datetime.now(timezone.utc))
        emb.description = f"{member.mention} (`{member.id}`)\ncuenta: <t:{int(member.created_at.timestamp())}:R>"
        emb.set_footer(text=_now())
        await bot.log_embed(emb)

    @bot.event
    async def on_member_remove(member: discord.Member) -> None:
        if member.guild.id != settings.guild_id:
            return
        emb = discord.Embed(title="Leave / kick", color=0xD29922, timestamp=datetime.now(timezone.utc))
        emb.description = f"{member} (`{member.id}`)"
        emb.set_footer(text=_now())
        await bot.log_embed(emb)

    @bot.event
    async def on_member_update(before: discord.Member, after: discord.Member) -> None:
        if after.guild.id != settings.guild_id:
            return
        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        added = after_ids - before_ids
        removed = before_ids - after_ids
        if not added and not removed:
            return
        lines = []
        for rid in sorted(added):
            role = after.guild.get_role(rid)
            lines.append(f"+ {role.mention if role else rid}")
        for rid in sorted(removed):
            role = after.guild.get_role(rid)
            lines.append(f"- {role.mention if role else rid}")
        emb = discord.Embed(title="Roles", color=0x1F6FEB, timestamp=datetime.now(timezone.utc))
        emb.description = f"{after.mention} (`{after.id}`)\n" + "\n".join(lines)
        emb.set_footer(text=_now())
        await bot.log_embed(emb)

    @bot.event
    async def on_audit_log_entry_create(entry: discord.AuditLogEntry) -> None:
        if entry.guild.id != settings.guild_id:
            return
        if entry.action not in (
            discord.AuditLogAction.ban,
            discord.AuditLogAction.unban,
            discord.AuditLogAction.kick,
        ):
            return
        emb = discord.Embed(
            title=entry.action.name.replace("_", " ").title(),
            color=0xDA3633,
            timestamp=datetime.now(timezone.utc),
        )
        target = getattr(entry, "target", None)
        emb.description = (
            f"target: {target} (`{getattr(target, 'id', '?')}`)\n"
            f"by: {entry.user} (`{getattr(entry.user, 'id', '?')}`)\n"
            f"reason: {entry.reason or '—'}"
        )
        emb.set_footer(text=_now())
        await bot.log_embed(emb)

    bot.run(watch_token(), log_handler=None)


if __name__ == "__main__":
    main()
