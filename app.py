from flask import Flask, render_template, request, redirect, session, flash
import secrets
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-12345')

# صفحه اصلی
@app.route('/')
def index():
    return render_template('index.html')

# لاگین کاربر
@app.route('/login', methods=['POST'])
def login():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    
    if not name or not phone:
        flash('لطفاً نام و شماره تلفن را وارد کنید', 'error')
        return redirect('/')
    
    # ایجاد شناسه کاربری
    user_id = secrets.token_hex(5).upper()
    session['user_id'] = user_id
    session['name'] = name
    
    flash(f'خوش آمدید {name}! شناسه شما: {user_id}', 'success')
    return redirect('/dashboard')

# صفحه کاربر
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/')
    
    return render_template('dashboard.html', 
                         name=session['name'],
                         user_id=session['user_id'])

# ارسال پیام
@app.route('/send_message', methods=['GET', 'POST'])
def send_message():
    if 'user_id' not in session:
        return redirect('/')
    
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id', '').strip()
        message = request.form.get('message', '').strip()
        
        if receiver_id and message:
            flash(f'پیام به کاربر {receiver_id} ارسال شد', 'success')
            return redirect('/dashboard')
    
    return render_template('send_message.html')

# لاگین ادمین
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == 'admin' and password == 'admin-13899831':
            session['is_admin'] = True
            flash('ورود به پنل مدیریت موفقیت‌آمیز بود', 'success')
            return redirect('/admin_dashboard')
        else:
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    
    return render_template('admin_login.html')

# پنل ادمین
@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect('/admin_login')
    
    return render_template('admin_dashboard.html')

# خروج
@app.route('/logout')
def logout():
    session.clear()
    flash('با موفقیت خارج شدید', 'info')
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)