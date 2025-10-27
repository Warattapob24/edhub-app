# app/auth/routes.py
from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user
from app.auth import bp
from app.models import User
from app.forms import LoginForm
from urllib.parse import urlsplit
from app.utils import log_activity

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # ถ้าผู้ใช้ login อยู่แล้ว ให้ redirect ไปหน้าหลักเลย
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        # ตรวจสอบว่า user ไม่มีอยู่จริง หรือรหัสผ่านผิด
        if user is None or not user.check_password(form.password.data):
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
            return redirect(url_for('auth.login'))
        
        # ถ้าถูกต้อง ให้ login ผู้ใช้เข้าระบบ
        login_user(user, remember=form.remember_me.data)
        log_activity('USER_LOGIN', f'User {user.username} logged in.')
        session['user_type'] = 'teacher'
        
        # ไปยังหน้าที่ผู้ใช้พยายามจะเข้าถึงก่อนหน้า (ถ้ามี)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
        
    return render_template('auth/login.html', title='เข้าสู่ระบบ', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    session.pop('user_type', None)
    return redirect(url_for('main.welcome'))