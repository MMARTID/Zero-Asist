import sys
from unittest.mock import MagicMock

# Mock google.cloud.firestore and google.genai before app modules are imported.
# This prevents credential/API-key errors during module-level client initialization.
_mock_firestore = MagicMock()
_mock_firestore.transactional = lambda f: f
sys.modules['google.cloud.firestore'] = _mock_firestore

_mock_genai = MagicMock()
sys.modules['google.genai'] = _mock_genai
