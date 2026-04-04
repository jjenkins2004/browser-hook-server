# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError

# Will automatically throw exceptions if vars are missing
class Keys(BaseSettings):
    #Defining mandatory env variables
    SUPABASE_URL: str
    SUPABASE_KEY: str
    BROWSER_USE_KEY: str

    # Configuration options for Pydantic model
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

# Try creating the Key object and validate
try:
    keys = Keys() # type: ignore[call-arg]
except ValidationError as e:
    # Print the validation errors and exit
    print("Missing or invalid environment variables:")
    print(e.json())
    raise SystemExit("Error: Could not load environment variables properly.")