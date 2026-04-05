# Exit on error
set -e

# Activate the virtual environment
if [ -f "venv/bin/activate" ]; then
	source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
	source .venv/bin/activate
else
	echo "No virtual environment found. Expected venv/ or .venv/."
	exit 1
fi

# Run the app
uvicorn app.main:app --reload --port 8000