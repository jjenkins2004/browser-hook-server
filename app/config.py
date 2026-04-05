# app/config.py
import base64

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError


# Will automatically throw exceptions if vars are missing
class Keys(BaseSettings):
    # Defining mandatory env variables
    SUPABASE_URL: str
    SUPABASE_KEY: str
    BROWSER_USE_KEY: str
    P8_KEY_BASE64: str

    # Configuration options for Pydantic model
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    def p8_key(self) -> str:
        """Decode the base64-encoded .p8 key into its raw string content."""
        try:
            return base64.b64decode(self.P8_KEY_BASE64).decode("utf-8")
        except Exception as exc:
            raise ValueError("Invalid P8_KEY_BASE64: could not decode key") from exc


# Try creating the Key object and validate
try:
    keys = Keys()  # type: ignore[call-arg]
except ValidationError as e:
    # Print the validation errors and exit
    print("Missing or invalid environment variables:")
    print(e.json())
    raise SystemExit("Error: Could not load environment variables properly.")
