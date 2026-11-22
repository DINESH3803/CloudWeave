"""
Pytest Test Suite Configuration and Path Setup.
Adds the repository root and controller directories to sys.path
so tests can import shared, controller, and client modules seamlessly.
"""
import sys
from pathlib import Path

# Add project root and controller directory to python search path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "controller"))
