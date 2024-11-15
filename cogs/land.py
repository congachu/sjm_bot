import datetime
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from typing import Optional


class LandView(View):
    def __init__(self, bot, channel_id: int, owner_id: Optional[int], price: int):
        super().__init__(timeout=30)
        self.bot = bot
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.price = price

        button_label = "구매하기" if not owner_id else "인수하기"
        buy_button = Button(label=button_label, style=discord.ButtonStyle.green, custom_id=f"buy_{channel_id}")
        buy_button.callback = self.buy_callback
        self.add_item(buy_button)

        close_button = Button(label="닫기", style=discord.ButtonStyle.red, custom_id=f"close_{channel_id}")
        close_button.callback = self.close_callback
        self.add_item(close_button)

    async def ensure_user(self, user_id):
        self.bot.cursor.execute("SELECT 1 FROM users WHERE uuid = %s", (user_id,))
        if not self.bot.cursor.fetchone():
            print(f"Inserting user {user_id} into users table.")
            self.bot.cursor.execute("INSERT INTO users (uuid) VALUES (%s)", (user_id,))
            self.bot.conn.commit()

    async def buy_callback(self, interaction: discord.Interaction):
        buyer_id = interaction.user.id
        await self.ensure_user(buyer_id)

        self.bot.cursor.execute("SELECT owner_id FROM lands WHERE channel_id = %s", (self.channel_id,))
        owner_data = self.bot.cursor.fetchone()

        if owner_data is not None:
            self.owner_id = owner_data[0]

        print(self.owner_id, buyer_id)
        # 자기 자신의 땅은 살 수 없음
        if self.owner_id == buyer_id:
            await interaction.response.send_message("자신의 땅은 구매할 수 없습니다.", ephemeral=True)
            return

        # 구매자의 잔액 확인
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (buyer_id,))
        buyer_balance = self.bot.cursor.fetchone()[0]  # 위에서 ensure_user를 했으므로 항상 존재함
        purchase_price = self.price if not self.owner_id else int(self.price * 1.2)

        if buyer_balance < purchase_price:
            await interaction.response.send_message(f"잔액이 부족합니다. 필요한 금액: {purchase_price:,}원", ephemeral=True)
            return

        # 트랜잭션 시작
        try:
            current_time = datetime.datetime.now()

            # 구매자의 잔액 감소
            self.bot.cursor.execute("UPDATE users SET money = money - %s WHERE uuid = %s", (purchase_price, buyer_id))

            if self.owner_id:  # 이전 소유자가 있는 경우
                await self.ensure_user(self.owner_id)
                # 이전 소유자에게 돈 지급
                self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s",
                                        (purchase_price, self.owner_id))

            print(f"guild_id: {interaction.guild_id}, channel_id: {self.channel_id}, buyer_id: {buyer_id}, purchase_price: {purchase_price}")
            # 땅 소유권 이전 및 가격 업데이트
            self.bot.cursor.execute("""
                SELECT id FROM lands WHERE guild_id = %s AND channel_id = %s
            """, (interaction.guild_id, self.channel_id))

            land = self.bot.cursor.fetchone()

            if land:
                self.bot.cursor.execute("""
                    UPDATE lands
                    SET owner_id = %s, current_price = %s, last_transaction_date = %s
                    WHERE guild_id = %s AND channel_id = %s
                """, (buyer_id, purchase_price, current_time, interaction.guild_id, self.channel_id))
            else:
                self.bot.cursor.execute("""
                    INSERT INTO lands (guild_id, channel_id, owner_id, current_price, purchase_date)
                    VALUES (%s, %s, %s, %s, %s)
                """, (interaction.guild_id, self.channel_id, buyer_id, purchase_price, current_time))

            self.bot.cursor.execute("""
                SELECT owner_id, current_price
                FROM lands 
                WHERE guild_id = %s AND channel_id = %s
            """, (interaction.guild_id, self.channel_id))
            updated_data = self.bot.cursor.fetchone()
            print(f"Updated data: {updated_data}")

            # 땅 ID 조회
            self.bot.cursor.execute("""
                SELECT id FROM lands 
                WHERE guild_id = %s AND channel_id = %s
            """, (interaction.guild_id, self.channel_id))
            land_id = self.bot.cursor.fetchone()[0]

            # 거래 기록 추가 - 소유자가 있는 경우와 없는 경우를 구분
            if self.owner_id:  # 인수의 경우
                self.bot.cursor.execute("""
                    INSERT INTO land_transactions 
                    (land_id, seller_id, buyer_id, transaction_price, transaction_type)
                    VALUES (%s, %s, %s, %s, %s)
                """, (land_id, self.owner_id, buyer_id, purchase_price, 'TRANSFER'))
            else:  # 첫 구매의 경우
                self.bot.cursor.execute("""
                    INSERT INTO land_transactions 
                    (land_id, buyer_id, transaction_price, transaction_type)
                    VALUES (%s, %s, %s, %s)
                """, (land_id, buyer_id, purchase_price, 'PURCHASE'))

            self.bot.conn.commit()

            # 성공 메시지
            channel = interaction.guild.get_channel(self.channel_id)
            seller = interaction.guild.get_member(self.owner_id) if self.owner_id else None

            if self.owner_id and seller:
                seller = interaction.guild.get_member(self.owner_id)
                await interaction.response.send_message(
                    f"🏆 {interaction.user.mention}님이 {seller.mention}님의 땅 {channel.mention}을(를) "
                    f"{purchase_price:,}원에 인수했습니다!")
            elif self.owner_id and not seller:
                await interaction.response.send_message(
                    f"🏆 {interaction.user.mention}님이 {channel.mention}을(를) {purchase_price:,}원에 인수했습니다!")
            else:
                await interaction.response.send_message(
                    f"🎉 {interaction.user.mention}님이 {channel.mention}을(를) {purchase_price:,}원에 구매했습니다!")

        except Exception as e:
            self.bot.conn.rollback()
            await interaction.response.send_message("거래 처리 중 오류가 발생했습니다.", ephemeral=True)
            raise e

    async def close_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="메시지가 닫혔습니다.", embed=None, view=None)


class Land(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _convert_to_datetime(self, timestamp) -> Optional[datetime.datetime]:
        """Convert timestamp to datetime object safely"""
        if isinstance(timestamp, (int, float)):
            return datetime.datetime.fromtimestamp(timestamp)
        return timestamp

    @app_commands.command(name="땅정보", description="채널의 소유권 정보를 확인합니다.")
    async def land_info(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        target_channel = channel or interaction.channel

        self.bot.cursor.execute("""
            SELECT l.*, u.money 
            FROM lands l
            LEFT JOIN users u ON l.owner_id = u.uuid
            WHERE l.guild_id = %s AND l.channel_id = %s
        """, (interaction.guild_id, target_channel.id))

        land_data = self.bot.cursor.fetchone()

        if not land_data:
            embed = discord.Embed(
                title=f"🏞️ {target_channel.name} 땅 정보",
                description="아직 주인이 없는 땅입니다.",
                color=discord.Color.green()
            )
            embed.add_field(name="기본 가격", value=f"1,000,000원", inline=False)

            view = LandView(self.bot, target_channel.id, None, 1000000)
            await interaction.response.send_message(embed=embed, view=view)
            return

        owner = interaction.guild.get_member(land_data[3])
        embed = discord.Embed(
            title=f"🏞️ {target_channel.name} 땅 정보",
            description=f"소유자: {owner.mention if owner else '알 수 없음'}",
            color=discord.Color.blue()
        )

        embed.add_field(name="현재 가격", value=f"{land_data[5]:,}원", inline=True)
        embed.add_field(name="인수 가격", value=f"{int(land_data[5] * 1.2):,}원", inline=True)

        purchase_date = self._convert_to_datetime(land_data[5])
        if purchase_date:
            embed.add_field(name="구매일", value=purchase_date.strftime("%Y-%m-%d %H:%M"), inline=False)

        last_transaction_date = self._convert_to_datetime(land_data[6])
        if last_transaction_date:
            embed.add_field(name="마지막 거래일", value=last_transaction_date.strftime("%Y-%m-%d %H:%M"), inline=False)

        view = LandView(self.bot, target_channel.id, land_data[2], land_data[4])
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="내땅", description="자신이 소유한 땅 목록을 확인합니다.")
    async def my_lands(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        self.bot.cursor.execute("""
            SELECT channel_id, current_price, purchase_date
            FROM lands
            WHERE guild_id = %s AND owner_id = %s
            ORDER BY purchase_date DESC
        """, (interaction.guild_id, interaction.user.id))

        lands = self.bot.cursor.fetchall()

        if not lands:
            await interaction.response.send_message("소유한 땅이 없습니다.")
            return

        embed = discord.Embed(
            title=f"🗺️ {interaction.user.name}님의 소유 땅 목록",
            description=f"총 {len(lands)}개의 땅을 소유중입니다.",
            color=discord.Color.blue()
        )

        total_value = 0
        for channel_id, price, purchase_date in lands:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                total_value += price
                purchase_date = self._convert_to_datetime(purchase_date)
                date_str = purchase_date.strftime('%Y-%m-%d') if purchase_date else '날짜 정보 없음'
                embed.add_field(
                    name=channel.name,
                    value=f"가격: {price:,}원\n구매일: {date_str}",
                    inline=False
                )

        embed.add_field(name="총 자산가치", value=f"{total_value:,}원", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="땅순위", description="서버 내 땅 보유 순위를 확인합니다.")
    async def land_ranking(self, interaction: discord.Interaction):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        self.bot.cursor.execute("""
            SELECT owner_id, COUNT(*) as land_count, SUM(current_price) as total_value
            FROM lands
            WHERE guild_id = %s AND owner_id IS NOT NULL
            GROUP BY owner_id
            ORDER BY total_value DESC
            LIMIT 10
        """, (interaction.guild_id,))

        rankings = self.bot.cursor.fetchall()

        if not rankings:
            await interaction.response.send_message("아직 땅을 소유한 사용자가 없습니다.")
            return

        embed = discord.Embed(
            title="🏆 땅 보유 순위",
            description="서버 내 땅 자산 순위입니다.",
            color=discord.Color.gold()
        )

        for rank, (owner_id, land_count, total_value) in enumerate(rankings, 1):
            member = interaction.guild.get_member(owner_id)
            if member:
                embed.add_field(
                    name=f"{rank}. {member.name}",
                    value=f"보유 땅: {land_count}개\n총 자산: {total_value:,}원",
                    inline=False
                )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Land(bot))