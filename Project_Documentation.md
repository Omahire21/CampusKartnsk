# CampusKart - Project Documentation

## 1. Introduction
**CampusKart** is a localized e-commerce marketplace web application designed explicitly for college students. The platform allows students to buy, sell, or exchange used and new items within their educational campus. It promotes affordability and recycling by providing seniors an easy way to sell textbooks, engineering tools, drafters, or electronics to juniors or peers.

## 2. Problem Statement
Every year, college students buy new study materials and engineering equipment, which become useless for them after passing out or moving to the next academic year. Often, they throw these materials away or sell them to scrap dealers at negligible prices. Concurrently, juniors entering the same course struggle to afford expensive new books and tools. There is currently no unified, trusted, and localized platform for students belonging to the same college to discover, buy, and sell these items efficiently among themselves.

## 3. Proposed Solution
CampusKart bridges this gap by creating an exclusive platform meant for college communities. 
- **Direct College Filter:** Students register specifying their college (from a curated list). They can then filter and search for items available exclusively in their college or nearby institutions.
- **Trust Factor:** By implementing a KYC (Know Your Customer) system and a student ID check, the platform verifies user authenticity, building trust that isn't typically available on general classifieds websites.
- **Internal Communication:** An integrated real-time chat system allows buyers and sellers to negotiate without exposing personal contact info initially.

## 4. Technology Stack
- **Frontend / Client-Side**: HTML5, CSS3, JavaScript, Jinja2 Templates (Flask integration)
- **Backend / Server-Side**: Python (3.x) with the **Flask** web framework
- **Database**: MySQL (using `mysql-connector-python`)
- **Web Server Gateway Interface (WSGI)**: Werkzeug / Gunicorn (deployment)
- **Security**: Werkzeug Security (`generate_password_hash`, `check_password_hash`)

## 5. System Architecture & Core Modules

The system is structured as an MVC-like Flask architecture using templates:

### Authentication Module
Handles secure user registration and login. Passwords are encrypted before storing in the MySQL database. Provides session management for authenticated users, along with a "Forgot Password" feature utilizing email and college name verification.

### Product Management Module
Registered students can upload their products. They can add a title, description, category, and up to 5 images for a single item. Sellers can mark their active items as `available` or `sold`. Views on product pages are tracked.

### Search and Filter Module
Provides a powerful search bar to find products by names or keywords. Allows filtering products by standard categories (e.g., Electronics, Notes, Instruments) and college campus.

### Chat & Messaging Module
Buyers can message sellers straight from the product page. The chat history is saved against respective product records, making negotiation contextual and straightforward. Users have a dedicated **"My Chats"** dashboard to track all ongoing conversations.

### Cart and Order Analysis
Students can add multiple products to a shopping cart before deciding to message the respective sellers. There is also an **Orders** page that categorizes user history into "Purchases" (inferred via chat history) and "Sales".

### Admin Panel & KYC Verification
An admin dashboard to govern the platform:
- Overview charts for total active users, available vs sold items, and category distribution.
- Monitor active user chats and items.
- A **KYC Upload module** lets students verify their profiles by uploading a college ID/document, pending admin validation.

## 6. Database Schema Summary
The project works primarily with four tables in MySQL:
- `users`: Stores id, username, email, encrypted password, college, is_admin status, department info, and profile pictures.
- `products`: Stores product listings, linked to the seller via `seller_id` (FOREIGN KEY). Includes columns for price, category, status (`available`/`sold`), views, and college.
- `messages`: Records chat history. Includes `sender_id`, `receiver_id`, `product_id`, and a timestamp. 
- `cart`: Maps a `user_id` to a `product_id` to temporarily save items they are interested in buying.
- `kyc_requests`: Table linking `user_id` to uploaded document verification forms.

## 7. How to Run the Application Locally

1. **Pre-requisites**: Python 3.x and MySQL Server.
2. **Setup Database**: Keep a MySQL server running (port 3306), open `schema.sql` and run it in the MySQL terminal to create the database (`campuskart`) and all required tables.
3. **Environment**: Ensure the credentials in `app.py` or `.env` file match your MySQL credentials (user, password `admin`, database `campuskart`).
4. **Install Dependencies**: Run `pip install -r requirements.txt`.
5. **Start the Flask Server**: Open terminal, navigate to the project directory, and run `python app.py` or `flask run`. 
6. **Access website**: Open a web browser and go to `http://localhost:5000/`.
