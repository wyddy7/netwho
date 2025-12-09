import asyncio
from aiogram import Bot
from loguru import logger

class KeepTyping:
    """
    Context manager to keep the 'typing' status active for long-running operations.
    Usage:
        async with KeepTyping(bot, chat_id):
            await long_running_operation()
    """
    def __init__(self, bot: Bot, chat_id: int, action: str = "typing", interval: int = 4):
        self.bot = bot
        self.chat_id = chat_id
        self.action = action
        self.interval = interval
        self.task = None

    async def __aenter__(self):
        self.task = asyncio.create_task(self._keep_typing())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _keep_typing(self):
        try:
            while True:
                await self.bot.send_chat_action(chat_id=self.chat_id, action=self.action)
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Failed to send chat action: {e}")

