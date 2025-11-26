import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-super-secret-key-12345-change-this'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///messaging_app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # اطلاعات ادمین
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin-13899831"