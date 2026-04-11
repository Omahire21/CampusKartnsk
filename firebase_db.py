import os
import uuid
from datetime import datetime
from firebase_config import get_firestore_db, get_storage_bucket, init_firebase

init_firebase()

def create_user(email, password, username, college):
    db = get_firestore_db()
    
    user_data = {
        'email': email,
        'username': username,
        'college': college,
        'created_at': datetime.now(),
        'is_admin': False,
        'kyc_status': 'pending',
        'profile_pic': 'profile.jpeg'
    }
    
    doc_ref = db.collection('users').document(email)
    doc_ref.set(user_data)
    
    return {'id': email, 'email': email, 'username': username}

def get_user(email):
    db = get_firestore_db()
    doc = db.collection('users').document(email).get()
    
    if doc.exists:
        return doc.to_dict()
    return None

def get_user_by_username(username):
    db = get_firestore_db()
    users = db.collection('users').where('username', '==', username).limit(1).get()
    
    for user in users:
        return user.to_dict()
    return None

def get_all_users():
    db = get_firestore_db()
    users = db.collection('users').get()
    return [u.to_dict() for u in users]

def update_user(email, data):
    db = get_firestore_db()
    db.collection('users').document(email).update(data)

def delete_user(email):
    db = get_firestore_db()
    db.collection('users').document(email).delete()

def get_user_count():
    db = get_firestore_db()
    return len(db.collection('users').get())

def create_product(seller_id, seller_name, name, price, description, category, usage_info, image_url, college):
    db = get_firestore_db()
    
    product_id = str(uuid.uuid4())[:8]
    
    product_data = {
        'seller_id': seller_id,
        'seller_name': seller_name,
        'name': name,
        'price': int(price),
        'description': description,
        'category': category,
        'usage_info': usage_info,
        'image_url': image_url,
        'college': college,
        'status': 'available',
        'views': 0,
        'created_at': datetime.now()
    }
    
    db.collection('products').document(product_id).set(product_data)
    return product_id

def get_product(product_id):
    db = get_firestore_db()
    doc = db.collection('products').document(product_id).get()
    
    if doc.exists:
        data = doc.to_dict()
        data['id'] = product_id
        return data
    return None

def get_all_products(college=None, category=None, limit=50):
    db = get_firestore_db()
    products_ref = db.collection('products')
    
    all_docs = products_ref.get()
    results = []
    
    for doc in all_docs:
        data = doc.to_dict()
        data['id'] = doc.id
        
        if data.get('status') != 'available':
            continue
        if college and data.get('college') != college:
            continue
        if category and data.get('category') != category:
            continue
            
        results.append(data)
    
    return results[:limit]

def get_products_by_seller(seller_id):
    db = get_firestore_db()
    products = db.collection('products').where('seller_id', '==', seller_id).get()
    return [p.to_dict() | {'id': p.id} for p in products]

def update_product(product_id, data):
    db = get_firestore_db()
    db.collection('products').document(product_id).update(data)

def delete_product(product_id):
    db = get_firestore_db()
    db.collection('products').document(product_id).delete()

def get_available_count():
    db = get_firestore_db()
    return len([p for p in db.collection('products').get() if p.to_dict().get('status') == 'available'])

def get_sold_count():
    db = get_firestore_db()
    return len([p for p in db.collection('products').get() if p.to_dict().get('status') == 'sold'])

def create_chat(product_id, buyer_id, seller_id):
    db = get_firestore_db()
    
    chat_id = f"{product_id}_{buyer_id}"
    
    chat_data = {
        'product_id': product_id,
        'buyer_id': buyer_id,
        'seller_id': seller_id,
        'created_at': datetime.now(),
        'last_message': ''
    }
    
    db.collection('chats').document(chat_id).set(chat_data)
    return chat_id

def get_chats(user_id):
    db = get_firestore_db()
    
    bought_chats = db.collection('chats').where('buyer_id', '==', user_id).get()
    sold_chats = db.collection('chats').where('seller_id', '==', user_id).get()
    
    chats = []
    for c in bought_chats + sold_chats:
        data = c.to_dict()
        data['id'] = c.id
        chats.append(data)
    
    return chats

def add_message(chat_id, sender_id, message):
    db = get_firestore_db()
    
    message_data = {
        'chat_id': chat_id,
        'sender_id': sender_id,
        'message': message,
        'timestamp': datetime.now()
    }
    
    db.collection('messages').document().set(message_data)
    
    db.collection('chats').document(chat_id).update({
        'last_message': message,
        'last_timestamp': datetime.now()
    })

def get_messages(chat_id):
    db = get_firestore_db()
    messages = db.collection('messages').where('chat_id', '==', chat_id).get()
    return [m.to_dict() for m in messages]

def add_favorite(user_id, product_id):
    db = get_firestore_db()
    db.collection('favorites').document(f"{user_id}_{product_id}").set({
        'user_id': user_id,
        'product_id': product_id,
        'created_at': datetime.now()
    })

def remove_favorite(user_id, product_id):
    db = get_firestore_db()
    db.collection('favorites').document(f"{user_id}_{product_id}").delete()

def get_favorites(user_id):
    db = get_firestore_db()
    favorites = db.collection('favorites').where('user_id', '==', user_id).get()
    
    products = []
    for f in favorites:
        product_id = f.to_dict().get('product_id')
        if product_id:
            product = get_product(product_id)
            if product:
                products.append(product)
    
    return products

def is_favorited(user_id, product_id):
    db = get_firestore_db()
    doc = db.collection('favorites').document(f"{user_id}_{product_id}").get()
    return doc.exists

def get_stats():
    db = get_firestore_db()
    
    return {
        'user_count': len(db.collection('users').get()),
        'available_count': get_available_count(),
        'sold_count': get_sold_count()
    }

def get_category_stats():
    db = get_firestore_db()
    products = db.collection('products').get()
    
    categories = {}
    for p in products:
        cat = p.to_dict().get('category', 'Other')
        categories[cat] = categories.get(cat, 0) + 1
    
    return categories
