import datetime
import json
import random

import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from discord.ui import View, Button


class PaginationView(View):
    def __init__(self, bot, total_pages: int, current_page: int):
        super().__init__(timeout=60)  # 60초 후 버튼 비활성화
        self.bot = bot
        self.current_page = current_page
        self.total_pages = total_pages

        # 이전 페이지 버튼
        if current_page > 1:
            prev_button = Button(label="이전", style=discord.ButtonStyle.primary,
                                 custom_id=f"prev_{current_page - 1}")
            prev_button.callback = self.prev_callback
            self.add_item(prev_button)

        # 다음 페이지 버튼
        if current_page < total_pages:
            next_button = Button(label="다음", style=discord.ButtonStyle.primary,
                                 custom_id=f"next_{current_page + 1}")
            next_button.callback = self.next_callback
            self.add_item(next_button)

    async def prev_callback(self, interaction: discord.Interaction):
        # 이전 페이지 데이터 가져오기
        guild_members = interaction.guild.members
        member_ids = [member.id for member in guild_members]

        self.bot.cursor.execute("SELECT uuid, money FROM users WHERE uuid IN %s ORDER BY money DESC",
                                (tuple(member_ids),))
        user_data = self.bot.cursor.fetchall()

        page_size = 10
        total_pages = (len(user_data) + page_size - 1) // page_size

        # 새 페이지의 데이터 표시
        start_index = (self.current_page - 2) * page_size
        end_index = start_index + page_size
        user_data_page = user_data[start_index:end_index]

        embed = discord.Embed(title=f"이 서버의 잔고 순위 - {self.current_page - 1}/{total_pages} 페이지",
                              color=discord.Color.blue())

        for rank, (user_id, balance) in enumerate(user_data_page, start=start_index + 1):
            user = interaction.guild.get_member(user_id)
            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"{rank}. {username}", value=f"{balance:,}원", inline=False)

        view = PaginationView(self.bot, total_pages, self.current_page - 1)
        await interaction.response.edit_message(embed=embed, view=view)

    async def next_callback(self, interaction: discord.Interaction):
        # 다음 페이지 데이터 가져오기
        guild_members = interaction.guild.members
        member_ids = [member.id for member in guild_members]

        self.bot.cursor.execute("SELECT uuid, money FROM users WHERE uuid IN %s ORDER BY money DESC",
                                (tuple(member_ids),))
        user_data = self.bot.cursor.fetchall()

        page_size = 10
        total_pages = (len(user_data) + page_size - 1) // page_size

        # 새 페이지의 데이터 표시
        start_index = self.current_page * page_size
        end_index = start_index + page_size
        user_data_page = user_data[start_index:end_index]

        embed = discord.Embed(title=f"이 서버의 잔고 순위 - {self.current_page + 1}/{total_pages} 페이지",
                              color=discord.Color.blue())

        for rank, (user_id, balance) in enumerate(user_data_page, start=start_index + 1):
            user = interaction.guild.get_member(user_id)
            username = user.name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"{rank}. {username}", value=f"{balance:,}원", inline=False)

        view = PaginationView(self.bot, total_pages, self.current_page + 1)
        await interaction.response.edit_message(embed=embed, view=view)

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        self.schedule_daily_interest_notification()

    def schedule_daily_interest_notification(self):
        self.scheduler.add_job(self.daily_interest_notification, CronTrigger(hour=0, minute=0))

    async def daily_interest_notification(self):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        for guild in self.bot.guilds:
            channel_id, role_id = await settings_cog.get_notification_settings(guild.id)

            if channel_id:
                channel = guild.get_channel(channel_id)
                role = guild.get_role(role_id) if role_id else None

                if channel:
                    if role:
                        await channel.send(f"{role.mention} 다음 이자를 받을 수 있는 시간이 되었습니다!")
                    else:
                        await channel.send("다음 이자를 받을 수 있는 시간이 되었습니다!")

    async def ensure_user(self, user_id):
        self.bot.cursor.execute("SELECT * FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        if not user_data:
            # 사용자가 없으면 추가
            print(user_id)
            self.bot.cursor.execute("INSERT INTO users (uuid) VALUES (%s)", (user_id,))
            self.bot.conn.commit()

    @app_commands.command(name="잔고", description="사용자의 잔액을 확인합니다.")
    async def get_money(self, interaction: discord.Interaction, member: discord.Member = None):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        if not member:
            member = interaction.user
        user_id = member.id  # Discord 고유 사용자 ID
        await self.ensure_user(user_id)  # 사용자가 없으면 자동으로 추가
        # 사용자 잔액 조회
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        await interaction.response.send_message(f"{member.name}님의 잔액: {user_data[0]:,}원")

    @app_commands.command(name="보상금", description="관리자 전용 명령어입니다.")
    async def increase_money(self, interaction: discord.Interaction, amount: int, receiver: discord.Member = None):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

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
            await interaction.response.send_message(f"{interaction.user.name}님의 잔액이 {amount:,}원만큼 추가되었습니다.")
        else:
            await interaction.response.send_message(f"{receiver.name}님의 잔액이 {amount:,}원만큼 추가되었습니다.")

    @app_commands.command(name="벌금", description="관리자 전용 명령어입니다.")
    async def decrease_money(self, interaction: discord.Interaction, amount: int, receiver: discord.Member = None):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

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
            await interaction.response.send_message(f"{interaction.user.name}님의 잔액이 {amount:,}원만큼 감소되었습니다.")
        else:
            await interaction.response.send_message(f"{receiver.name}님의 잔액이 {amount:,}원만큼 감소되었습니다.")

    @app_commands.command(name="송금", description="다른 사용자에게 돈을 송금합니다.")
    async def send_money(self, interaction: discord.Interaction, receiver: discord.Member, amount: int):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

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
            f"{interaction.user.name}님이 {receiver.name}님에게 {amount:,}원을 송금했습니다.")

    @app_commands.command(name="꽁돈", description="1시간마다 꽁돈을 지급합니다.")
    async def hourly_reward(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

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
                f"{reward_amount}원을 주웠다!\n잔액: {new_balance:,}원")
        else:
            # Calculate the remaining time until the next reward
            remaining_time = 3600 - (current_time - last_hourly).total_seconds()
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            await interaction.response.send_message(
                f"{minutes}분 {seconds}초 후에 꽁돈을 받을 수 있습니다.")

    @app_commands.command(name="이자", description="은행 이자를 받습니다.")
    async def interest(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

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
                f"오늘 {int(current_balance * 0.075):,}원의 이자를 받으셨습니다.\n현재 잔액: {new_balance:,}원")
        else:
            now = datetime.datetime.now()
            next_midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining_time = next_midnight - now

            hours = remaining_time.seconds // 3600
            minutes = (remaining_time.seconds % 3600) // 60
            seconds = remaining_time.seconds % 60

            await interaction.response.send_message(f"다음 이자까지 {hours}시간 {minutes}분 {seconds}초 남았습니다.")

    async def show_balance_rank(self, interaction: discord.Interaction, page: int = 1):
        # 명령어를 호출한 서버의 멤버 목록 가져오기
        guild_members = interaction.guild.members

        # 데이터베이스에서 서버 멤버들의 정보 가져오기
        member_ids = [member.id for member in guild_members]
        self.bot.cursor.execute("SELECT uuid, money FROM users WHERE uuid IN %s ORDER BY money DESC",
                              (tuple(member_ids),))
        user_data = self.bot.cursor.fetchall()

        # 총 페이지 수 계산
        page_size = 10
        total_pages = (len(user_data) + page_size - 1) // page_size

        # 현재 페이지의 데이터 가져오기
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        user_data_page = user_data[start_index:end_index]

        # 임베드 메시지 생성
        embed = discord.Embed(title=f"이 서버의 잔고 순위 - {page}/{total_pages} 페이지", color=discord.Color.blue())

        for rank, (user_id, balance) in enumerate(user_data_page, start=start_index + 1):
            user = interaction.guild.get_member(user_id)
            if user:
                username = user.name
            else:
                username = f"Unknown User ({user_id})"
            embed.add_field(name=f"{rank}. {username}", value=f"{balance:,}원", inline=False)

        # 버튼이 있는 뷰 생성
        view = PaginationView(self.bot, total_pages, page)

        # 첫 메시지인지 또는 버튼을 통한 업데이트인지 확인
        if interaction.response.is_done():
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="순위", description="이 서버의 사용자들의 잔고 순위를 보여줍니다.")
    async def balance_rank_command(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        await self.show_balance_rank(interaction)


async def setup(bot):
    await bot.add_cog(Bank(bot))