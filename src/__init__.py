# Redirect src to backend_core
import sys
import backend_core
sys.modules['src'] = backend_core
