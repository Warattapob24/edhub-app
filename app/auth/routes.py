# app/auth/routes.py
from flask import current_app, render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required, login_user, logout_user
from app import db
from app.auth import bp
from app.auth.decorators import initial_setup_required
from app.auth.forms import LoginForm, InitialSetupForm
from app.models import Role, User, Student
from urllib.parse import urlparse # <<< แก้ไข: เปลี่ยนที่ import มาจากที่นี่

# FILE: app/auth/routes.py

# --- เพิ่ม Import Student ---
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user
from app import db
from app.auth import bp
from app.auth.forms import LoginForm
from app.models import User, Student
from app.services import log_action # <<< เพิ่ม Student

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Redirect based on role after login
        if current_user.has_role('Admin'):
            return redirect(url_for('admin.index')) # Corrected admin dashboard route
        elif current_user.has_role('Teacher'):
            return redirect(url_for('teacher.dashboard'))
        elif current_user.has_role('Student'):
             return redirect(url_for('student.dashboard')) # Assuming student blueprint exists
        # Add redirects for other roles if necessary
        else:
             return redirect(url_for('main.index')) # Default redirect

    form = LoginForm()
    if form.validate_on_submit():
        username_input = form.username.data
        password_input = form.password.data
        user = None
        is_student_login = False

        # 1. Try finding a User by username first (standard login)
        user = User.query.filter_by(username=username_input).first()
        if user and user.check_password(password_input):
            # Standard user login successful
            pass # Proceed to login_user below
        else:
            # 2. If standard login fails, try finding a Student by student_id
            student = Student.query.filter_by(student_id=username_input).first()
            if student and student.student_id == password_input: # Check if password is also the student_id
                # 3. Check if the student has an associated User account
                if student.user:
                    user = student.user
                    is_student_login = True
                    # Check flags (optional for students)
                    # if user.must_change_username or user.must_change_password:
                    #     flash('นักเรียนต้องเปลี่ยนชื่อผู้ใช้/รหัสผ่าน (กรุณาติดต่อผู้ดูแล)', 'warning')
                else:
                    # 4. [AUTO-CREATE USER] If no associated User, create one
                    try:
                        new_user = User(
                            username=f"student_{student.student_id}", # Or just student.student_id
                            first_name=student.first_name,
                            last_name=student.last_name,
                            name_prefix=student.name_prefix,
                            must_change_username=False, # Students likely don't change these
                            must_change_password=False
                        )
                        student_role = Role.query.filter_by(name='Student').first()
                        if not student_role:
                            student_role = Role(name='Student', description='Student Role')
                            db.session.add(student_role)
                            db.session.flush() # Get ID

                        new_user.roles.append(student_role)
                        db.session.add(new_user)
                        db.session.flush() # Get new_user ID

                        student.user_id = new_user.id # Link student to the new user

                        # Log auto-creation before commit
                        log_action(
                            "Auto-Create Student User",
                            user=None, # Action performed by system/login process
                            model=User,
                            record_id=new_user.id,
                            new_value={'username': new_user.username, 'student_id': student.student_id}
                        )

                        db.session.commit()
                        user = new_user
                        is_student_login = True
                        flash('สร้างบัญชีผู้ใช้สำหรับนักเรียนเรียบร้อยแล้ว', 'info')
                    except Exception as e:
                        db.session.rollback()
                        flash(f'เกิดข้อผิดพลาดในการสร้างบัญชีนักเรียน: {e}', 'danger')
                        current_app.logger.error(f"Error auto-creating user for student {student.id}: {e}")
                        # Log the creation failure
                        log_action(f"Auto-Create Student User Failed: {type(e).__name__}", user=None, model=User)
                        try: db.session.commit()
                        except: db.session.rollback()
                        user = None # Ensure login fails

            else:
                # If neither standard user nor student login matches
                user = None

        if user is None:
            # --- [START LOG] Log failed login attempt ---
            log_action("Login Failed", user=None, new_value={'username': username_input})
            try:
                db.session.commit() # Commit the failure log immediately
            except Exception as log_err:
                 db.session.rollback()
                 current_app.logger.error(f"Failed to commit login failure log: {log_err}")
            # --- [END LOG] ---
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
            return redirect(url_for('auth.login'))

        # If user is found (either standard or student)
        login_user(user, remember=form.remember_me.data)

        # --- [START LOG] Log successful login ---
        log_action("Login Success", user=user)
        try:
            db.session.commit() # Commit the login success log
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit login success log: {log_err}")
        # --- [END LOG] ---


        # Handle redirection
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            # Redirect based on role
            if user.has_role('Admin'): next_page = url_for('admin.index') # Corrected admin route
            elif user.has_role('Teacher'): next_page = url_for('teacher.dashboard')
            elif user.has_role('Advisor'): next_page = url_for('advisor.dashboard')
            elif user.has_role('Department Head'): next_page = url_for('department.dashboard')
            elif user.has_role('Academic Affair'): next_page = url_for('academic.dashboard')
            elif user.has_role('Director'): next_page = url_for('director.dashboard')
            elif user.has_role('Student'): next_page = url_for('student.dashboard')
            else: next_page = url_for('main.index') # Default

        # Check if non-student user needs setup (moved after login_user)
        if not is_student_login and (user.must_change_username or user.must_change_password):
            flash('กรุณาเปลี่ยนชื่อผู้ใช้หรือรหัสผ่าน', 'warning')
            return redirect(url_for('auth.initial_setup')) # Force setup

        return redirect(next_page)

    return render_template('auth/login.html', title='เข้าสู่ระบบ', form=form)

@bp.route('/dashboard')
# @login_required
@initial_setup_required # <<< เพิ่ม Decorator นี้เข้ามา
def dashboard():
    return render_template('teacher/dashboard.html', title='Teacher Dashboard')

@bp.route('/logout')
def logout():
    logout_user()
    flash('คุณได้ออกจากระบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/initial-setup', methods=['GET', 'POST'])
@login_required
def initial_setup():
    # ถ้าตั้งค่าเรียบร้อยแล้ว ไม่ควรเข้ามาหน้านี้ได้อีก
    if not current_user.must_change_username and not current_user.must_change_password:
        return redirect(url_for('teacher.dashboard'))

    form = InitialSetupForm()
    # ส่ง user_id เข้าไปใน form เพื่อใช้ในการ validate email
    form.user_id = current_user.id 

    if form.validate_on_submit():
        # อัปเดตข้อมูลผู้ใช้
        current_user.username = form.username.data
        current_user.set_password(form.password.data)
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data
        
        # อัปเดต relationships
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data
        
        # ปรับ Flag
        current_user.must_change_username = False
        current_user.must_change_password = False
        
        db.session.commit()
        flash('ตั้งค่าบัญชีของคุณเรียบร้อยแล้ว ยินดีต้อนรับ!', 'success')
        return redirect(url_for('teacher.dashboard'))

    # สำหรับ GET request, เติมข้อมูลที่มีอยู่แล้วลงในฟอร์ม
    elif request.method == 'GET':
        form.job_title.data = current_user.job_title
        form.email.data = current_user.email
        form.member_of_groups.data = current_user.member_of_groups
        form.advised_classrooms.data = current_user.advised_classrooms

    return render_template('auth/initial_setup.html', title='ตั้งค่าบัญชีครั้งแรก', form=form)