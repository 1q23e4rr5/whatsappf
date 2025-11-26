from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import os
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-12345-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///whatsapp.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# اطلاعات لاگین ادمین
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-13899831"

# مدل‌های پایگاه داده
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    user_id = db.Column(db.String(10), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'user_id': self.user_id,
            'last_seen': self.last_seen.strftime('%H:%M') if self.last_seen else 'آنلاین'
        }

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String(10), nullable=False)
    user2_id = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_other_user(self, current_user_id):
        return self.user2_id if self.user1_id == current_user_id else self.user1_id

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(10), nullable=False)
    contact_id = db.Column(db.String(10), nullable=False)
    contact_name = db.Column(db.String(100), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

# ایجاد پایگاه داده
with app.app_context():
    db.create_all()

# دکوراتور برای دسترسی ادمین
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect('/admin_login')
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# ==================== Routes ====================

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect('/chats')
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    
    if not name or not phone:
        flash('لطفاً نام و شماره تلفن را وارد کنید', 'error')
        return redirect('/')
    
    # بررسی کاربر موجود
    existing_user = User.query.filter_by(phone=phone).first()
    
    if existing_user:
        # کاربر موجود
        session['user_id'] = existing_user.user_id
        session['name'] = existing_user.name
        session['is_admin'] = False
        
        # آپدیت last_seen
        existing_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        flash(f'خوش آمدید {existing_user.name}! شناسه شما: {existing_user.user_id}', 'success')
    else:
        # کاربر جدید
        user_id = secrets.token_hex(5).upper()
        new_user = User(name=name, phone=phone, user_id=user_id)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            session['user_id'] = user_id
            session['name'] = name
            session['is_admin'] = False
            
            # نمایش شناسه کاربری جدید به کاربر
            flash(f'حساب کاربری جدید ایجاد شد! شناسه شما: {user_id} - لطفاً این شناسه را ذخیره کنید', 'success')
        except Exception as e:
            db.session.rollback()
            flash('خطا در ایجاد حساب کاربری', 'error')
            return redirect('/')
    
    return redirect('/chats')

# صفحه چت‌ها (لیست مخاطبین)
@app.route('/chats')
@login_required
def chats():
    user_id = session['user_id']
    
    # دریافت تمام چت‌های کاربر
    user_chats = Chat.query.filter(
        (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
    ).all()
    
    # ساخت لیست چت‌ها با آخرین پیام
    chats_data = []
    for chat in user_chats:
        other_user_id = chat.get_other_user(user_id)
        other_user = User.query.filter_by(user_id=other_user_id).first()
        
        if other_user:
            # دریافت آخرین پیام
            last_message = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.desc()).first()
            
            # تعداد پیام‌های خوانده نشده
            unread_count = Message.query.filter_by(
                chat_id=chat.id, 
                sender_id=other_user_id,
                read=False
            ).count()
            
            chats_data.append({
                'chat_id': chat.id,
                'other_user': other_user.to_dict(),
                'last_message': {
                    'content': last_message.content if last_message else 'شروع گفتگو',
                    'timestamp': last_message.timestamp.strftime('%H:%M') if last_message else '',
                    'is_me': last_message.sender_id == user_id if last_message else False
                },
                'unread_count': unread_count
            })
    
    # مرتب‌سازی بر اساس آخرین پیام
    chats_data.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message']['timestamp'] else '', reverse=True)
    
    return render_template('chats.html',
                         user_name=session['name'],
                         user_id=session['user_id'],
                         chats=chats_data)

# صفحه چت با کاربر خاص
@app.route('/chat/<other_user_id>')
@login_required
def chat_page(other_user_id):
    user_id = session['user_id']
    
    # پیدا کردن یا ایجاد چت
    chat = Chat.query.filter(
        ((Chat.user1_id == user_id) & (Chat.user2_id == other_user_id)) |
        ((Chat.user1_id == other_user_id) & (Chat.user2_id == user_id))
    ).first()
    
    if not chat:
        # ایجاد چت جدید
        other_user = User.query.filter_by(user_id=other_user_id).first()
        if not other_user:
            flash('کاربر یافت نشد', 'error')
            return redirect('/chats')
        
        chat = Chat(user1_id=user_id, user2_id=other_user_id)
        db.session.add(chat)
        db.session.commit()
        
        # اضافه کردن به مخاطبین
        existing_contact = Contact.query.filter_by(user_id=user_id, contact_id=other_user_id).first()
        if not existing_contact:
            contact = Contact(user_id=user_id, contact_id=other_user_id, contact_name=other_user.name)
            db.session.add(contact)
            db.session.commit()
    
    # دریافت تمام پیام‌های این چت
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.asc()).all()
    
    # علامت‌گذاری پیام‌ها به عنوان خوانده شده
    unread_messages = Message.query.filter_by(chat_id=chat.id, sender_id=other_user_id, read=False).all()
    for msg in unread_messages:
        msg.read = True
    db.session.commit()
    
    # اطلاعات کاربر مقابل
    other_user = User.query.filter_by(user_id=other_user_id).first()
    
    # دریافت لیست چت‌ها برای سایدبار
    user_chats = Chat.query.filter(
        (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
    ).all()
    
    chats_data = []
    for user_chat in user_chats:
        chat_other_user_id = user_chat.get_other_user(user_id)
        chat_other_user = User.query.filter_by(user_id=chat_other_user_id).first()
        
        if chat_other_user:
            last_msg = Message.query.filter_by(chat_id=user_chat.id).order_by(Message.timestamp.desc()).first()
            unread_count = Message.query.filter_by(chat_id=user_chat.id, sender_id=chat_other_user_id, read=False).count()
            
            chats_data.append({
                'chat_id': user_chat.id,
                'other_user': chat_other_user.to_dict(),
                'last_message': {
                    'content': last_msg.content if last_msg else 'شروع گفتگو',
                    'timestamp': last_msg.timestamp.strftime('%H:%M') if last_msg else '',
                    'is_me': last_msg.sender_id == user_id if last_msg else False
                },
                'unread_count': unread_count
            })
    
    chats_data.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message']['timestamp'] else '', reverse=True)
    
    return render_template('chat.html',
                         user_name=session['name'],
                         user_id=session['user_id'],
                         other_user=other_user.to_dict(),
                         messages=messages,
                         chat_id=chat.id,
                         chats=chats_data)

# API برای ارسال پیام
@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    user_id = session['user_id']
    data = request.get_json()
    
    chat_id = data.get('chat_id')
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'success': False, 'message': 'پیام نمی‌تواند خالی باشد'})
    
    try:
        # پیدا کردن چت
        chat = Chat.query.get(chat_id)
        if not chat:
            return jsonify({'success': False, 'message': 'چت یافت نشد'})
        
        # پیدا کردن کاربر مقابل
        other_user_id = chat.get_other_user(user_id)
        
        # ایجاد پیام جدید
        new_message = Message(
            chat_id=chat_id,
            sender_id=user_id,
            sender_name=session['name'],
            content=content
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': new_message.id,
                'content': new_message.content,
                'sender_id': new_message.sender_id,
                'sender_name': new_message.sender_name,
                'timestamp': new_message.timestamp.strftime('%H:%M'),
                'is_me': True
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'خطا در ارسال پیام'})

# API برای دریافت پیام‌های جدید
@app.route('/api/get_new_messages/<int:chat_id>')
@login_required
def get_new_messages(chat_id):
    user_id = session['user_id']
    
    # دریافت پیام‌های جدید
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp.asc()).all()
    
    # علامت‌گذاری پیام‌های دریافتی به عنوان خوانده شده
    chat = Chat.query.get(chat_id)
    other_user_id = chat.get_other_user(user_id)
    unread_messages = Message.query.filter_by(chat_id=chat_id, sender_id=other_user_id, read=False).all()
    for msg in unread_messages:
        msg.read = True
    db.session.commit()
    
    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'is_me': msg.sender_id == user_id,
            'read': msg.read
        })
    
    return jsonify({'success': True, 'messages': messages_data})

# API برای جستجوی کاربر
@app.route('/api/search_user')
@login_required
def search_user():
    query = request.args.get('q', '').strip()
    user_id = session['user_id']
    
    if not query or len(query) < 2:
        return jsonify({'success': True, 'users': []})
    
    # جستجو در کاربران
    users = User.query.filter(
        (User.user_id.contains(query)) | (User.name.contains(query))
    ).filter(User.user_id != user_id).limit(10).all()
    
    users_data = [user.to_dict() for user in users]
    
    return jsonify({'success': True, 'users': users_data})

# شروع چت جدید
@app.route('/start_chat', methods=['POST'])
@login_required
def start_chat():
    user_id = session['user_id']
    other_user_id = request.form.get('user_id', '').strip().upper()
    
    if not other_user_id:
        flash('لطفاً شناسه کاربری را وارد کنید', 'error')
        return redirect('/chats')
    
    # بررسی وجود کاربر
    other_user = User.query.filter_by(user_id=other_user_id).first()
    if not other_user:
        flash('کاربری با این شناسه یافت نشد', 'error')
        return redirect('/chats')
    
    # پیدا کردن یا ایجاد چت
    chat = Chat.query.filter(
        ((Chat.user1_id == user_id) & (Chat.user2_id == other_user_id)) |
        ((Chat.user1_id == other_user_id) & (Chat.user2_id == user_id))
    ).first()
    
    if not chat:
        chat = Chat(user1_id=user_id, user2_id=other_user_id)
        db.session.add(chat)
        db.session.commit()
        
        # اضافه کردن به مخاطبین
        existing_contact = Contact.query.filter_by(user_id=user_id, contact_id=other_user_id).first()
        if not existing_contact:
            contact = Contact(user_id=user_id, contact_id=other_user_id, contact_name=other_user.name)
            db.session.add(contact)
            db.session.commit()
    
    return redirect(f'/chat/{other_user_id}')

# ==================== Admin Routes ====================

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('ورود به پنل مدیریت موفقیت‌آمیز بود', 'success')
            return redirect('/admin_dashboard')
        else:
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    users = User.query.order_by(User.registration_date.desc()).all()
    messages = Message.query.order_by(Message.timestamp.desc()).all()
    chats = Chat.query.all()
    
    stats = {
        'total_users': len(users),
        'total_messages': len(messages),
        'total_chats': len(chats),
        'unread_messages': Message.query.filter_by(read=False).count(),
    }
    
    return render_template('admin_dashboard.html',
                         users=users,
                         messages=messages,
                         chats=chats,
                         stats=stats)

@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    
    if user:
        try:
            # حذف تمام داده‌های مرتبط
            Chat.query.filter((Chat.user1_id == user.user_id) | (Chat.user2_id == user.user_id)).delete()
            Contact.query.filter((Contact.user_id == user.user_id) | (Contact.contact_id == user.user_id)).delete()
            Message.query.filter(Message.sender_id == user.user_id).delete()
            db.session.delete(user)
            db.session.commit()
            
            flash(f'کاربر {user.name} با موفقیت حذف شد', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در حذف کاربر: {str(e)}', 'error')
    
    return redirect('/admin_dashboard')

@app.route('/logout')
def logout():
    # آپدیت last_seen قبل از خروج
    if session.get('user_id'):
        user = User.query.filter_by(user_id=session['user_id']).first()
        if user:
            user.last_seen = datetime.utcnow()
            db.session.commit()
    
    session.clear()
    return redirect('/')

@app.route('/admin_logout')
def admin_logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
