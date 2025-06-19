import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import re
from datetime import datetime, timedelta, timezone

# Make sure these IDs are ints, not strings
GUILD_ID = 1288926604415733854
REQUIRED_ROLE_ID = 1288926707285495941
ANNOUNCEMENT_CHANNEL_ID = 1290777608782483640
WEBHOOK_URL = "https://discord.com/api/webhooks/1290778044948283483/bquY_ka1ndRd7OL7tpZYJUuw5RVQTch0fe_3ddG-uPYTnXOvOZVGZTeY3c9BYAlkuPBD"
WEBHOOK_MESSAGE_ID = 1290778370749104263
LOGGING_CHANNEL_ID = 1288927464080543806

# TOKEN must be set on bot object or passed somehow (recommended: bot token is set outside plugin)
# We'll access it with `self.bot.http.token` here, which is the bot token (discord.py internal)
# If your bot does not expose token, you may need to pass it in differently.

from embeds import (
    flighterrorembed,
    flightsuccessembed,
    flightstepembed,
)

class FlightScheduler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_webhook.start()

    def cog_unload(self):
        self.update_webhook.cancel()

    @tasks.loop(minutes=5)
    async def update_webhook(self):
        token = self.bot.http.token
        if not token:
            return  # no token available, skip

        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as sess:
            try:
                r = await sess.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/scheduled-events", headers=headers)
                if r.status != 200:
                    return
                events = await r.json()
            except Exception:
                return

            upcoming = sorted(
                [e for e in events if datetime.fromisoformat(e['scheduled_start_time'][:-1]) > datetime.utcnow()],
                key=lambda e: e['scheduled_start_time']
            )

            if not upcoming:
                embed = {
                    "title": "Upcoming Flights",
                    "description": "No flights scheduled.",
                    "color": 0xE5E1DE,
                    "footer": {"text": "Updates every 5 min"}
                }
            else:
                embed = {
                    "title": "Upcoming Flights",
                    "fields": [{"name": e["name"], "value": e.get("description", "")} for e in upcoming[:2]],
                    "color": 0xE5E1DE,
                    "footer": {"text": "Updates every 5 min"}
                }

            # PATCH the webhook message
            try:
                await sess.patch(
                    f"{WEBHOOK_URL}/messages/{WEBHOOK_MESSAGE_ID}",
                    json={"embeds": [embed]},
                    headers={"Content-Type": "application/json"}
                )
            except Exception:
                pass

            ch = self.bot.get_channel(LOGGING_CHANNEL_ID)
            if ch:
                try:
                    await ch.send("Updated webhook.")
                except Exception:
                    pass

    async def ask(self, ctx, prompt):
        if isinstance(prompt, discord.Embed):
            await ctx.send(embed=prompt)
        else:
            await ctx.send(prompt)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60)
            if msg.content.lower() == 'cancel':
                await ctx.send(embed=flighterrorembed("Flight creation cancelled."))
                raise asyncio.CancelledError
            return msg.content
        except asyncio.TimeoutError:
            await ctx.send(embed=flighterrorembed("Timed out. Please try again later."))
            raise

    @commands.command()
    async def createflight(self, ctx):
        if REQUIRED_ROLE_ID not in [r.id for r in ctx.author.roles]:
            await ctx.reply("You don't have permission to use this command.")
            return

        try:
            flight_number = await self.ask(ctx, flightstepembed("Enter the flight number (e.g., EA301)."))
            flight_time_raw = await self.ask(ctx, flightstepembed("Enter the flight time as a Unix timestamp (e.g., 1727780400)."))
            flight_time = int(flight_time_raw)
            start = datetime.utcfromtimestamp(flight_time)
            end = start + timedelta(minutes=45)

            aircraft_type = await self.ask(ctx, flightstepembed("Enter the aircraft type (e.g., A320neo)."))
            departure = await self.ask(ctx, flightstepembed("Enter the departure airport (e.g., Edinburgh)."))
            arrival = await self.ask(ctx, flightstepembed("Enter the arrival airport (e.g., Madeira)."))
            roblox_link = await self.ask(ctx, flightstepembed("Enter the Roblox game link.."))

            payload = {
                "name": f"{flight_number} | {departure} - {arrival}",
                "description": (
                    f'<:Tail:1375059430269517885> **Etihad Airways** cordially invites you to attend Flight **{flight_number}**, '
                    f'operating from **{departure}** to **{arrival}** aboard a **{aircraft_type}**.\n\n'
                    f'<:Star:1375535064141795460> All passengers are requested to review the flight itinerary in `#itinerary` prior to departure to ensure a smooth and professional operation.'
                ),
                "scheduled_start_time": start.isoformat(),
                "scheduled_end_time": end.isoformat(),
                "privacy_level": 2,
                "entity_type": 3,
                "entity_metadata": {"location": roblox_link}
            }

            token = self.bot.http.token
            headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

            async with aiohttp.ClientSession() as sess:
                r = await sess.post(
                    f"https://discord.com/api/v10/guilds/{GUILD_ID}/scheduled-events",
                    json=payload,
                    headers=headers
                )
                if r.status == 201:
                    await ctx.send(embed=flightsuccessembed("✅ Flight created successfully!"))
                    log = self.bot.get_channel(LOGGING_CHANNEL_ID)
                    if log:
                        await log.send(embed=discord.Embed(
                            title="Logging",
                            color=0xE5E1DE
                        ).add_field(name="Create Flight", value=f"{ctx.author} created flight {_
