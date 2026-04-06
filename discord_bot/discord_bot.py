"""
Discord 機器人 — 通知與指令接收
token / channel_id 從專案根目錄的 config.json 讀取：
  {
    "discord_bot": {
      "token": "YOUR_BOT_TOKEN",
      "channel_id": 123456789012345678,
      "allowed_user_ids": []   // 空陣列表示允許所有人，填入 ID 則只允許指定使用者
    }
  }

支援指令（預設前綴 !）：
  !ping               確認機器人在線
  !status             查詢目前各任務執行狀態
  !start <任務名稱>   啟動指定任務
  !stop  <任務名稱>   停止指定任務
  !help               顯示可用指令

外部呼叫：
  bot = DiscordBot("config.json")
  bot.register_status_callback(fn)          # fn() -> dict[str, bool]
  bot.register_start_callback(fn)           # fn(task_name: str) -> str
  bot.register_stop_callback(fn)            # fn(task_name: str) -> str
  bot.start()                               # 背景執行緒啟動
  bot.notify("訊息")                        # 傳送通知到指定頻道
  bot.stop()                                # 停止機器人
"""

import asyncio
import json
import os
import threading
from typing import Callable, Optional

import discord
from discord.ext import commands


class DiscordBot:
    def __init__(self, config_path: str = "config.json"):
        self._config_path = config_path
        self._token: str = ""
        self._channel_id: int = 0
        self._allowed_user_ids: list[int] = []
        self._prefix: str = "!"

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[commands.Bot] = None

        self._status_cb: Optional[Callable[[], dict]] = None
        self._start_cb: Optional[Callable[[str], str]] = None
        self._stop_cb: Optional[Callable[[str], str]] = None

        self._ready_event = threading.Event()  # 新增：用來同步執行緒狀態

        self._load_config()
        self._build_client()

    # ── 設定 ────────────────────────────────────────────────────

    def _load_config(self):
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"找不到設定檔：{self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        discord_cfg = cfg.get("discord_bot", {})
        self._token = discord_cfg.get("token", "")
        self._channel_id = int(discord_cfg.get("channel_id", 0))
        self._allowed_user_ids = [int(uid) for uid in discord_cfg.get("allowed_user_ids", [])]
        if not self._token:
            raise ValueError("config.json 中 discord_bot.token 未設定")

    # ── 回呼註冊 ─────────────────────────────────────────────────

    def register_status_callback(self, fn: Callable[[], dict]):
        """fn() -> dict[任務名稱, 是否執行中]"""
        self._status_cb = fn

    def register_start_callback(self, fn: Callable[[str], str]):
        """fn(task_name) -> 結果訊息"""
        self._start_cb = fn

    def register_stop_callback(self, fn: Callable[[str], str]):
        """fn(task_name) -> 結果訊息"""
        self._stop_cb = fn

    # ── 建立 Bot ─────────────────────────────────────────────────

    def _build_client(self):
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = commands.Bot(command_prefix=self._prefix, intents=intents)
        self._client.remove_command("help")  # 移除預設 help，改為自訂

        @self._client.event
        async def on_ready():
            print(f"[DiscordBot] 已登入：{self._client.user} (id={self._client.user.id})")
            self._ready_event.set()  # 標記：現在可以開始發送通知了
            await self._send("✅ MapleStory 輔助機器人已上線")

        @self._client.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.CommandNotFound):
                await ctx.send(f"❓ 未知指令，輸入 `{self._prefix}help` 查看可用指令")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"⚠️ 缺少必要參數：`{error.param.name}`")
            else:
                await ctx.send(f"❌ 錯誤：{error}")

        @self._client.command(name="ping")
        async def cmd_ping(ctx):
            print(f"[DiscordBot] ping from channel_id={ctx.channel.id}")
            if not self._is_allowed(ctx):
                return
            latency = round(self._client.latency * 1000)
            await ctx.send(f"🏓 Pong！延遲 {latency} ms")

        @self._client.command(name="help")
        async def cmd_help(ctx):
            print(f"[DiscordBot] help from channel_id={ctx.channel.id}")
            if not self._is_allowed(ctx):
                return
            lines = [
                "**MapleStory 輔助機器人指令列表**",
                f"`{self._prefix}ping`　　　　確認機器人在線",
                f"`{self._prefix}status`　　　查詢各任務執行狀態",
                f"`{self._prefix}start <任務>`　啟動指定任務",
                f"`{self._prefix}stop <任務>` 　停止指定任務",
                f"`{self._prefix}help`　　　　顯示此說明",
            ]
            await ctx.send("\n".join(lines))

        @self._client.command(name="status")
        async def cmd_status(ctx):
            print(f"[DiscordBot] status from channel_id={ctx.channel.id}")
            if not self._is_allowed(ctx):
                return
            if self._status_cb is None:
                await ctx.send("⚠️ 狀態查詢功能尚未連接主程式")
                return
            try:
                status: dict = self._status_cb()
            except Exception as e:
                await ctx.send(f"❌ 取得狀態失敗：{e}")
                return
            if not status:
                await ctx.send("📋 目前沒有任何任務")
                return
            lines = ["**任務狀態**"]
            for task_name, running in status.items():
                icon = "🟢" if running else "⚫"
                state = "執行中" if running else "已停止"
                lines.append(f"{icon} `{task_name}` — {state}")
            await ctx.send("\n".join(lines))

        @self._client.command(name="start")
        async def cmd_start(ctx, *, task_name: str):
            print(f"[DiscordBot] start from channel_id={ctx.channel.id}")
            if not self._is_allowed(ctx):
                return
            if self._start_cb is None:
                await ctx.send("⚠️ 啟動功能尚未連接主程式")
                return
            try:
                result = self._start_cb(task_name.strip())
                await ctx.send(f"▶️ {result}")
            except Exception as e:
                await ctx.send(f"❌ 啟動失敗：{e}")

        @self._client.command(name="stop")
        async def cmd_stop(ctx, *, task_name: str):
            print(f"[DiscordBot] stop from channel_id={ctx.channel.id}")
            if not self._is_allowed(ctx):
                return
            if self._stop_cb is None:
                await ctx.send("⚠️ 停止功能尚未連接主程式")
                return
            try:
                result = self._stop_cb(task_name.strip())
                await ctx.send(f"⏹️ {result}")
            except Exception as e:
                await ctx.send(f"❌ 停止失敗：{e}")

    def _is_allowed(self, ctx) -> bool:
        if not self._allowed_user_ids:
            return True
        if ctx.author.id in self._allowed_user_ids:
            return True
        return False

    # ── 啟動 / 停止 ──────────────────────────────────────────────

    def start(self):
        """在背景執行緒啟動機器人（非阻塞）"""
        if self._thread and self._thread.is_alive():
            print("[DiscordBot] 機器人已在執行中")
            return

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._client.start(self._token))
            except asyncio.CancelledError:
                pass
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=_run, name="DiscordBotThread", daemon=True)
        self._thread.start()
        print("[DiscordBot] 機器人背景執行緒已啟動")

    def stop(self):
        """關閉機器人"""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        print("[DiscordBot] 機器人已關閉")

    # ── 通知 ─────────────────────────────────────────────────────

    def notify(self, message: str):
        """傳送通知訊息（增加安全性檢查）"""
        if not self._ready_event.is_set():
            print(f"[DiscordBot] 警告：機器人尚未就緒，訊息將被丟棄：{message}")
            return

        if self._loop and self._loop.is_running():
            # 確保使用 threadsafe 呼叫
            asyncio.run_coroutine_threadsafe(self._send(message), self._loop)
        else:
            print("[DiscordBot] Loop 未執行中")

    async def _send(self, message: str):
        try:
            # 優先使用 fetch 確保一定能抓到頻道（雖然慢一點點但更穩）
            channel = await self._client.fetch_channel(self._channel_id)
            if channel:
                await channel.send(message)
        except Exception as e:
            print(f"[DiscordBot] 發送失敗：{e}")