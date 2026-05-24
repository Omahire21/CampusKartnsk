"""
firebase_db.py — CampusKart's complete Firestore data layer.
All database operations go through this module. No MySQL anywhere.

Collections:
  users/{email}
  products/{auto_id}
  messages/{auto_id}
  kyc_requests/{email}
  favorites/{email_productid}
"""

import uuid
from datetime import datetime
from firebase_config import get_firestore_db, get_storage_bucket, init_firebase
from werkzeug.security import generate_password_hash, check_password_hash
from google.cloud.firestore_v1.base_query import FieldFilter

init_firebase()

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_dict(doc):
    """Convert a Firestore document snapshot to a dict with 'id' key."""
    if not doc.exists:
        return None
    data = doc.to_dict()
    data['id'] = doc.id
    return data


def _make_product_id():
    return str(uuid.uuid4()).replace('-', '')[:16]


# ─────────────────────────────────────────────────────────────────────────────
# USER OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _next_mck_id(db):
    """Atomically generate the next sequential MCK-ID string (e.g. 'MCK-0000001')."""
    counter_ref = db.collection('counters').document('mck_id')
    max_retries = 5
    for attempt in range(max_retries):
        doc = counter_ref.get()
        next_num = (doc.to_dict().get('seq', 0) if doc.exists else 0) + 1
        if counter_ref.set({'seq': next_num}, merge=True):
            return f"MCK-{next_num:07d}"
    # Fallback: uuid-based (very unlikely path)
    return f"MCK-{uuid.uuid4().int % 10**7:07d}"


def create_user(email, password, username, college):
    """Register a new user. Returns user dict or raises on duplicate."""
    db = get_firestore_db()
    ref = db.collection('users').document(email.lower())

    if ref.get().exists:
        raise ValueError("Email already registered.")

    # Username uniqueness check removed to allow duplicate names

    # Generate sequential MCK-ID (e.g. "MCK-0000001")
    mck_id = _next_mck_id(db)

    user_data = {
        'email': email.lower(),
        'username': username,
        'password': generate_password_hash(password),
        'college': college,
        'is_admin': False,
        'phone': '',
        'department': '',
        'student_id_num': '',
        'course': '',
        'batch': '',
        'hostel': '',
        'profile_pic': '',
        'mck_id': mck_id,
        'verification_status': 'not_submitted',
        'created_at': datetime.utcnow(),
    }
    ref.set(user_data)
    user_data['id'] = email.lower()

    # Send Automated Welcome Message from Admin
    welcome_msg = (
        f"Hi {username}! 👋 Welcome to CampusKart Nashik.\n\n"
        "I'm the platform admin. If you face any issues related to the website, "
        "KYC verification, or need any help, you can directly reply to this chat. "
        "I'll get back to you here.\n\n"
        "Happy Trading! 🎓"
    )
    try:
        send_message('admin@campuskart.com', 'CampusKartAdmin', email.lower(), welcome_msg, product_id=None)
    except Exception as e:
        print(f"Failed to send welcome message: {e}")

    return user_data


def get_user_by_email(email):
    """Fetch user by email. Returns dict or None."""
    db = get_firestore_db()
    doc = db.collection('users').document(email.lower()).get()
    user = _doc_to_dict(doc)
    if user and not user.get('mck_id'):
        mck_id = _next_mck_id(db)
        db.collection('users').document(email.lower()).update({'mck_id': mck_id})
        user['mck_id'] = mck_id
    return user


def get_user_by_username(username):
    """Fetch user by username. Returns dict or None."""
    db = get_firestore_db()
    docs = db.collection('users').where(
        filter=FieldFilter('username', '==', username)
    ).limit(1).get()
    docs = list(docs)
    return _doc_to_dict(docs[0]) if docs else None


def get_user_by_id(user_id):
    """user_id IS the email in Firestore. Alias for clarity."""
    return get_user_by_email(user_id)


def get_user_by_mck_id(mck_id):
    """Fetch user by their MCK-ID string (e.g. 'MCK-0000001')."""
    db = get_firestore_db()
    docs = db.collection('users').where(
        filter=FieldFilter('mck_id', '==', mck_id)
    ).limit(1).get()
    docs = list(docs)
    return _doc_to_dict(docs[0]) if docs else None


def authenticate_user(identifier, password):
    """
    Authenticate by email OR username.
    Returns user dict on success, None on failure.
    """
    # Try email first
    user = get_user_by_email(identifier)
    if not user:
        user = get_user_by_username(identifier)
    if user and check_password_hash(user.get('password', ''), password):
        return user
    return None


def update_user(email, data):
    """Update arbitrary fields on a user document."""
    db = get_firestore_db()
    db.collection('users').document(email.lower()).update(data)


def delete_user(email):
    db = get_firestore_db()
    email_lower = email.lower()
    
    # 1. Delete all products listed by the user
    products_ref = db.collection('products').where(filter=FieldFilter('seller_id', '==', email_lower)).get()
    for product in products_ref:
        product.reference.delete()
        
    # 2. Delete user's KYC request if any
    db.collection('kyc_requests').document(email_lower).delete()
    
    # 3. Delete any reports against this user
    reports_ref = db.collection('reports').where(filter=FieldFilter('reported_id', '==', email_lower)).get()
    for rep in reports_ref:
        rep.reference.delete()
        
    # 4. Delete user document
    db.collection('users').document(email_lower).delete()

def promote_to_admin(user_id):
    db = get_firestore_db()
    db.collection('users').document(user_id.lower()).update({'is_admin': True})


def get_all_users():
    """Return all user dicts (for admin panel)."""
    db = get_firestore_db()
    docs = db.collection('users').get()
    return [_doc_to_dict(d) for d in docs]


def get_user_count():
    db = get_firestore_db()
    return len(db.collection('users').where(
        filter=FieldFilter('is_admin', '==', False)
    ).get())


def reset_password(email, college, new_password):
    """
    Reset password after verifying email + college match.
    Returns True on success, False if no matching user.
    """
    user = get_user_by_email(email)
    if not user:
        return False
    if user.get('college', '').strip().lower() != college.strip().lower():
        return False
    update_user(email, {'password': generate_password_hash(new_password)})
    return True


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def create_product(seller_id, seller_name, name, price, description,
                   category, usage_info, image_urls, college):
    """
    Create a new product listing.
    image_urls: list of strings (local filenames or Firebase Storage URLs).
    Returns the new product id.
    """
    db = get_firestore_db()
    product_id = _make_product_id()
    data = {
        'seller_id': seller_id,
        'seller_name': seller_name,
        'name': name,
        'price': float(price),
        'description': description,
        'category': category,
        'usage_info': usage_info,
        'image_urls': image_urls if isinstance(image_urls, list) else [image_urls],
        'college': college,
        'status': 'available',
        'views': 0,
        'created_at': datetime.utcnow(),
    }
    db.collection('products').document(product_id).set(data)
    return product_id


def get_product(product_id):
    db = get_firestore_db()
    doc = db.collection('products').document(product_id).get()
    return _doc_to_dict(doc)


def get_all_products(category=None, search=None, college=None, status='available', limit=50):
    """
    Return products with optional filters.
    NOTE: Firestore does not support full-text search; we filter in Python for search queries.
    """
    db = get_firestore_db()
    ref = db.collection('products')

    query = ref.where(filter=FieldFilter('status', '==', status))

    if category:
        query = query.where(filter=FieldFilter('category', '==', category))
    if college:
        query = query.where(filter=FieldFilter('college', '==', college))

    # Sort in Python to avoid composite index requirement
    docs = list(query.limit(limit * 3).get())
    docs.sort(key=lambda x: x.to_dict().get('created_at', ''), reverse=True)
    results = [_doc_to_dict(d) for d in docs]

    # Python-side search filter (Firestore has no LIKE)
    if search:
        search_lower = search.lower()
        results = [
            p for p in results
            if search_lower in p.get('name', '').lower()
            or search_lower in p.get('description', '').lower()
        ]

    return results[:limit]


def get_products_by_seller(seller_id):
    db = get_firestore_db()
    docs = list(db.collection('products').where(
        filter=FieldFilter('seller_id', '==', seller_id)
    ).get())
    docs.sort(key=lambda x: x.to_dict().get('created_at', ''), reverse=True)
    return [_doc_to_dict(d) for d in docs]


def get_featured_products(limit=10):
    db = get_firestore_db()
    docs = list(db.collection('products').where(
        filter=FieldFilter('status', '==', 'available')
    ).limit(limit).get())
    docs.sort(key=lambda x: x.to_dict().get('created_at', ''), reverse=True)
    return [_doc_to_dict(d) for d in docs]


def update_product(product_id, data):
    db = get_firestore_db()
    db.collection('products').document(product_id).update(data)


def mark_product_sold(product_id, seller_id):
    """Mark sold only if caller is the seller. Returns True/False."""
    product = get_product(product_id)
    if not product or product.get('seller_id') != seller_id:
        return False
    update_product(product_id, {'status': 'sold'})
    return True


def increment_product_views(product_id):
    db = get_firestore_db()
    from google.cloud import firestore as fs
    db.collection('products').document(product_id).update({
        'views': fs.Increment(1)
    })


def delete_product(product_id):
    db = get_firestore_db()
    db.collection('products').document(product_id).delete()


def get_related_products(category, exclude_id, limit=4):
    db = get_firestore_db()
    docs = db.collection('products').where(
        filter=FieldFilter('category', '==', category)
    ).where(
        filter=FieldFilter('status', '==', 'available')
    ).limit(limit + 5).get()
    results = [_doc_to_dict(d) for d in docs if d.id != exclude_id]
    return results[:limit]


def get_available_count():
    db = get_firestore_db()
    return len(db.collection('products').where(
        filter=FieldFilter('status', '==', 'available')
    ).get())


def get_sold_count():
    db = get_firestore_db()
    return len(db.collection('products').where(
        filter=FieldFilter('status', '==', 'sold')
    ).get())


def get_all_products_admin():
    """Return ALL products for admin (no status filter)."""
    db = get_firestore_db()
    docs = list(db.collection('products').get())
    docs.sort(key=lambda x: x.to_dict().get('created_at', ''), reverse=True)
    return [_doc_to_dict(d) for d in docs]


def get_category_stats():
    """Return {category: count} dict."""
    db = get_firestore_db()
    docs = db.collection('products').get()
    counts = {}
    for d in docs:
        cat = d.to_dict().get('category', 'Other')
        counts[cat] = counts.get(cat, 0) + 1
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def send_message(sender_id, sender_name, receiver_id, message, product_id=None):
    db = get_firestore_db()
    data = {
        'sender_id': sender_id,
        'sender_name': sender_name,
        'receiver_id': receiver_id,
        'product_id': product_id,
        'message': message,
        'timestamp': datetime.utcnow(),
    }
    db.collection('messages').add(data)


def get_messages(sender_id, receiver_id, product_id=None):
    """Get full chat history between two users for a given product."""
    db = get_firestore_db()

    # Firestore can't do OR queries across different fields directly.
    # Fetch both directions and merge.
    def _fetch(s, r):
        q = db.collection('messages').where(
            filter=FieldFilter('sender_id', '==', s)
        ).where(
            filter=FieldFilter('receiver_id', '==', r)
        )
        if product_id:
            q = q.where(filter=FieldFilter('product_id', '==', product_id))
        else:
            q = q.where(filter=FieldFilter('product_id', '==', None))
        return list(q.get())

    docs_a = _fetch(sender_id, receiver_id)
    docs_b = _fetch(receiver_id, sender_id)
    all_docs = docs_a + docs_b

    messages = []
    for d in all_docs:
        m = d.to_dict()
        m['id'] = d.id
        messages.append(m)

    messages.sort(key=lambda x: str(x.get('timestamp', '')))
    return messages


def mark_messages_read(sender_id, receiver_id, product_id=None):
    """Mark all messages FROM sender TO receiver (for this product) as read."""
    db = get_firestore_db()
    q = db.collection('messages').where(
        filter=FieldFilter('sender_id', '==', sender_id)
    ).where(
        filter=FieldFilter('receiver_id', '==', receiver_id)
    )
    if product_id:
        q = q.where(filter=FieldFilter('product_id', '==', product_id))
    docs = q.get()
    batch = db.batch()
    for doc in docs:
        data = doc.to_dict()
        if not data.get('read_at'):
            batch.update(doc.reference, {'read_at': datetime.utcnow()})
    try:
        batch.commit()
    except Exception:
        pass  # Non-critical; don't crash the chat page


def get_recent_messages(limit=5):
    """For admin dashboard."""
    db = get_firestore_db()
    docs = list(db.collection('messages').get())
    docs.sort(key=lambda x: x.to_dict().get('timestamp', ''), reverse=True)
    return [_doc_to_dict(d) for d in docs[:limit]]

def get_all_conversations():
    """Admin only: Return all unique conversations across the platform."""
    db = get_firestore_db()
    all_msgs = list(db.collection('messages').get())
    
    seen = {}
    for doc in all_msgs:
        m = _doc_to_dict(doc)
        s_id = m['sender_id']
        r_id = m['receiver_id']
        pid = m.get('product_id') or 'admin'
        
        # Consistent key regardless of who sent/received
        participants = tuple(sorted([s_id, r_id]))
        key = f"{participants[0]}_{participants[1]}_{pid}"

        curr_time_str = str(m.get('timestamp', ''))
        seen_time_str = str(seen[key].get('last_time', '')) if key in seen else ''

        if key not in seen or curr_time_str > seen_time_str:
            seen[key] = {
                'product_id': m.get('product_id'),
                'user1_id': participants[0],
                'user2_id': participants[1],
                'last_message': m.get('message', ''),
                'last_time': m.get('timestamp'),
                'sender_id': s_id
            }

    convs = []
    for key, c in seen.items():
        u1 = get_user_by_id(c['user1_id']) or {}
        u2 = get_user_by_id(c['user2_id']) or {}
        c['user1_name'] = u1.get('username', c['user1_id'])
        c['user2_name'] = u2.get('username', c['user2_id'])

        if c['product_id']:
            prod = get_product(c['product_id']) or {}
            c['product_name'] = prod.get('name', 'Item')
        else:
            c['product_name'] = 'Admin Support'

        convs.append(c)

    convs.sort(key=lambda x: str(x.get('last_time', '')), reverse=True)
    return convs


def get_user_conversations(user_id):
    """
    Return a list of unique conversations the user is involved in.
    Each item has: product_id, product_name, other_user_id, other_username, last_message, last_time
    """
    db = get_firestore_db()

    sent = list(db.collection('messages').where(
        filter=FieldFilter('sender_id', '==', user_id)
    ).get())
    received = list(db.collection('messages').where(
        filter=FieldFilter('receiver_id', '==', user_id)
    ).get())

    all_msgs = sent + received
    seen = {}

    for doc in all_msgs:
        m = doc.to_dict()
        other = m['receiver_id'] if m['sender_id'] == user_id else m['sender_id']
        pid = m.get('product_id') or 'admin'
        key = f"{other}_{pid}"

        curr_time_str = str(m.get('timestamp', ''))
        seen_time_str = str(seen[key].get('last_time', '')) if key in seen else ''

        if key not in seen or curr_time_str > seen_time_str:
            seen[key] = {
                'product_id': m.get('product_id'),
                'other_user_id': other,
                'last_message': m.get('message', ''),
                'last_time': m.get('timestamp'),
            }

    # Enrich with user + product names
    convs = []
    for key, c in seen.items():
        other_user = get_user_by_id(c['other_user_id']) or {}
        c['other_username'] = other_user.get('username', c['other_user_id'])

        if c['product_id']:
            prod = get_product(c['product_id']) or {}
            c['product_name'] = prod.get('name', 'Item')
        else:
            c['product_name'] = 'Admin Support'

        convs.append(c)

    convs.sort(key=lambda x: str(x.get('last_time', '')), reverse=True)
    return convs


# ─────────────────────────────────────────────────────────────────────────────
# KYC OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def submit_kyc(user_id, full_name, phone, college_name, student_id, doc_filename=None):
    """Create or update a KYC request for the user."""
    db = get_firestore_db()

    # Check for duplicate phone/student ID in pending or approved requests
    phone_query = db.collection('kyc_requests').where(filter=FieldFilter('phone', '==', phone)).get()
    for doc in phone_query:
        doc_data = doc.to_dict()
        if doc_data.get('user_id') != user_id and doc_data.get('status') in ['pending', 'approved']:
            raise ValueError("Mobile number already in use by another verified student.")

    id_query = db.collection('kyc_requests').where(filter=FieldFilter('student_id', '==', student_id)).get()
    for doc in id_query:
        doc_data = doc.to_dict()
        if doc_data.get('user_id') != user_id and doc_data.get('status') in ['pending', 'approved']:
            raise ValueError("Student ID already in use by another verified student.")

    ref = db.collection('kyc_requests').document(user_id)

    data = {
        'user_id': user_id,
        'full_name': full_name,
        'phone': phone,
        'college_name': college_name,
        'student_id': student_id,
        'status': 'pending',
        'admin_note': None,
        'submitted_at': datetime.utcnow(),
    }
    if doc_filename is not None:
        data['doc_filename'] = doc_filename

    existing = ref.get()
    if existing.exists:
        ref.update(data)
    else:
        ref.set(data)


def get_kyc(user_id):
    """Return user's KYC record or None."""
    db = get_firestore_db()
    doc = db.collection('kyc_requests').document(user_id).get()
    return _doc_to_dict(doc)


def get_pending_kyc_requests():
    db = get_firestore_db()
    docs = list(db.collection('kyc_requests').where(
        filter=FieldFilter('status', '==', 'pending')
    ).get())
    docs.sort(key=lambda x: x.to_dict().get('submitted_at', ''), reverse=True)
    results = []
    for d in docs:
        rec = _doc_to_dict(d)
        user = get_user_by_id(rec['user_id']) or {}
        rec['user_email'] = user.get('email', rec['user_id'])
        results.append(rec)
    return results

def get_all_kyc_requests():
    db = get_firestore_db()
    docs = list(db.collection('kyc_requests').get())
    docs.sort(key=lambda x: x.to_dict().get('submitted_at', ''), reverse=True)
    results = []
    for d in docs:
        rec = _doc_to_dict(d)
        user = get_user_by_id(rec['user_id']) or {}
        rec['user_email'] = user.get('email', rec['user_id'])
        results.append(rec)
    return results


def get_pending_kyc_count():
    db = get_firestore_db()
    return len(db.collection('kyc_requests').where(
        filter=FieldFilter('status', '==', 'pending')
    ).get())


def admin_kyc_action(user_id, action, note=''):
    """action: 'approve' or 'reject'"""
    db = get_firestore_db()
    new_status = 'approved' if action == 'approve' else 'rejected'
    db.collection('kyc_requests').document(user_id).update({
        'status': new_status,
        'admin_note': note,
    })
    # Also update the user's verification_status
    update_user(user_id, {'verification_status': new_status})


# ─────────────────────────────────────────────────────────────────────────────
# FAVORITES OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _fav_doc_id(user_id, product_id):
    return f"{user_id.replace('@', '_').replace('.', '_')}_{product_id}"


def is_favorited(user_id, product_id):
    db = get_firestore_db()
    return db.collection('favorites').document(_fav_doc_id(user_id, product_id)).get().exists


def add_favorite(user_id, product_id):
    db = get_firestore_db()
    db.collection('favorites').document(_fav_doc_id(user_id, product_id)).set({
        'user_id': user_id,
        'product_id': product_id,
        'created_at': datetime.utcnow(),
    })


def remove_favorite(user_id, product_id):
    db = get_firestore_db()
    db.collection('favorites').document(_fav_doc_id(user_id, product_id)).delete()


def toggle_favorite(user_id, product_id):
    """Toggle and return 'added' or 'removed'."""
    if is_favorited(user_id, product_id):
        remove_favorite(user_id, product_id)
        return 'removed'
    else:
        add_favorite(user_id, product_id)
        return 'added'


def get_favorite_product_ids(user_id):
    db = get_firestore_db()
    docs = db.collection('favorites').where(
        filter=FieldFilter('user_id', '==', user_id)
    ).get()
    return [d.to_dict().get('product_id') for d in docs]


def get_favorite_products(user_id):
    product_ids = get_favorite_product_ids(user_id)
    products = []
    for pid in product_ids:
        p = get_product(pid)
        if p:
            products.append(p)
    return products


# ─────────────────────────────────────────────────────────────────────────────
# LEADERBOARD
# ─────────────────────────────────────────────────────────────────────────────

def get_unverified_users():
    """Get all non-admin users who are not approved."""
    db = get_firestore_db()
    users = get_all_users()
    non_admins = [u for u in users if not u.get('is_admin')]
    
    unverified = []
    for u in non_admins:
        if u.get('verification_status') != 'approved':
            unverified.append(u)
    return unverified

# ─────────────────────────────────────────────────────────────────────────────
# MODERATION / REPORTING
# ─────────────────────────────────────────────────────────────────────────────

def report_user(reporter_id, reported_id, reason):
    db = get_firestore_db()
    db.collection('reports').add({
        'reporter_id': reporter_id,
        'reported_id': reported_id,
        'reason': reason,
        'created_at': datetime.utcnow(),
    })

def get_all_reports():
    db = get_firestore_db()
    docs = db.collection('reports').get()
    reports = []
    for d in docs:
        rep = d.to_dict()
        rep['id'] = d.id
        # optionally attach user info
        reports.append(rep)
    reports.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
    return reports

def delete_report(report_id):
    db = get_firestore_db()
    db.collection('reports').document(report_id).delete()

def get_leaderboard(limit=20):
    """
    Returns top sellers by number of sold items.
    """
    db = get_firestore_db()
    users = get_all_users()
    non_admins = [u for u in users if not u.get('is_admin')]

    board = []
    for u in non_admins:
        uid = u['id']
        listings = get_products_by_seller(uid)
        deals = sum(1 for p in listings if p.get('status') == 'sold')
        active = sum(1 for p in listings if p.get('status') == 'available')
        board.append({
            'id': uid,
            'username': u.get('username'),
            'college': u.get('college'),
            'deals': deals,
            'active': active,
        })

    board.sort(key=lambda x: (-x['deals'], -x['active']))
    return board[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# FILE UPLOAD (Firebase Storage)
# ─────────────────────────────────────────────────────────────────────────────

def upload_file_to_storage(local_path, destination_blob_name):
    """
    Upload a local file to Firebase Storage.
    Returns the public URL string, or None on failure.
    """
    try:
        b = get_storage_bucket()
        if not b:
            return None
        blob = b.blob(destination_blob_name)
        blob.upload_from_filename(local_path)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"Storage upload error: {e}")
        return None
