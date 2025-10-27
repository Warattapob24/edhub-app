# config.py
import os

# หาตำแหน่งของไฟล์ปัจจุบันเพื่อสร้าง path ที่ถูกต้อง
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """
    คลาสสำหรับเก็บการตั้งค่าหลักของแอปพลิเคชัน
    """
    # Secret Key เป็นสิ่งจำเป็นสำหรับความปลอดภัยของ Session และอื่นๆ
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess-this-secret-key'

    # ตั้งค่าฐานข้อมูลให้ใช้ SQLite ซึ่งเป็นไฟล์เดี่ยวๆ ชื่อ app.db
    # อยู่ในตำแหน่งเดียวกับไฟล์ config.py
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db') + '?timeout=20'

    # ปิดการใช้งานฟีเจอร์ของ SQLAlchemy ที่เราไม่ได้ใช้ เพื่อลด overhead
    SQLALCHEMY_TRACK_MODIFICATIONS = False