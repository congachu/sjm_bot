import datetime
import json
import random

import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        self.schedule_daily_interest_notification()

    def load_notification_settings(self):
        # 파일에서 알림 설정을 불러오기
        try:
            with open("notification_settings.json", "r") as file:
                data = json.load(file)
                self.guild_id = data.get("guild_id")
                self.channel_id = data.get("channel_id")
                self.role_id = data.get("role_id")
        except FileNotFoundError:
            # 파일이 없으면 설정 초기화
            self.guild_id = None
            self.channel_id = None
            self.role_id = None

    def save_notification_settings(self):
        # 알림 설정을 파일에 저장
        with open("notification_settings.json", "w") as file:
            json.dump({
                "guild_id": self.guild_id,
                "channel_id": self.channel_id,
                "role_id": self.role_id
            }, file)

    def schedule_daily_interest_notification(self):
        self.scheduler.add_job(self.daily_interest_notification, CronTrigger(hour=0, minute=0))

    async def daily_interest_notification(self):
        # 설정된 서버와 채널에 알림 전송
        if self.guild_id and self.channel_id and self.role_id:
            guild = self.bot.get_guild(self.guild_id)
            if guild:
                channel = guild.get_channel(self.channel_id)
                role = guild.get_role(self.role_id)

                if channel:
                    if role:
                        await channel.send(f"{role.mention} 다음 이자를 받을 수 있는 시간이 되었습니다!")
                    else:
                        await channel.send("다음 이자를 받을 수 있는 시간이 되었습니다!")
                else:
                    print("채널 또는 역할을 찾을 수 없습니다.")
            else:
                print("서버를 찾을 수 없습니다.")
        else:
            print("알림 설정이 되어 있지 않습니다.")

    @app_commands.command(name="알림설정", description="알림을 보낼 채널과 역할을 설정합니다.")
    async def set_notification(self, interaction: discord.Interaction, role: discord.Role = None):
        # 어드민 권한 확인
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        # 현재 채널과 역할을 설정하고 저장
        self.guild_id = interaction.guild.id
        self.channel_id = interaction.channel.id
        self.role_id = role.id if role else None
        self.save_notification_settings()

        if role:
            await interaction.response.send_message(
                f"알림이 {interaction.channel.mention} 채널과 {role.mention} 역할로 설정되었습니다.")
        else:
            await interaction.response.send_message(f"알림이 {interaction.channel.mention} 채널로 설정되었습니다.")

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

    @app_commands.command(name="꽁돈", description="1시간마다 꽁돈을 지급합니다.")
    async def hourly_reward(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        await self.ensure_user(user_id)

        self.bot.cursor.execute("SELECT money, last_hourly FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        last_hourly = user_data[1]
        current_time = datetime.datetime.now()

        if not last_hourly or (current_time - last_hourly).total_seconds() >= 3600:
            reward_amount = random.randint(1000, 5000)
            new_balance = user_data[0] + reward_amount

            # Update the user's balance and last hourly reward time in the database
            self.bot.cursor.execute("UPDATE users SET money = %s, last_hourly = %s WHERE uuid = %s",
                                    (new_balance, current_time, user_id))
            self.bot.conn.commit()

            await interaction.response.send_message(
                f"{reward_amount}원을 주웠다!\n잔액: {new_balance}원")
        else:
            # Calculate the remaining time until the next reward
            remaining_time = 3600 - (current_time - last_hourly).total_seconds()
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            await interaction.response.send_message(
                f"{minutes}분 {seconds}초 후에 꽁돈을 받을 수 있습니다.")

    @app_commands.command(name="이자", description="은행 이자를 받습니다.")
    async def interest(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        self.bot.cursor.execute("SELECT money, last_interest FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        current_balance = user_data[0]
        last_interest = user_data[1]

        if current_balance < 10000:
            await interaction.response.send_message("이자는 잔고 10000원부터 받을 수 있습니다.")
            return

        # 마지막 이자 지급 시간 확인
        if last_interest is None or last_interest.date() != datetime.datetime.now().date():
            # 오늘 처음 이자를 지급하는 경우
            new_balance = int(current_balance + current_balance * 0.075)
            self.bot.cursor.execute("UPDATE users SET money = %s, last_interest = %s WHERE uuid = %s",
                                    (new_balance, datetime.datetime.now(), user_id))
            self.bot.conn.commit()

            await interaction.response.send_message(
                f"오늘 {int(current_balance * 0.075)}원의 이자를 받으셨습니다.\n현재 잔액: {new_balance}원")
        else:
            now = datetime.datetime.now()
            next_midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining_time = next_midnight - now

            hours = remaining_time.seconds // 3600
            minutes = (remaining_time.seconds % 3600) // 60
            seconds = remaining_time.seconds % 60

            await interaction.response.send_message(f"다음 이자까지 {hours}시간 {minutes}분 {seconds}초 남았습니다.")


async def setup(bot):
    await bot.add_cog(Bank(bot))