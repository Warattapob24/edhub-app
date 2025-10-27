# G:/.../app/admin/__init__.py

from flask import Blueprint

# 1. สร้าง "พิมพ์เขียว" (Blueprint) สำหรับส่วนของ Admin
#    เราประกาศให้ระบบรู้ว่าพิมพ์เขียวนี้ชื่อ 'admin'
bp = Blueprint('admin', __name__)

# 2. โหลดไฟล์ routes.py เข้ามาเพื่อให้ระบบรู้จัก URL ต่างๆ ของ Admin
#    บรรทัดนี้สำคัญมาก เพราะมันจะไปดึงโค้ดใน routes.py มาผูกกับ bp ที่เราสร้างไว้
from app.admin import routes