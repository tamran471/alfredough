from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL connection
def create_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Tamran@471",
        database="alfredough_pos"
    )

# Admin login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = %s AND password = %s", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin:
            session['admin'] = admin[0]
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid login")
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

@app.route('/')
def home():
    return render_template('index.html')

# Admin dashboard
@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    def get_stats(start_date):
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders WHERE created_at >= %s", (start_date,))
        count, total = cursor.fetchone()
        return {'orders': count, 'total': total}

    stats = {
        'today': get_stats(today),
        'week': get_stats(start_of_week),
        'month': get_stats(start_of_month)
            # Fetch kitchen stock data
   

    }
     


    cursor.close()
    conn.close()

    return render_template('dashboard.html', stats=stats)


# Add product
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    # Fetch all categories
    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        new_category = request.form.get('new_category').strip()
        category_id = request.form.get('category_id')

        # If a new category is provided
        if new_category:
            cursor.execute("INSERT INTO categories (name) VALUES (%s)", (new_category,))
            conn.commit()
            category_id = cursor.lastrowid  # use new category id
        else:
            category_id = int(category_id)

        # Insert product with selected or new category
        cursor.execute(
            "INSERT INTO products (name, price, category_id) VALUES (%s, %s, %s)",
            (name, price, category_id)
        )
        conn.commit()
        flash('Product added successfully.')
        return redirect(url_for('view_products'))

    cursor.close()
    conn.close()
    return render_template('add_product.html', categories=categories)


# View products
@app.route('/view_products')
def view_products():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    # Fetch categories and products
    cursor.execute("""
        SELECT c.id, c.name, p.id, p.name, p.price
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id
        ORDER BY c.name, p.name
    """)
    rows = cursor.fetchall()

    # Organize data into a dict: {category: [products]}
    category_products = {}
    for cat_id, cat_name, prod_id, prod_name, prod_price in rows:
        if cat_name not in category_products:
            category_products[cat_name] = []
        if prod_id:  # Only add if product exists
            category_products[cat_name].append((prod_id, prod_name, prod_price))

    cursor.close()
    conn.close()
    return render_template('view_products.html', category_products=category_products)


# Create order
@app.route('/create_order', methods=['GET', 'POST'])
def create_order():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.name, p.id, p.name, p.price
        FROM categories c
        JOIN products p ON c.id = p.category_id
        WHERE p.status = 'active'
        ORDER BY c.name, p.name
    """)
    rows = cursor.fetchall()

    category_products = {}
    for cat_name, pid, pname, price in rows:
        if cat_name not in category_products:
            category_products[cat_name] = []
        category_products[cat_name].append((pid, pname, price))

    if request.method == 'POST':
        order_type = request.form['order_type']
        extra_info = {}

        if order_type == 'quick_serve':
            extra_info['table_number'] = request.form['table_number']
            extra_info['waiter_name'] = request.form['waiter_name']
        elif order_type == 'takeaway':
            extra_info['customer_name'] = request.form['customer_name']
            extra_info['customer_contact'] = request.form['customer_contact']
        elif order_type == 'delivery':
            extra_info['rider_name'] = request.form['rider_name']
            extra_info['customer_name'] = request.form['customer_name']
            extra_info['customer_contact'] = request.form['customer_contact']

        order_total = 0
        items = []

        for key in request.form:
            if key.startswith('qty_'):
               pid = key.split('_')[1]
               try:
                   qty = int(request.form[key])
               except ValueError: 
                      qty = 0
               if qty > 0:
                 cursor.execute("SELECT price FROM products WHERE id = %s", (pid,))
                 result = cursor.fetchone()
                 if result:
                     price = result[0]
                     order_total += price * qty
                     items.append((pid, qty))


        cursor.execute("""
            INSERT INTO orders (total_amount, order_type, extra_info)
            VALUES (%s, %s, %s)
        """, (order_total, order_type, str(extra_info)))

        order_id = cursor.lastrowid

        for pid, qty in items:
            for _ in range(qty):
                cursor.execute("INSERT INTO order_items (order_id, product_id) VALUES (%s, %s)", (order_id, pid))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('view_invoice', order_id=order_id))

    cursor.close()
    conn.close()
    return render_template('create_order.html', category_products=category_products)


# View invoice
@app.route('/invoice/<int:order_id>')
def view_invoice(order_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, total_amount, created_at, order_type FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    cursor.execute("""
        SELECT p.name, p.price, COUNT(*) as quantity
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
        GROUP BY p.id
    """, (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('invoice.html', order=order, items=items)

# Generate Invoice Page with Stats
@app.route('/generate_invoice')
def generate_invoice():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    return render_template('generate_invoice.html')

# View Invoices by Date Range
@app.route('/view_invoices/<string:range_type>')
def view_invoices(range_type):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    today = datetime.today()
    if range_type == 'today':
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_type == 'week':
        start = today - timedelta(days=today.weekday())
    elif range_type == 'month':
        start = today.replace(day=1)
    else:
        flash('Invalid range type')
        return redirect(url_for('generate_invoice'))

    cursor.execute("SELECT * FROM orders WHERE created_at >= %s", (start,))
    invoices = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('view_invoices.html', invoices=invoices, range_type=range_type)




#delete product

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    # Delete product from table
    cursor.execute("UPDATE products SET status = 'inactive' WHERE id = %s", (product_id,))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Product deleted successfully.")
    return redirect(url_for('view_products'))

# Kitchen stock
@app.route('/kitchen_stock', methods=['GET', 'POST'])
def kitchen_stock():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form['item_name']
            quantity = float(request.form['quantity'])
            unit = request.form['unit']
            cursor.execute("INSERT INTO kitchen_stock (name, quantity, unit) VALUES (%s, %s, %s)", (name, quantity, unit))
            conn.commit()
            flash(f"{name} ({quantity} {unit}) added to kitchen stock.")


        elif action == 'use':
            stock_id = int(request.form['stock_id'])
            used_qty = float(request.form['used_quantity'])
            cursor.execute("UPDATE kitchen_stock SET quantity = quantity - %s WHERE id = %s AND quantity >= %s", (used_qty, stock_id, used_qty))
            conn.commit()

        elif action == 'update':
            stock_id = int(request.form['stock_id'])
            new_qty = float(request.form['new_quantity'])
            cursor.execute("UPDATE kitchen_stock SET quantity = %s WHERE id = %s", (new_qty, stock_id))
            conn.commit()

        elif action == 'delete':
            stock_id = int(request.form['stock_id'])
            cursor.execute("DELETE FROM kitchen_stock WHERE id = %s", (stock_id,))
            conn.commit()

    cursor.execute("SELECT id, name, quantity, unit FROM kitchen_stock")
    stock_items = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('kitchen_stock.html', stock_items=stock_items)


# Update stock (increase quantity)
@app.route('/update_stock/<int:stock_id>', methods=['POST'])
def update_stock(stock_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    quantity = float(request.form['quantity'])

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kitchen_stock SET quantity = quantity + %s WHERE id = %s", (quantity, stock_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Stock updated successfully.')
    return redirect(url_for('kitchen_stock'))


# Use stock (decrease quantity)
@app.route('/use_stock/<int:stock_id>', methods=['POST'])
def use_stock(stock_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    used_quantity = float(request.form['used_quantity'])

    conn = create_connection()
    cursor = conn.cursor()
    # Prevent going negative
    cursor.execute("UPDATE kitchen_stock SET quantity = GREATEST(0, quantity - %s) WHERE id = %s", (used_quantity, stock_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Stock usage recorded.')
    return redirect(url_for('kitchen_stock'))


# Delete stock item
@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kitchen_stock WHERE id = %s", (stock_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Stock item deleted.')
    return redirect(url_for('kitchen_stock'))




if __name__ == '__main__':
    app.run(debug=True)
