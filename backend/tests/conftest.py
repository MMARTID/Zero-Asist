import sys
from unittest.mock import MagicMock

# Mock google.cloud.firestore and google.genai before app modules are imported.
# This prevents credential/API-key errors during module-level client initialization.
_mock_firestore = MagicMock()
_mock_firestore.transactional = lambda f: f
sys.modules['google.cloud.firestore'] = _mock_firestore

_mock_genai = MagicMock()
sys.modules['google.genai'] = _mock_genai

# Mock firebase_admin — imported lazily in auth.py.  No existing package
# depends on it, so this is safe (unlike google.oauth2 which conflicts with
# google_auth_oauthlib).
_mock_firebase_admin = MagicMock()
_mock_firebase_admin._apps = {"default": True}  # skip initialize_app()
sys.modules['firebase_admin'] = _mock_firebase_admin
sys.modules['firebase_admin.auth'] = _mock_firebase_admin.auth
