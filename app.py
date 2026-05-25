import os
import secrets
import random
import smtplib
from email.mime.text import MIMEText
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_from_directory, jsonify)
from werkzeug.utils import secure_filename
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuskart_secret_2026_change_in_prod')

# ── Firebase init ──────────────────────────────────────────────────────────────
from firebase_config import init_firebase
init_firebase()
import firebase_db as fb

# ── File upload config ─────────────────────────────────────────────────────────
if os.environ.get('VERCEL') == '1':
    UPLOAD_FOLDER    = '/tmp/uploads'
    KYC_UPLOAD_FOLDER= '/tmp/kyc_docs'
else:
    UPLOAD_FOLDER    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    KYC_UPLOAD_FOLDER= os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kyc_docs')
ALLOWED_IMG_EXT  = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_KYC_EXT  = {'png', 'jpg', 'jpeg', 'pdf'}
MAX_PRODUCT_IMGS = 5

app.config['UPLOAD_FOLDER']     = UPLOAD_FOLDER
app.config['KYC_UPLOAD_FOLDER'] = KYC_UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER,     exist_ok=True)
os.makedirs(KYC_UPLOAD_FOLDER, exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def allowed_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG_EXT

def allowed_kyc(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_KYC_EXT

def unique_filename(user_id, original):
    safe = secure_filename(original)
    ts   = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    return f"{user_id}_{ts}_{safe}"

def save_local(file_obj, folder, filename):
    path = os.path.join(folder, filename)
    file_obj.save(path)
    return path

def try_upload_to_storage(local_path, blob_name):
    """Try Firebase Storage upload; fall back to local URL on failure."""
    url = fb.upload_file_to_storage(local_path, blob_name)
    return url  # None means local fallback will be used in templates

def process_images(products):
    """Ensure each product has a 'first_image' and 'is_external' field."""
    if products is None:
        return []
    if isinstance(products, dict):
        products = [products]
    for p in products:
        urls = p.get('image_urls') or []
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.split(',') if u.strip()]
        p['image_urls'] = urls
        p['first_image'] = urls[0] if urls else ''
        p['is_external']  = p['first_image'].startswith('http') if p['first_image'] else False
    return products

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Access denied.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ── College list ───────────────────────────────────────────────────────────────
NASHIK_COLLEGES = sorted([
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
    "SVIT Chincholi",
])

# ══════════════════════════════════════════════════════════════════════════════
# INFO & STATIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/safety')
def safety():
    return render_template('safety.html')

@app.route('/rules')
def rules():
    return render_template('rules.html')

# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    products = fb.get_featured_products(10)
    process_images(products)
    fav_ids = fb.get_favorite_product_ids(session['user_id']) if session.get('user_id') else []
    return render_template('index.html', products=products, favorite_ids=fav_ids)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        otp      = request.form.get('otp', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        college  = request.form.get('college', '').strip()

        if not all([username, email, otp, password, college]):
            flash('All fields including OTP are required.', 'error')
            return redirect(url_for('register'))
            
        if session.get('reg_email') != email or session.get('reg_otp') != otp:
            flash('Invalid OTP or Email combination.', 'error')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('register'))

        try:
            fb.create_user(email, password, username, college)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('register'))
    return render_template('register.html', colleges=NASHIK_COLLEGES)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('email', '').strip()
        password   = request.form.get('password', '')
        user = fb.authenticate_user(identifier, password)
        if user:
            session['user_id']    = user['id']   # email
            session['username']   = user['username']
            session['college']    = user['college']
            session['is_admin']   = user.get('is_admin', False)
            session['profile_pic']= user.get('profile_pic', '')
            kyc = fb.get_kyc(user['id'])
            session['kyc_status'] = kyc['status'] if kyc else 'not_submitted'
            flash(f"Welcome back, {user['username']}!", 'success')
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('admin') if user.get('is_admin') else url_for('index'))
        flash('Invalid credentials.', 'error')
        return redirect(url_for('login', **request.args))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/send-otp', methods=['POST'])
def send_otp():
    email = request.json.get('email', '').strip().lower()
    purpose = request.json.get('purpose', 'reset') # 'reset' or 'register'
    if not email:
        return jsonify({'status': 'error', 'message': 'Email required'})
    
    # Check if user exists based on purpose
    user = fb.get_user_by_id(email)
    if purpose == 'reset' and not user:
        return jsonify({'status': 'error', 'message': 'Email not registered'})
    elif purpose == 'register' and user:
        return jsonify({'status': 'error', 'message': 'Email already registered'})

    otp = str(random.randint(100000, 999999))
    if purpose == 'register':
        session['reg_otp'] = otp
        session['reg_email'] = email
        subject = "CampusKart Registration OTP"
        body = f"Welcome to CampusKart!\n\nYour registration OTP is: {otp}\n\nIf you did not request this, please ignore this email."
    else:
        session['reset_otp'] = otp
        session['reset_email'] = email
        subject = "CampusKart Password Reset OTP"
        body = f"Your CampusKart password reset OTP is: {otp}\n\nIf you did not request this, please ignore this email."

    try:
        sender_email = os.environ.get('SMTP_EMAIL', '')
        sender_pass = os.environ.get('SMTP_PASSWORD', '')
        if sender_email and sender_pass:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = email

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender_email, sender_pass)
                server.send_message(msg)
            return jsonify({'status': 'success', 'message': 'OTP sent to your email successfully.'})
        else:
            # Fallback for local development
            print(f"==============\nMOCK OTP for {email}: {otp}\n==============")
            return jsonify({'status': 'success', 'message': 'SMTP not configured. OTP printed to console for testing.'})
    except Exception as e:
        print(f"SMTP Error: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to send email. Check SMTP settings.'})

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email       = request.form.get('email', '').strip().lower()
        otp         = request.form.get('otp', '').strip()
        new_password= request.form.get('new_password', '')
        
        # Verify OTP
        if session.get('reset_email') != email or session.get('reset_otp') != otp:
            flash('Invalid OTP or Email combination.', 'error')
            return redirect(url_for('forgot_password'))

        if len(new_password.strip()) < 8:
            flash('New password must be at least 8 characters long and cannot be just spaces.', 'error')
            return redirect(url_for('forgot_password'))
            
        # Bypass college check since OTP is verified
        user = fb.get_user_by_id(email)
        if user and fb.reset_password(email, user.get('college', ''), new_password):
            session.pop('reset_otp', None)
            session.pop('reset_email', None)
            flash('Password reset successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        flash('Password reset failed.', 'error')
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html', colleges=NASHIK_COLLEGES)


# ══════════════════════════════════════════════════════════════════════════════
# KYC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    if session.get('is_admin'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        full_name   = request.form.get('full_name', '').strip()
        phone       = request.form.get('phone', '').strip()
        college_name= request.form.get('college_name', '').strip()
        student_id  = request.form.get('student_id', '').strip()
        doc_file    = request.files.get('document')
        doc_url     = None

        if doc_file and doc_file.filename and allowed_kyc(doc_file.filename):
            fname     = unique_filename(session['user_id'], doc_file.filename)
            local_path= save_local(doc_file, KYC_UPLOAD_FOLDER, fname)
            # Try Firebase Storage; fall back to local filename
            uploaded  = fb.upload_file_to_storage(local_path, f"kyc_docs/{fname}")
            doc_url   = uploaded if uploaded else fname

        # Profile picture
        prof_file = request.files.get('profile_pic')
        if prof_file and prof_file.filename and allowed_kyc(prof_file.filename):
            pfname    = f"avatar_{unique_filename(session['user_id'], prof_file.filename)}"
            plocal    = save_local(prof_file, UPLOAD_FOLDER, pfname)
            pu        = fb.upload_file_to_storage(plocal, f"avatars/{pfname}")
            pic_url   = pu if pu else pfname
            fb.update_user(session['user_id'], {'profile_pic': pic_url})
            session['profile_pic'] = pic_url

        try:
            fb.submit_kyc(session['user_id'], full_name, phone, college_name, student_id, doc_url)
            session['kyc_status'] = 'pending'
            flash('Verification submitted! Admin will review your documents.', 'success')
            return redirect(url_for('kyc'))
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('kyc'))

    kyc_record = fb.get_kyc(session['user_id'])
    return render_template('kyc.html', kyc=kyc_record)


@app.route('/kyc/doc/<path:filename>')
@login_required
def kyc_doc(filename):
    # Security: only owner or admin can access
    user_id = session['user_id']
    kyc_record = fb.get_kyc(user_id)
    is_owner = kyc_record and kyc_record.get('doc_filename', '').endswith(filename)
    if not is_owner and not session.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    return send_from_directory(KYC_UPLOAD_FOLDER, filename)


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/profile')
@login_required
def profile():
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    user     = fb.get_user_by_id(session['user_id'])
    if user:
        session['kyc_status'] = user.get('verification_status', 'unverified')
    kyc_rec  = fb.get_kyc(session['user_id'])
    listings = fb.get_products_by_seller(session['user_id'])
    process_images(listings)
    deals_done = sum(1 for p in listings if p.get('status') == 'sold')
    return render_template('profile.html', user=user, kyc=kyc_rec,
                           my_listings=listings, deals_done=deals_done, seller_rating=0.0)


@app.route('/profile/<string:mck_id>')
def public_profile(mck_id):
    if not mck_id.startswith('MCK-'):
        return 'Invalid Profile ID', 400
    try:
        user_email_or_id = mck_id[4:]  # after 'MCK-'
    except Exception:
        return 'Invalid Profile ID', 400

    # Support sequential MCK-ID lookup first, then legacy MCK-<email>
    profile_user = fb.get_user_by_mck_id(mck_id)
    if not profile_user:
        profile_user = fb.get_user_by_id(user_email_or_id)

    if not profile_user:
        return 'User not found', 404

    seller_id = profile_user.get('id') or profile_user.get('email')
    listings = fb.get_products_by_seller(seller_id)
    process_images(listings)
    deals = sum(1 for p in listings if p.get('status') == 'sold')
    available = [p for p in listings if p.get('status') == 'available']
    return render_template('public_profile.html', p_user=profile_user,
                           deals=deals, req_id=mck_id, listings=available)


@app.route('/profile/photo', methods=['POST'])
@login_required
def update_profile_photo():
    prof_file = request.files.get('profile_pic')
    if prof_file and prof_file.filename and allowed_kyc(prof_file.filename):
        pfname = f"avatar_{unique_filename(session['user_id'], prof_file.filename)}"
        plocal = save_local(prof_file, UPLOAD_FOLDER, pfname)
        pu     = fb.upload_file_to_storage(plocal, f"avatars/{pfname}")
        pic_url= pu if pu else pfname
        fb.update_user(session['user_id'], {'profile_pic': pic_url})
        session['profile_pic'] = pic_url
        flash('Profile photo updated!', 'success')
    return redirect(url_for('profile'))


@app.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    fields = ['username', 'phone', 'college', 'department', 'student_id_num', 'course', 'batch', 'hostel']
    data   = {f: request.form.get(f, '').strip() for f in fields}
    fb.update_user(session['user_id'], data)
    session['username'] = data['username']
    session['college']  = data['college']
    flash('Profile updated!', 'success')
    return redirect(url_for('profile'))


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTS ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/products')
def products():
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    category       = request.args.get('category')
    search         = request.args.get('search')
    college_filter = request.args.get('college')

    items = fb.get_all_products(category=category, search=search, college=college_filter)
    process_images(items)
    fav_ids = fb.get_favorite_product_ids(session['user_id']) if session.get('user_id') else []
    return render_template('products.html', products=items, colleges=NASHIK_COLLEGES,
                           current_college=college_filter, favorite_ids=fav_ids)


@app.route('/add-product', methods=['GET', 'POST'])
@login_required
def add_product():
    if session.get('is_admin'):
        flash('Admins cannot list products.', 'error')
        return redirect(url_for('admin'))

    if request.method == 'POST':
        name       = request.form.get('name', '').strip()
        price_raw  = request.form.get('price', '0').strip()
        description= request.form.get('description', '').strip()
        usage_info = request.form.get('usage_info', '').strip()
        category   = request.form.get('category', '').strip()

        if not all([name, description, category]):
            flash('Name, description, and category are required.', 'error')
            return redirect(url_for('add_product'))
        try:
            price = float(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            flash('Enter a valid price.', 'error')
            return redirect(url_for('add_product'))

        files       = request.files.getlist('image')
        image_urls  = []
        for f in files[:MAX_PRODUCT_IMGS]:
            if f and f.filename and allowed_img(f.filename):
                fname  = unique_filename(session['user_id'], f.filename)
                lpath  = save_local(f, UPLOAD_FOLDER, fname)
                url    = fb.upload_file_to_storage(lpath, f"products/{fname}")
                image_urls.append(url if url else fname)

        user = fb.get_user_by_id(session['user_id'])
        fb.create_product(
            seller_id   = session['user_id'],
            seller_name = session['username'],
            name        = name,
            price       = price,
            description = description,
            category    = category,
            usage_info  = usage_info,
            image_urls  = image_urls,
            college     = user.get('college', session.get('college', '')),
        )
        flash('Product listed successfully!', 'success')
        return redirect(url_for('products'))

    return render_template('add_product.html')


@app.route('/product/<string:product_id>')
def product_detail(product_id):
    if not session.get('user_id'):
        flash('Please create an account to view product details.', 'info')
        return redirect(url_for('register'))
    product = fb.get_product(product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('products'))

    fb.increment_product_views(product_id)
    process_images(product)
    ca = product.get('created_at')
    product['posted_date'] = ca.strftime('%d/%m/%Y') if hasattr(ca, 'strftime') else str(ca)[:10]

    related = fb.get_related_products(product.get('category', ''), product_id)
    process_images(related)

    is_favorited = fb.is_favorited(session['user_id'], product_id) if session.get('user_id') else False
    seller = fb.get_user_by_id(product.get('seller_id', '')) or {}
    product['seller_name']  = seller.get('username', 'Unknown')
    product['seller_email'] = seller.get('email', '')

    return render_template('product_detail.html', product=product,
                           related=related, is_favorited=is_favorited)


@app.route('/product/mark-sold/<string:product_id>')
@login_required
def mark_product_sold(product_id):
    success = fb.mark_product_sold(product_id, session['user_id'])
    flash('Product marked as sold!' if success else 'You can only mark your own products as sold.', 
          'success' if success else 'error')
    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/product/delete/<string:product_id>', methods=['POST'])
@login_required
def delete_own_product(product_id):
    product = fb.get_product(product_id)
    if product and product.get('seller_id') == session['user_id']:
        fb.delete_product(product_id)
        flash('Product deleted.', 'success')
    else:
        flash('Unauthorized.', 'error')
    return redirect(url_for('my_items'))


# ══════════════════════════════════════════════════════════════════════════════
# FAVORITES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/favorites')
@login_required
def favorites():
    items = fb.get_favorite_products(session['user_id'])
    process_images(items)
    return render_template('favorites.html', favorites=items)


@app.route('/favorites/toggle/<string:product_id>', methods=['POST'])
def toggle_favorite(product_id):
    if 'user_id' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Login required'}), 401
        return redirect(url_for('login'))
    action = fb.toggle_favorite(session['user_id'], product_id)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': action})
    return redirect(request.referrer or url_for('products'))


# ══════════════════════════════════════════════════════════════════════════════
# MY ITEMS / CHATS / LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/my-items')
@login_required
def my_items():
    listings = fb.get_products_by_seller(session['user_id'])
    process_images(listings)
    available  = sum(1 for p in listings if p.get('status') == 'available')
    sold       = sum(1 for p in listings if p.get('status') == 'sold')
    total_val  = sum(float(p.get('price', 0)) for p in listings if p.get('status') == 'available')
    stats = {'total': len(listings), 'available': available, 'sold': sold, 'total_value': int(total_val)}
    return render_template('my_items.html', my_listings=listings, stats=stats)


@app.route('/leaderboard')
@login_required
def leaderboard():
    leaders = fb.get_leaderboard(20)
    return render_template('leaderboard.html', leaders=leaders)


@app.route('/my-chats')
@login_required
def my_chats():
    convs = fb.get_user_conversations(session['user_id'])
    return render_template('my_chats.html', conversations=convs)


@app.route('/chat/<string:product_id>/<string:receiver_id>', methods=['GET', 'POST'])
@login_required
def chat(product_id, receiver_id):
    if session.get('is_admin'):
        flash('Use admin dashboard to message students.', 'info')
        return redirect(url_for('admin'))

    user_id  = session['user_id']
    real_pid = None if product_id == '0' else product_id

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            fb.send_message(user_id, session['username'], receiver_id, message, real_pid)
        return redirect(url_for('chat', product_id=product_id, receiver_id=receiver_id))

    messages  = fb.get_messages(user_id, receiver_id, real_pid)

    # Mark messages FROM receiver as read (receiver = the other person's msgs we are now viewing)
    fb.mark_messages_read(receiver_id, user_id, real_pid)

    product   = fb.get_product(real_pid) if real_pid else {'name': 'Admin Support', 'id': '0'}
    receiver  = fb.get_user_by_id(receiver_id) or {'username': receiver_id}
    return render_template('chat.html', messages=messages, product=product,
                           receiver=receiver, product_id=product_id, receiver_id=receiver_id,
                           my_id=user_id)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin():
    users    = fb.get_all_users()
    products = fb.get_all_products_admin()
    process_images(products)

    # Enrich products with seller name
    for p in products:
        seller = fb.get_user_by_id(p.get('seller_id', '')) or {}
        p['seller_name'] = seller.get('username', 'Unknown')

    # Pre-calculate user metrics
    for u in users:
        u['listing_count'] = len([p for p in products if p.get('seller_id') == u['id']])
        u['report_count'] = 0

    cat_data  = fb.get_category_stats()
    kyc_reqs  = fb.get_pending_kyc_requests()
    all_conversations = fb.get_all_conversations()
    admin_inbox = fb.get_user_conversations(session['user_id'])
    kyc_count = fb.get_pending_kyc_count()
    kyc_requests = fb.get_all_kyc_requests()
    reports = fb.get_all_reports()
    
    # Calculate stats
    stats = {
        'total_users': len(users),
        'total_products': len(products),
        'pending_kyc': len([k for k in kyc_requests if k.get('status') == 'pending']),
        'total_reports': len(reports),
        'user_count': len(users),
        'available_count': len([p for p in products if p.get('status') == 'available']),
        'sold_count': len([p for p in products if p.get('status') == 'sold']),
        'cat_labels': list(cat_data.keys()),
        'cat_counts': list(cat_data.values())
    }
    
    # Enrich reports with username if available
    user_map = {u['id']: u['username'] for u in users}
    for rep in reports:
        rep['reporter_name'] = user_map.get(rep.get('reporter_id'), 'Unknown')
        rep['reported_name'] = user_map.get(rep.get('reported_id'), 'Unknown')
        # Increment report count for reported user
        reported_user = next((u for u in users if u['id'] == rep.get('reported_id')), None)
        if reported_user:
            reported_user['report_count'] = reported_user.get('report_count', 0) + 1

    return render_template('admin.html', users=users, products=products, stats=stats,
                           all_conversations=all_conversations,
                           admin_inbox=admin_inbox,
                           kyc_requests=kyc_requests, kyc_pending_count=stats['pending_kyc'],
                           reports=reports)


@app.route('/admin/kyc-action', methods=['POST'])
@admin_required
def admin_kyc_action():
    user_id = request.form.get('user_id', '')
    action  = request.form.get('action', '')
    note    = request.form.get('note', '')
    fb.admin_kyc_action(user_id, action, note)
    flash(f"KYC {'approved' if action == 'approve' else 'rejected'} successfully!", 'success')
    return redirect(url_for('admin'))


@app.route('/admin/send-message', methods=['POST'])
@admin_required
def send_admin_message():
    receiver_id  = request.form.get('user_id', '')
    message_text = request.form.get('message', '').strip()
    if message_text:
        fb.send_message(session['user_id'], 'Admin', receiver_id,
                        message_text, product_id=None)
    flash('Message sent to student!', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/delete-product/<string:product_id>')
@admin_required
def delete_product(product_id):
    fb.delete_product(product_id)
    flash('Product deleted.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/toggle-status/<string:product_id>', methods=['POST'])
@admin_required
def admin_toggle_status(product_id):
    product = fb.get_product(product_id)
    if product:
        new_status = 'sold' if product.get('status') == 'available' else 'available'
        fb.update_product(product_id, {'status': new_status})
        flash(f'Product marked as {new_status}.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/delete-user/<string:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    fb.delete_user(user_id)
    flash('User and all associated data deleted.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/promote/<string:user_id>', methods=['POST'])
@admin_required
def promote_user(user_id):
    fb.promote_to_admin(user_id)
    flash('User has been successfully promoted to Admin.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete-report/<string:report_id>', methods=['POST'])
@admin_required
def delete_report(report_id):
    fb.delete_report(report_id)
    flash('Report dismissed successfully.', 'success')
    return redirect(url_for('admin'))

@app.route('/report-user', methods=['POST'])
@login_required
def report_user():
    data = request.get_json()
    reported_id = data.get('reported_id')
    reason = data.get('reason')
    if not reported_id or not reason:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400
    
    fb.report_user(session['user_id'], reported_id, reason)
    return jsonify({'status': 'success'})


# ══════════════════════════════════════════════════════════════════════════════
# STATIC / INFO PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        flash('Message received! We will get back to you soon.', 'success')
        return redirect(url_for('index'))
    return render_template('contact.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ══════════════════════════════════════════════════════════════════════════════
# PRESENCE API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/presence/ping', methods=['POST'])
def presence_ping():
    """Update current user's last_active timestamp."""
    if 'user_id' not in session:
        return jsonify({'status': 'error'}), 401
    from firebase_config import get_firestore_db
    db = get_firestore_db()
    db.collection('presence').document(session['user_id']).set({
        'last_active': datetime.utcnow(),
        'username': session.get('username', '')
    })
    return jsonify({'status': 'ok'})


@app.route('/api/presence/<path:user_id>')
def presence_check(user_id):
    """Return online status of a user. Online = active within last 3 minutes."""
    from firebase_config import get_firestore_db
    from datetime import timedelta
    db = get_firestore_db()
    doc = db.collection('presence').document(user_id).get()
    if not doc.exists:
        return jsonify({'online': False, 'last_seen': None})
    data = doc.to_dict()
    last_active = data.get('last_active')
    if last_active and (datetime.utcnow() - last_active.replace(tzinfo=None)) < timedelta(minutes=3):
        return jsonify({'online': True})
    return jsonify({'online': False, 'last_seen': str(last_active)[:16] if last_active else None})


@app.route('/api/search')
def api_search():
    """Live search API — returns up to 8 matching products as JSON."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    results = fb.get_all_products(search=q, limit=8)
    output = []
    for p in results:
        images = p.get('image_urls') or []
        first_img = images[0] if images else None
        is_external = bool(first_img and (first_img.startswith('http://') or first_img.startswith('https://')))
        output.append({
            'id': p.get('id'),
            'name': p.get('name', ''),
            'price': p.get('price', 0),
            'image': first_img,
            'is_external': is_external,
            'college': p.get('college', ''),
        })
    return jsonify(output)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    debug = os.environ.get('FLASK_ENV', 'development') != 'production'
    app.run(debug=debug, port=5000)
