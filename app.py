import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuskart_secret_key_dev')

# Firebase check
USE_FIREBASE = True
try:
    from firebase_config import init_firebase
    from firebase_db import fb_db
    init_firebase()
    print("Firebase initialized for app")
except Exception as e:
    print(f"Firebase init failed: {e}")
    USE_FIREBASE = False

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
KYC_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kyc_docs')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['KYC_UPLOAD_FOLDER'] = KYC_UPLOAD_FOLDER

# MySQL Connection Details
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

def allowed_kyc_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'pdf'}

def process_product_images(products_list):
    """Processes product images to determine if they are external and handles multiple images."""
    if products_list is None:
        return []
    if isinstance(products_list, dict):
        products_list = [products_list]
        
    for product in products_list:
        # Robust handling of None, empty strings, and whitespace
        raw_url = str(product.get('image_url', '') or '').strip()
        
        if raw_url.startswith('http'):
            product['is_external'] = True
        else:
            product['is_external'] = False
            
        if raw_url:
            # Handle comma separated filenames and clean up whitespace
            product['first_image'] = raw_url.split(',')[0].strip()
        else:
            product['first_image'] = ''
    
    return products_list

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
    
    # Get featured products (latest 10 for 2 full rows)
    cursor.execute("SELECT * FROM products WHERE status = 'available' ORDER BY created_at DESC LIMIT 10")
    products = cursor.fetchall()

    process_product_images(products)
    
    # Get user's favorite product IDs
    favorite_ids = []
    if session.get('user_id'):
        cursor.execute("SELECT product_id FROM favorites WHERE user_id = %s", (session['user_id'],))
        favorite_ids = [row['product_id'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return render_template('index.html', products=products, favorite_ids=favorite_ids)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirm_password', '')
        college = request.form['college']

        # Check passwords match
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
        
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
            session['profile_pic'] = user.get('profile_pic')
            # Load KYC status into session
            conn2 = get_db_connection()
            cur2 = conn2.cursor(dictionary=True)
            cur2.execute("SELECT status FROM kyc_requests WHERE user_id = %s ORDER BY submitted_at DESC LIMIT 1", (user['id'],))
            kyc_row = cur2.fetchone()
            session['kyc_status'] = kyc_row['status'] if kyc_row else 'not_submitted'
            cur2.close()
            conn2.close()
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

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()
        new_password = request.form.get('new_password', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s AND college = %s", (email, college))
        user = cursor.fetchone()

        if user:
            # Update password
            hashed_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user['id']))
            conn.commit()
            flash('Password reset successfully! You can now log in.', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))
        else:
            flash('Verification failed. Email and registered college do not match.', 'error')
            cursor.close()
            conn.close()
            
    return render_template('forgot_password.html', colleges=NASHIK_COLLEGES)


# ---- KYC Routes ----

@app.route('/kyc', methods=['GET', 'POST'])
def kyc():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('is_admin'):
        return redirect(url_for('admin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        full_name   = request.form.get('full_name', '').strip()
        phone       = request.form.get('phone', '').strip()
        college_name= request.form.get('college_name', '').strip()
        student_id  = request.form.get('student_id', '').strip()
        doc_file    = request.files.get('document')
        doc_filename = None

        if doc_file and doc_file.filename and allowed_kyc_file(doc_file.filename):
            if not os.path.exists(app.config['KYC_UPLOAD_FOLDER']):
                os.makedirs(app.config['KYC_UPLOAD_FOLDER'])
            safe_name = secure_filename(doc_file.filename)
            doc_filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            doc_file.save(os.path.join(app.config['KYC_UPLOAD_FOLDER'], doc_filename))

        # Check if existing KYC record
        cursor.execute("SELECT id FROM kyc_requests WHERE user_id = %s", (session['user_id'],))
        existing = cursor.fetchone()

        if existing:
            if doc_filename:
                cursor.execute("""
                    UPDATE kyc_requests SET full_name=%s, phone=%s, college_name=%s,
                    student_id=%s, doc_filename=%s, status='pending', admin_note=NULL, submitted_at=NOW()
                    WHERE user_id=%s""",
                    (full_name, phone, college_name, student_id, doc_filename, session['user_id']))
            else:
                cursor.execute("""
                    UPDATE kyc_requests SET full_name=%s, phone=%s, college_name=%s,
                    student_id=%s, status='pending', admin_note=NULL, submitted_at=NOW()
                    WHERE user_id=%s""",
                    (full_name, phone, college_name, student_id, session['user_id']))
        else:
            cursor.execute("""
                INSERT INTO kyc_requests (user_id, full_name, phone, college_name, student_id, doc_filename, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')""",
                (session['user_id'], full_name, phone, college_name, student_id, doc_filename))

        # Handle profile picture upload
        profile_file = request.files.get('profile_pic')
        if profile_file and profile_file.filename and allowed_kyc_file(profile_file.filename):
            safe_prof = secure_filename(profile_file.filename)
            prof_filename = f"avatar_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_prof}"
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            profile_file.save(os.path.join(app.config['UPLOAD_FOLDER'], prof_filename))
            cursor.execute("UPDATE users SET profile_pic=%s WHERE id=%s", (prof_filename, session['user_id']))
            session['profile_pic'] = prof_filename

        conn.commit()
        session['kyc_status'] = 'pending'
        flash('Verification submitted! Admin will review your documents.', 'success')
        cursor.close(); conn.close()
        return redirect(url_for('kyc'))

    # GET – fetch existing record
    cursor.execute("SELECT * FROM kyc_requests WHERE user_id = %s", (session['user_id'],))
    kyc_record = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('kyc.html', kyc=kyc_record)

@app.route('/kyc/doc/<filename>')
def kyc_doc(filename):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return send_from_directory(app.config['KYC_UPLOAD_FOLDER'], filename)

# ---- Profile Routes ----

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('is_admin'):
        return redirect(url_for('admin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM kyc_requests WHERE user_id = %s", (session['user_id'],))
    kyc_record = cursor.fetchone()

    cursor.execute("SELECT * FROM products WHERE seller_id = %s ORDER BY created_at DESC", (session['user_id'],))
    my_listings = cursor.fetchall()
    process_product_images(my_listings)

    # Seller stats
    cursor.execute("SELECT COUNT(*) as cnt FROM products WHERE seller_id = %s AND status='sold'", (session['user_id'],))
    deals_done = cursor.fetchone()['cnt']

    cursor.close(); conn.close()
    return render_template('profile.html', user=user, kyc=kyc_record,
                           my_listings=my_listings, deals_done=deals_done, seller_rating=0.0)

@app.route('/profile/<string:mck_id>')
def public_profile(mck_id):
    if not mck_id.startswith('MCK-'):
        return "Invalid Profile ID", 400
    try:
        user_id = int(mck_id.split('-')[1])
    except:
        return "Invalid Profile ID", 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    profile_user = cursor.fetchone()
    
    if not profile_user:
        cursor.close(); conn.close()
        return "User not found", 404
        
    cursor.execute("SELECT COUNT(*) as cnt FROM products WHERE seller_id=%s AND status='sold'", (user_id,))
    deals_done = cursor.fetchone()['cnt']
    
    cursor.execute("SELECT * FROM products WHERE seller_id=%s AND status='available'", (user_id,))
    listings = cursor.fetchall()
    process_product_images(listings)
        
    cursor.close(); conn.close()
    
    return render_template('public_profile.html', p_user=profile_user, deals=deals_done, req_id=mck_id, listings=listings)

@app.route('/profile/photo', methods=['POST'])
def update_profile_photo():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    profile_file = request.files.get('profile_pic')
    if profile_file and profile_file.filename and allowed_kyc_file(profile_file.filename):
        safe_prof = secure_filename(profile_file.filename)
        prof_filename = f"avatar_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_prof}"
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        profile_file.save(os.path.join(app.config['UPLOAD_FOLDER'], prof_filename))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET profile_pic=%s WHERE id=%s", (prof_filename, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()
        
        session['profile_pic'] = prof_filename
        flash('Profile photo updated successfully!', 'success')
        
    return redirect(url_for('profile'))

@app.route('/profile/edit', methods=['POST'])
def profile_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    username    = request.form.get('username', '').strip()
    phone       = request.form.get('phone', '').strip()
    college     = request.form.get('college', '').strip()
    department  = request.form.get('department', '').strip()
    student_id_num = request.form.get('student_id_num', '').strip()
    course      = request.form.get('course', '').strip()
    batch       = request.form.get('batch', '').strip()
    hostel      = request.form.get('hostel', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET username=%s, phone=%s, college=%s, department=%s,
        student_id_num=%s, course=%s, batch=%s, hostel=%s WHERE id=%s""",
        (username, phone, college, department, student_id_num, course, batch, hostel, session['user_id']))
    conn.commit()
    session['username'] = username
    session['college']  = college
    cursor.close(); conn.close()
    flash('Profile updated!', 'success')
    return redirect(url_for('profile'))

# ---- Favorites Routes ----

@app.route('/favorites')
def favorites():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.* FROM favorites f
        JOIN products p ON f.product_id = p.id
        WHERE f.user_id = %s ORDER BY f.created_at DESC
    """, (session['user_id'],))
    items = cursor.fetchall()
    process_product_images(items)
    cursor.close(); conn.close()
    return render_template('favorites.html', favorites=items)

@app.route('/favorites/toggle/<int:product_id>', methods=['POST'])
def toggle_favorite(product_id):
    if 'user_id' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"status": "error", "message": "Login required"}, 401
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favorites WHERE user_id=%s AND product_id=%s", (session['user_id'], product_id))
    fav = cursor.fetchone()
    
    status = "added"
    if fav:
        cursor.execute("DELETE FROM favorites WHERE id=%s", (fav[0],))
        # flash('Removed from favorites.', 'info') # Removed flash for AJAX to avoid cluttering next page load
        status = "removed"
    else:
        try:
            cursor.execute("INSERT IGNORE INTO favorites (user_id, product_id) VALUES (%s, %s)",
                           (session['user_id'], product_id))
            # flash('Added to favorites!', 'success')
            status = "added"
        except Exception:
            pass
            
    conn.commit()
    cursor.close(); conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"status": "success", "action": status}
        
    return redirect(request.referrer or url_for('products'))

# ---- My Items Route ----

@app.route('/my-items')
def my_items():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE seller_id=%s ORDER BY created_at DESC", (session['user_id'],))
    listings = cursor.fetchall()
    process_product_images(listings)
    available = sum(1 for p in listings if p['status'] == 'available')
    sold      = sum(1 for p in listings if p['status'] == 'sold')
    total_val = sum(float(p['price']) for p in listings if p['status'] == 'available')
    cursor.close(); conn.close()
    stats = {'total': len(listings), 'available': available, 'sold': sold, 'total_value': int(total_val)}
    return render_template('my_items.html', my_listings=listings, stats=stats)

# ---- Leaderboard Route ----

@app.route('/leaderboard')
def leaderboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.username, u.college,
               COUNT(CASE WHEN p.status='sold' THEN 1 END) as deals,
               COUNT(CASE WHEN p.status='available' THEN 1 END) as active
        FROM users u
        LEFT JOIN products p ON p.seller_id = u.id
        WHERE u.is_admin = 0
        GROUP BY u.id
        ORDER BY deals DESC, active DESC
        LIMIT 20
    """)
    leaders = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('leaderboard.html', leaders=leaders)

# ---- My Chats Route ----

@app.route('/my-chats')
def my_chats():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    uid = session['user_id']
    # Get distinct conversations
    cursor.execute("""
        SELECT
            IFNULL(m.product_id, 0) as product_id,
            IFNULL(p.name, 'Admin Support') as product_name,
            CASE WHEN m.sender_id = %s THEN m.receiver_id ELSE m.sender_id END as other_user_id,
            u.username as other_username,
            MAX(m.message) as last_message,
            MAX(m.timestamp) as last_time
        FROM messages m
        LEFT JOIN products p ON m.product_id = p.id
        JOIN users u ON u.id = CASE WHEN m.sender_id = %s THEN m.receiver_id ELSE m.sender_id END
        WHERE (m.sender_id = %s OR m.receiver_id = %s)
        GROUP BY m.product_id, p.name, other_user_id, u.username
        ORDER BY last_time DESC
    """, (uid, uid, uid, uid))
    convs = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('my_chats.html', conversations=convs)

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
    
    # Process product images
    process_product_images(items)
    
    # Sort colleges for easier selection
    sorted_colleges = sorted(NASHIK_COLLEGES)
    
    # Get user's favorite product IDs
    favorite_ids = []
    if session.get('user_id'):
        cursor.execute("SELECT product_id FROM favorites WHERE user_id = %s", (session['user_id'],))
        favorite_ids = [row['product_id'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return render_template('products.html', products=items, colleges=sorted_colleges, current_college=college_filter, favorite_ids=favorite_ids)

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
        
        files = request.files.getlist('image')
        saved_files = []
        for file in files[:5]: # Max 5 images
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                saved_files.append(unique_filename)
        
        image_url = ','.join(saved_files)
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
    if not product:
        conn.close()
        flash('Product not found.', 'error')
        return redirect(url_for('products'))
    
    # Track views (ignore errors if column missing)
    try:
        cursor.execute("UPDATE products SET views = views + 1 WHERE id = %s", (product_id,))
        conn.commit()
    except:
        pass
        
    product['posted_date'] = product['created_at'].strftime('%d/%m/%Y') if product.get('created_at') else datetime.now().strftime('%d/%m/%Y')
    process_product_images(product)
    
    # Get related products (same category)
    cursor.execute("""
        SELECT * FROM products 
        WHERE category = %s AND id != %s AND status = 'available' 
        LIMIT 4
    """, (product['category'], product_id))
    related = cursor.fetchall()
    process_product_images(related)

    # Check if favorited
    user_id = session.get('user_id')
    is_favorited = False
    if user_id:
        cursor.execute("SELECT id FROM favorites WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        is_favorited = True if cursor.fetchone() else False
    
    cursor.close()
    conn.close()
    
    return render_template('product_detail.html', product=product, related=related, is_favorited=is_favorited)

@app.route('/chat/<int:product_id>/<int:receiver_id>', methods=['GET', 'POST'])
def chat(product_id, receiver_id):
    if 'user_id' not in session:
        flash('Please login to message sellers.', 'error')
        return redirect(url_for('login'))

    if session.get('is_admin'):
        flash('Admin chat feature is coming soon within the dashboard.', 'info')
        return redirect(url_for('admin'))
        
    user_id = session['user_id']
    actual_pid = None if product_id == 0 else product_id
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        message = request.form['message']
        cursor.execute("INSERT INTO messages (sender_id, receiver_id, product_id, message) VALUES (%s, %s, %s, %s)",
                       (user_id, receiver_id, actual_pid, message))
        conn.commit()
        
    # Get chat history
    if actual_pid is None:
        cursor.execute("""
            SELECT m.*, u.username as sender_name 
            FROM messages m 
            JOIN users u ON m.sender_id = u.id 
            WHERE m.product_id IS NULL AND (
                (m.sender_id = %s AND m.receiver_id = %s) OR 
                (m.sender_id = %s AND m.receiver_id = %s)
            )
            ORDER BY m.timestamp ASC
        """, (user_id, receiver_id, receiver_id, user_id))
    else:
        cursor.execute("""
            SELECT m.*, u.username as sender_name 
            FROM messages m 
            JOIN users u ON m.sender_id = u.id 
            WHERE m.product_id = %s AND (
                (m.sender_id = %s AND m.receiver_id = %s) OR 
                (m.sender_id = %s AND m.receiver_id = %s)
            )
            ORDER BY m.timestamp ASC
        """, (actual_pid, user_id, receiver_id, receiver_id, user_id))
    messages = cursor.fetchall()
    
    # Get product info
    if actual_pid is None:
        product = {'name': 'Admin Support'}
    else:
        cursor.execute("SELECT name FROM products WHERE id = %s", (actual_pid,))
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
    
    cursor.execute("""
        SELECT u.*, 
        (SELECT status FROM kyc_requests k WHERE k.user_id = u.id ORDER BY k.submitted_at DESC LIMIT 1) as kyc_status 
        FROM users u
    """)
    users = cursor.fetchall()
    
    cursor.execute("SELECT p.*, u.username as seller_name FROM products p JOIN users u ON p.seller_id = u.id ORDER BY p.created_at DESC")
    products = cursor.fetchall()
    process_product_images(products)
    
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

    # KYC Requests
    cursor.execute("""
        SELECT k.*, u.email as user_email
        FROM kyc_requests k
        JOIN users u ON k.user_id = u.id
        WHERE k.status = 'pending'
        ORDER BY k.submitted_at DESC
    """)
    kyc_requests = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as cnt FROM kyc_requests WHERE status = 'pending'")
    kyc_pending_count = cursor.fetchone()['cnt']

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
    return render_template('admin.html', users=users, products=products, stats=stats,
                           recent_messages=recent_messages,
                           kyc_requests=kyc_requests, kyc_pending_count=kyc_pending_count)

@app.route('/admin/kyc-action', methods=['POST'])
def admin_kyc_action():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    kyc_id = request.form['kyc_id']
    action = request.form['action']  # 'approve' or 'reject'
    note   = request.form.get('note', '')

    new_status = 'approved' if action == 'approve' else 'rejected'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kyc_requests SET status=%s, admin_note=%s WHERE id=%s",
                   (new_status, note, kyc_id))
    # Also update user's verification_status in users table
    cursor.execute("UPDATE users SET verification_status=%s WHERE id=(SELECT user_id FROM kyc_requests WHERE id=%s)",
                   (new_status, kyc_id))
    conn.commit()
    cursor.close(); conn.close()
    flash(f'KYC {new_status} successfully!', 'success')
    return redirect(url_for('admin'))

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

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('User removed successfully.', 'success')
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
