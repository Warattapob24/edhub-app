# app/auth/decorators.py

from functools import wraps
from flask import redirect, url_for
from flask_login import current_user

def initial_setup_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            if current_user.must_change_username or current_user.must_change_password:
                return redirect(url_for('auth.initial_setup'))
        return f(*args, **kwargs)
    return decorated_function