"""PyInstaller's entry script: umcub_gui/__main__.py uses relative imports, so it cannot be the script itself."""
import sys

from umcub_gui.__main__ import main

sys.exit(main())
