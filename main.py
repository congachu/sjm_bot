import os
import discord
from discord.ext import commands
import psycopg2
from dotenv import load_dotenv

load_dotenv()

class AClient(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.synced = False
        self.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST")
        )
        self.cursor = self.conn.cursor()

    async def setup_hook(self):
        guild = discord.Object(id=os.getenv("GUILD_ID"))  # 여기에 당신의 서버 ID를 넣으세요
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        # cogs 폴더 내 모든 .py 파일을 로드합니다.
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")  # .py 확장자 제거
        if not self.synced:  # 명령어를 한 번만 동기화
            await self.tree.sync()
            self.synced = True
        print("준비 완료")

    def close_db(self):
        self.cursor.close()
        self.conn.close()

client = AClient()

@client.event
async def on_close():
    client.close_db()

# 봇 실행
client.run(os.getenv("DISCORD_TOKEN"))
