import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuskart_secret_key_dev')

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# MySQL Connection Details — reads from environment variables (Railway) or falls back to local
db_config = {
    'host':     os.environ.get('MYSQLHOST',     'localhost'),
    'user':     os.environ.get('MYSQLUSER',     'root'),
    'password': os.environ.get('MYSQLPASSWORD', 'admin'),
    'database': os.environ.get('MYSQLDATABASE', 'campuskart'),
    'port':     int(os.environ.get('MYSQLPORT', 3306)),
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---

NASHIK_COLLEGES = [
    "K.R.T. Arts, B.H. Commerce and A.M. Science (KTHM) College",
    "Pune Vidyarthi Griha (PVG) College of Engineering & Management",
    "CMCS (College of Management and Computer Science), Nashik",
    "K.K. Wagh Arts, Commerce, Science & Computer Science College",
    "Ashoka Center for Business and Computer Studies (ACBCS)",
    "HPT Arts and RYK Science College",
    "BYK (Sinnarkar) College of Commerce",
    "K.K. Wagh Institute of Engineering Education & Research (KKWIEER)",
    "Sandip University, Nashik",
    "MET Bhujbal Knowledge City",
    "NDMVP's K.B.T. College of Engineering",
    "NDMVP's College of Pharmacy",
    "MGV's Karmaveer Bhausaheb Hiray (KBH) College",
    "Gokhale Education Society's R.H. Sapat College",
    "SITRC (Sandip Foundation)",
    "SNJB's College of Engineering & Pharmacy, Chandwad",
    "Nashik Gramin Shikshan Prasarak Mandal's College of Pharmacy",
    "Guru Gobind Singh College of Engineering",
    "Matoshri College of Engineering & Research Centre",
    "SVIT Chincholi"
]

@app.route('/')
def index():
    # If admin is logged in, redirect them specifically to the admin panel
    if session.get('is_admin'):
        return redirect(url_for('admin'))
        
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500
    cursor = conn.cursor(dictionary=True)
    
    # Get featured products (latest 6)
    cursor.execute("SELECT * FROM products WHERE status = 'available' ORDER BY created_at DESC LIMIT 6")
    products = cursor.fetchall()

    for product in products:
        if product['image_url'] and product['image_url'].startswith('http'):
            product['is_external'] = True
        else:
            product['is_external'] = False
    
    cursor.close()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        college = request.form['college']
        
        # Verify college email domain (relaxed for testing)
        if not (email.endswith('.edu') or '@college' in email or email.endswith('.com')):
            flash('Please use a valid college email address', 'error')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, email, password, college) VALUES (%s, %s, %s, %s)",
                           (username, email, hashed_password, college))
            conn.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email already registered.', 'error')
        finally:
            cursor.close()
            conn.close()
            
    return render_template('register.html', colleges=NASHIK_COLLEGES)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['email'] # Can be email or username
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Allow login by email OR username
        cursor.execute("SELECT * FROM users WHERE email = %s OR username = %s", (identifier, identifier))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['college'] = user['college']
            session['is_admin'] = user['is_admin']
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('products'))
        else:
            flash('Invalid credentials.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/products')
def products():
    if session.get('is_admin'):
        return redirect(url_for('admin'))
        
    category = request.args.get('category')
    search = request.args.get('search')
    college_filter = request.args.get('college')
    
    # Logic fix: If user is logged in, only filter by their college if no other filters are active
    # This was causing items from other colleges to disappear in the 'Shop' page
    if 'user_id' in session and not any([category, search, college_filter]):
        # Optional: Show items from my college by default, but let users clear it
        pass 

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT * FROM products WHERE status = 'available'"
    params = []
    
    if category:
        query += " AND category = %s"
        params.append(category)
    if search:
        query += " AND (name LIKE %s OR description LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    if college_filter:
        query += " AND college = %s"
        params.append(college_filter)
        
    query += " ORDER BY created_at DESC"
    
    cursor.execute(query, tuple(params))
    items = cursor.fetchall()
    
    # Force absolute URLs for placeholder images if they start with http
    for item in items:
        if item['image_url'] and item['image_url'].startswith('http'):
            item['is_external'] = True
        else:
            item['is_external'] = False
    
    # Sort colleges for easier selection
    sorted_colleges = sorted(NASHIK_COLLEGES)
    
    cursor.close()
    conn.close()
    return render_template('products.html', products=items, colleges=sorted_colleges, current_college=college_filter)

@app.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        flash('Please login to sell items.', 'error')
        return redirect(url_for('login'))
        
    if session.get('is_admin'):
        flash('Admins cannot sell products. Switch to student account.', 'error')
        return redirect(url_for('admin'))
        
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        usage_info = request.form['usage_info']
        category = request.form['category']
        college = session['college']
        
        file = request.files['image']
        image_url = ''
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            image_url = unique_filename
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (seller_id, name, price, description, category, usage_info, image_url, college) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                       (session['user_id'], name, price, description, category, usage_info, image_url, college))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('products'))
        
    return render_template('add_product.html')

@app.route('/product/mark-sold/<int:product_id>')
def mark_product_sold(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    # Ensure only the seller can mark it as sold
    cursor.execute("UPDATE products SET status = 'sold' WHERE id = %s AND seller_id = %s", (product_id, session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Product marked as sold!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if not session.get('user_id'):
        flash('Please create an account to view product details.', 'info')
        return redirect(url_for('register'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT p.*, u.username as seller_name, u.email as seller_email FROM products p JOIN users u ON p.seller_id = u.id WHERE p.id = %s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('products'))
        
    return render_template('product_detail.html', product=product)

@app.route('/chat/<int:product_id>/<int:receiver_id>', methods=['GET', 'POST'])
def chat(product_id, receiver_id):
    if 'user_id' not in session:
        flash('Please login to message sellers.', 'error')
        return redirect(url_for('login'))

    if session.get('is_admin'):
        flash('Admin chat feature is coming soon within the dashboard.', 'info')
        return redirect(url_for('admin'))
        
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        message = request.form['message']
        cursor.execute("INSERT INTO messages (sender_id, receiver_id, product_id, message) VALUES (%s, %s, %s, %s)",
                       (user_id, receiver_id, product_id, message))
        conn.commit()
        
    # Get chat history
    cursor.execute("""
        SELECT m.*, u.username as sender_name 
        FROM messages m 
        JOIN users u ON m.sender_id = u.id 
        WHERE m.product_id = %s AND (
            (m.sender_id = %s AND m.receiver_id = %s) OR 
            (m.sender_id = %s AND m.receiver_id = %s)
        )
        ORDER BY m.timestamp ASC
    """, (product_id, user_id, receiver_id, receiver_id, user_id))
    messages = cursor.fetchall()
    
    # Get product info
    cursor.execute("SELECT name FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    
    # Get receiver info
    cursor.execute("SELECT username FROM users WHERE id = %s", (receiver_id,))
    receiver = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template('chat.html', messages=messages, product=product, receiver=receiver, product_id=product_id, receiver_id=receiver_id)

@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    cursor.execute("SELECT p.*, u.username as seller_name FROM products p JOIN users u ON p.seller_id = u.id ORDER BY p.created_at DESC")
    products = cursor.fetchall()
    
    # Statistics for Graphs
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_admin = 0")
    user_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM products WHERE status = 'available'")
    available_count = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM products WHERE status = 'sold'")
    sold_count = cursor.fetchone()['total']
    
    # Category Distribution for Chart
    cursor.execute("SELECT category, COUNT(*) as count FROM products GROUP BY category")
    category_data = cursor.fetchall()
    category_labels = [row['category'] for row in category_data]
    category_counts = [row['count'] for row in category_data]
    
    # Get latest active chats (last 5 messages)
    cursor.execute("SELECT m.*, u.username as sender_name FROM messages m JOIN users u ON m.sender_id = u.id ORDER BY m.timestamp DESC LIMIT 5")
    recent_messages = cursor.fetchall()
    
    stats = {
        'user_count': user_count,
        'available_count': available_count,
        'sold_count': sold_count,
        'total_products': available_count + sold_count,
        'cat_labels': category_labels,
        'cat_counts': category_counts
    }
    
    cursor.close()
    conn.close()
    return render_template('admin.html', users=users, products=products, stats=stats, recent_messages=recent_messages)

@app.route('/admin/send-message', methods=['POST'])
def send_admin_message():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
        
    receiver_id = request.form['user_id']
    message_text = request.form['message']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fixed IntegrityError: Ensure product_id is NULL for admin global messages
    # The database schema was updated but Python code must pass None for NULL
    cursor.execute("INSERT INTO messages (sender_id, receiver_id, product_id, message) VALUES (%s, %s, %s, %s)",
                   (session['user_id'], receiver_id, None, f"[ADMIN MESSAGE]: {message_text}"))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Message sent to student!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete-product/<int:product_id>')
def delete_product(product_id):
    if not session.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Product deleted.', 'success')
    return redirect(url_for('admin'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Simple simulated contact logic
        flash('Message sent! We will get back to you soon.', 'success')
        return redirect(url_for('index'))
    return render_template('contact.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    # debug=True only in local development; production uses gunicorn
    app.run(debug=os.environ.get('FLASK_ENV') != 'production')
