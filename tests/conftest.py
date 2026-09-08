import os
import sys

# Make `import outreach` / `import storage` work no matter where pytest runs.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
