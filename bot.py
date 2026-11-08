import asyncio, os, time, aiohttp
from aiohttp import web
import discord
from discord.ext import commands

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
STAFF_ROLE_IDS = [1567026563369664590]
PROMO_CHANNEL_ID = 1568991830245253263
START_TIME = time.time()

# -------------------- 1. 24/7 KEEP-ALIVE SERVER --------------------
async def handle_ping(req):
    return web.Response(text=f"Promotion Bot 24/7 | Uptime: {int((time.time() - START_TIME)//60)}m")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000))).start()

async def self_ping_loop():
    await asyncio.sleep(20)
    url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/"
    async with aiohttp.ClientSession() as s:
        while True:
            try:
                async with s.get(url, timeout=10): pass
            except Exception: pass
            await asyncio.sleep(240)

def is_staff(m: discord.Member) -> bool:
    return m.guild_permissions.administrator or m.guild_permissions.manage_roles or any(r.id in STAFF_ROLE_IDS for r in m.roles)

# -------------------- 2. BOT & PROMOTION / DEMOTION COMMANDS --------------------
class PromotionBot(commands.Bot):
    def __init__(self, msg_intent: bool = True):
        intents = discord.Intents.default()
        intents.message_content = msg_intent
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

def reg_cmds(b: PromotionBot):
    async def post_rank_update(interaction: discord.Interaction, officer: discord.Member, new_rank: discord.Role, reason: str, old_rank: discord.Role, is_promo: bool):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ High Command / Staff only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        # Update Discord Roles
        try:
            if old_rank and old_rank in officer.roles:
                await officer.remove_roles(old_rank)
            await officer.add_roles(new_rank, reason=f"{'Promoted' if is_promo else 'Demoted'} by {interaction.user}: {reason}")
        except Exception:
            pass

        emb = discord.Embed(
            title="🎖️ OFFICIAL OFFICER PROMOTION" if is_promo else "📉 OFFICIAL OFFICER DEMOTION",
            description=(
                f"👤 **Officer:** {officer.mention} (`{officer.id}`)\n"
                + (f"📋 **Previous Rank:** {old_rank.mention}\n" if old_rank else "")
                + f"{'📈' if is_promo else '📉'} **New Rank:** {new_rank.mention}\n"
                f"📝 **Reason / Notes:** {reason}\n"
                f"✍️ **Authorized By:** {interaction.user.mention}"
            ),
            color=discord.Color.green() if is_promo else discord.Color.red(),
        )
        emb.set_thumbnail(url=officer.display_avatar.url)

        # Send to Promotion Channel (1568991830245253263)
        target_ch = interaction.guild.get_channel(PROMO_CHANNEL_ID) or interaction.channel
        await target_ch.send(content=officer.mention, embed=emb)

        try:
            await officer.send(
                f"{'🎉 **CONGRATULATIONS!** You were **PROMOTED**' if is_promo else '⚠️ Your rank was updated'} to **{new_rank.name}** in **{interaction.guild.name}**!\n> **Reason:** {reason}"
            )
        except Exception:
            pass

        await interaction.followup.send(f"✅ Logged {'promotion' if is_promo else 'demotion'} for {officer.mention} in {target_ch.mention}!", ephemeral=True)

    @b.tree.command(name="promote", description="Promote an officer and post in the promotions channel")
    async def s_promote(interaction: discord.Interaction, officer: discord.Member, new_rank: discord.Role, reason: str, old_rank: discord.Role = None):
        await post_rank_update(interaction, officer, new_rank, reason, old_rank, True)

    @b.tree.command(name="demote", description="Demote an officer and post in the promotions channel")
    async def s_demote(interaction: discord.Interaction, officer: discord.Member, new_rank: discord.Role, reason: str, old_rank: discord.Role = None):
        await post_rank_update(interaction, officer, new_rank, reason, old_rank, False)

async def main():
    await run_web_server()
    asyncio.create_task(self_ping_loop())
    if not BOT_TOKEN:
        while True: await asyncio.sleep(3600)
    bot = PromotionBot(True)
    reg_cmds(bot)
    try:
        await bot.start(BOT_TOKEN)
    except discord.PrivilegedIntentsRequired:
        await bot.close()
        bot = PromotionBot(False)
        reg_cmds(bot)
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
  
