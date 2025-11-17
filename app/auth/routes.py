# FILE: app/auth/routes.py
import os
import requests
import certifi
from flask import current_app, render_template, flash, redirect, session, url_for, request
from flask_login import current_user, login_required, login_user, logout_user
from app import db
from app.auth import bp
from app.auth.decorators import initial_setup_required
from app.auth.forms import EditProfileForm, LoginForm, InitialSetupForm
# --- แก้ไข Import ให้ครบถ้วน ---
from app.models import Role, User, Student
from app.services import log_action
from urllib.parse import urlparse
# --- สิ้นสุดการแก้ไข Import ---
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleRequest

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # [FIX] ตรวจสอบเงื่อนไข 2 ชั้น ตาม Workflow ที่ถูกต้อง
        # 1. ถ้าต้องเปลี่ยนรหัสผ่าน (Admin สร้าง) -> ส่งไป setup (สำคัญที่สุด)
        if current_user.must_change_password:
             flash('กรุณาตั้งรหัสผ่านใหม่ และตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
             return redirect(url_for('auth.initial_setup'))
        # 2. ถ้ามาจาก Google (แต่ยังไม่กรอกข้อมูล) -> ส่งไป setup
        if not current_user.initial_setup_complete:
             flash('กรุณาตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
             return redirect(url_for('auth.initial_setup'))
        # 3. ถ้าผ่านหมด -> ไป Dashboard
        return redirect(get_redirect_target(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        if password_required and not form.password.data:
            # ถ้าเป็นผู้ใช้ที่ "ต้อง" เปลี่ยนรหัส แต่ "ไม่ได้กรอก" รหัสใหม่
            flash('กรุณาตั้งรหัสผ่านใหม่', 'danger')
            return render_template('auth/initial_setup.html', 
                                   title='ตั้งค่าบัญชีครั้งแรก', 
                                   form=form,
                                   password_required=password_required)
        
        username_input = form.username.data
        password_input = form.password.data
        user = None
        is_student_login = False

        user = User.query.filter_by(username=username_input).first()
        
        login_successful = False
        potential_student = Student.query.filter_by(student_id=username_input).first()

        if user and user.check_password(password_input):
            # Standard user login
            login_successful = True
        elif potential_student and potential_student.student_id == password_input:
            # (ตรรกะการ Login ของนักเรียน ... เหมือนเดิม)
            if potential_student.user:
                user = potential_student.user
                is_student_login = True
                login_successful = True 
            else:
                try:
                    new_user = User(
                        username=f"student_{potential_student.student_id}",
                        first_name=potential_student.first_name,
                        last_name=potential_student.last_name,
                        name_prefix=potential_student.name_prefix,
                        must_change_username=False,
                        must_change_password=False,
                        initial_setup_complete=True # นักเรียนไม่ต้อง setup
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
                    db.session.flush()
                    # (Log Action...)
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
                    user = None
                    login_successful = False

        if not login_successful:
            log_action("Login Failed", user=None, new_value={'username': username_input})
            try: db.session.commit()
            except Exception as log_err:
                db.session.rollback()
                current_app.logger.error(f"Failed to commit login failure log: {log_err}")
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
            return redirect(url_for('auth.login'))

        # Login สำเร็จ
        login_user(user, remember=form.remember_me.data)
        log_action("Login Success", user=user)
        try: db.session.commit()
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit login success log: {log_err}")

        # --- [THE REAL FIX] ---
        # ตรวจสอบ Workflow ที่ถูกต้องสำหรับครู/Admin
        if not is_student_login:
            # 1. (สำคัญที่สุด) ถ้าต้องเปลี่ยนรหัสผ่าน (Admin สร้าง) -> ส่งไป setup
            if user.must_change_password:
                flash('กรุณาตั้งรหัสผ่านใหม่ และตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
                return redirect(url_for('auth.initial_setup'))
            # 2. (สำหรับ Google) ถ้ายังไม่กรอกข้อมูล -> ส่งไป setup
            if not user.initial_setup_complete:
                flash('กรุณาตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
                return redirect(url_for('auth.initial_setup'))
        # --- [END FIX] ---

        return redirect(get_redirect_target(user))

    return render_template('auth/login.html', title='เข้าสู่ระบบ', form=form)

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
    # 1. ถ้าต้องเปลี่ยนรหัส (Admin สร้าง) -> ให้ทำต่อ
    # 2. ถ้ามาจาก Google (ยังไม่กรอกข้อมูล) -> ให้ทำต่อ
    if not current_user.must_change_password and current_user.initial_setup_complete:
        flash('บัญชีของคุณตั้งค่าเรียบร้อยแล้ว', 'info')
        return redirect(get_redirect_target(current_user))

    form = InitialSetupForm()
    password_required = current_user.must_change_password
    form.user_id = current_user.id

    if form.validate_on_submit():
        old_username = current_user.username
        old_email = current_user.email

        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data

        # อัปเดตข้อมูลส่วนตัว (ทุกคนต้องทำ)
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data
        
        # อัปเดตข้อมูล Login (เฉพาะคนที่ต้องเปลี่ยน)
        if password_required:
            current_user.username = form.username.data
            current_user.set_password(form.password.data)
            current_user.must_change_username = False
            current_user.must_change_password = False

        # --- [MODIFY] ตั้ง Flag ใหม่ ---
        current_user.initial_setup_complete = True
        # --- สิ้นสุด [MODIFY] ---

        try:
            db.session.commit()
            flash('ตั้งค่าบัญชีของคุณเรียบร้อยแล้ว ยินดีต้อนรับ!', 'success')

            log_action("Initial Setup Complete", user=current_user,
                       old_value={'username': old_username, 'email': old_email},
                       new_value={'username': current_user.username, 'email': current_user.email})
            try: db.session.commit()
            except Exception as log_err:
                db.session.rollback()
                current_app.logger.error(f"Failed to commit initial setup log: {log_err}")
            
            return redirect(get_redirect_target(current_user))

        except Exception as e:
             db.session.rollback()
             flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'danger')
             current_app.logger.error(f"Error during initial setup save for user {current_user.id}: {e}")
             return redirect(url_for('auth.initial_setup'))

    elif request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.username.data = current_user.username
        form.job_title.data = current_user.job_title
        form.email.data = current_user.email
        form.member_of_groups.data = current_user.member_of_groups
        form.advised_classrooms.data = current_user.advised_classrooms

    return render_template('auth/initial_setup.html', 
                           title='ตั้งค่าบัญชีครั้งแรก', 
                           form=form,
                           password_required=password_required)

# --- [NEW] เพิ่ม Route ใหม่สำหรับ Edit Profile ---
@bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # ผู้ใช้ที่ยังตั้งค่าไม่เสร็จ จะถูกบังคับไปหน้า initial_setup ก่อน
    if not current_user.initial_setup_complete or current_user.must_change_password:
        flash('กรุณาตั้งค่าบัญชีครั้งแรกให้เสร็จสมบูรณ์ก่อน', 'warning')
        return redirect(url_for('auth.initial_setup'))
        
    form = EditProfileForm()

    if form.validate_on_submit():
        # บันทึกข้อมูลส่วนตัว (บังคับ)
        current_user.username = form.username.data
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data
        
        # บันทึกรหัสผ่าน (ถ้ามีการกรอก)
        if form.password.data:
            current_user.set_password(form.password.data)
            flash('บันทึกรหัสผ่านใหม่เรียบร้อยแล้ว', 'success')

        try:
            db.session.commit()
            flash('บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว', 'success')
            
            # (Optional: Log)
            log_action("Profile Edited", user=current_user)
            try: db.session.commit()
            except Exception as log_err:
                db.session.rollback()
                current_app.logger.error(f"Failed to commit profile edit log: {log_err}")

            return redirect(url_for('auth.edit_profile'))
        
        except Exception as e:
             db.session.rollback()
             flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'danger')
             current_app.logger.error(f"Error during profile edit for user {current_user.id}: {e}")

    elif request.method == 'GET':
        # เติมข้อมูลปัจจุบันลงในฟอร์ม
        form.username.data = current_user.username
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.job_title.data = current_user.job_title
        form.email.data = current_user.email
        form.member_of_groups.data = current_user.member_of_groups
        form.advised_classrooms.data = current_user.advised_classrooms

    return render_template('auth/edit_profile.html', 
                           title='แก้ไขข้อมูลส่วนตัว', 
                           form=form)

# --- [FIX] เพิ่มบรรทัดนี้เพื่ออนุญาต HTTP (สำหรับ Local Development) ---
if not os.environ.get('RENDER'):
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# --- [NEW] ฟังก์ชันสำหรับสร้าง OAuth Flow (เวอร์ชันปลอดภัย) ---
def get_google_flow():
    """สร้าง instance ของ Google OAuth Flow จาก Config."""
    
    # [FIX] สร้าง client_config dictionary จาก Config แทนการอ่านไฟล์
    client_config = {
        "web": {
            "client_id": current_app.config['GOOGLE_CLIENT_ID'],
            "client_secret": current_app.config['GOOGLE_CLIENT_SECRET'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [
                "http://127.0.0.1:5000/auth/google-callback",
                "http://localhost:5000/auth/google-callback",
                "https://edhub-app.onrender.com/auth/google-callback"
            ]
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config, # 👈 [FIX] เปลี่ยนจาก .from_client_secrets_file
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/forms.body",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/script.projects"
        ],
        redirect_uri=url_for('auth.google_callback', _external=True)
    )
    return flow

# --- [NEW] Route สำหรับเริ่ม Google Login ---
@bp.route('/google-login')
def google_login():
    """
    Redirect ไปยังหน้า Google Consent Screen.
    """
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state # เก็บ state ไว้ตรวจสอบการโจมตี CSRF
    return redirect(authorization_url)
# --- สิ้นสุด [NEW] ---

# --- [REVISED] Route สำหรับรับ Callback จาก Google (แก้ไข Case 3) ---
@bp.route('/google-callback')
def google_callback():
    """
    จัดการ Callback หลังจาก Google Authenticate สำเร็จ.
    """
    if request.args.get('state') != session.get('state'):
        flash('เกิดข้อผิดพลาดในการยืนยันตัวตน (Invalid state)', 'danger')
        return redirect(url_for('auth.login'))

    flow = get_google_flow()
    
    try:
        # นี่คือวิธีที่ปลอดภัยในการแก้ปัญหา SSLError
        flow.fetch_token(
            authorization_response=request.url,
            verify=certifi.where()
        )
    except Exception as e:
        current_app.logger.error(f"Error fetching Google token: {e}")
        flash(f'เกิดข้อผิดพลาดในการเชื่อมต่อ Google (SSL): {e}', 'danger')
        return redirect(url_for('auth.login'))

    credentials = flow.credentials
    
    try:
        # --- [FIX 2] ปิดการตรวจสอบที่นี่ด้วย (เผื่อไว้) ---
        authed_session = requests.Session()
        authed_session.verify = certifi.where()
        google_request = GoogleRequest(session=authed_session)

        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_request, 
            current_app.config['GOOGLE_CLIENT_ID']
        )
    except ValueError as e:
        current_app.logger.error(f"Error verifying Google ID token: {e}")
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลผู้ใช้: {e}', 'danger')
        return redirect(url_for('auth.login'))

    google_id = id_info.get('sub')
    user_email = id_info.get('email')
    user_first_name = id_info.get('given_name')
    user_last_name = id_info.get('family_name')

    if not google_id or not user_email:
        flash('ไม่สามารถดึงข้อมูล Google ID หรือ Email ได้', 'danger')
        return redirect(url_for('auth.login'))

    # (ตรรกะ Login/Register เหมือนเดิม)
    user = User.query.filter_by(google_id=google_id).first()
    if user:
        user.google_credentials_json = credentials.to_json() 
        login_user(user, remember=True)
        log_action("Login Success (Google)", user=user)
        db.session.commit()
        if not user.initial_setup_complete:
            flash('ยินดีต้อนรับ! กรุณากรอกข้อมูลส่วนตัวให้ครบถ้วน', 'info')
            return redirect(url_for('auth.initial_setup'))
        return redirect(get_redirect_target(user))

    user = User.query.filter_by(email=user_email).first()
    if user:
        user.google_id = google_id
        user.google_credentials_json = credentials.to_json()
        db.session.add(user)
        log_action("Link Google Account", user=user, new_value={'google_id': google_id})
        db.session.commit()
        login_user(user, remember=True)
        if not user.initial_setup_complete:
            flash('เชื่อมต่อบัญชี Google สำเร็จ! กรุณากรอกข้อมูลส่วนตัว', 'info')
            return redirect(url_for('auth.initial_setup'))
        return redirect(get_redirect_target(user))

    if User.query.filter_by(username=user_email).first():
        flash(f'ไม่สามารถสร้างบัญชีได้: ชื่อผู้ใช้ (Username) "{user_email}" นี้ถูกใช้ไปแล้ว', 'danger')
        return redirect(url_for('auth.login'))

    try:
        new_user = User(
            google_id=google_id,
            email=user_email,
            first_name=user_first_name,
            last_name=user_last_name,
            username=user_email,
            password_hash=None, 
            must_change_username=False,
            must_change_password=False,
            initial_setup_complete=False,
            google_credentials_json = credentials.to_json()
        )
        db.session.add(new_user)
        db.session.commit()
        log_action("Auto-Create User (Google)", user=new_user, new_value={'email': user_email, 'google_id': google_id})
        db.session.commit()
        login_user(new_user, remember=True)
        flash('สร้างบัญชีผู้ใช้ผ่าน Google สำเร็จ! กรุณาตั้งค่าบัญชีของคุณ', 'success')
        return redirect(url_for('auth.initial_setup'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user from Google: {e}")
        flash(f'เกิดข้อผิดพลาดในการสร้างบัญชี: {e}', 'danger')
        return redirect(url_for('auth.login'))
    
# --- [NEW] ฟังก์ชันสำหรับหา Dashboard ที่ถูกต้อง ---
def get_redirect_target(user):
    """
    หา Dashboard ที่ถูกต้องสำหรับ User.
    """
    next_page = request.args.get('next')
    if next_page and urlparse(next_page).netloc == '':
        return next_page # ถ้ามี 'next' ที่ปลอดภัย
        
    # ลำดับการ Redirect
    if user.has_role('Admin'):
        return url_for('admin.index')
    elif user.has_role('Director'):
        return url_for('director.dashboard')
    elif user.has_role('Academic Affair'):
        return url_for('academic.dashboard')
    elif user.has_role('Department Head'):
        return url_for('department.dashboard')
    elif user.led_grade_level:
        return url_for('grade_level_head.dashboard')
    elif user.has_role('Advisor'):
        return url_for('advisor.dashboard')
    elif user.has_role('Teacher'):
        return url_for('teacher.dashboard')
    elif user.has_role('Student'):
         return url_for('student.dashboard')
    else:
         return url_for('main.index')

