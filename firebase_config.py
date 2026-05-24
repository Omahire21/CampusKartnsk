import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ─── Configuration ────────────────────────────────────────────────────────────
# Priority 1: Service account JSON file (local dev) → set FIREBASE_CREDENTIALS_PATH
# Priority 2: Individual environment variables (production / Vercel)
# ──────────────────────────────────────────────────────────────────────────────

firebase_initialized = False
db = None
bucket = None


def _build_cred():
    """Return a firebase_admin.credentials.Certificate object or None."""
    # Option A: path to a local service-account JSON file
    json_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
    if json_path and os.path.isfile(json_path):
        return credentials.Certificate(json_path)

    # Option B: individual env vars (Vercel / CI)
    project_id    = os.environ.get("FIREBASE_PROJECT_ID", "")
    raw_key       = os.environ.get("FIREBASE_PRIVATE_KEY", "")
    # Format key properly regardless of how it was pasted
    private_key   = raw_key.replace("\\n", "\n")
    if "-----BEGIN PRIVATE KEY-----" in private_key and "\n" not in private_key:
        private_key = private_key.replace(" ", "\n")
        private_key = private_key.replace("-----BEGIN\nPRIVATE\nKEY-----", "-----BEGIN PRIVATE KEY-----")
        private_key = private_key.replace("-----END\nPRIVATE\nKEY-----", "-----END PRIVATE KEY-----")
        
    client_email  = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    private_key_id = os.environ.get("FIREBASE_PRIVATE_KEY_ID", "")
    client_id     = os.environ.get("FIREBASE_CLIENT_ID", "")

    if private_key and client_email:
        cfg = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": private_key_id,
            "private_key": private_key,
            "client_email": client_email,
            "client_id": client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": (
                f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}"
            ),
        }
        return credentials.Certificate(cfg)

    return None


def init_firebase():
    global firebase_initialized, db, bucket

    if firebase_initialized:
        return db, bucket

    try:
        cred = _build_cred()
        if not cred:
            print("[WARNING] Firebase credentials not found. Set FIREBASE_CREDENTIALS_PATH or env vars.")
            return None, None
            
        storage_bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "")
        if not firebase_admin._apps:
            init_kwargs = {"credential": cred}
            if storage_bucket_name:
                init_kwargs["options"] = {"storageBucket": storage_bucket_name}
            firebase_admin.initialize_app(**init_kwargs)

        db = firestore.client()
        if storage_bucket_name:
            bucket = storage.bucket(storage_bucket_name)

        firebase_initialized = True
        print("[OK] Firebase initialized successfully!")
        return db, bucket

    except Exception as exc:
        print(f"[ERROR] Firebase init error: {exc}")
        return None, None


def get_firestore_db():
    if not firebase_initialized:
        init_firebase()
    return db


def get_storage_bucket():
    if not firebase_initialized:
        init_firebase()
    return bucket
