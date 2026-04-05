from enum import Enum


class Tables(str, Enum):
    BROWSER_SESSION = "browser_session"

    def __str__(self) -> str:
        return self.value
