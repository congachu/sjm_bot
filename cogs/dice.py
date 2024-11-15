import random

import discord
from discord import app_commands
from discord.ext import commands

class Dice(commands.Cog):
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

    @app_commands.command(name="홀짝", description="주사위 눈금으로 승부가 결정납니다.\n승리시 1.75배, 패배시 0배")
    @app_commands.choices(choice=[
        app_commands.Choice(name="홀", value="odd"),
        app_commands.Choice(name="짝", value="even")
    ])
    async def binary_dice(self, interaction: discord.Interaction, amount: int, choice: str):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        user_id = interaction.user.id
        await self.ensure_user(user_id)

        # 현재 잔액 확인
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (user_id,))
        current_balance = self.bot.cursor.fetchone()[0]

        # 배팅 금액 검증
        if amount <= 0:
            await interaction.response.send_message("0원 이하로는 배팅할 수 없습니다.", ephemeral=True)
            return

        if current_balance < amount:
            await interaction.response.send_message("잔액이 부족합니다.", ephemeral=True)
            return

        # 주사위 굴리기
        dice = random.randint(1, 6)
        is_odd = dice % 2 == 1
        user_chose_odd = choice == "odd"

        # 승패 결정
        if (is_odd and user_chose_odd) or (not is_odd and not user_chose_odd):
            # 승리 (1.75배)
            winnings = int(amount * 0.75)  # 추가 수익만 계산
            self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s",
                                    (winnings, user_id))  # 추가 수익만 더함
            result_msg = f"승리! {winnings:,}원을 얻었습니다."
        else:
            # 패배 (0배 = 전부 손실)
            loss = int(amount)  # 잃을 금액 계산
            self.bot.cursor.execute("UPDATE users SET money = money - %s WHERE uuid = %s",
                                    (loss, user_id))  # 손실금액을 뺌
            result_msg = f"패배... {loss:,}원을 잃었습니다."

        self.bot.conn.commit()

        # 새로운 잔액 조회
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (user_id,))
        new_balance = self.bot.cursor.fetchone()[0]

        # 결과 메시지
        await interaction.response.send_message(
            f"🎲 주사위: {dice}\n"
            f"선택: {'홀' if user_chose_odd else '짝'}\n"
            f"{result_msg}\n"
            f"현재 잔액: {new_balance:,}원"
        )



async def setup(bot):
    await bot.add_cog(Dice(bot))