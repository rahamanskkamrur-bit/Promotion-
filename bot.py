import asyncio
import os
import time
import aiohttp
from aiohttp import web
import discord
from discord.ext import commands

# =====================================================================
# 1. CONFIGURATION & RANK PREFIX TABLE
# =====================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
STAFF_ROLE_IDS = [1567026563369664590]
PROMO_CHANNEL_ID = 1568991830245253263
START_TIME = time.time()

# Ordered from most specific to general so "Deputy Inspector" matches D/INS before "Inspector" (INS)
RANK_PREFIX_RULES = [
    ("chief of police", "CH"),
    ("assistant chief", "AC"),
    ("deputy chief", "DC"),
    ("chief superintendent", "C/SUPT"),
    ("superintendent", "SUPT"),
    ("deputy inspector", "D/INS"),
    ("inspector", "INS"),
    ("commander", "CMD"),
    ("captain", "CPT"),
    ("lieutenant", "LT"),
    ("sergeant", "SGT"),
    ("corporal", "CPL"),
    ("senior officer", "S/OFC"),
    ("police officer", "OFC"),
    ("officer", "OFC"),
    ("cadet", "CDT"),
    ("recruit", "RCT"),
    ("chief", "CH"),
]


def get_rank_prefix(role_name: str) -> str:
    """Matches a Discord role name to its short rank prefix (e.g. 'Chief Superintendent' -> 'C/SUPT')."""
    low = role_name.lower().strip()
    for keyword, prefix in RANK_PREFIX_RULES:
        if keyword in low:
            return prefix

    # Fallback if a custom role name is used: take initials or first 4 letters
    words = [w for w in role_name.upper().split() if w.isalpha()]
    if len(words) >= 2:
        return "/".join(w[0] for w in words[:2])
    return role_name.upper()[:4].strip()


def extract_roblox_username(member: discord.Member, roblox_username: str = None) -> str:
    """
    Uses the provided Roblox username, or automatically extracts it from their
    existing 'RANK | RobloxUser' nickname so you don't even have to re-type it!
    """
    if roblox_username and roblox_username.strip():
        return roblox_username.strip()

    current_name = member.nick or member.display_name or member.name
    if "|" in current_name:
        return current_name.split("|", 1)[1].strip()
    return current_name.strip()


def build_rank_nickname(role_name: str, member: discord.Member, roblox_username: str = None) -> str:
    prefix = get_rank_prefix(role_name)
    rblx_user = extract_roblox_username(member, roblox_username)
    # Discord nicknames have a strict 32-character limit
    return f"{prefix} | {rblx_user}"[:32]


# =====================================================================
# 2. 24/7 KEEP-ALIVE WEB SERVER & AUTO-PINGER
# =====================================================================
async def handle_ping(req):
    return web.Response(text=f"Promotion Bot 24/7 | Uptime: {int((time.time() - START_TIME) // 60)}m")


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
                async with s.get(url, timeout=10):
                    pass
            except Exception:
                pass
            await asyncio.sleep(240)


def is_staff(m: discord.Member) -> bool:
    return (
        m.guild_permissions.administrator
        or m.guild_permissions.manage_roles
        or any(r.id in STAFF_ROLE_IDS for r in m.roles)
    )


# =====================================================================
# 3. BOT & PROMOTION / DEMOTION COMMANDS
# =====================================================================
class PromotionBot(commands.Bot):
    def __init__(self, msg_intent: bool = True):
        intents = discord.Intents.default()
        intents.message_content = msg_intent
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        print(f"✅ Promotion Bot ONLINE as {self.user}")


def reg_cmds(b: PromotionBot):
    async def post_rank_update(
        interaction: discord.Interaction,
        officer: discord.Member,
        new_rank: discord.Role,
        reason: str,
        roblox_username: str,
        old_rank: discord.Role,
        is_promo: bool,
    ):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ High Command / Staff only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        # 1. Update Discord Roles
        try:
            if old_rank and old_rank in officer.roles:
                await officer.remove_roles(old_rank)
            await officer.add_roles(
                new_rank,
                reason=f"{'Promoted' if is_promo else 'Demoted'} by {interaction.user}: {reason}",
            )
        except Exception:
            pass

        # 2. Format & Apply New Nickname: e.g. "SUPT | RobloxUser" or "D/INS | RobloxUser"
        new_nickname = build_rank_nickname(new_rank.name, officer, roblox_username)
        nick_status = f"`{new_nickname}` ✅"
        try:
            await officer.edit(nick=new_nickname, reason=f"Rank updated to {new_rank.name}")
        except discord.Forbidden:
            nick_status = f"`{new_nickname}` *(Bot role must be above {officer.display_name} to auto-rename)*"
        except Exception:
            nick_status = f"`{new_nickname}`"

        # 3. Build Promotion / Demotion Embed
        emb = discord.Embed(
            title="🎖️ OFFICIAL OFFICER PROMOTION" if is_promo else "📉 OFFICIAL OFFICER DEMOTION",
            description=(
                f"👤 **Officer:** {officer.mention} (`{officer.id}`)\n"
                + (f"📋 **Previous Rank:** {old_rank.mention}\n" if old_rank else "")
                + f"{'📈' if is_promo else '📉'} **New Rank:** {new_rank.mention}\n"
                f"🏷️ **Updated Nickname:** {nick_status}\n"
                f"📝 **Reason / Notes:** {reason}\n"
                f"✍️ **Authorized By:** {interaction.user.mention}"
            ),
            color=discord.Color.green() if is_promo else discord.Color.red(),
        )
        emb.set_thumbnail(url=officer.display_avatar.url)

        # 4. Post to Promotion Channel (1568991830245253263)
        target_ch = interaction.guild.get_channel(PROMO_CHANNEL_ID) or interaction.channel
        await target_ch.send(content=officer.mention, embed=emb)

        # 5. DM the Officer
        try:
            await officer.send(
                f"{'🎉 **CONGRATULATIONS!** You were **PROMOTED**' if is_promo else '⚠️ Your rank was updated'} "
                f"to **{new_rank.name}** (`{new_nickname}`) in **{interaction.guild.name}**!\n"
                f"> **Reason:** {reason}"
            )
        except Exception:
            pass

        await interaction.followup.send(
            f"✅ Logged {'promotion' if is_promo else 'demotion'} for {officer.mention} -> **`{new_nickname}`** in {target_ch.mention}!",
            ephemeral=True,
        )

    @b.tree.command(name="promote", description="Promote an officer, update their rank role & set their RANK | RobloxUser nickname")
    @discord.app_commands.describe(
        officer="The officer being promoted",
        new_rank="Their new rank role (e.g. Inspector, Superintendent, Deputy Chief)",
        reason="Reason for the promotion",
        roblox_username="Their Roblox username (optional if already in their nickname)",
        old_rank="Optional: Previous rank role to remove",
    )
    async def s_promote(
        interaction: discord.Interaction,
        officer: discord.Member,
        new_rank: discord.Role,
        reason: str,
        roblox_username: str = None,
        old_rank: discord.Role = None,
    ):
        await post_rank_update(interaction, officer, new_rank, reason, roblox_username, old_rank, True)

    @b.tree.command(name="demote", description="Demote an officer, update their rank role & set their RANK | RobloxUser nickname")
    @discord.app_commands.describe(
        officer="The officer being demoted",
        new_rank="Their new rank role",
        reason="Reason for the demotion",
        roblox_username="Their Roblox username (optional if already in their nickname)",
        old_rank="Optional: Previous rank role to remove",
    )
    async def s_demote(
        interaction: discord.Interaction,
        officer: discord.Member,
        new_rank: discord.Role,
        reason: str,
        roblox_username: str = None,
        old_rank: discord.Role = None,
    ):
        await post_rank_update(interaction, officer, new_rank, reason, roblox_username, old_rank, False)


async def main():
    await run_web_server()
    asyncio.create_task(self_ping_loop())
    if not BOT_TOKEN:
        while True:
            await asyncio.sleep(3600)
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
    
