import os
import tempfile
import subprocess
from pathlib import Path
from loguru import logger

class AudioService:
    @staticmethod
    def convert_ogg_to_mp3(ogg_path: str | Path) -> str:
        """
        Конвертирует OGG (opus) в MP3 используя системный ffmpeg.
        Возвращает путь к временному MP3 файлу.
        """
        ogg_path = Path(ogg_path)
        if not ogg_path.exists():
            raise FileNotFoundError(f"Source file not found: {ogg_path}")

        # Создаем временный файл для mp3
        fd, mp3_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd) 

        try:
            logger.debug(f"Converting {ogg_path} to {mp3_path} via ffmpeg...")
            
            # Запускаем ffmpeg как подпроцесс
            # -y : перезаписать выходной файл
            # -i : входной файл
            # -vn : без видео
            # -acodec libmp3lame : кодек mp3
            # -q:a 2 : качество VBR (0-9, 2 - отлично)
            command = [
                "ffmpeg", "-y", 
                "-i", str(ogg_path),
                "-vn", 
                "-acodec", "libmp3lame", 
                "-q:a", "2", 
                mp3_path
            ]
            
            # Запускаем и ждем завершения, скрывая вывод (или логируя его при ошибке)
            process = subprocess.run(
                command, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            
            logger.debug("Conversion successful")
            return mp3_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr.decode()}")
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
            raise RuntimeError(f"FFmpeg conversion error: {e.stderr.decode()}")
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
            raise

    @staticmethod
    def cleanup_file(path: str | Path):
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                logger.debug(f"Deleted temp file: {path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {path}: {e}")

