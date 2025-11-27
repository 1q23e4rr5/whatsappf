from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import secrets
import os
import json
from functools import wraps
import logging
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import re

# تنظیمات logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# تنظیم دیتابیس برای Render
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mailgram.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# ایجاد پوشه آپلود
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# اطلاعات لاگین ادمین (ثابت - پاک نمی‌شود)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("MailGramAdmin2024!")

# مدل‌های پایگاه داده
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    user_id = db.Column(db.String(10), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    registration_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_online = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
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
    last_activity = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def get_other_user(self, current_user_id):
        return self.user2_id if self.user1_id == current_user_id else self.user1_id

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    read = db.Column(db.Boolean, default=False)
    delivered = db.Column(db.Boolean, default=False)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.String(10), nullable=False)
    group_id = db.Column(db.String(15), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.String(15), nullable=False)
    user_id = db.Column(db.String(10), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_admin = db.Column(db.Boolean, default=False)

class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.String(15), nullable=False)
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    read_by = db.Column(db.Text, default='[]')  # JSON list of user_ids who read the message

class MessageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_type = db.Column(db.String(20), nullable=False)  # private, group
    sender_id = db.Column(db.String(10), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    receiver_id = db.Column(db.String(100), nullable=False)  # user_id or group_id
    content = db.Column(db.Text, nullable=False)
    message_type_detail = db.Column(db.String(20), default='text')
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address = db.Column(db.String(45), nullable=True)

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
        password = request.form.get('password', '').strip()
        
        if not name or not phone or not password:
            flash('لطفاً تمام فیلدها را پر کنید', 'error')
            return redirect('/')
        
        if len(phone) < 10:
            flash('شماره تلفن معتبر نیست', 'error')
            return redirect('/')
        
        if len(password) < 4:
            flash('رمز عبور باید حداقل 4 کاراکتر باشد', 'error')
            return redirect('/')
        
        # بررسی کاربر موجود
        existing_user = User.query.filter_by(phone=phone).first()
        
        if existing_user:
            # بررسی رمز عبور
            if check_password_hash(existing_user.password_hash, password):
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
                flash('رمز عبور اشتباه است', 'error')
                return redirect('/')
        else:
            # کاربر جدید
            user_id = secrets.token_hex(5).upper()
            password_hash = generate_password_hash(password)
            
            new_user = User(
                name=name, 
                phone=phone, 
                user_id=user_id,
                password_hash=password_hash,
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
        
        # دریافت تمام چت‌های خصوصی کاربر
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
        
        # دریافت گروه‌های کاربر
        user_groups = GroupMember.query.filter_by(user_id=user_id).all()
        groups_data = []
        for member in user_groups:
            group = Group.query.filter_by(group_id=member.group_id).first()
            if group:
                # دریافت آخرین پیام گروه
                last_message = GroupMessage.query.filter_by(group_id=group.group_id).order_by(GroupMessage.timestamp.desc()).first()
                
                groups_data.append({
                    'group_id': group.group_id,
                    'name': group.name,
                    'last_message': {
                        'content': last_message.content if last_message else 'شروع گفتگو',
                        'timestamp': last_message.timestamp.strftime('%H:%M') if last_message else '',
                        'sender_name': last_message.sender_name if last_message else ''
                    }
                })
        
        # مرتب‌سازی بر اساس آخرین پیام
        chats_data.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message']['timestamp'] else '', reverse=True)
        
        return render_template('chats.html',
                             user_name=session['name'],
                             user_id=session['user_id'],
                             chats=chats_data,
                             groups=groups_data)
                             
    except Exception as e:
        logger.error(f"Chats page error: {str(e)}")
        flash('خطا در بارگذاری چت‌ها', 'error')
        return redirect('/')

@app.route('/chat/<other_user_id>')
@login_required
def chat_page(other_user_id):
    try:
        user_id = session['user_id']
        
        # بررسی وجود کاربر مقابل
        other_user = User.query.filter_by(user_id=other_user_id).first()
        if not other_user:
            flash('کاربر یافت نشد', 'error')
            return redirect('/chats')
        
        # پیدا کردن یا ایجاد چت
        chat = Chat.query.filter(
            ((Chat.user1_id == user_id) & (Chat.user2_id == other_user_id)) |
            ((Chat.user1_id == other_user_id) & (Chat.user2_id == user_id))
        ).first()
        
        if not chat:
            # ایجاد چت جدید
            chat = Chat(user1_id=user_id, user2_id=other_user_id)
            db.session.add(chat)
            db.session.commit()
        
        # دریافت تمام پیام‌های این چت
        messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.asc()).all()
        
        # علامت‌گذاری پیام‌ها به عنوان تحویل شده
        undelivered_messages = Message.query.filter_by(chat_id=chat.id, delivered=False).all()
        for msg in undelivered_messages:
            msg.delivered = True
        db.session.commit()
        
        # علامت‌گذاری پیام‌ها به عنوان خوانده شده
        unread_messages = Message.query.filter_by(chat_id=chat.id, sender_id=other_user_id, read=False).all()
        for msg in unread_messages:
            msg.read = True
        db.session.commit()
        
        return render_template('chat.html',
                             user_name=session['name'],
                             user_id=session['user_id'],
                             other_user=other_user.to_dict(),
                             messages=messages,
                             chat_id=chat.id)
                             
    except Exception as e:
        logger.error(f"Chat page error: {str(e)}")
        flash('خطا در بارگذاری چت', 'error')
        return redirect('/chats')

@app.route('/group/<group_id>')
@login_required
def group_page(group_id):
    try:
        user_id = session['user_id']
        
        # بررسی عضویت کاربر در گروه
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            flash('شما عضو این گروه نیستید', 'error')
            return redirect('/chats')
        
        group = Group.query.filter_by(group_id=group_id).first()
        if not group:
            flash('گروه یافت نشد', 'error')
            return redirect('/chats')
        
        # دریافت اعضای گروه
        members = GroupMember.query.filter_by(group_id=group_id).all()
        
        # دریافت پیام‌های گروه
        messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.timestamp.asc()).all()
        
        # آپدیت خوانده شدن پیام‌ها
        for message in messages:
            read_by = json.loads(message.read_by)
            if user_id not in read_by:
                read_by.append(user_id)
                message.read_by = json.dumps(read_by)
        db.session.commit()
        
        return render_template('group.html',
                             user_name=session['name'],
                             user_id=session['user_id'],
                             group=group,
                             members=members,
                             messages=messages)
                             
    except Exception as e:
        logger.error(f"Group page error: {str(e)}")
        flash('خطا در بارگذاری گروه', 'error')
        return redirect('/chats')

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    try:
        user_id = session['user_id']
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('لطفاً نام گروه را وارد کنید', 'error')
            return redirect('/chats')
        
        # ایجاد شناسه گروه
        group_id = secrets.token_hex(8).upper()
        
        # ایجاد گروه
        group = Group(
            name=name,
            description=description,
            creator_id=user_id,
            group_id=group_id
        )
        db.session.add(group)
        
        # اضافه کردن سازنده به عنوان ادمین
        creator_member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            user_name=session['name'],
            is_admin=True
        )
        db.session.add(creator_member)
        
        db.session.commit()
        
        flash(f'گروه "{name}" با موفقیت ایجاد شد', 'success')
        logger.info(f"Group created: {name} ({group_id}) by {user_id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create group error: {str(e)}")
        flash('خطا در ایجاد گروه', 'error')
    
    return redirect('/chats')

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    try:
        user_id = session['user_id']
        group_id = request.form.get('group_id', '').strip().upper()
        
        if not group_id:
            flash('لطفاً شناسه گروه را وارد کنید', 'error')
            return redirect('/chats')
        
        # بررسی وجود گروه
        group = Group.query.filter_by(group_id=group_id).first()
        if not group:
            flash('گروهی با این شناسه یافت نشد', 'error')
            return redirect('/chats')
        
        # بررسی عضویت قبلی
        existing_member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if existing_member:
            flash('شما قبلاً عضو این گروه هستید', 'error')
            return redirect('/chats')
        
        # اضافه کردن به گروه
        member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            user_name=session['name']
        )
        db.session.add(member)
        db.session.commit()
        
        flash(f'شما با موفقیت به گروه "{group.name}" پیوستید', 'success')
        logger.info(f"User {user_id} joined group {group_id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Join group error: {str(e)}")
        flash('خطا در پیوستن به گروه', 'error')
    
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
        
        # آپدیت آخرین فعالیت چت
        chat.last_activity = datetime.now(timezone.utc)
        
        # لاگ پیام برای ادمین
        message_log = MessageLog(
            message_type='private',
            sender_id=user_id,
            sender_name=session['name'],
            receiver_id=other_user_id,
            content=content,
            message_type_detail='text'
        )
        db.session.add(message_log)
        
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
                'is_me': True,
                'read': False,
                'delivered': False
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Send message error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در ارسال پیام'})

@app.route('/api/send_group_message', methods=['POST'])
@login_required
def send_group_message():
    try:
        user_id = session['user_id']
        data = request.get_json()
        
        group_id = data.get('group_id')
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'message': 'پیام نمی‌تواند خالی باشد'})
        
        # بررسی عضویت در گروه
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            return jsonify({'success': False, 'message': 'شما عضو این گروه نیستید'})
        
        # ایجاد پیام گروهی
        new_message = GroupMessage(
            group_id=group_id,
            sender_id=user_id,
            sender_name=session['name'],
            content=content
        )
        
        db.session.add(new_message)
        
        # آپدیت آخرین فعالیت گروه
        group = Group.query.filter_by(group_id=group_id).first()
        if group:
            group.last_activity = datetime.now(timezone.utc)
        
        # لاگ پیام برای ادمین
        message_log = MessageLog(
            message_type='group',
            sender_id=user_id,
            sender_name=session['name'],
            receiver_id=group_id,
            content=content,
            message_type_detail='text'
        )
        db.session.add(message_log)
        
        db.session.commit()
        
        logger.info(f"Group message sent: {user_id} -> {group_id}")
        
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
        logger.error(f"Send group message error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در ارسال پیام'})

@app.route('/api/upload_file', methods=['POST'])
@login_required
def upload_file():
    try:
        user_id = session['user_id']
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'فایلی انتخاب نشده'})
        
        file = request.files['file']
        chat_id = request.form.get('chat_id')
        group_id = request.form.get('group_id')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'فایلی انتخاب نشده'})
        
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{secrets.token_hex(8)}_{filename}")
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            
            # تشخیص نوع فایل
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                message_type = 'image'
            elif file_extension in ['mp3', 'wav', 'ogg']:
                message_type = 'audio'
            else:
                message_type = 'file'
            
            if chat_id:  # پیام خصوصی
                chat = Chat.query.get(chat_id)
                if not chat:
                    return jsonify({'success': False, 'message': 'چت یافت نشد'})
                
                other_user_id = chat.get_other_user(user_id)
                
                new_message = Message(
                    chat_id=chat_id,
                    sender_id=user_id,
                    sender_name=session['name'],
                    content=f'فایل {message_type}',
                    message_type=message_type,
                    file_path=file_path,
                    file_name=filename,
                    file_size=file_size
                )
                
                # لاگ برای ادمین
                message_log = MessageLog(
                    message_type='private',
                    sender_id=user_id,
                    sender_name=session['name'],
                    receiver_id=other_user_id,
                    content=f'فایل {message_type}: {filename}',
                    message_type_detail=message_type
                )
                
            elif group_id:  # پیام گروهی
                membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
                if not membership:
                    return jsonify({'success': False, 'message': 'شما عضو این گروه نیستید'})
                
                new_message = GroupMessage(
                    group_id=group_id,
                    sender_id=user_id,
                    sender_name=session['name'],
                    content=f'فایل {message_type}',
                    message_type=message_type,
                    file_path=file_path,
                    file_name=filename,
                    file_size=file_size
                )
                
                # لاگ برای ادمین
                message_log = MessageLog(
                    message_type='group',
                    sender_id=user_id,
                    sender_name=session['name'],
                    receiver_id=group_id,
                    content=f'فایل {message_type}: {filename}',
                    message_type_detail=message_type
                )
            else:
                return jsonify({'success': False, 'message': 'مقصد پیام مشخص نیست'})
            
            db.session.add(new_message)
            db.session.add(message_log)
            db.session.commit()
            
            logger.info(f"File uploaded: {filename} by {user_id}")
            
            return jsonify({
                'success': True,
                'message': {
                    'id': new_message.id,
                    'content': new_message.content,
                    'sender_id': new_message.sender_id,
                    'sender_name': new_message.sender_name,
                    'timestamp': new_message.timestamp.strftime('%H:%M'),
                    'is_me': True,
                    'message_type': message_type,
                    'file_name': filename,
                    'file_size': file_size
                }
            })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"File upload error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در آپلود فایل'})

@app.route('/download/<int:message_id>')
@login_required
def download_file(message_id):
    try:
        user_id = session['user_id']
        
        # پیدا کردن پیام
        message = Message.query.get(message_id)
        if not message:
            message = GroupMessage.query.get(message_id)
        
        if not message or not message.file_path:
            flash('فایل یافت نشد', 'error')
            return redirect('/chats')
        
        # بررسی دسترسی
        if hasattr(message, 'chat_id'):  # پیام خصوصی
            chat = Chat.query.get(message.chat_id)
            if user_id not in [chat.user1_id, chat.user2_id]:
                flash('دسترسی غیرمجاز', 'error')
                return redirect('/chats')
        else:  # پیام گروهی
            membership = GroupMember.query.filter_by(group_id=message.group_id, user_id=user_id).first()
            if not membership:
                flash('دسترسی غیرمجاز', 'error')
                return redirect('/chats')
        
        return send_file(message.file_path, as_attachment=True, download_name=message.file_name)
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        flash('خطا در دانلود فایل', 'error')
        return redirect('/chats')

@app.route('/api/get_new_messages/<int:chat_id>')
@login_required
def get_new_messages(chat_id):
    try:
        user_id = session['user_id']
        
        # بررسی دسترسی به چت
        chat = Chat.query.get(chat_id)
        if not chat or user_id not in [chat.user1_id, chat.user2_id]:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'})
        
        # دریافت پیام‌های جدید
        messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp.asc()).all()
        
        # علامت‌گذاری پیام‌های دریافتی به عنوان تحویل شده و خوانده شده
        other_user_id = chat.get_other_user(user_id)
        undelivered_messages = Message.query.filter_by(chat_id=chat_id, delivered=False).all()
        unread_messages = Message.query.filter_by(chat_id=chat_id, sender_id=other_user_id, read=False).all()
        
        for msg in undelivered_messages:
            msg.delivered = True
        
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
                'read': msg.read,
                'delivered': msg.delivered,
                'message_type': msg.message_type,
                'file_name': msg.file_name,
                'file_size': msg.file_size
            })
        
        return jsonify({'success': True, 'messages': messages_data})
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در دریافت پیام‌ها'})

@app.route('/api/get_new_group_messages/<group_id>')
@login_required
def get_new_group_messages(group_id):
    try:
        user_id = session['user_id']
        
        # بررسی عضویت در گروه
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            return jsonify({'success': False, 'message': 'شما عضو این گروه نیستید'})
        
        # دریافت پیام‌های جدید
        messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.timestamp.asc()).all()
        
        # آپدیت خوانده شدن پیام‌ها
        for message in messages:
            read_by = json.loads(message.read_by)
            if user_id not in read_by:
                read_by.append(user_id)
                message.read_by = json.dumps(read_by)
        db.session.commit()
        
        messages_data = []
        for msg in messages:
            read_by = json.loads(msg.read_by)
            messages_data.append({
                'id': msg.id,
                'content': msg.content,
                'sender_id': msg.sender_id,
                'sender_name': msg.sender_name,
                'timestamp': msg.timestamp.strftime('%H:%M'),
                'is_me': msg.sender_id == user_id,
                'read': user_id in read_by,
                'message_type': msg.message_type,
                'file_name': msg.file_name,
                'file_size': msg.file_size
            })
        
        return jsonify({'success': True, 'messages': messages_data})
        
    except Exception as e:
        logger.error(f"Get group messages error: {str(e)}")
        return jsonify({'success': False, 'message': 'خطا در دریافت پیام‌ها'})

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
        
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
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
        messages = MessageLog.query.order_by(MessageLog.timestamp.desc()).limit(100).all()
        chats = Chat.query.all()
        groups = Group.query.all()
        
        # آمار پیشرفته
        online_users = User.query.filter_by(is_online=True).count()
        today = datetime.now(timezone.utc).date()
        today_users = User.query.filter(db.func.date(User.registration_date) == today).count()
        total_messages = Message.query.count() + GroupMessage.query.count()
        
        stats = {
            'total_users': len(users),
            'total_messages': total_messages,
            'total_chats': len(chats),
            'total_groups': len(groups),
            'online_users': online_users,
            'today_users': today_users
        }
        
        return render_template('admin_dashboard.html',
                             users=users,
                             messages=messages,
                             chats=chats,
                             groups=groups,
                             stats=stats)
                             
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        flash('خطا در بارگذاری پنل مدیریت', 'error')
        return render_template('admin_dashboard.html', users=[], messages=[], chats=[], groups=[], stats={})

@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get(user_id)
        
        if user:
            user_info = f"{user.name} ({user.user_id})"
            
            # غیرفعال کردن کاربر به جای حذف
            user.is_active = False
            user.is_online = False
            
            db.session.commit()
            
            flash(f'کاربر {user_info} با موفقیت غیرفعال شد', 'success')
            logger.info(f"Admin disabled user: {user_info}")
        else:
            flash('کاربر یافت نشد', 'error')
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete user error: {str(e)}")
        flash(f'خطا در غیرفعال کردن کاربر: {str(e)}', 'error')
    
    return redirect('/admin_dashboard')

@app.route('/admin/activate_user/<int:user_id>')
@admin_required
def activate_user(user_id):
    try:
        user = User.query.get(user_id)
        
        if user:
            user.is_active = True
            db.session.commit()
            
            flash(f'کاربر {user.name} با موفقیت فعال شد', 'success')
            logger.info(f"Admin activated user: {user.name}")
        else:
            flash('کاربر یافت نشد', 'error')
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Activate user error: {str(e)}")
        flash(f'خطا در فعال کردن کاربر: {str(e)}', 'error')
    
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
