# Exit on error
set -e

# Activate the virtual environment
source venv/bin/activate

# Run the app
uvicorn app.main:app --reload --port 8000