import discord
from discord import app_commands
from discord.ext import commands

class GuildSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def setup_guild_settings_table(self):
        await self.bot.conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                notification_channel_id BIGINT,
                notification_role_id BIGINT,
                UNIQUE(guild_id)
            )
        """)

    @app_commands.command(name="알림설정", description="알림을 보낼 채널과 역할을 설정합니다.")
    async def set_notification(self, interaction: discord.Interaction, role: discord.Role = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        self.bot.cursor.execute("""
            INSERT INTO guild_settings 
                (guild_id, notification_channel_id, notification_role_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (guild_id) 
            DO UPDATE SET 
                notification_channel_id = EXCLUDED.notification_channel_id,
                notification_role_id = EXCLUDED.notification_role_id
        """, (interaction.guild.id, interaction.channel.id, role.id if role else None))
        self.bot.conn.commit()

        if role:
            await interaction.response.send_message(
                f"알림이 {interaction.channel.mention} 채널과 {role.mention} 역할로 설정되었습니다.")
        else:
            await interaction.response.send_message(
                f"알림이 {interaction.channel.mention} 채널로 설정되었습니다.")

    @app_commands.command(name="설정확인", description="현재 서버의 설정을 확인합니다.")
    async def check_settings(self, interaction: discord.Interaction):
        self.bot.cursor.execute("""
            SELECT notification_channel_id, notification_role_id
            FROM guild_settings
            WHERE guild_id = %s
        """, (interaction.guild.id,))

        settings = self.bot.cursor.fetchone()

        if not settings:
            await interaction.response.send_message("이 서버의 설정이 없습니다.")
            return

        notification_channel = interaction.guild.get_channel(settings[0])
        notification_role = interaction.guild.get_role(settings[1]) if settings[1] else None

        embed = discord.Embed(title="서버 설정", color=discord.Color.blue())
        embed.add_field(
            name="알림 채널",
            value=notification_channel.mention if notification_channel else "설정되지 않음",
            inline=False
        )
        embed.add_field(
            name="알림 역할",
            value=notification_role.mention if notification_role else "설정되지 않음",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    # Bank 클래스에서 사용할 메서드들
    async def check_command_permission(self, interaction: discord.Interaction) -> bool:
        # 일단 모두 허용
        return True

    async def get_notification_settings(self, guild_id: int) -> tuple:
        """알림 설정 가져오기"""
        self.bot.cursor.execute("""
            SELECT notification_channel_id, notification_role_id 
            FROM guild_settings 
            WHERE guild_id = %s
        """, (guild_id,))

        result = self.bot.cursor.fetchone()
        if result:
            return result[0], result[1]
        return None, None


async def setup(bot):
    await bot.add_cog(GuildSettings(bot))