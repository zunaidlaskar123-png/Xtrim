"""
Xtrim Premium / Free tier system.

Premium is stored locally in bot/data/premium.json.
Only OWNER_IDS can grant/revoke Premium.
No payment processor is included; this is an owner-managed entitlement system.
"""
from __future__ import annotations

import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands

from core import Context
from utils.config import OWNER_IDS, BotName

from utils.premium import (
    premium_data,
    save_premium_data,
    is_premium,
    premium_entry,
    premium_remaining,
)


def premium_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("Premium features are only available in servers.")
        if not is_premium(ctx.guild.id):
            remaining = "This server is on the Free tier."
            raise commands.CheckFailure(
                f"💎 **{BotName} Premium**\n{remaining}\n"
                f"Ask the bot owner to enable Premium for this server."
            )
        return True
    return commands.check(predicate)


class Premium(commands.Cog):
    """Xtrim Free/Premium tier management and Premium-only features."""

    def __init__(self, bot):
        self.bot = bot

    def _owner_only(self, ctx: commands.Context) -> bool:
        return ctx.author.id in OWNER_IDS

    @commands.group(name="premium", aliases=["prem"], invoke_without_command=True)
    async def premium(self, ctx: Context):
        """Show this server's Free/Premium tier."""
        if ctx.guild is None:
            return await ctx.send("💎 Premium tiers are server-only.")

        entry = premium_entry(ctx.guild.id)
        embed = discord.Embed(
            title=f"💎 {BotName} Premium",
            color=0x9B59B6,
        )
        if entry:
            expires = entry.get("expires_at")
            if expires:
                dt = datetime.fromisoformat(expires)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                expiry_text = discord.utils.format_dt(dt, "R")
            else:
                expiry_text = "Never (lifetime)"

            embed.description = (
                "**Tier:** 💎 Premium\n"
                f"**Expires:** {expiry_text}\n\n"
                "**Premium features:**\n"
                "• Premium server statistics\n"
                "• Premium announcements\n"
                "• Premium-only commands\n"
                "• No Prefix\n"
                "• Per-server bot avatar + bio\n"
                "• Priority feature access"
            )
        else:
            embed.description = (
                "**Tier:** 🆓 Free\n\n"
                "**Free includes:**\n"
                "• Core moderation and utility commands\n"
                "• Standard server tools\n\n"
                "**Premium adds:**\n"
                "• Advanced server statistics\n"
                "• Premium announcements\n"
                "• No Prefix\n"
                "• Per-server bot avatar + bio\n"
                "• Premium-only utilities"
            )
        embed.set_footer(text=BotName)
        await ctx.send(embed=embed)

    @premium.command(name="status")
    async def premium_status(self, ctx: Context):
        """Check the current server tier."""
        await self.premium.callback(self, ctx)

    @premium.command(name="add")
    async def premium_add(self, ctx: Context, guild_id: int, days: int = 30):
        """Owner: grant Premium to a guild. Use 0 days for lifetime."""
        if not self._owner_only(ctx):
            return await ctx.send("❌ Owner-only command.")

        if days < 0:
            return await ctx.send("❌ Days cannot be negative.")
        if days > 3650:
            return await ctx.send("❌ Maximum duration is 3650 days.")

        guild = self.bot.get_guild(guild_id)
        data = premium_data()

        if days == 0:
            expires_at = None
            duration = "lifetime"
        else:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            duration = f"{days} days"

        data[str(guild_id)] = {
            "tier": "premium",
            "granted_by": ctx.author.id,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
        }
        save_premium_data(data)

        name = guild.name if guild else str(guild_id)
        await ctx.send(f"💎 **Premium enabled** for **{name}** (`{guild_id}`) for **{duration}**.")

    @premium.command(name="remove")
    async def premium_remove(self, ctx: Context, guild_id: int):
        """Owner: remove Premium from a guild."""
        if not self._owner_only(ctx):
            return await ctx.send("❌ Owner-only command.")

        data = premium_data()
        removed = data.pop(str(guild_id), None)
        save_premium_data(data)

        if removed:
            await ctx.send(f"🆓 Premium removed from `{guild_id}`. The server is now Free.")
        else:
            await ctx.send(f"ℹ️ `{guild_id}` is already on the Free tier.")

    @premium.command(name="list")
    async def premium_list(self, ctx: Context):
        """Owner: list Premium guilds."""
        if not self._owner_only(ctx):
            return await ctx.send("❌ Owner-only command.")

        data = premium_data()
        active = []
        for gid in list(data):
            if premium_entry(int(gid)):
                active.append(gid)

        if not active:
            return await ctx.send("💎 No active Premium servers.")

        lines = []
        for gid in active[:25]:
            guild = self.bot.get_guild(int(gid))
            entry = premium_entry(int(gid))
            name = guild.name if guild else "Unknown server"
            expires = entry.get("expires_at") if entry else None
            expiry = "Lifetime" if not expires else discord.utils.format_dt(
                datetime.fromisoformat(expires), "R"
            )
            lines.append(f"• **{name}** (`{gid}`) — {expiry}")

        embed = discord.Embed(title=f"💎 {BotName} Premium Servers", description="\n".join(lines))
        await ctx.send(embed=embed)

    @commands.command(name="pstats", aliases=["premiumstats"])
    @premium_check()
    async def premium_stats(self, ctx: Context):
        """Premium-only detailed server statistics."""
        guild = ctx.guild
        bots = sum(1 for m in guild.members if m.bot)
        humans = max(0, guild.member_count - bots)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = max(0, len(guild.roles) - 1)

        embed = discord.Embed(
            title=f"💎 {guild.name} — Premium Stats",
            color=0x9B59B6,
        )
        embed.add_field(name="Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="Humans", value=f"{humans:,}", inline=True)
        embed.add_field(name="Bots", value=f"{bots:,}", inline=True)
        embed.add_field(name="Text Channels", value=str(text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=str(voice_channels), inline=True)
        embed.add_field(name="Roles", value=str(roles), inline=True)
        embed.add_field(name="Server ID", value=str(guild.id), inline=False)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"{BotName} Premium")
        await ctx.send(embed=embed)

    @commands.command(name="pannounce", aliases=["premiumannounce"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @premium_check()
    async def premium_announce(self, ctx: Context, *, message: str):
        """Premium-only announcement embed."""
        embed = discord.Embed(
            title=f"📢 {BotName} Premium Announcement",
            description=message,
            color=0x9B59B6,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=BotName)
        await ctx.send(embed=embed)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


    @commands.group(
        name="pbot",
        aliases=["botprofile"],
        invoke_without_command=True,
    )
    @commands.guild_only()
    @premium_check()
    @commands.has_permissions(manage_guild=True)
    async def premium_bot_profile(self, ctx: Context):
        """Premium: customize this bot's per-server profile."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @premium_bot_profile.command(name="avatar", aliases=["pfp", "icon"])
    @commands.guild_only()
    @premium_check()
    @commands.has_permissions(manage_guild=True)
    async def premium_bot_avatar(self, ctx: Context, source: str | None = None):
        """Premium: set/reset the bot avatar for this server."""
        member = ctx.guild.me
        if member is None:
            return await ctx.send("❌ I could not find my server profile.")

        if source and source.lower() in {"reset", "remove", "default"}:
            try:
                await member.edit(avatar=None, reason=f"Premium bot avatar reset by {ctx.author}")
            except discord.HTTPException as e:
                return await ctx.send(f"❌ Failed to reset the server avatar: `{e}`")
            return await ctx.send("✅ Premium bot server avatar has been reset.")

        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        url = source
        if attachment:
            url = attachment.url

        if not url:
            return await ctx.send(
                "❌ Attach a PNG/JPG/GIF image or provide an image URL.\n"
                "Example: `<pbot avatar https://example.com/avatar.png>`"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        return await ctx.send(f"❌ Could not download the image (HTTP {response.status}).")
                    data = await response.read()

            if len(data) > 8 * 1024 * 1024:
                return await ctx.send("❌ Image is too large. Keep it under 8 MB.")

            await member.edit(avatar=data, reason=f"Premium bot avatar changed by {ctx.author}")
        except (aiohttp.InvalidURL, aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            return await ctx.send(f"❌ Invalid image URL: `{e}`")
        except discord.HTTPException as e:
            return await ctx.send(f"❌ Discord rejected the avatar update: `{e}`")

        await ctx.send("✅ Premium bot server avatar updated.")

    @premium_bot_profile.command(name="bio", aliases=["about", "description"])
    @commands.guild_only()
    @premium_check()
    @commands.has_permissions(manage_guild=True)
    async def premium_bot_bio(self, ctx: Context, *, bio: str | None = None):
        """Premium: set/reset the bot bio for this server."""
        member = ctx.guild.me
        if member is None:
            return await ctx.send("❌ I could not find my server profile.")

        if not bio:
            return await ctx.send(
                "❌ Give me the new bio text, or use `<pbot bio reset>` to clear it."
            )

        if bio.strip().lower() in {"reset", "remove", "default"}:
            new_bio = None
        else:
            new_bio = bio.strip()
            if len(new_bio) > 190:
                return await ctx.send("❌ Bio must be 190 characters or fewer.")

        try:
            await member.edit(bio=new_bio, reason=f"Premium bot bio changed by {ctx.author}")
        except TypeError:
            return await ctx.send(
                "❌ Your installed Pycord version is too old for per-server bot bios. "
                "Update Pycord to 2.7+ first."
            )
        except discord.HTTPException as e:
            return await ctx.send(f"❌ Discord rejected the bio update: `{e}`")

        await ctx.send("✅ Premium bot server bio updated." if new_bio else "✅ Premium bot server bio reset.")

    @premium_bot_profile.command(name="show", aliases=["view"])
    @commands.guild_only()
    @premium_check()
    async def premium_bot_profile_show(self, ctx: Context):
        """Premium: show the bot's current server profile."""
        member = ctx.guild.me
        if member is None:
            return await ctx.send("❌ I could not find my server profile.")

        embed = discord.Embed(
            title=f"💎 {BotName} Premium Bot Profile",
            color=0x9B59B6,
        )
        embed.add_field(name="Server", value=ctx.guild.name, inline=False)
        embed.add_field(name="Bio", value=getattr(member, "bio", None) or "Not set", inline=False)
        embed.add_field(name="Avatar", value="Custom server avatar" if member.guild_avatar else "Default avatar", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"{BotName} Premium")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Premium(bot))
