# app/decorators.py
from functools import wraps
from flask import abort
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # แก้ไขเงื่อนไขให้ตรวจสอบจาก list ของ roles
        if not current_user.is_authenticated or 'admin' not in [role.key for role in current_user.roles]:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function