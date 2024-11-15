import random
import discord
from discord import app_commands
from discord.ext import commands


class Card:
    def __init__(self, suit, value):
        self.suit = suit
        self.value = value

    def __str__(self):
        suits = {'hearts': '♥', 'diamonds': '♦', 'clubs': '♣', 'spades': '♠'}
        values = {
            1: 'A', 11: 'J', 12: 'Q', 13: 'K',
            **{i: str(i) for i in range(2, 11)}
        }
        return f"{suits[self.suit]}{values[self.value]}"


class Deck:
    def __init__(self):
        self.cards = []
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        for suit in suits:
            for value in range(1, 14):
                self.cards.append(Card(suit, value))
        random.shuffle(self.cards)

    def draw(self):
        return self.cards.pop()


class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}  # 진행 중인 게임 저장

    async def ensure_user(self, user_id):
        self.bot.cursor.execute("SELECT * FROM users WHERE uuid = %s", (user_id,))
        user_data = self.bot.cursor.fetchone()
        if not user_data:
            self.bot.cursor.execute("INSERT INTO users (uuid) VALUES (%s)", (user_id,))
            self.bot.conn.commit()

    def calculate_hand(self, hand):
        total = 0
        aces = 0

        for card in hand:
            if card.value == 1:  # Ace
                aces += 1
            elif card.value > 10:  # Face cards
                total += 10
            else:
                total += card.value

        # Ace 처리
        for _ in range(aces):
            if total + 11 <= 21:
                total += 11
            else:
                total += 1

        return total

    def is_blackjack(self, hand):
        # 카드가 정확히 2장이고, 합이 21인 경우만 블랙잭으로 인정
        if len(hand) != 2:
            return False

        # Ace와 10점 카드(10,J,Q,K)가 있는지 확인
        has_ace = any(card.value == 1 for card in hand)
        has_ten = any(card.value >= 10 for card in hand)

        return has_ace and has_ten

    @app_commands.command(name="블랙잭", description="블랙잭 게임을 시작합니다.\n승리시 2배, 무승부시 1배, 패배시 0배")
    async def blackjack(self, interaction: discord.Interaction, amount: int):
        settings_cog = self.bot.get_cog('GuildSettings')
        if not settings_cog:
            return

        if not await settings_cog.check_command_permission(interaction):
            await interaction.response.send_message("이 채널에서는 명령어를 사용할 수 없습니다.", ephemeral=True)
            return

        user_id = interaction.user.id

        if user_id in self.games:
            await interaction.response.send_message(
                "이미 진행 중인 게임이 있습니다. 현재 게임을 완료해주세요.",
                ephemeral=True
            )
            return

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

        # 새 게임 시작
        deck = Deck()
        player_hand = [deck.draw(), deck.draw()]
        dealer_hand = [deck.draw(), deck.draw()]

        self.games[user_id] = {
            'deck': deck,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'amount': amount,
            'status': 'playing'
        }

        # 버튼 생성
        view = discord.ui.View()
        hit_button = discord.ui.Button(label="히트", style=discord.ButtonStyle.primary, custom_id="hit")
        stand_button = discord.ui.Button(label="스탠드", style=discord.ButtonStyle.secondary, custom_id="stand")

        async def hit_callback(interaction):
            game = self.games.get(user_id)
            if not game or game['status'] != 'playing':
                return

            # 카드 추가 드로우
            game['player_hand'].append(game['deck'].draw())
            player_total = self.calculate_hand(game['player_hand'])

            if player_total > 21:
                await self.end_game(interaction, user_id, "bust")
            else:
                await self.update_game_message(interaction, user_id)

        async def stand_callback(interaction):
            game = self.games.get(user_id)
            if not game or game['status'] != 'playing':
                return

            # 딜러 플레이
            dealer_total = self.calculate_hand(game['dealer_hand'])
            while dealer_total < 17:
                game['dealer_hand'].append(game['deck'].draw())
                dealer_total = self.calculate_hand(game['dealer_hand'])

            await self.end_game(interaction, user_id, "stand")

        hit_button.callback = hit_callback
        stand_button.callback = stand_callback
        view.add_item(hit_button)
        view.add_item(stand_button)

        # 초기 게임 상태 표시
        player_total = self.calculate_hand(player_hand)
        dealer_cards = f"{dealer_hand[0]} ??"
        player_cards = " ".join(str(card) for card in player_hand)

        await interaction.response.send_message(
            f"딜러의 패: {dealer_cards}\n"
            f"당신의 패: {player_cards} (총합: {player_total})\n"
            f"배팅 금액: {amount}원",
            view=view
        )

    async def update_game_message(self, interaction, user_id):
        game = self.games[user_id]
        player_total = self.calculate_hand(game['player_hand'])
        dealer_cards = f"{game['dealer_hand'][0]} ??"
        player_cards = " ".join(str(card) for card in game['player_hand'])

        await interaction.response.edit_message(
            content=f"딜러의 패: {dealer_cards}\n"
                    f"당신의 패: {player_cards} (총합: {player_total})\n"
                    f"배팅 금액: {game['amount']}원"
        )

    async def end_game(self, interaction, user_id, reason):
        game = self.games[user_id]
        player_hand = game['player_hand']
        dealer_hand = game['dealer_hand']
        player_total = self.calculate_hand(player_hand)
        dealer_total = self.calculate_hand(dealer_hand)
        amount = game['amount']

        # 결과 계산
        if reason == "bust":
            result = "패배"
            winnings = -amount
        else:
            player_blackjack = self.is_blackjack(player_hand)
            dealer_blackjack = self.is_blackjack(dealer_hand)

            if player_blackjack:
                if dealer_blackjack:
                    result = "무승부 (블랙잭)"
                    winnings = 0
                else:
                    result = "블랙잭!"
                    winnings = int(amount * 1.5)  # 원금 포함 2.5배
            elif dealer_blackjack:
                result = "패배 (딜러 블랙잭)"
                winnings = -int(amount * 1.5)
            elif dealer_total > 21:
                result = "승리"
                winnings = amount
            elif player_total > dealer_total:
                result = "승리"
                winnings = amount
            elif player_total < dealer_total:
                result = "패배"
                winnings = -amount
            else:
                result = "무승부"
                winnings = 0

        if winnings > 0:
            self.bot.cursor.execute("SELECT owner_id FROM lands WHERE guild_id = %s", (interaction.guild.id,))
            owner_id = self.bot.cursor.fetchone()
            if owner_id and owner_id[0] and owner_id[0] != user_id:
                # Deduct commission only if the user is NOT the landowner
                landowner_cut = int(winnings * 0.02)
                winnings_after_cut = winnings - landowner_cut

                # Deduct commission from player's winnings
                self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s",
                                        (winnings_after_cut, user_id))
                # Add commission to landowner's balance
                self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s",
                                        (landowner_cut, owner_id[0]))
            else:
                # If the user is the landowner, credit full winnings
                self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s", (winnings, user_id))
        else:
            # Loss or tie; update player's balance directly
            self.bot.cursor.execute("UPDATE users SET money = money + %s WHERE uuid = %s", (winnings, user_id))

        self.bot.conn.commit()

        # 새로운 잔액 조회
        self.bot.cursor.execute("SELECT money FROM users WHERE uuid = %s", (user_id,))
        new_balance = self.bot.cursor.fetchone()[0]

        dealer_cards = " ".join(str(card) for card in dealer_hand)
        player_cards = " ".join(str(card) for card in player_hand)

        # 결과 메시지 전송
        msg = f"게임 종료!\n" \
              f"딜러의 패: {dealer_cards} (총합: {dealer_total})\n" \
              f"당신의 패: {player_cards} (총합: {player_total})\n" \
              f"결과: {result}\n"

        if winnings > 0:
            msg += f"획득: +{winnings}원\n"
        elif winnings < 0:
            msg += f"손실: {winnings}원\n"
        else:
            msg += "금액 변동 없음\n"

        msg += f"현재 잔액: {new_balance}원"

        await interaction.response.edit_message(
            content=msg,
            view=None
        )

        # 게임 정보 삭제
        del self.games[user_id]


async def setup(bot):
    await bot.add_cog(Blackjack(bot))