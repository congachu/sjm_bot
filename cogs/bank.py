import discord
from discord import app_commands
from discord.ext import commands

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_user(self, user_id):
        self.bot.cursor.execute("SELECT * FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        if not user_data:
            # 사용자가 없으면 추가
            print(user_id)
            self.bot.cursor.execute("INSERT INTO users (uuid) VALUES (%s)", (user_id,))
            self.bot.conn.commit()

    @app_commands.command(name="잔고", description="사용자의 잔액을 확인합니다.")
    async def get_money(self, interaction: discord.Interaction):
        user_id = interaction.user.id  # Discord 고유 사용자 ID
        await self.ensure_user(user_id)  # 사용자가 없으면 자동으로 추가
        # 사용자 잔액 조회
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        await interaction.response.send_message(f"{interaction.user.name}님의 잔액: {user_data[0]}원")

    @app_commands.command(name="보상금", description="관리자 전용 명령어입니다.")
    async def increase_money(self, interaction: discord.Interaction, amount: int, receiver: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

            # receiver가 지정되지 않았으면 명령어 사용자를 receiver로 설정
        if receiver is None:
            receiver = interaction.user

        receiver_id = receiver.id
        await self.ensure_user(receiver_id)

        # 잔액 업데이트
        self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid= %s", (amount, receiver_id))
        self.bot.conn.commit()

        # 메시지 출력 (receiver가 본인인지 다른 사용자인지에 따라 다른 메시지)
        if receiver_id == interaction.user.id:
            await interaction.response.send_message(f"{interaction.user.name}님의 잔액이 {amount}원만큼 추가되었습니다.")
        else:
            await interaction.response.send_message(f"{receiver.name}님의 잔액이 {amount}원만큼 추가되었습니다.")

    @app_commands.command(name="벌금", description="관리자 전용 명령어입니다.")
    async def decrease_money(self, interaction: discord.Interaction, amount: int, receiver: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

            # receiver가 지정되지 않았으면 명령어 사용자를 receiver로 설정
        if receiver is None:
            receiver = interaction.user

        receiver_id = receiver.id
        await self.ensure_user(receiver_id)

        # 잔액 업데이트
        self.bot.cursor.execute("UPDATE users SET money = money - %s WHERE uuid= %s", (amount, receiver_id))
        self.bot.conn.commit()

        # 메시지 출력 (receiver가 본인인지 다른 사용자인지에 따라 다른 메시지)
        if receiver_id == interaction.user.id:
            await interaction.response.send_message(f"{interaction.user.name}님의 잔액이 {amount}원만큼 감소되었습니다.")
        else:
            await interaction.response.send_message(f"{receiver.name}님의 잔액이 {amount}원만큼 감소되었습니다.")

    @app_commands.command(name="송금", description="다른 사용자에게 돈을 송금합니다.")
    async def send_money(self, interaction: discord.Interaction, receiver: discord.Member, amount: int):
        sender_id = interaction.user.id
        receiver_id = receiver.id

        # 송금하는 사람과 받는 사람의 계정 확인
        await self.ensure_user(sender_id)
        await self.ensure_user(receiver_id)

        # 송금하는 사람의 잔액 확인
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (sender_id,))
        sender_balance = self.bot.cursor.fetchone()[0]

        if sender_balance < amount:
            await interaction.response.send_message("잔액이 부족합니다.")
            return

        # 송금 처리
        self.bot.cursor.execute("UPDATE users SET money = money - %s WHERE uuid = %s", (amount, sender_id))
        self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s", (amount, receiver_id))
        self.bot.conn.commit()

        await interaction.response.send_message(
            f"{interaction.user.name}님이 {receiver.name}님에게 {amount}원을 송금했습니다.")


async def setup(bot):
    await bot.add_cog(Bank(bot))