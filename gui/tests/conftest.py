import os
import sys

GUI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(GUI_DIR)
sys.path.insert(0, os.path.join(REPO_DIR, "scripts"))
sys.path.insert(0, GUI_DIR)
