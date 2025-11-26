from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import secrets
import os
from functools import wraps
import logging

# تنظیمات logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7  # 7 days

db = SQLAlchemy(app)

# اطلاعات لاگین ادمین - تغییر دهید!
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'GlobalAdmin2024!')

# مدل‌های پایگاه داده
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    user_id = db.Column(db.String(10), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_online = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'user_id': self.user_id,
            'last_seen': self.last_seen.strftime('%H:%M') if self.last_seen else 'آنلاین',
            'is_online': self.is_online
        }

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String(10), nullable=False)
    user2_id = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def get_other_user(self, current_user_id):
        return self.user2_id if self.user1_id == current_user_id else self.user1_id

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    read = db.Column(db.Boolean, default=False)
    message_type = db.Column(db.String(20), default='text')

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(10), nullable=False)
    contact_id = db.Column(db.String(10), nullable=False)
    contact_name = db.Column(db.String(100), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ایجاد پایگاه داده
with app.app_context():
    try:
        db.create_all()
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Database creation error: {str(e)}")

# دکوراتور برای دسترسی ادمین
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('برای دسترسی به این صفحه باید وارد شوید', 'error')
            return redirect('/admin_login')
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('لطفاً ابتدا وارد شوید', 'error')
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
    try:
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if not name or not phone:
            flash('لطفاً نام و شماره تلفن را وارد کنید', 'error')
            return redirect('/')
        
        if len(phone) < 10:
            flash('شماره تلفن معتبر نیست', 'error')
            return redirect('/')
        
        # بررسی کاربر موجود
        existing_user = User.query.filter_by(phone=phone).first()
        
        if existing_user:
            # کاربر موجود
            session['user_id'] = existing_user.user_id
            session['name'] = existing_user.name
            session['is_admin'] = False
            
            # آپدیت وضعیت آنلاین
            existing_user.last_seen = datetime.now(timezone.utc)
            existing_user.is_online = True
            db.session.commit()
            
            flash(f'خوش آمدید {existing_user.name}! شناسه شما: {existing_user.user_id}', 'success')
            logger.info(f"User logged in: {existing_user.name} ({existing_user.user_id})")
        else:
            # کاربر جدید
            user_id = secrets.token_hex(5).upper()
            new_user = User(
                name=name, 
                phone=phone, 
                user_id=user_id,
                is_online=True
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            session['user_id'] = user_id
            session['name'] = name
            session['is_admin'] = False
            
            flash(f'حساب کاربری جدید ایجاد شد! شناسه شما: {user_id} - لطفاً این شناسه را ذخیره کنید', 'success')
            logger.info(f"New user registered: {name} ({user_id})")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Login error: {str(e)}")
        flash('خطا در ورود به سیستم', 'error')
        return redirect('/')
    
    return redirect('/chats')

@app.route('/chats')
@login_required
def chats():
    try:
        user_id = session['user_id']
        
        # آپدیت وضعیت آنلاین
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.last_seen = datetime.now(timezone.utc)
            user.is_online = True
            db.session.commit()
        
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
                             
    except Exception as e:
        logger.error(f"Chats page error: {str(e)}")
        flash('خطا در بارگذاری چت‌ها', 'error')
        return redirect('/')

@app.route('/chat/<other_user_id>')
@login_required
def chat_page(other_user_id):
    try:
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
        if not other_user:
            flash('کاربر یافت نشد', 'error')
            return redirect('/chats')
        
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
                             
    except Exception as e:
        logger.error(f"Chat page error: {str(e)}")
        flash('خطا در بارگذاری چت', 'error')
        return redirect('/chats')

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    try:
        user_id = session['user_id']
        data = request.get_json()
        
        chat_id = data.get('chat_id')
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'message': 'پیام نمی‌تواند خالی باشد'})
        
        if len(content) > 1000:
            return jsonify({'success': False, 'message': 'پیام بسیار طولانی است'})
        
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
        
        logger.info(f"Message sent: {user_id} -> {other_user_id}")
        
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
        logger.error(f"Send message error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در ارسال پیام'})

@app.route('/api/get_new_messages/<int:chat_id>')
@login_required
def get_new_messages(chat_id):
    try:
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
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در دریافت پیام‌ها'})

@app.route('/api/search_user')
@login_required
def search_user():
    try:
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
        
    except Exception as e:
        logger.error(f"Search user error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در جستجو'})

@app.route('/start_chat', methods=['POST'])
@login_required
def start_chat():
    try:
        user_id = session['user_id']
        other_user_id = request.form.get('user_id', '').strip().upper()
        
        if not other_user_id:
            flash('لطفاً شناسه کاربری را وارد کنید', 'error')
            return redirect('/chats')
        
        if other_user_id == user_id:
            flash('نمی‌توانید با خودتان چت کنید', 'error')
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
        
        logger.info(f"Chat started: {user_id} -> {other_user_id}")
        return redirect(f'/chat/{other_user_id}')
        
    except Exception as e:
        logger.error(f"Start chat error: {str(e)}")
        flash('خطا در شروع چت', 'error')
        return redirect('/chats')

# ==================== Admin Routes ====================

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session.permanent = True
            flash('ورود به پنل مدیریت موفقیت‌آمیز بود', 'success')
            logger.info("Admin logged in successfully")
            return redirect('/admin_dashboard')
        else:
            flash('نام کاربری یا رمز عبور اشتباه است', 'error')
            logger.warning(f"Failed admin login attempt: {username}")
    
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    try:
        users = User.query.order_by(User.registration_date.desc()).all()
        messages = Message.query.order_by(Message.timestamp.desc()).limit(100).all()
        chats = Chat.query.all()
        
        # آمار پیشرفته
        online_users = User.query.filter_by(is_online=True).count()
        today = datetime.now(timezone.utc).date()
        today_users = User.query.filter(db.func.date(User.registration_date) == today).count()
        
        stats = {
            'total_users': len(users),
            'total_messages': Message.query.count(),
            'total_chats': len(chats),
            'unread_messages': Message.query.filter_by(read=False).count(),
            'online_users': online_users,
            'today_users': today_users
        }
        
        return render_template('admin_dashboard.html',
                             users=users,
                             messages=messages,
                             chats=chats,
                             stats=stats)
                             
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        flash('خطا در بارگذاری پنل مدیریت', 'error')
        return render_template('admin_dashboard.html', users=[], messages=[], chats=[], stats={})

@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get(user_id)
        
        if user:
            user_info = f"{user.name} ({user.user_id})"
            
            # حذف تمام داده‌های مرتبط
            Chat.query.filter((Chat.user1_id == user.user_id) | (Chat.user2_id == user.user_id)).delete()
            Contact.query.filter((Contact.user_id == user.user_id) | (Contact.contact_id == user.user_id)).delete()
            Message.query.filter(Message.sender_id == user.user_id).delete()
            db.session.delete(user)
            db.session.commit()
            
            flash(f'کاربر {user_info} با موفقیت حذف شد', 'success')
            logger.info(f"Admin deleted user: {user_info}")
        else:
            flash('کاربر یافت نشد', 'error')
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete user error: {str(e)}")
        flash(f'خطا در حذف کاربر: {str(e)}', 'error')
    
    return redirect('/admin_dashboard')

@app.route('/logout')
def logout():
    try:
        # آپدیت وضعیت آفلاین
        if session.get('user_id'):
            user = User.query.filter_by(user_id=session['user_id']).first()
            if user:
                user.last_seen = datetime.now(timezone.utc)
                user.is_online = False
                db.session.commit()
                logger.info(f"User logged out: {user.name} ({user.user_id})")
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
    
    session.clear()
    return redirect('/')

@app.route('/admin_logout')
def admin_logout():
    session.clear()
    flash('با موفقیت از پنل مدیریت خارج شدید', 'success')
    return redirect('/')

# API برای وضعیت آنلاین
@app.route('/api/update_online_status', methods=['POST'])
@login_required
def update_online_status():
    try:
        user_id = session['user_id']
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.last_seen = datetime.now(timezone.utc)
            user.is_online = True
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False})

# خطای 404
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

# خطای 500
@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
