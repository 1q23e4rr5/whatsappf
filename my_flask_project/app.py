from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import os
from functools import wraps

# ایمپورت تنظیمات
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)

# مدل‌های پایگاه داده
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.String(10), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.name} - {self.user_id}>'

class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    receiver_id = db.Column(db.String(10), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<Message {self.sender_id} -> {self.receiver_id}>'

# ایجاد پایگاه داده
def init_database():
    with app.app_context():
        db.create_all()
        print("✅ پایگاه داده ایجاد شد")

# دکوراتور برای دسترسی ادمین
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('لطفاً به عنوان ادمین وارد شوید', 'error')
            return redirect('/admin_login')
        return f(*args, **kwargs)
    return decorated_function

# دکوراتور برای دسترسی کاربران
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('لطفاً ابتدا وارد شوید', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# ==================== Routes ====================

# صفحه اصلی - ورود کاربران
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if not name or not phone:
            flash('لطفاً نام و شماره تلفن را وارد کنید', 'error')
            return render_template('index.html')
        
        # بررسی کاربر موجود
        existing_user = User.query.filter_by(phone=phone).first()
        
        if existing_user:
            session['user_id'] = existing_user.user_id
            session['name'] = existing_user.name
            session['is_admin'] = False
            flash(f'خوش آمدید {existing_user.name}!', 'success')
        else:
            # ایجاد کاربر جدید
            user_id = secrets.token_hex(5).upper()
            new_user = User(name=name, phone=phone, user_id=user_id)
            
            try:
                db.session.add(new_user)
                db.session.commit()
                session['user_id'] = user_id
                session['name'] = name
                session['is_admin'] = False
                flash('حساب کاربری جدید ایجاد شد!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('خطا در ایجاد حساب کاربری', 'error')
                return render_template('index.html')
        
        return redirect('/dashboard')
    
    return render_template('index.html')

# صفحه اصلی کاربر
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    name = session['name']
    
    # دریافت پیام‌ها
    received_messages = PrivateMessage.query.filter_by(
        receiver_id=user_id
    ).order_by(PrivateMessage.timestamp.desc()).all()
    
    sent_messages = PrivateMessage.query.filter_by(
        sender_id=user_id
    ).order_by(PrivateMessage.timestamp.desc()).all()
    
    # علامت‌گذاری پیام‌های خوانده شده
    for message in received_messages:
        if not message.read:
            message.read = True
    db.session.commit()
    
    return render_template('dashboard.html',
                         name=name,
                         user_id=user_id,
                         received_messages=received_messages,
                         sent_messages=sent_messages)

# ارسال پیام
@app.route('/send_message', methods=['GET', 'POST'])
@login_required
def send_message():
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id', '').strip().upper()
        message_text = request.form.get('message', '').strip()
        
        if not receiver_id or not message_text:
            flash('لطفاً شناسه کاربری و متن پیام را وارد کنید', 'error')
            return render_template('send_message.html')
        
        # بررسی وجود کاربر مقصد
        receiver = User.query.filter_by(user_id=receiver_id).first()
        if not receiver:
            flash('کاربری با این شناسه یافت نشد', 'error')
            return render_template('send_message.html')
        
        # ارسال پیام
        new_message = PrivateMessage(
            sender_id=session['user_id'],
            sender_name=session['name'],
            receiver_id=receiver_id,
            message=message_text
        )
        
        try:
            db.session.add(new_message)
            db.session.commit()
            flash(f'پیام با موفقیت برای کاربر {receiver_id} ارسال شد', 'success')
            return redirect('/dashboard')
        except Exception as e:
            db.session.rollback()
            flash('خطا در ارسال پیام', 'error')
    
    return render_template('send_message.html')

# API برای دریافت پیام‌های جدید
@app.route('/api/messages')
@login_required
def get_new_messages():
    user_id = session['user_id']
    
    new_messages = PrivateMessage.query.filter_by(
        receiver_id=user_id, 
        read=False
    ).order_by(PrivateMessage.timestamp.desc()).all()
    
    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': msg.id,
            'sender_name': msg.sender_name,
            'sender_id': msg.sender_id,
            'message': msg.message,
            'timestamp': msg.timestamp.strftime('%Y/%m/%d %H:%M')
        })
        msg.read = True
    
    db.session.commit()
    return jsonify({'success': True, 'messages': messages_data})

# ==================== Admin Routes ====================

# صفحه ورود ادمین
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session['is_admin'] = True
            session['admin_logged_in'] = True
            flash('ورود به پنل مدیریت موفقیت‌آمیز بود', 'success')
            return redirect('/admin_dashboard')
        else:
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    
    return render_template('admin_login.html')

# پنل مدیریت ادمین
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    users = User.query.order_by(User.registration_date.desc()).all()
    messages = PrivateMessage.query.order_by(PrivateMessage.timestamp.desc()).all()
    
    # آمار سیستم
    stats = {
        'total_users': len(users),
        'total_messages': len(messages),
        'unread_messages': PrivateMessage.query.filter_by(read=False).count(),
        'active_today': len([u for u in users if u.registration_date.date() == datetime.utcnow().date()])
    }
    
    return render_template('admin_dashboard.html',
                         users=users,
                         messages=messages,
                         stats=stats)

# حذف کاربر توسط ادمین
@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    
    if user:
        try:
            # حذف پیام‌های مرتبط
            PrivateMessage.query.filter_by(sender_id=user.user_id).delete()
            PrivateMessage.query.filter_by(receiver_id=user.user_id).delete()
            
            # حذف کاربر
            db.session.delete(user)
            db.session.commit()
            
            flash(f'کاربر {user.name} با موفقیت حذف شد', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در حذف کاربر: {str(e)}', 'error')
    else:
        flash('کاربر یافت نشد', 'error')
    
    return redirect('/admin_dashboard')

# حذف پیام توسط ادمین
@app.route('/admin/delete_message/<int:message_id>')
@admin_required
def delete_message(message_id):
    message = PrivateMessage.query.get(message_id)
    
    if message:
        try:
            db.session.delete(message)
            db.session.commit()
            flash('پیام با موفقیت حذف شد', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در حذف پیام: {str(e)}', 'error')
    else:
        flash('پیام یافت نشد', 'error')
    
    return redirect('/admin_dashboard')

# حذف چندین کاربر
@app.route('/admin/delete_multiple_users', methods=['POST'])
@admin_required
def delete_multiple_users():
    user_ids = request.form.getlist('user_ids')
    deleted_count = 0
    
    for user_id in user_ids:
        user = User.query.get(int(user_id))
        if user:
            try:
                # حذف پیام‌های مرتبط
                PrivateMessage.query.filter_by(sender_id=user.user_id).delete()
                PrivateMessage.query.filter_by(receiver_id=user.user_id).delete()
                
                # حذف کاربر
                db.session.delete(user)
                deleted_count += 1
            except Exception as e:
                db.session.rollback()
                flash(f'خطا در حذف کاربر {user.name}', 'error')
                return redirect('/admin_dashboard')
    
    db.session.commit()
    flash(f'{deleted_count} کاربر با موفقیت حذف شدند', 'success')
    return redirect('/admin_dashboard')

# ==================== System Routes ====================

# خروج کاربر
@app.route('/logout')
def logout():
    session.clear()
    flash('با موفقیت خارج شدید', 'info')
    return redirect('/')

# خروج ادمین
@app.route('/admin_logout')
def admin_logout():
    session.clear()
    flash('از پنل مدیریت خارج شدید', 'info')
    return redirect('/')

# صفحه درباره
@app.route('/about')
def about():
    return render_template('about.html')

# ==================== Main ====================

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)