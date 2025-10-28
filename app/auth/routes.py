# FILE: app/auth/routes.py
from flask import current_app, render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required, login_user, logout_user
from app import db
from app.auth import bp
from app.auth.decorators import initial_setup_required
from app.auth.forms import LoginForm, InitialSetupForm
# --- แก้ไข Import ให้ครบถ้วน ---
from app.models import Role, User, Student
from app.services import log_action
from urllib.parse import urlparse
# --- สิ้นสุดการแก้ไข Import ---

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # --- ลำดับการ Redirect สำหรับผู้ใช้ที่ Login อยู่แล้ว ---
        if current_user.has_role('Admin'):
            return redirect(url_for('admin.index'))
        elif current_user.has_role('Director'):
            return redirect(url_for('director.dashboard'))
        elif current_user.has_role('Academic Affair'):
            return redirect(url_for('academic.dashboard'))
        elif current_user.has_role('Department Head'): # หรือเช็ค current_user.led_subject_group
            return redirect(url_for('department.dashboard'))
        # อาจจะเพิ่ม Grade Level Head
        # elif current_user.led_grade_level: # หรือ current_user.has_role('Grade Level Head')
        #     return redirect(url_for('grade_level_head.dashboard'))
        elif current_user.has_role('Advisor'):
            return redirect(url_for('advisor.dashboard'))
        elif current_user.has_role('Teacher'):
            return redirect(url_for('teacher.dashboard'))
        elif current_user.has_role('Student'): # หรือเช็ค current_user.student_profile
             return redirect(url_for('student.dashboard'))
        else:
            return redirect(url_for('main.index')) # Default redirect
        # --- สิ้นสุดลำดับการ Redirect ---

    form = LoginForm()
    if form.validate_on_submit():
        username_input = form.username.data
        password_input = form.password.data
        user = None
        is_student_login = False

        # 1. Try finding a User by username first (standard login)
        user = User.query.filter_by(username=username_input).first()

        # --- ปรับปรุง Logic การเช็ค Password ---
        login_successful = False
        potential_student = Student.query.filter_by(student_id=username_input).first()

        if user and user.check_password(password_input):
            # Standard user login
            login_successful = True
        elif potential_student and potential_student.student_id == password_input:
            # Student login attempt using student_id for both username and password
            if potential_student.user:
                user = potential_student.user
                is_student_login = True
                login_successful = True # Found existing user linked to student
            else:
                # Auto-create user for student
                try:
                    new_user = User(
                        username=f"student_{potential_student.student_id}",
                        first_name=potential_student.first_name,
                        last_name=potential_student.last_name,
                        name_prefix=potential_student.name_prefix,
                        must_change_username=False,
                        must_change_password=False
                    )
                    student_role = Role.query.filter_by(name='Student').first()
                    if not student_role:
                        student_role = Role(name='Student', description='Student Role')
                        db.session.add(student_role)
                        db.session.flush()

                    new_user.roles.append(student_role)
                    db.session.add(new_user)
                    db.session.flush()

                    potential_student.user_id = new_user.id
                    db.session.flush() # Ensure user_id is associated before logging

                    log_action(
                        "Auto-Create Student User", user=None, model=User,
                        record_id=new_user.id,
                        new_value={'username': new_user.username, 'student_id': potential_student.student_id}
                    )
                    db.session.commit()
                    user = new_user
                    is_student_login = True
                    login_successful = True
                    flash('สร้างบัญชีผู้ใช้สำหรับนักเรียนเรียบร้อยแล้ว', 'info')
                except Exception as e:
                    db.session.rollback()
                    flash(f'เกิดข้อผิดพลาดในการสร้างบัญชีนักเรียน: {e}', 'danger')
                    current_app.logger.error(f"Error auto-creating user for student {potential_student.id}: {e}")
                    log_action(f"Auto-Create Student User Failed: {type(e).__name__}", user=None, model=User)
                    try: db.session.commit()
                    except: db.session.rollback()
                    user = None # Ensure login fails if auto-create fails
                    login_successful = False
        # --- สิ้นสุดการปรับปรุง Logic เช็ค Password ---

        if not login_successful: # Check the flag instead of user is None
            log_action("Login Failed", user=None, new_value={'username': username_input})
            try:
                db.session.commit()
            except Exception as log_err:
                db.session.rollback()
                current_app.logger.error(f"Failed to commit login failure log: {log_err}")
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
            return redirect(url_for('auth.login'))

        # If login is successful
        login_user(user, remember=form.remember_me.data)
        log_action("Login Success", user=user)
        try:
            db.session.commit()
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit login success log: {log_err}")

        # Handle redirection
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            # --- ลำดับการ Redirect หลัง Login สำเร็จ ---
            if user.has_role('Admin'):
                next_page = url_for('admin.index')
            elif user.has_role('Director'):
                next_page = url_for('director.dashboard')
            elif user.has_role('Academic Affair'):
                next_page = url_for('academic.dashboard')
            elif user.has_role('Department Head'): # หรือเช็ค user.led_subject_group
                next_page = url_for('department.dashboard')
            elif user.led_grade_level: # หรือ user.has_role('Grade Level Head')
                next_page = url_for('grade_level_head.dashboard')
            elif user.has_role('Advisor'):
                next_page = url_for('advisor.dashboard')
            elif user.has_role('Teacher'):
                next_page = url_for('teacher.dashboard')
            elif user.has_role('Student'): # หรือเช็ค user.student_profile
                 next_page = url_for('student.dashboard')
            else:
                 next_page = url_for('main.index') # Default
            # --- สิ้นสุดลำดับการ Redirect ---

        # Check if non-student user needs initial setup
        if not is_student_login and (user.must_change_username or user.must_change_password):
            flash('กรุณาเปลี่ยนชื่อผู้ใช้หรือรหัสผ่าน', 'warning')
            # Redirect to initial_setup regardless of 'next_page' if setup is required
            return redirect(url_for('auth.initial_setup'))

        return redirect(next_page)

    # For GET request or failed form validation
    return render_template('auth/login.html', title='เข้าสู่ระบบ', form=form)


# --- Route นี้อาจจะไม่จำเป็นแล้ว ถ้า Default Redirect คือ main.index หรือ login ---
# @bp.route('/dashboard')
# @initial_setup_required
# def dashboard():
#     return render_template('teacher/dashboard.html', title='Teacher Dashboard')
# --- สิ้นสุด Route ที่อาจไม่จำเป็น ---


@bp.route('/logout')
def logout():
    # --- เพิ่ม Log การ Logout ---
    if current_user.is_authenticated:
        user_id = current_user.id # Get ID before logging out
        username = current_user.username
        logout_user()
        log_action("Logout Success", user=None, new_value={'user_id': user_id, 'username': username})
        try:
            db.session.commit()
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit logout log: {log_err}")
    else:
        logout_user() # Call it anyway just in case
    # --- สิ้นสุด Log การ Logout ---

    flash('คุณได้ออกจากระบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/initial-setup', methods=['GET', 'POST'])
@login_required
def initial_setup():
    # ถ้าตั้งค่าเรียบร้อยแล้ว ไม่ควรเข้ามาหน้านี้ได้อีก
    if not current_user.must_change_username and not current_user.must_change_password:
        # --- Redirect ไปยัง Dashboard ที่ถูกต้อง ไม่ใช่แค่ teacher ---
        if current_user.has_role('Admin'):
             return redirect(url_for('admin.index'))
        elif current_user.has_role('Director'):
             return redirect(url_for('director.dashboard'))
        elif current_user.has_role('Academic Affair'):
             return redirect(url_for('academic.dashboard'))
        elif current_user.has_role('Department Head'):
             return redirect(url_for('department.dashboard'))
        elif current_user.led_grade_level:
             return redirect(url_for('grade_level_head.dashboard'))
        elif current_user.has_role('Advisor'):
             return redirect(url_for('advisor.dashboard'))
        elif current_user.has_role('Teacher'):
             return redirect(url_for('teacher.dashboard'))
        elif current_user.has_role('Student'): # Student shouldn't reach here normally
             return redirect(url_for('student.dashboard'))
        else:
             return redirect(url_for('main.index'))
        # --- สิ้นสุดการ Redirect ---

    form = InitialSetupForm()
    # ส่ง user_id เข้าไปใน form เพื่อใช้ในการ validate email
    form.user_id = current_user.id

    if form.validate_on_submit():
        # เก็บค่าเก่าบางส่วน (เผื่อใช้ Log)
        old_username = current_user.username
        old_email = current_user.email

        # อัปเดตข้อมูลผู้ใช้
        current_user.username = form.username.data
        current_user.set_password(form.password.data)
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data

        # อัปเดต relationships (ควรทำหลังจาก commit หลัก หรือแยก session)
        # การกำหนด .data โดยตรงอาจไม่ใช่วิธีที่ SQLAlchemy ชอบที่สุดสำหรับ many-to-many
        # อาจจะต้อง clear แล้ว append ใหม่ หรือใช้ synchronize_session=False
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data

        # ปรับ Flag
        current_user.must_change_username = False
        current_user.must_change_password = False

        try:
            db.session.commit()
            flash('ตั้งค่าบัญชีของคุณเรียบร้อยแล้ว ยินดีต้อนรับ!', 'success')

            # --- 👇👇👇 แทนที่ด้วยโค้ด Redirect ที่ตรวจสอบ Role 👇👇👇 ---
            # Determine the correct dashboard based on roles AFTER setup
            if current_user.has_role('Admin'):
                next_page = url_for('admin.index')
            elif current_user.has_role('Director'):
                 next_page = url_for('director.dashboard')
            elif current_user.has_role('Academic Affair'):
                 next_page = url_for('academic.dashboard')
            elif current_user.has_role('Department Head'):
                 next_page = url_for('department.dashboard')
            elif current_user.led_grade_level:
                 next_page = url_for('grade_level_head.dashboard')
            elif current_user.has_role('Advisor'):
                 next_page = url_for('advisor.dashboard')
            elif current_user.has_role('Teacher'):
                next_page = url_for('teacher.dashboard')
            elif current_user.has_role('Student'): # Should not happen here
                next_page = url_for('student.dashboard')
            else:
                next_page = url_for('main.index')

            # Log action for initial setup completion
            log_action("Initial Setup Complete", user=current_user,
                       old_value={'username': old_username, 'email': old_email},
                       new_value={'username': current_user.username, 'email': current_user.email})
            try:
                db.session.commit() # Commit the log
            except Exception as log_err:
                db.session.rollback()
                current_app.logger.error(f"Failed to commit initial setup log: {log_err}")

            return redirect(next_page)
            # --- สิ้นสุดส่วนที่แทนที่ ---

        except Exception as e:
             db.session.rollback()
             flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'danger')
             current_app.logger.error(f"Error during initial setup save for user {current_user.id}: {e}")
             # Log failure?
             return redirect(url_for('auth.initial_setup')) # Redirect back to setup on error


    # สำหรับ GET request, เติมข้อมูลที่มีอยู่แล้วลงในฟอร์ม
    elif request.method == 'GET':
        form.username.data = current_user.username # Pre-fill username for editing
        form.job_title.data = current_user.job_title
        form.email.data = current_user.email
        form.member_of_groups.data = current_user.member_of_groups
        form.advised_classrooms.data = current_user.advised_classrooms

    return render_template('auth/initial_setup.html', title='ตั้งค่าบัญชีครั้งแรก', form=form)