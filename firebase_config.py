import os
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage

firebase_config = {
    "type": "service_account",
    "project_id": os.environ.get("FIREBASE_PROJECT_ID", "campuskart-ee453"),
    "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID", ""),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL", ""),
    "client_id": os.environ.get("FIREBASE_CLIENT_ID", ""),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("FIREBASE_CERT_URL", "")
}

firebase_initialized = False
db = None
bucket = None

def init_firebase():
    global firebase_initialized, db, bucket
    
    if firebase_initialized:
        return db, bucket
    
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred, {
                'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', 'campuskart-ee453.appspot.com')
            })
        
        db = firestore.client()
        bucket = storage.bucket(os.environ.get('FIREBASE_STORAGE_BUCKET', 'campuskart-ee453.appspot.com'))
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
