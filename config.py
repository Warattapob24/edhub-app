import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env')) # 👈 โหลดไฟล์ .env

class Config:
    # --- [FIX] อ่านจาก .env เท่านั้น ห้าม Hardcode ค่าลับ ---
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    # --- [END FIX] ---

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'app/static/uploads')
    RQ_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    RQ_QUEUES = ['default']
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"