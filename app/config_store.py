import os
import threading
from dotenv import set_key
from pathlib import Path


ALLOWED_KEYS = ("OPENAI_API_KEY", "TAVILY_API_KEY")


class SecretConfigStore:
    def __init__(self, env_path: Path) -> None:
        self.env_path = env_path
        self._lock = threading.Lock()

    def status(self) -> dict[str, bool]:
        return {key: bool(os.getenv(key, "").strip()) for key in ALLOWED_KEYS}

    def save(self, updates: dict[str, str | None]) -> dict[str, bool]:
        clean = {key: (value or "").strip() for key, value in updates.items() if key in ALLOWED_KEYS and value is not None}
        clean = {key: value for key, value in clean.items() if value}
        if not clean:
            return self.status()
        for key, value in clean.items():
            if len(value) < 16 or any(character.isspace() for character in value):
                raise ValueError(f"{key} 格式不正确：密钥不能包含空格且长度应不少于16位")

        with self._lock:
            self.env_path.touch(mode=0o600, exist_ok=True)
            # Quote values so dotenv metacharacters cannot alter configuration on restart.
            for name, value in clean.items():
                set_key(str(self.env_path), name, value, quote_mode="always")
            self.env_path.chmod(0o600)
            os.environ.update(clean)
        return self.status()

