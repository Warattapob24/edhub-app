from flask import render_template, flash, redirect, url_for, Blueprint, request
from flask_login import login_user, logout_user, login_required, current_user
from app.forms import LoginForm
from app.models import User
from app import db

# สร้าง Blueprint ใหม่ชื่อ 'main'
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@main_bp.route('/index')
def index():
    return render_template('index.html', title='Home') # เราจะสร้างไฟล์ index.html ง่ายๆ

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # [ปรับปรุง] ถ้าผู้ใช้ล็อกอินอยู่แล้ว ให้ส่งไปหน้า Dashboard ที่ถูกต้อง
        if current_user.has_role('Admin'):
            return redirect(url_for('admin.manage_users')) # หรือหน้าแรกของ Admin
        if current_user.has_role('DepartmentHead'):
            return redirect(url_for('department.dashboard'))
        if current_user.has_role('Teacher'):
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('main.index')) # หน้าเริ่มต้นสำหรับบทบาทอื่นๆ

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
            return redirect(url_for('main.login'))
        
        login_user(user, remember=form.remember_me.data)

        # [แก้ไข] เพิ่ม Logic การ Redirect ตามบทบาทหลังล็อกอินสำเร็จ
        if user.has_role('Admin'):
            return redirect(url_for('admin.manage_users')) # ส่ง Admin ไปที่นี่
        if user.has_role('DepartmentHead'):
            return redirect(url_for('department.dashboard'))
        if user.has_role('Teacher'):
            return redirect(url_for('teacher.dashboard'))
        
        # Redirect เริ่มต้นหากผู้ใช้ไม่มี Dashboard เฉพาะ
        return redirect(url_for('main.index'))
        
    return render_template('login.html', title='Sign In', form=form)
        
@main_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))
