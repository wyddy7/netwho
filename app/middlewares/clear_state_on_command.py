from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger

class ClearStateOnCommandMiddleware(BaseMiddleware):
    """
    Middleware that clears FSM state when user sends any command.
    This ensures commands always have priority over state handlers.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        # Check if this is a command
        if event.text and event.text.startswith("/"):
            state: FSMContext = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state:
                    logger.debug(f"Clearing FSM state {current_state} due to command: {event.text}")
                    await state.clear()
        
        return await handler(event, data)

