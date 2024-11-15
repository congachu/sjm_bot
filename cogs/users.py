import discord
from discord import app_commands
from discord.ext import commands

class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="퐁~! 응답 시간을 표시합니다.")
    async def ping(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return
        await interaction.response.send_message(f"퐁~! {self.bot.latency * 1000:.2f}ms")

    @app_commands.command(name="hello", description="봇이 'Hello!'를 출력합니다.")
    async def hello(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return
        await interaction.response.send_message("Hello!", ephemeral=False)

async def setup(bot):
    await bot.add_cog(Users(bot))