from pathlib import Path
from loguru import logger

class AudioService:
    @staticmethod
    def cleanup_file(path: str | Path):
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                logger.debug(f"Deleted temp file: {path}")
        except Exception as e:
            logger.warning("Failed to delete temp file {path}: {err}", path=path, err=repr(e))

