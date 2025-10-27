# path: app/decorators.py

from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def role_required(role_name):
    """
    Decorator to check if the current user has the required role.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # --- Logic ทั้งหมดจะถูกย้ายมาไว้ข้างในฟังก์ชันที่ซ้อนกันอยู่นี้ ---
            
            # 1. ตรวจสอบว่า Login แล้วหรือยัง
            if not current_user.is_authenticated:
                flash('กรุณาเข้าสู่ระบบเพื่อเข้าถึงหน้านี้', 'warning')
                return redirect(url_for('auth.login')) # **ปรับแก้เป็นหน้า login ของท่าน**

            # 2. ตรวจสอบว่ามี Role ที่ต้องการหรือไม่
            if not current_user.has_role(role_name):
                flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
                return redirect(url_for('main.index')) # **ปรับแก้เป็นหน้าหลักของท่าน**
            
            # 3. ถ้าผ่านทุกอย่าง ให้ไปต่อ
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ตรวจสอบว่าผู้ใช้ Login อยู่หรือไม่
        if not current_user.is_authenticated:
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ตรวจสอบว่าผู้ใช้ Login อยู่หรือไม่
        if not current_user.is_authenticated:
            return abort(403) # Forbidden
        
        # ตรวจสอบว่าผู้ใช้มี Role 'Admin' หรือไม่
        is_admin = any(role.name == 'Admin' for role in current_user.roles)
        if not is_admin:
            abort(403) # Forbidden
            
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        
        # ตรวจสอบว่าผู้ใช้มี Role 'Teacher' หรือไม่
        is_teacher = any(role.name == 'Teacher' for role in current_user.roles)
        if not is_teacher:
            abort(403)
            
        return f(*args, **kwargs)
    return decorated_function