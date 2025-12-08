import asyncio
import sys
import os
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.append(os.getcwd())

from app.services.ai_service import ai_service
from app.services.audio_service import AudioService
from loguru import logger

async def test_ai_pipeline():
    # 1. Тест Embeddings
    try:
        logger.info("Testing Embeddings...")
        vector = await ai_service.get_embedding("Test query")
        logger.success(f"Embedding generated! Length: {len(vector)} (Expected: 1536)")
    except Exception as e:
        logger.error(f"Embedding failed: {e}")

    # 2. Тест LLM Extraction
    try:
        logger.info("Testing LLM Extraction...")
        text = "Вчера встретил Диму Петрова, он директор завода, любит рыбалку. Договорились созвониться на следующей неделе."
        data = await ai_service.extract_contact_info(text)
        logger.success(f"Extracted: {data.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"LLM failed: {e}")

    # 3. Тест Audio (если есть файл)
    # logger.info("Testing Audio...")
    # ...

if __name__ == "__main__":
    asyncio.run(test_ai_pipeline())

