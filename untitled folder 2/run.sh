echo ""
echo "==================================================="
echo "  MediTrack - Emergency Medical Record System"
echo "==================================================="
echo ""

# Check Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    echo "Install it from: https://www.python.org/downloads/"
    exit 1
fi

echo "Python found!"
echo ""
echo "Installing required packages..."
pip3 install -r requirements.txt --quiet

echo "Starting MediTrack..."
echo "Open your browser at: http://localhost:5000"
echo ""
echo "Press CTRL+C to stop."
echo ""

python3 run.py
