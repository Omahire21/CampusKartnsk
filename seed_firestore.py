import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from firebase_config import init_firebase, get_firestore_db
init_firebase()

db = get_firestore_db()

dummy_products = [
    {
        "name": "Casio fx-991EX Scientific Calculator",
        "category": "Calculators",
        "description": "Used for 1 semester. Mint condition. Very helpful for Engineering and BSc students.",
        "price": 850.0,
        "condition": "Used",
        "college": "KK Wagh Engineering College",
        "usage_info": "Used - Like New",
        "image_urls": ["https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=500&q=80"],
        "first_image": "https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=500&q=80",
        "is_external": True,
        "seller_id": "admin@campuskart.com",
        "seller_name": "CampusKartAdmin",
        "status": "available",
        "views": 42,
        "created_at": datetime.utcnow()
    },
    {
        "name": "Engineering Drawing Board (Full Size)",
        "category": "Stationery",
        "description": "Sturdy wooden drawing board with clips. Perfect for first-year engineering drawing classes.",
        "price": 400.0,
        "condition": "Used",
        "college": "KTHM College",
        "usage_info": "Used - Good",
        "image_urls": ["https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=500&q=80"],
        "first_image": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=500&q=80",
        "is_external": True,
        "seller_id": "admin@campuskart.com",
        "seller_name": "CampusKartAdmin",
        "status": "available",
        "views": 15,
        "created_at": datetime.utcnow()
    },
    {
        "name": "Python Crash Course (2nd Edition)",
        "category": "Books",
        "description": "Best book to learn Python programming. No highlights or pen marks.",
        "price": 600.0,
        "condition": "Used",
        "college": "BYK College of Commerce",
        "usage_info": "Used - Like New",
        "image_urls": ["https://images.unsplash.com/photo-1526379095098-d400fd0bf935?w=500&q=80"],
        "first_image": "https://images.unsplash.com/photo-1526379095098-d400fd0bf935?w=500&q=80",
        "is_external": True,
        "seller_id": "admin@campuskart.com",
        "seller_name": "CampusKartAdmin",
        "status": "available",
        "views": 89,
        "created_at": datetime.utcnow()
    },
    {
        "name": "Mini Draftsman (Mini Drafter)",
        "category": "Stationery",
        "description": "Omega mini drafter with cover. Barely used.",
        "price": 250.0,
        "condition": "Used",
        "college": "Sandip University",
        "usage_info": "Used - Fair",
        "image_urls": ["https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=500&q=80"],
        "first_image": "https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=500&q=80",
        "is_external": True,
        "seller_id": "admin@campuskart.com",
        "seller_name": "CampusKartAdmin",
        "status": "available",
        "views": 5,
        "created_at": datetime.utcnow()
    }
]

print("Seeding dummy products to Firestore...")
for idx, prod in enumerate(dummy_products):
    db.collection('products').add(prod)
    print(f"Added product: {prod['name']}")

print("Done! You now have dummy products in your Firestore app.")
