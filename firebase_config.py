import os
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage

# Get from environment or use defaults
project_id = os.environ.get("FIREBASE_PROJECT_ID", "campuskart-ee453")
private_key = os.environ.get("FIREBASE_PRIVATE_KEY", "")
client_email = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
private_key_id = os.environ.get("FIREBASE_PRIVATE_KEY_ID", "")
client_id = os.environ.get("FIREBASE_CLIENT_ID", "")
storage_bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", f"{project_id}.appspot.com")

# Build config - only if we have the private key
firebase_config = None
if private_key:
    firebase_config = {
        "type": "service_account",
        "project_id": project_id,
        "private_key_id": private_key_id,
        "private_key": private_key.replace("\\n", "\n"),
        "client_email": client_email,
        "client_id": client_id,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}"
    }

firebase_initialized = False
db = None
bucket = None

def init_firebase():
    global firebase_initialized, db, bucket
    
    if firebase_initialized:
        return db, bucket
    
    # Check if Firebase is configured
    if not firebase_config:
        print("Firebase not configured - using MySQL fallback")
        return None, None
    
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred, {
                'storageBucket': storage_bucket
            })
        
        db = firestore.client()
        bucket = storage.bucket(storage_bucket)
        firebase_initialized = True
        
        print("Firebase initialized successfully!")
        return db, bucket
        
    except Exception as e:
        print(f"Firebase init error: {e}")
        return None, None

def get_firestore_db():
    if not db:
        init_firebase()
    return db

def get_storage_bucket():
    if not bucket:
        init_firebase()
    return bucket
