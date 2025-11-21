# FILE: app/auth/routes.py
import os
import requests
import certifi
import json
from flask import current_app, render_template, flash, redirect, session, url_for, request
from flask_login import current_user, login_required, login_user, logout_user
from app import db
from app.auth import bp
from app.auth.forms import EditProfileForm, LoginForm, InitialSetupForm
from app.models import Role, User, Student
from app.services import log_action
from urllib.parse import urlparse
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleRequest

# --- Configuration for Production/Proxy ---
# Always allow insecure transport because the app runs behind Render's HTTPS proxy
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_google_flow():
    """สร้าง instance ของ Google OAuth Flow จาก Config."""
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

    # Scopes ที่ถูกต้อง (ต้องเป็น Plain String ห้ามมี markdown link)
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/forms.body",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/script.projects",
            "https://www.googleapis.com/auth/script.scriptapp",
            "https://www.googleapis.com/auth/script.deployments"
        ],
        redirect_uri=url_for('auth.google_callback', _external=True)
    )
    return flow

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.must_change_password:
             flash('กรุณาตั้งรหัสผ่านใหม่ และตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
             return redirect(url_for('auth.initial_setup'))
        if not current_user.initial_setup_complete:
             flash('กรุณาตั้งค่าบัญชีของคุณให้เสร็จสมบูรณ์', 'warning')
             return redirect(url_for('auth.initial_setup'))
        return redirect(get_redirect_target(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        username_input = form.username.data
        password_input = form.password.data
        user = User.query.filter_by(username=username_input).first()
        
        login_successful = False
        potential_student = Student.query.filter_by(student_id=username_input).first()
        is_student_login = False

        if user and user.check_password(password_input):
            login_successful = True
        elif potential_student and potential_student.student_id == password_input:
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
                        initial_setup_complete=True
                    )
                    student_role = Role.query.filter_by(name='Student').first()
                    if not student_role:
                        student_role = Role(name='Student', description='Student Role')
                        db.session.add(student_role)
                        db.session.flush()

                    new_user.roles.append(student_role)
                    db.session.add(new_user)
                    potential_student.user_id = new_user.id
                    
                    log_action("Auto-Create Student User", user=None, model=User, record_id=new_user.id)
                    db.session.commit()
                    user = new_user
                    is_student_login = True
                    login_successful = True
                    flash('สร้างบัญชีผู้ใช้สำหรับนักเรียนเรียบร้อยแล้ว', 'info')
                except Exception as e:
                    db.session.rollback()
                    flash(f'เกิดข้อผิดพลาดในการสร้างบัญชีนักเรียน: {e}', 'danger')
                    login_successful = False

        if not login_successful:
            log_action("Login Failed", user=None, new_value={'username': username_input})
            try: db.session.commit()
            except: pass
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        log_action("Login Success", user=user)
        try: db.session.commit()
        except: pass

        if not is_student_login:
            if user.must_change_password:
                return redirect(url_for('auth.initial_setup'))
            if not user.initial_setup_complete:
                return redirect(url_for('auth.initial_setup'))

        return redirect(get_redirect_target(user))

    return render_template('auth/login.html', title='เข้าสู่ระบบ', form=form)

@bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        user_id = current_user.id
        username = current_user.username
        logout_user()
        log_action("Logout Success", user=None, new_value={'user_id': user_id, 'username': username})
        try: db.session.commit()
        except: pass
    else:
        logout_user()
    flash('คุณได้ออกจากระบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/initial-setup', methods=['GET', 'POST'])
@login_required
def initial_setup():
    if not current_user.must_change_password and current_user.initial_setup_complete:
        return redirect(get_redirect_target(current_user))

    form = InitialSetupForm()
    password_required = current_user.must_change_password
    form.user_id = current_user.id

    if form.validate_on_submit():
        old_username = current_user.username
        
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data
        
        if password_required:
            current_user.username = form.username.data
            current_user.set_password(form.password.data)
            current_user.must_change_username = False
            current_user.must_change_password = False

        current_user.initial_setup_complete = True

        try:
            db.session.commit()
            flash('ตั้งค่าบัญชีของคุณเรียบร้อยแล้ว ยินดีต้อนรับ!', 'success')
            log_action("Initial Setup Complete", user=current_user, old_value={'username': old_username})
            try: db.session.commit()
            except: pass
            return redirect(get_redirect_target(current_user))
        except Exception as e:
             db.session.rollback()
             flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

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

@bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not current_user.initial_setup_complete or current_user.must_change_password:
        flash('กรุณาตั้งค่าบัญชีครั้งแรกให้เสร็จสมบูรณ์ก่อน', 'warning')
        return redirect(url_for('auth.initial_setup'))
        
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.job_title = form.job_title.data
        current_user.email = form.email.data
        current_user.member_of_groups = form.member_of_groups.data
        current_user.advised_classrooms = form.advised_classrooms.data
        
        if form.password.data:
            current_user.set_password(form.password.data)
            flash('บันทึกรหัสผ่านใหม่เรียบร้อยแล้ว', 'success')

        try:
            db.session.commit()
            flash('บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว', 'success')
            log_action("Profile Edited", user=current_user)
            try: db.session.commit()
            except: pass
            return redirect(url_for('auth.edit_profile'))
        except Exception as e:
             db.session.rollback()
             flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    elif request.method == 'GET':
        form.username.data = current_user.username
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.job_title.data = current_user.job_title
        form.email.data = current_user.email
        form.member_of_groups.data = current_user.member_of_groups
        form.advised_classrooms.data = current_user.advised_classrooms

    return render_template('auth/edit_profile.html', title='แก้ไขข้อมูลส่วนตัว', form=form)

@bp.route('/google-login')
def google_login():
    """Redirect ไปยังหน้า Google Consent Screen."""
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

@bp.route('/google-callback')
def google_callback():
    """จัดการ Callback หลังจาก Google Authenticate สำเร็จ."""
    if request.args.get('state') != session.get('state'):
        flash('เกิดข้อผิดพลาดในการยืนยันตัวตน (Invalid state)', 'danger')
        return redirect(url_for('auth.login'))

    flow = get_google_flow()
    try:
        flow.fetch_token(authorization_response=request.url, verify=certifi.where())
    except Exception as e:
        current_app.logger.error(f"Error fetching Google token: {e}")
        flash(f'เกิดข้อผิดพลาดในการเชื่อมต่อ Google: {e}', 'danger')
        return redirect(url_for('auth.login'))

    credentials = flow.credentials
    try:
        authed_session = requests.Session()
        authed_session.verify = certifi.where()
        google_request = GoogleRequest(session=authed_session)
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, google_request, current_app.config['GOOGLE_CLIENT_ID']
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

    user = User.query.filter_by(google_id=google_id).first()
    if user:
        user.google_credentials_json = credentials.to_json() 
        login_user(user, remember=True)
        log_action("Login Success (Google)", user=user)
        db.session.commit()
        if not user.initial_setup_complete:
            return redirect(url_for('auth.initial_setup'))
        return redirect(get_redirect_target(user))

    user = User.query.filter_by(email=user_email).first()
    if user:
        user.google_id = google_id
        user.google_credentials_json = credentials.to_json()
        db.session.add(user)
        log_action("Link Google Account", user=user)
        db.session.commit()
        login_user(user, remember=True)
        if not user.initial_setup_complete:
            return redirect(url_for('auth.initial_setup'))
        return redirect(get_redirect_target(user))

    if User.query.filter_by(username=user_email).first():
        flash(f'ไม่สามารถสร้างบัญชีได้: ชื่อผู้ใช้ "{user_email}" มีผู้ใช้งานแล้ว', 'danger')
        return redirect(url_for('auth.login'))

    try:
        new_user = User(
            google_id=google_id,
            email=user_email,
            first_name=user_first_name,
            last_name=user_last_name,
            username=user_email,
            initial_setup_complete=False,
            google_credentials_json = credentials.to_json()
        )
        db.session.add(new_user)
        db.session.commit()
        log_action("Auto-Create User (Google)", user=new_user)
        db.session.commit()
        login_user(new_user, remember=True)
        flash('สร้างบัญชีผู้ใช้ผ่าน Google สำเร็จ! กรุณาตั้งค่าบัญชีของคุณ', 'success')
        return redirect(url_for('auth.initial_setup'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user from Google: {e}")
        flash(f'เกิดข้อผิดพลาดในการสร้างบัญชี: {e}', 'danger')
        return redirect(url_for('auth.login'))

def get_redirect_target(user):
    next_page = request.args.get('next')
    if next_page and urlparse(next_page).netloc == '':
        return next_page
    if user.has_role('Admin'): return url_for('admin.index')
    elif user.has_role('Director'): return url_for('director.dashboard')
    elif user.has_role('Academic Affair'): return url_for('academic.dashboard')
    elif user.has_role('Department Head'): return url_for('department.dashboard')
    elif user.led_grade_level: return url_for('grade_level_head.dashboard')
    elif user.has_role('Advisor'): return url_for('advisor.dashboard')
    elif user.has_role('Teacher'): return url_for('teacher.dashboard')
    elif user.has_role('Student'): return url_for('student.dashboard')
    else: return url_for('main.index')