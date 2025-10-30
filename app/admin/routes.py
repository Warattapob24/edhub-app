# app/admin/routes.py

from collections import defaultdict
from datetime import datetime, time
import shutil
from urllib.parse import parse_qs, urlparse
import zipfile
from flask_wtf.file import FileAllowed
import io
import math
from PIL import Image
from sqlalchemy.exc import IntegrityError # สำหรับดักจับ Error ข้อมูลซ้ำ
from flask_wtf import FlaskForm
from wtforms import FileField, HiddenField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired
from app.admin import bp
from flask import abort, json, jsonify, render_template, redirect, send_file, url_for, flash, request, current_app, send_from_directory, session
from app import db
from sqlalchemy import func, or_
import json, os, uuid
import pandas as pd
from sqlalchemy.orm import joinedload, selectinload
from app.models import AcademicYear, AdministrativeDepartment, AssessmentDimension, AssessmentTemplate, AssessmentTopic, AttendanceRecord, AttendanceWarning, AuditLog, Classroom, Course, Curriculum, Enrollment, GradeLevel, GradedItem, Indicator, LearningStrand, LearningUnit, LessonPlan, Notification, Program, Role, Room, RubricLevel, Score, Semester, Setting, Standard, Student, Subject, SubjectGroup, SubjectType, TimeSlot, User, WeeklyScheduleSlot
from app.admin.forms import AcademicYearForm, AddUserForm, AssessmentDimensionForm, AssessmentTemplateForm, AssessmentTopicForm, AssessmentTopicForm, AssignAdvisorsForm, AssignHeadsForm, ClassroomForm, CurriculumForm, EditUserForm, EnrollmentForm, GradeLevelForm, ProgramForm, RoleForm, RubricLevelForm, SemesterForm, StudentForm, SubjectForm, SubjectForm, SubjectGroupForm, SubjectTypeForm, get_all_academic_years, get_all_semesters, get_all_grade_levels
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.services import log_action, promote_students_to_next_year, copy_schedule_structure
# from flask_login import login_required # This will be enabled later

BATCH_SIZE = 20 # กำหนดขนาดของแต่ละ Batch (ปรับค่าได้ตามความเหมาะสม)

def _cleanup_file(filepath):
    """ Safely delete a file if it exists. """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            current_app.logger.info(f"Deleted temporary import file: {filepath}")
    except Exception as del_err:
        current_app.logger.error(f"Error deleting temporary import file {filepath}: {del_err}")

@bp.route('/')
@login_required
def index():
    """
    This is the main dashboard for the Admin Panel.
    For now, it renders a simple layout.
    """
    return render_template('admin/dashboard.html', title='แดชบอร์ดแอดมิน')

class SettingsForm(FlaskForm):
    school_name = StringField('ชื่อโรงเรียน', validators=[DataRequired()])
    school_address = TextAreaField('ที่อยู่โรงเรียน')
    submit = SubmitField('บันทึกการตั้งค่า')

    school_district = StringField('อำเภอ/เขต')
    school_province = StringField('จังหวัด')
    school_affiliation = StringField('หน่วยงานต้นสังกัด')
    school_logo = FileField('โลโก้โรงเรียน (ไฟล์รูปภาพ)', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'รองรับเฉพาะไฟล์รูปภาพเท่านั้น!')
    ])
    
    submit = SubmitField('บันทึกการตั้งค่า')
    
# เส้นทางสำหรับแสดงรายการบทบาท (READ)
@bp.route('/roles')
# @login_required
def list_roles():
    roles = Role.query.order_by(Role.id).all()
    return render_template('admin/roles.html', roles=roles, title='จัดการบทบาท')

# --- ส่วนจัดการการตั้งค่า (Settings Management) ---
@bp.route('/settings', methods=['GET', 'POST'])
@login_required
# @admin_required
def manage_settings():
    form = SettingsForm() # สมมติว่าฟอร์มของคุณชื่อนี้
    current_logo_setting = Setting.query.filter_by(key='school_logo_path').first()
    current_logo_url = url_for('static', filename=f"uploads/{current_logo_setting.value}") if current_logo_setting and current_logo_setting.value else None

    if form.validate_on_submit():
        try:
            changes = {} # Track changes for logging
            old_logo_value = current_logo_setting.value if current_logo_setting else None

            # --- File Upload Handling (โค้ดเดิมของคุณ) ---
            logo_file = form.school_logo.data
            if logo_file:
                # Create unique filename
                filename = secure_filename(f"{uuid.uuid4().hex}_{logo_file.filename}")
                upload_folder = os.path.join(current_app.static_folder, 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, filename)

                # Delete old file if exists
                if old_logo_value:
                    old_file_path = os.path.join(upload_folder, old_logo_value)
                    if os.path.exists(old_file_path):
                        try: os.remove(old_file_path)
                        except OSError as oe: current_app.logger.warning(f"Could not delete old logo {old_logo_value}: {oe}")
                
                # --- [โค้ดเดิม] บันทึกโลโก้หลัก ---
                logo_file.save(file_path)

                # --- [START] 🔽 โค้ดใหม่: สร้าง Favicon อัตโนมัติ 🔽 ---
                try:
                    # 1. กำหนดตำแหน่งที่จะบันทึกไฟล์ (ใน /static/img/)
                    favicon_32_path = os.path.join(current_app.static_folder, 'img', 'favicon_32.png')
                    favicon_180_path = os.path.join(current_app.static_folder, 'img', 'favicon_180.png')
                    os.makedirs(os.path.join(current_app.static_folder, 'img'), exist_ok=True) # สร้างโฟลเดอร์ 'img' ถ้ายังไม่มี

                    # 2. เปิดไฟล์โลโก้หลักที่เพิ่งบันทึก (file_path)
                    with Image.open(file_path) as img:
                        # 3. สร้างเวอร์ชัน 32x32
                        img_32 = img.copy()
                        img_32.thumbnail((32, 32), Image.Resampling.LANCZOS)
                        img_32.save(favicon_32_path, "PNG", optimize=True)
                        
                        # 4. สร้างเวอร์ชัน 180x180 (สำหรับ apple-touch-icon)
                        img_180 = img.copy()
                        img_180.thumbnail((180, 180), Image.Resampling.LANCZOS)
                        img_180.save(favicon_180_path, "PNG", optimize=True)

                    # 5. [สำคัญ] อัปเดต 'favicon_version' ในฐานข้อมูลเพื่อทำ Cache Busting
                    new_version = str(int(time.time())) # ใช้ timestamp ปัจจุบัน
                    
                    # --- [FIX] ใช้ .filter_by(key=...) เสมอ ---
                    favicon_setting = Setting.query.filter_by(key='favicon_version').first()
                    
                    if not favicon_setting:
                        favicon_setting = Setting(key='favicon_version', value=new_version)
                        db.session.add(favicon_setting)
                    else:
                        favicon_setting.value = new_version
                    
                    changes['favicon_version'] = {'old': favicon_setting.value if 'value' in locals() and favicon_setting else None, 'new': new_version} # แก้ไขการอ้างอิงเล็กน้อย
                    flash('สร้าง Favicon อัตโนมัติจากโลโก้ใหม่เรียบร้อยแล้ว', 'info')

                except Exception as e:
                    current_app.logger.error(f"Failed to generate favicon: {e}")
                    flash(f'บันทึกโลโก้หลักสำเร็จ แต่สร้าง Favicon อัตโนมัติไม่สำเร็จ: {e}', 'warning')
                # --- [END] 🔼 โค้ดใหม่: สร้าง Favicon อัตโนมัติ 🔼 ---


                # --- [โค้ดเดิม] อัปเดต Setting DB entry ---
                setting_logo = Setting.query.filter_by(key='school_logo_path').first()
                if setting_logo:
                    setting_logo.value = filename
                else:
                    setting_logo = Setting(key='school_logo_path', value=filename)
                    db.session.add(setting_logo)

                # Track change for log
                changes['school_logo_path'] = {'old': old_logo_value, 'new': filename}
                current_logo_url = url_for('static', filename=f"uploads/{filename}") # Update URL for immediate display

            # --- Text Settings Handling (โค้ดเดิมของคุณ) ---
            settings_to_update = {
                'school_name': form.school_name.data,
                'school_address': form.school_address.data,
                'school_district': form.school_district.data,
                'school_province': form.school_province.data,
                'school_affiliation': form.school_affiliation.data
            }
            for key, value in settings_to_update.items():
                setting = Setting.query.filter_by(key=key).first()
                if setting:
                    if setting.value != value: # Only log if value changed
                        changes[key] = {'old': setting.value, 'new': value}
                        setting.value = value
                else:
                    changes[key] = {'old': None, 'new': value}
                    setting = Setting(key=key, value=value)
                    db.session.add(setting)

            # --- [START LOG] Log the changes before commit (โค้ดเดิมของคุณ) ---
            if changes: # Only log if something actually changed
                log_action("Update Settings", model=Setting, new_value=changes) # Log all changes together
            # --- [END LOG] ---

            db.session.commit() # Commit setting changes, favicon_version, and log
            flash('บันทึกการตั้งค่าเรียบร้อยแล้ว', 'success')
            # No redirect needed, stay on page to show updated logo/values

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating settings: {e}", exc_info=True)
            # --- [START LOG] Log failure (โค้ดเดิมของคุณ) ---
            log_action(f"Update Settings Failed: {type(e).__name__}")
            try:
                db.session.commit() # Commit failure log
            except Exception as log_err:
                 db.session.rollback()
                 current_app.logger.error(f"Failed to commit settings update failure log: {log_err}")
            # --- [END LOG] ---
            flash(f'เกิดข้อผิดพลาดในการบันทึกการตั้งค่า: {e}', 'danger')

    # Load existing values on GET request (โค้ดเดิมของคุณ)
    if request.method == 'GET':
        for field_name, field in form._fields.items():
            if field.type not in ['FileField', 'SubmitField', 'CSRFTokenField']:
                setting = Setting.query.filter_by(key=field_name).first()
                if setting and setting.value:
                    field.data = setting.value

    return render_template('admin/settings.html',
                           form=form,
                           title='ตั้งค่าโรงเรียน',
                           current_logo_url=current_logo_url)

# เส้นทางสำหรับเพิ่มบทบาทใหม่ (CREATE)
@bp.route('/roles/add', methods=['GET', 'POST'])
# @login_required
def add_role():
    form = RoleForm()
    if form.validate_on_submit():
        role = Role(name=form.name.data, description=form.description.data)
        db.session.add(role)
        db.session.commit()
        flash('เพิ่มบทบาทใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_roles'))
    return render_template('admin/role_form.html', form=form, title='เพิ่มบทบาทใหม่')

# เส้นทางสำหรับแก้ไขบทบาท (UPDATE)
@bp.route('/roles/edit/<int:role_id>', methods=['GET', 'POST'])
# @login_required
def edit_role(role_id):
    role = Role.query.get_or_404(role_id)
    form = RoleForm(obj=role)
    if form.validate_on_submit():
        role.name = form.name.data
        role.description = form.description.data
        db.session.commit()
        flash('แก้ไขข้อมูลบทบาทเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_roles'))
    return render_template('admin/role_form.html', form=form, title='แก้ไขบทบาท')

# เส้นทางสำหรับลบบทบาท (DELETE)
@bp.route('/roles/delete/<int:role_id>', methods=['POST'])
# @login_required
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    # เพิ่มเงื่อนไขป้องกันการลบบทบาทที่มีผู้ใช้งาน
    if role.users:
        flash('ไม่สามารถลบบทบาทนี้ได้เนื่องจากมีผู้ใช้งานในบทบาทนี้อยู่', 'danger')
        return redirect(url_for('admin.list_roles'))
    db.session.delete(role)
    db.session.commit()
    flash('ลบบทบาทเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_roles'))

# เส้นทางสำหรับแสดงรายการผู้ใช้ (READ)
@bp.route('/users')
@login_required # Add @admin_required if you have one
def list_users():
    # --- Filter Logic Start ---
    search_name = request.args.get('name', '', type=str).strip()
    selected_role_id = request.args.get('role_id', '', type=str).strip() # Get as string first

    query = User.query # Start with the base query

    # Apply name filter if provided
    if search_name:
        search_pattern = f"%{search_name}%"
        query = query.filter(or_(
            User.first_name.ilike(search_pattern),
            User.last_name.ilike(search_pattern),
            User.username.ilike(search_pattern) # Optional: search username too
        ))

    # Apply role filter if provided and valid
    role_id_int = None # Variable to hold integer role ID for template
    if selected_role_id:
        try:
            role_id_int = int(selected_role_id)
            # Join with the roles relationship and filter by Role.id
            query = query.join(User.roles).filter(Role.id == role_id_int)
        except ValueError:
            flash('Role ID ที่ระบุไม่ถูกต้อง', 'warning')
            selected_role_id = '' # Clear invalid ID

    # Get all roles for the filter dropdown
    all_roles = Role.query.order_by(Role.name).all()
    # --- Filter Logic End ---

    # Pagination using the potentially filtered query
    page = request.args.get('page', 1, type=int)
    # Use the filtered query here, and adjust per_page if needed (e.g., from config)
    pagination = query.order_by(User.id.asc()).paginate(
        page=page, per_page=current_app.config.get('USERS_PER_PAGE', 20), error_out=False # Use config or default to 20
    )
    users = pagination.items

    return render_template('admin/users.html',
                           title='จัดการผู้ใช้งาน', # Keep your title
                           # icon_class='bi-people-fill', # Keep your icon class if you use it
                           users=users,
                           pagination=pagination,
                           # --- Pass filter values back to the template ---
                           all_roles=all_roles,
                           current_name_filter=search_name,
                           current_role_id=role_id_int
                           # --- End pass filter values ---
                          )

# เส้นทางสำหรับเพิ่มผู้ใช้ใหม่ (CREATE)
@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
# @admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                email=form.email.data,
                name_prefix=form.name_prefix.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                job_title=form.job_title.data
            )
            user.set_password(form.password.data)
            user.roles = form.roles.data
            db.session.add(user)
            db.session.flush() # Flush to get user.id before logging

            # --- [START LOG] Log user creation before commit ---
            log_action(
                "Create User",
                model=User,
                record_id=user.id,
                new_value={'username': user.username, 'name': user.full_name, 'roles': [r.name for r in user.roles]}
            )
            # --- [END LOG] ---

            db.session.commit() # Commit user and log together
            flash('เพิ่มผู้ใช้งานใหม่เรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin.list_users'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating user: {e}", exc_info=True)
            # --- [START LOG] Log failure attempt ---
            log_action(
                f"Create User Failed: {type(e).__name__}", # Log exception type
                model=User,
                new_value={'username': form.username.data}
            )
            try:
                db.session.commit() # Commit the failure log
            except Exception as log_err:
                 db.session.rollback()
                 current_app.logger.error(f"Failed to commit user creation failure log: {log_err}")
            # --- [END LOG] ---
            flash(f'เกิดข้อผิดพลาดในการสร้างผู้ใช้: {e}', 'danger')

    return render_template('admin/user_form.html', form=form, title='เพิ่มผู้ใช้งานใหม่')

# เส้นทางสำหรับแก้ไขผู้ใช้ (UPDATE)
@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = EditUserForm(obj=user)
    if form.validate_on_submit():
        try:
            # Store old values before making changes
            old_values = {
                'username': user.username,
                'email': user.email,
                'name_prefix': user.name_prefix,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'job_title': user.job_title,
                'roles': sorted([r.name for r in user.roles]) # Sort roles for consistent comparison
            }

            user.username = form.username.data
            user.email = form.email.data
            user.name_prefix = form.name_prefix.data
            user.first_name = form.first_name.data
            user.last_name = form.last_name.data
            user.job_title = form.job_title.data
            password_changed = False
            if form.password.data:
                user.set_password(form.password.data)
                password_changed = True
            user.roles = form.roles.data

            # Prepare new values
            new_values = {
                'username': user.username,
                'email': user.email,
                'name_prefix': user.name_prefix,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'job_title': user.job_title,
                'roles': sorted([r.name for r in user.roles]), # Sort roles
                'password_changed': password_changed
            }

            # --- [START LOG] Log the edit action before commit ---
            # Compare dictionaries to log only actual changes (optional enhancement)
            changed_fields_old = {}
            changed_fields_new = {}
            for key in old_values:
                if old_values[key] != new_values.get(key):
                     changed_fields_old[key] = old_values[key]
                     changed_fields_new[key] = new_values.get(key)
            if password_changed: # Always log if password changed
                 changed_fields_old['password'] = '******'
                 changed_fields_new['password'] = 'Changed'

            if changed_fields_old: # Only log if there are actual changes
                log_action("Edit User", model=User, record_id=user.id, old_value=changed_fields_old, new_value=changed_fields_new)
            # --- [END LOG] ---

            db.session.commit() # Commit changes and log together
            flash('แก้ไขข้อมูลผู้ใช้งานเรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin.list_users'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing user {user_id}: {e}", exc_info=True)
            # --- [START LOG] Log failure ---
            log_action(f"Edit User Failed: {type(e).__name__}", model=User, record_id=user_id)
            try:
                db.session.commit() # Commit failure log
            except Exception as log_err:
                 db.session.rollback()
                 current_app.logger.error(f"Failed to commit user edit failure log: {log_err}")
            # --- [END LOG] ---
            flash(f'เกิดข้อผิดพลาดในการแก้ไขผู้ใช้: {e}', 'danger')

    return render_template('admin/user_form.html', form=form, title='แก้ไขผู้ใช้งาน')

# เส้นทางสำหรับลบผู้ใช้ (DELETE)
@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
# @admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
       flash('ไม่สามารถลบผู้ใช้ปัจจุบันได้', 'danger')
       return redirect(url_for('admin.list_users'))
    try:
        # Get user info before deleting for the log
        user_info = {'username': user.username, 'name': user.full_name, 'id': user.id}
        db.session.delete(user)

        # --- [START LOG] Log deletion before commit ---
        log_action("Delete User", model=User, record_id=user_id, old_value=user_info)
        # --- [END LOG] ---

        db.session.commit() # Commit deletion and log together
        flash('ลบผู้ใช้งานเรียบร้อยแล้ว', 'info')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        # --- [START LOG] Log failure ---
        log_action(f"Delete User Failed: {type(e).__name__}", model=User, record_id=user_id)
        try:
            db.session.commit() # Commit failure log
        except Exception as log_err:
             db.session.rollback()
             current_app.logger.error(f"Failed to commit user deletion failure log: {log_err}")
        # --- [END LOG] ---
        flash(f'เกิดข้อผิดพลาดในการลบผู้ใช้: {e}', 'danger')

    return redirect(url_for('admin.list_users'))

# Route for displaying all grade levels (READ)
@bp.route('/grade-levels')
def list_grade_levels():
    page = request.args.get('page', 1, type=int)
    pagination = GradeLevel.query.order_by(GradeLevel.id).paginate(
        page=page, per_page=20, error_out=False
    )
    grades = pagination.items
    return render_template('admin/grade_levels.html', 
                           grades=grades, 
                           pagination=pagination,
                           title='จัดการระดับชั้น')

# Route for adding a new grade level (CREATE)
@bp.route('/grade-levels/add', methods=['GET', 'POST'])
# @login_required
def add_grade_level():
    form = GradeLevelForm()
    if form.validate_on_submit():
        grade = GradeLevel(name=form.name.data, short_name=form.short_name.data)
        db.session.add(grade)
        db.session.commit()
        flash('เพิ่มระดับชั้นใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_grade_levels'))
    return render_template('admin/grade_level_form.html', form=form, title='เพิ่มระดับชั้นใหม่')

# Route for editing a grade level (UPDATE)
@bp.route('/grade-levels/edit/<int:grade_id>', methods=['GET', 'POST'])
# @login_required
def edit_grade_level(grade_id):
    grade = GradeLevel.query.get_or_404(grade_id)
    form = GradeLevelForm(obj=grade)
    if form.validate_on_submit():
        grade.name = form.name.data
        grade.short_name = form.short_name.data
        db.session.commit()
        flash('แก้ไขข้อมูลระดับชั้นเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_grade_levels'))
    return render_template('admin/grade_level_form.html', form=form, title='แก้ไขระดับชั้น')

# Route for deleting a grade level (DELETE)
@bp.route('/grade-levels/delete/<int:grade_id>', methods=['POST'])
# @login_required
def delete_grade_level(grade_id):
    grade = GradeLevel.query.get_or_404(grade_id)
    db.session.delete(grade)
    db.session.commit()
    flash('ลบระดับชั้นเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_grade_levels'))

# Route for displaying all subject groups (READ)
@bp.route('/subject-groups')
def list_subject_groups():
    groups = SubjectGroup.query.order_by(SubjectGroup.name).all()
    return render_template('admin/subject_groups.html', groups=groups, title='จัดการกลุ่มสาระการเรียนรู้')

@bp.route('/subject-groups/add', methods=['GET', 'POST'])
def add_subject_group():
    form = SubjectGroupForm()
    if form.validate_on_submit():
        new_group = SubjectGroup(name=form.name.data)
        db.session.add(new_group)
        db.session.commit()
        flash('สร้างกลุ่มสาระฯ ใหม่เรียบร้อยแล้ว', 'success')
    # หาก validate ไม่ผ่าน (ซึ่งไม่น่าเกิดกับฟอร์มที่มีแค่ชื่อ) ก็แค่ redirect กลับ
    return redirect(url_for('admin.list_subject_groups'))

# Route for deleting a subject group (DELETE)
@bp.route('/subject-groups/delete/<int:group_id>', methods=['POST'])
# @login_required
def delete_subject_group(group_id):
    group = SubjectGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    flash('ลบกลุ่มสาระฯ เรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_subject_groups'))

# Route for displaying all subject types (READ)
@bp.route('/subject-types')
# @login_required
def list_subject_types():
    subject_types = SubjectType.query.order_by(SubjectType.name).all()
    return render_template('admin/subject_types.html', types=subject_types, title='จัดการประเภทวิชา')

# Route for adding a new subject type (CREATE)
@bp.route('/subject-types/add', methods=['GET', 'POST'])
# @login_required
def add_subject_type():
    form = SubjectTypeForm()
    if form.validate_on_submit():
        # Note: Renamed variable from 'type' to 'subject_type' to avoid conflict with Python's built-in type()
        subject_type = SubjectType(name=form.name.data)
        db.session.add(subject_type)
        db.session.commit()
        flash('เพิ่มประเภทวิชาใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_subject_types'))
    return render_template('admin/subject_type_form.html', form=form, title='เพิ่มประเภทวิชาใหม่')

# Route for editing a subject type (UPDATE)
@bp.route('/subject-types/edit/<int:type_id>', methods=['GET', 'POST'])
# @login_required
def edit_subject_type(type_id):
    subject_type = SubjectType.query.get_or_404(type_id)
    form = SubjectTypeForm(obj=subject_type)
    if form.validate_on_submit():
        subject_type.name = form.name.data
        db.session.commit()
        flash('แก้ไขข้อมูลประเภทวิชาเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_subject_types'))
    return render_template('admin/subject_type_form.html', form=form, title='แก้ไขประเภทวิชา')

# Route for deleting a subject type (DELETE)
@bp.route('/subject-types/delete/<int:type_id>', methods=['POST'])
# @login_required
def delete_subject_type(type_id):
    subject_type = SubjectType.query.get_or_404(type_id)
    db.session.delete(subject_type)
    db.session.commit()
    flash('ลบประเภทวิชาเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_subject_types'))

# เส้นทางสำหรับแสดงรายการปีการศึกษา
@bp.route('/academic-years')
def list_academic_years():
    years = AcademicYear.query.order_by(AcademicYear.year.desc()).all()
    return render_template('admin/academic_years.html', years=years, title='จัดการปีการศึกษา')

# เส้นทางสำหรับเพิ่มปีการศึกษาใหม่
@bp.route('/academic-years/add', methods=['GET', 'POST'])
def add_academic_year():
    form = AcademicYearForm()
    if form.validate_on_submit():
        year = AcademicYear(year=form.year.data)
        db.session.add(year)
        db.session.commit()
        flash('เพิ่มปีการศึกษาใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_academic_years'))
    return render_template('admin/academic_year_form.html', form=form, title='เพิ่มปีการศึกษาใหม่')

# เส้นทางสำหรับแก้ไขปีการศึกษา
@bp.route('/academic-years/edit/<int:year_id>', methods=['GET', 'POST'])
def edit_academic_year(year_id):
    year = AcademicYear.query.get_or_404(year_id)
    form = AcademicYearForm(obj=year)
    if form.validate_on_submit():
        year.year = form.year.data
        db.session.commit()
        flash('แก้ไขข้อมูลปีการศึกษาเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_academic_years'))
    return render_template('admin/academic_year_form.html', form=form, title='แก้ไขปีการศึกษา')

# เส้นทางสำหรับลบปีการศึกษา
@bp.route('/academic-years/delete/<int:year_id>', methods=['POST'])
def delete_academic_year(year_id):
    year = AcademicYear.query.get_or_404(year_id)
    # หมายเหตุ: อาจจะต้องเพิ่มเงื่อนไขป้องกันการลบ ถ้ามีข้อมูลอื่นผูกอยู่กับปีการศึกษานี้ในอนาคต
    db.session.delete(year)
    db.session.commit()
    flash('ลบปีการศึกษาเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_academic_years'))

@bp.route('/semesters')
def list_semesters():
    semesters = Semester.query.order_by(Semester.id.desc()).all()
    return render_template('semesters.html', semesters=semesters, title='รายการภาคเรียนทั้งหมด')

@bp.route('/semesters/add', methods=['GET', 'POST'])
def add_semester():
    form = SemesterForm()
    if form.validate_on_submit():
        if form.is_current.data:
            # ทำให้ภาคเรียนอื่นทั้งหมดไม่เป็นภาคเรียนปัจจุบัน
            Semester.query.update({Semester.is_current: False})
        
        semester = Semester(
            term=form.term.data,
            academic_year=form.academic_year.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            is_current=form.is_current.data
        )
        db.session.add(semester)
        db.session.commit()
        flash('เพิ่มภาคเรียนใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_academic_years'))
    return render_template('admin/semester_form.html', form=form, title='เพิ่มภาคเรียนใหม่')

@bp.route('/semesters/edit/<int:semester_id>', methods=['GET', 'POST'])
def edit_semester(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    form = SemesterForm(obj=semester)
    if form.validate_on_submit():
        # --- START: CORRECTED LOGIC ---
        # ตรวจสอบว่ามีการติ๊กเลือก "ภาคเรียนปัจจุบัน" หรือไม่
        if form.is_current.data:
            # 1. สั่งล้างค่า is_current ของทุกภาคเรียนใน DB ให้เป็น False ทั้งหมดก่อน
            #    วิธีนี้จะปลอดภัยและแน่นอนกว่าการกรองออก
            Semester.query.update({'is_current': False})
        
        # 2. นำข้อมูลจากฟอร์มทั้งหมดมาใส่ใน object ของ semester ที่เรากำลังแก้ไข
        semester.term = form.term.data
        semester.academic_year = form.academic_year.data
        semester.start_date = form.start_date.data
        semester.end_date = form.end_date.data
        # 3. กำหนดค่า is_current (จะเป็น True ถ้าติ๊ก, False ถ้าไม่ติ๊ก)
        semester.is_current = form.is_current.data
        # --- END: CORRECTED LOGIC ---
        
        db.session.commit()
        flash('แก้ไขข้อมูลภาคเรียนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_academic_years'))
        
    return render_template('admin/semester_form.html', form=form, title='แก้ไขภาคเรียน')

@bp.route('/semesters/delete/<int:semester_id>', methods=['POST'])
def delete_semester(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    # หมายเหตุ: ในอนาคตควรเพิ่มเงื่อนไขป้องกันการลบภาคเรียนที่มีข้อมูลผูกอยู่ เช่น curriculum
    db.session.delete(semester)
    db.session.commit()
    flash('ลบภาคเรียนเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_academic_years'))

# เส้นทางสำหรับแสดงรายการรายวิชา
@bp.route('/subjects')
def list_subjects():
# 1. รับค่า Filter จาก URL
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    group_id = request.args.get('group_id', 0, type=int)
    type_id = request.args.get('type_id', 0, type=int)
    grade_id = request.args.get('grade_id', 0, type=int)

    # 2. สร้าง Query พื้นฐาน
    query = Subject.query.order_by(Subject.subject_code)

    # 3. ใช้ Filter กับ Query (ถ้ามี)
    if q:
        query = query.filter(
            or_(
                Subject.name.ilike(f'%{q}%'),
                Subject.subject_code.ilike(f'%{q}%')
            )
        )
    if group_id:
        query = query.filter(Subject.subject_group_id == group_id)
    if type_id:
        query = query.filter(Subject.subject_type_id == type_id)
    if grade_id:
        # กรองสำหรับ Many-to-Many relationship (grade_levels)
        query = query.filter(Subject.grade_levels.any(id=grade_id))

    # 4. ทำ Pagination กับ Query ที่กรองแล้ว
    # (ท่านอาจต้องปรับ PER_PAGE ให้เหมาะสม)
    PER_PAGE = 20 
    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)
    subjects = pagination.items

    # 5. ดึงข้อมูลสำหรับใส่ใน Dropdown ของ Filter
    all_groups = SubjectGroup.query.order_by(SubjectGroup.name).all()
    all_types = SubjectType.query.order_by(SubjectType.name).all()
    all_grades = GradeLevel.query.order_by(GradeLevel.id).all()
    
    # 6. สร้าง Form เปล่าสำหรับ CSRF (ใช้ในปุ่มลบ)
    form = FlaskForm() 

    return render_template('admin/subjects.html', 
                           subjects=subjects, 
                           pagination=pagination,
                           form=form,
                           title='จัดการรายวิชา',
                           # ส่งค่า Filter กลับไปที่ Template
                           q=q,
                           selected_group_id=group_id,
                           selected_type_id=type_id,
                           selected_grade_id=grade_id,
                           # ส่งรายการสำหรับ Dropdown
                           all_groups=all_groups,
                           all_types=all_types,
                           all_grades=all_grades
                           )
                           
# เส้นทางสำหรับเพิ่มรายวิชาใหม่
@bp.route('/subjects/add', methods=['GET', 'POST'])
def add_subject():
    form = SubjectForm()
    if form.validate_on_submit():
        subject = Subject(
            subject_code=form.subject_code.data,
            name=form.name.data,
            credit=form.credit.data,
            subject_group=form.subject_group.data,
            subject_type=form.subject_type.data
        )
        db.session.add(subject) # <-- เพิ่มบรรทัดนี้ที่หายไป
        # ต้อง add subject ก่อน ถึงจะกำหนด relationship แบบ many-to-many ได้
        subject.grade_levels = form.grade_levels.data
        db.session.commit()
        flash('เพิ่มรายวิชาใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_subjects'))
    return render_template('admin/subject_form.html', form=form, title='เพิ่มรายวิชาใหม่')

# เส้นทางสำหรับแก้ไขรายวิชา
@bp.route('/subjects/edit/<int:subject_id>', methods=['GET', 'POST'])
def edit_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    form = SubjectForm(obj=subject)

    # --- [ START V17 MODIFICATION ] ---
    # รับค่า Filter และ Page จาก URL arguments
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str)
    group_id = request.args.get('group_id', 0, type=int)
    type_id = request.args.get('type_id', 0, type=int)
    grade_id = request.args.get('grade_id', 0, type=int)

    # สร้าง Dictionary สำหรับส่งต่อ Parameters
    redirect_args = {
        'page': page, 
        'q': q, 
        'group_id': group_id, 
        'type_id': type_id, 
        'grade_id': grade_id
    }
    # --- [ END V17 MODIFICATION ] ---

    if form.validate_on_submit():
        subject.subject_code = form.subject_code.data
        subject.name = form.name.data
        subject.credit = form.credit.data
        subject.subject_group = form.subject_group.data
        subject.subject_type = form.subject_type.data
        subject.grade_levels = form.grade_levels.data # <-- แก้ไข V14 แล้ว
        db.session.commit()
        flash('แก้ไขข้อมูลรายวิชาเรียบร้อยแล้ว', 'success')
        
        # --- [ START V17 MODIFICATION ] ---
        # ส่งต่อ Filter Parameters กลับไปที่ list_subjects
        return redirect(url_for('admin.list_subjects', **redirect_args))
        # --- [ END V17 MODIFICATION ] ---
    
    # ส่งต่อ Filter Parameters ไปยัง Template (เผื่อใช้ในปุ่ม Cancel)
    # และส่งค่า page ที่ถูกต้อง
    return render_template('admin/subject_form.html', 
                           form=form, 
                           title='แก้ไขรายวิชา', 
                           page=page, # <-- ส่ง page ที่ถูกต้อง
                           redirect_args=redirect_args) # <-- ส่ง args สำหรับปุ่ม Cancel

# เส้นทางสำหรับลบรายวิชา
@bp.route('/subjects/delete/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    
    # --- [ START V17 MODIFICATION ] ---
    # ดึงค่า Filter และ Page จาก URL ที่ผู้ใช้เข้ามา (Referer)
    redirect_args = {}
    try:
        referer_url = request.referrer
        if referer_url:
            parsed_url = urlparse(referer_url)
            query_params = parse_qs(parsed_url.query)
            # ดึงค่าที่ต้องการ ถ้ามีใน URL เดิม
            redirect_args['page'] = int(query_params.get('page', ['1'])[0])
            redirect_args['q'] = query_params.get('q', [''])[0]
            redirect_args['group_id'] = int(query_params.get('group_id', ['0'])[0])
            redirect_args['type_id'] = int(query_params.get('type_id', ['0'])[0])
            redirect_args['grade_id'] = int(query_params.get('grade_id', ['0'])[0])
    except Exception as e:
        current_app.logger.warning(f"Could not parse referer URL for delete redirect: {e}")
        redirect_args = {'page': 1} # Fallback to page 1 if parsing fails
    # --- [ END V17 MODIFICATION ] ---

    try:
        db.session.delete(subject)
        db.session.commit()
        flash('ลบรายวิชาเรียบร้อยแล้ว', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการลบรายวิชา: {e}', 'danger')
        current_app.logger.error(f"Error deleting subject {subject_id}: {e}", exc_info=True)

    # --- [ START V17 MODIFICATION ] ---
    # Redirect กลับไปหน้าเดิม พร้อม Filter เดิม
    return redirect(url_for('admin.list_subjects', **redirect_args))
    # --- [ END V17 MODIFICATION ] ---

# --- ส่วนจัดการหลักสูตร (Curriculum Management) ---
@bp.route('/api/curriculum/<int:semester_id>/<int:grade_id>')
def get_curriculum_for_selection(semester_id, grade_id):
    existing_subjects = Curriculum.query.filter_by(semester_id=semester_id, grade_level_id=grade_id).all()
    existing_subject_ids = [c.subject_id for c in existing_subjects]
    return jsonify(existing_subject_ids)

@bp.route('/curriculum', methods=['GET', 'POST'])
def manage_curriculum():
    if request.method == 'POST':
        # --- POST Logic (ปรับปรุงให้รับ program_id) ---
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid data'}), 400

        semester_id = data.get('semester_id')
        grade_id = data.get('grade_level_id')
        program_id = data.get('program_id') # <-- รับ program_id
        selected_subject_ids = data.get('subject_ids', [])

        # --- [START V26 VALIDATION] ---
        # Basic validation
        if not all([semester_id, grade_id, program_id]):
             return jsonify({'status': 'error', 'message': 'Missing semester, grade, or program ID'}), 400
        # --- [END V26 VALIDATION] ---

        try:
            # --- [ START REVISED LOGIC ] ---

            # --- 1. รับ ID และแปลงเป็น Integer แต่เนิ่นๆ ---
            semester_id_str = data.get('semester_id')
            grade_id_str = data.get('grade_level_id')
            program_id_str = data.get('program_id')
            selected_subject_ids_str = data.get('subject_ids', [])

            try:
                semester_id = int(semester_id_str)
                grade_id = int(grade_id_str)
                program_id = int(program_id_str)
                # ใช้ set เพื่อให้แน่ใจว่า ID ไม่ซ้ำ และแปลงเป็น integer
                selected_subject_ids = set(map(int, selected_subject_ids_str))
            except (ValueError, TypeError, AttributeError):
                 return jsonify({'status': 'error', 'message': 'รูปแบบ ID ที่ส่งมาไม่ถูกต้อง'}), 400

            # --- [START V26 VALIDATION] --- (เหมือนเดิม)
            if not all([semester_id, grade_id, program_id]):
                return jsonify({'status': 'error', 'message': 'Missing semester, grade, or program ID'}), 400
            # --- [END V26 VALIDATION] ---

            # --- 2. ค้นหา Subject ID ที่มีอยู่ *เดิม* สำหรับบริบทนี้ ---
            existing_curriculum_items = Curriculum.query.filter_by(
                semester_id=semester_id,
                grade_level_id=grade_id,
                program_id=program_id
            ).all()
            existing_subject_ids = {c.subject_id for c in existing_curriculum_items}

            # --- 3. คำนวณหา ID ที่ต้อง ลบ และ เพิ่ม ---
            ids_to_delete = existing_subject_ids - selected_subject_ids
            ids_to_add = selected_subject_ids - existing_subject_ids

            # --- 4. Log การเปลี่ยนแปลง (ถ้ามี) ---
            if ids_to_delete or ids_to_add:
                log_action(
                    action="Update Curriculum",
                    model=Curriculum,
                    record_id=f"S{semester_id}-G{grade_id}-P{program_id}",
                    old_value={'subject_ids': sorted(list(existing_subject_ids))},
                    new_value={'subject_ids': sorted(list(selected_subject_ids))}
                )

            # --- 5. ทำการลบ *เฉพาะ* ID ที่ต้องลบ ---
            if ids_to_delete:
                # หา object Curriculum ที่จะลบจริงๆ
                items_to_delete = [item for item in existing_curriculum_items if item.subject_id in ids_to_delete]
                for item in items_to_delete:
                    db.session.delete(item)
                # หรือใช้วิธี Query Delete ที่เร็วกว่า (แต่ต้องระวังเรื่อง session synchronization)
                # Curriculum.query.filter(
                #     Curriculum.semester_id == semester_id,
                #     Curriculum.grade_level_id == grade_id,
                #     Curriculum.program_id == program_id,
                #     Curriculum.subject_id.in_(ids_to_delete)
                # ).delete(synchronize_session=False)

            # --- 6. ทำการเพิ่ม *เฉพาะ* ID ที่ต้องเพิ่ม ---
            if ids_to_add:
                db.session.bulk_insert_mappings(
                    Curriculum,
                    [{'semester_id': semester_id,
                      'grade_level_id': grade_id,
                      'program_id': program_id,
                      'subject_id': sub_id}
                     for sub_id in ids_to_add]
                )

            # --- 7. Commit การเปลี่ยนแปลงทั้งหมด ---
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'บันทึกเรียบร้อยแล้ว'})

            # --- [ END REVISED LOGIC ] ---

        except Exception as e:
            db.session.rollback()
            # --- [START LOGGING FAILURE - เหมือนเดิม] ---
            # ใช้ f-string หรือ .format() ในการสร้าง record_id
            log_record_id = f"S{semester_id_str or '?'}-G{grade_id_str or '?'}-P{program_id_str or '?'}"
            log_action(f"Update Curriculum Failed: {type(e).__name__}", model=Curriculum, record_id=log_record_id)
            try: db.session.commit()
            except: db.session.rollback()
            # --- [END LOGGING FAILURE] ---
            current_app.logger.error(f"Error updating curriculum {log_record_id}: {e}", exc_info=True)
            # Check specifically for UniqueViolation to give a clearer message
            if isinstance(e, IntegrityError) and 'UniqueViolation' in str(e.orig):
                 return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: ข้อมูลซ้ำซ้อน ({e.orig})'}), 409 # 409 Conflict
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # --- GET Request Logic (ปรับปรุงให้รองรับ program_id) ---
    form = CurriculumForm() # ใช้สำหรับสร้าง Dropdown

    all_semesters = get_all_semesters()
    all_grades = get_all_grade_levels()
    all_programs = Program.query.order_by(Program.name).all() # <-- Query Programs

    form.semester.choices = [(s.id, f"{s.term}/{s.academic_year.year}") for s in all_semesters]
    form.grade_level.choices = [(g.id, g.name) for g in all_grades]
    form.program.choices = [(p.id, p.name) for p in all_programs] # <-- เพิ่ม Program choices

    # ดึงค่าที่เลือกจาก URL หรือตั้งค่าเริ่มต้น
    selected_semester_id = request.args.get('semester', type=int)
    selected_grade_id = request.args.get('grade_level', type=int)
    selected_program_id = request.args.get('program', type=int) # <-- รับ program จาก URL

    if not selected_semester_id and all_semesters:
        selected_semester_id = all_semesters[0].id
    if not selected_grade_id and all_grades:
        selected_grade_id = all_grades[0].id
    if not selected_program_id and all_programs:
        # ใช้ Program แรก (อาจจะเป็น 'ทั่วไป') เป็นค่าเริ่มต้น
        selected_program_id = all_programs[0].id # <-- ตั้งค่า program เริ่มต้น

    form.semester.data = selected_semester_id
    form.grade_level.data = selected_grade_id
    form.program.data = selected_program_id # <-- กำหนดค่า program ให้ฟอร์ม

    # Master Data รายวิชา (เหมือนเดิม - ดึงทุกวิชาของ Grade)
    master_curriculum = {}
    for grade in all_grades:
        subjects_for_grade = grade.subjects.options(joinedload(Subject.subject_type)).order_by(Subject.subject_code).all()
        master_curriculum[grade.id] = [
            {"id": s.id, "code": s.subject_code, "name": s.name, "type": s.subject_type.name, "credit": s.credit}
            for s in subjects_for_grade
        ]

    # --- [START V26 MODIFICATION] ปรับ Key ของ Existing Curriculum ---
    # Master Data หลักสูตรที่มีอยู่ (ปรับ Key ให้รวม program_id)
    all_existing_curriculum_items = Curriculum.query.all()
    all_existing_curriculum = {}
    for item in all_existing_curriculum_items:
        key = f"{item.semester_id}-{item.grade_level_id}-{item.program_id}" # <-- Key ใหม่
        if key not in all_existing_curriculum:
            all_existing_curriculum[key] = []
        all_existing_curriculum[key].append(item.subject_id)
    # --- [END V26 MODIFICATION] ---

    return render_template(
        'admin/manage_curriculum_ajax.html',
        form=form,
        title='จัดการหลักสูตร',
        master_curriculum_json=json.dumps(master_curriculum),
        all_existing_curriculum_json=json.dumps(all_existing_curriculum)
        # ไม่ต้องส่ง selected_ids แยก เพราะ JavaScript จะดึงจาก all_existing_curriculum_json เอง
    )

# เส้นทางสำหรับแสดงรายการห้องเรียน
@bp.route('/classrooms')
@login_required
#@admin_required
def list_classrooms():
    # --- [ START V25 MODIFICATION ] ---
    all_programs = Program.query.order_by(Program.name).all()
    # --- [ END V25 MODIFICATION ] ---

    current_semester = Semester.query.filter_by(is_current=True).options(joinedload(Semester.academic_year)).first()
    if current_semester:
        current_academic_year = current_semester.academic_year
    else:
        current_academic_year = None
    if not current_academic_year:
        flash('กรุณากำหนดปีการศึกษาปัจจุบันก่อน', 'warning')
        classrooms_by_grade = {}
        # +++ 1. เพิ่ม pagination_object เปล่า กรณีไม่มีข้อมูล +++
        pagination_object = None 
    else:
        # +++ 2. เพิ่มการดึงค่า page จาก URL +++
        page = request.args.get('page', 1, type=int)

        # +++ 3. เปลี่ยนจาก .all() เป็น .paginate() +++
        pagination_object = GradeLevel.query.options(
            selectinload(GradeLevel.classrooms).joinedload(Classroom.program), 
            selectinload(GradeLevel.classrooms).joinedload(Classroom.advisors),
            selectinload(GradeLevel.classrooms).joinedload(Classroom.room) 
        ).order_by(GradeLevel.id).paginate(
            page=page, per_page=10, error_out=False  # (ปรับ per_page 10 หน้า หรือตามต้องการ)
        )

        # +++ 4. ดึง .items จาก pagination_object มาใช้ +++
        grade_levels_items = pagination_object.items 

        classrooms_by_grade = {
            grade.name: sorted(
                [c for c in grade.classrooms if c.academic_year_id == current_academic_year.id],
                key=lambda x: x.name
            )
            for grade in grade_levels_items # <--- 5. วนลูปจาก .items
        }

    form = ClassroomForm() 
    csrf_form = FlaskForm() 

    return render_template('admin/classrooms.html',
                           title='จัดการห้องเรียน',
                           classrooms_by_grade=classrooms_by_grade,
                           form=form, 
                           csrf_form=csrf_form,
                           all_programs=all_programs,
                           current_academic_year=current_academic_year,
                           # +++ 6. ส่ง pagination object ทั้งก้อนไปด้วย +++
                           pagination=pagination_object
                           )

@bp.route('/api/classroom/<int:classroom_id>/set-program', methods=['POST'])
@login_required
#@admin_required
def set_classroom_program(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    data = request.get_json()
    
    if data is None:
         return jsonify({'status': 'error', 'message': 'Invalid request data'}), 400

    new_program_id = data.get('program_id') # Expecting {'program_id': ID_or_null}

    # Convert empty string or 0 from dropdown to None (NULL in DB)
    if isinstance(new_program_id, str) and not new_program_id.strip():
        new_program_id = None
    elif isinstance(new_program_id, int) and new_program_id == 0:
         new_program_id = None
    elif new_program_id is not None:
         try:
             new_program_id = int(new_program_id)
             # Optional: Check if the program ID actually exists
             if not Program.query.get(new_program_id):
                 return jsonify({'status': 'error', 'message': 'Invalid Program ID'}), 400
         except (ValueError, TypeError):
              return jsonify({'status': 'error', 'message': 'Invalid Program ID format'}), 400

    if classroom.program_id != new_program_id:
        old_program_name = classroom.program.name if classroom.program else None
        classroom.program_id = new_program_id
        try:
            db.session.commit()
            new_program_name = classroom.program.name if classroom.program else None
            log_action("Update Classroom Program", model=Classroom, record_id=classroom.id,
                       old_value={'program': old_program_name}, new_value={'program': new_program_name})
            db.session.commit() # Commit log
            return jsonify({'status': 'success', 'message': 'บันทึกสายการเรียนสำเร็จ'})
        except Exception as e:
            db.session.rollback()
            log_action(f"Update Classroom Program Failed: {type(e).__name__}", model=Classroom, record_id=classroom.id)
            try: db.session.commit()
            except: db.session.rollback()
            current_app.logger.error(f"Error setting program for classroom {classroom_id}: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500
    else:
        # No change needed
        return jsonify({'status': 'success', 'message': 'ไม่มีการเปลี่ยนแปลง'})                           

# เส้นทางสำหรับเพิ่มห้องเรียนใหม่
@bp.route('/classrooms/add', methods=['GET', 'POST'])
def add_classroom():
    form = ClassroomForm()
    if form.validate_on_submit():
        classroom = Classroom(
            name=form.name.data,
            academic_year=form.academic_year.data,
            grade_level=form.grade_level.data
        )
        db.session.add(classroom)
        db.session.commit()
        flash('เพิ่มห้องเรียนใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_classrooms'))
    return render_template('admin/classroom_form.html', form=form, title='เพิ่มห้องเรียนใหม่')

# เส้นทางสำหรับแก้ไขห้องเรียน
@bp.route('/classrooms/edit/<int:classroom_id>', methods=['GET', 'POST'])
def edit_classroom(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    form = ClassroomForm(obj=classroom)
    if form.validate_on_submit():
        classroom.name = form.name.data
        classroom.academic_year = form.academic_year.data
        classroom.grade_level = form.grade_level.data
        db.session.commit()
        flash('แก้ไขข้อมูลห้องเรียนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_classrooms'))
    return render_template('admin/classroom_form.html', form=form, title='แก้ไขห้องเรียน')

# เส้นทางสำหรับลบห้องเรียน
@bp.route('/classrooms/delete/<int:classroom_id>', methods=['POST'])
def delete_classroom(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    db.session.delete(classroom)
    db.session.commit()
    flash('ลบห้องเรียนเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_classrooms'))

@bp.route('/students')
@login_required
def list_students():
    if not current_user.has_role('Admin'):
        abort(403)

    # --- START: ส่วนตรรกะการกรองข้อมูล ---
    page = request.args.get('page', 1, type=int)
    # อ่านค่าจาก query string สำหรับการกรอง
    q = request.args.get('q', '', type=str)
    classroom_id = request.args.get('classroom_id', 0, type=int)
    status = request.args.get('status', '', type=str)

    # สร้าง query เริ่มต้น
    query = Student.query

    # 1. กรองด้วยคำค้นหา (Search Query)
    if q:
        search_term = f"%{q}%"
        query = query.filter(or_(
            Student.student_id.like(search_term),
            Student.first_name.like(search_term),
            Student.last_name.like(search_term)
        ))

    current_year = AcademicYear.query.order_by(AcademicYear.year.desc()).first()

    # 2. กรองด้วยห้องเรียน (Classroom)
    if classroom_id and current_year:
        query = query.join(Enrollment).filter(
            Enrollment.classroom_id == classroom_id
        )

    # 3. กรองด้วยสถานะ (Status)
    if status:
        query = query.filter(Student.status == status)
    
    # --- END: ส่วนตรรกะการกรองข้อมูล ---

    # ดึงข้อมูลนักเรียนพร้อม pagination หลังจากกรองแล้ว
    pagination = query.order_by(Student.student_id).paginate(
        page=page, per_page=20, error_out=False
    )
    students = pagination.items
    
    # ตรวจสอบ Header เพื่อแยกว่าเป็น AJAX request หรือไม่
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # ถ้าใช่, ส่งเฉพาะส่วนของตารางกลับไป
        return render_template('admin/_students_table.html',
                               students=students,
                               pagination=pagination,
                               current_year=current_year)

    # ถ้าเป็นการโหลดปกติ, ส่งข้อมูลสำหรับ Filter ไปด้วย
    classrooms = []
    if current_year:
        classrooms = Classroom.query.filter_by(academic_year_id=current_year.id).order_by(Classroom.name).all()
    statuses = ['กำลังศึกษา', 'พักการเรียน', 'ลาออก', 'ย้ายออก', 'แขวนลอย', 'พ้นสภาพ', 'จบการศึกษา']

    return render_template('admin/students.html', 
                           title="จัดการข้อมูลนักเรียน",
                           students=students, 
                           pagination=pagination,
                           current_year=current_year,
                           classrooms=classrooms, # ส่งข้อมูลห้องเรียนไปที่ template
                           statuses=statuses)     # ส่งข้อมูลสถานะไปที่ template

# เส้นทางสำหรับเพิ่มนักเรียนใหม่
@bp.route('/students/add', methods=['GET', 'POST'])
def add_student():
    form = StudentForm()
    if form.validate_on_submit():
        student = Student(
            student_id=form.student_id.data,
            name_prefix=form.name_prefix.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data
        )
        db.session.add(student)
        db.session.commit()
        flash('เพิ่มข้อมูลนักเรียนใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_students'))
    return render_template('admin/student_form.html', form=form, title='เพิ่มนักเรียนใหม่')

# เส้นทางสำหรับแก้ไขข้อมูลนักเรียน
@bp.route('/students/edit/<int:student_db_id>', methods=['GET', 'POST'])
def edit_student(student_db_id):
    student = Student.query.get_or_404(student_db_id)
    form = StudentForm(obj=student)
    if form.validate_on_submit():
        student.student_id = form.student_id.data
        student.name_prefix = form.name_prefix.data
        student.first_name = form.first_name.data
        student.last_name = form.last_name.data
        db.session.commit()
        flash('แก้ไขข้อมูลนักเรียนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_students'))
    return render_template('admin/student_form.html', form=form, title='แก้ไขข้อมูลนักเรียน')

# --- ส่วนจัดการนักเรียนในห้องเรียน (Enrollment Management) ---
@bp.route('/classroom/<int:classroom_id>/enroll', methods=['GET', 'POST'])
def manage_enrollment(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    
    # ค้นหาห้องเรียนทั้งหมดในปีการศึกษาเดียวกัน เพื่อทำ Dropdown สลับห้อง
    all_classrooms_in_year = Classroom.query.filter_by(
        academic_year_id=classroom.academic_year_id
    ).order_by(Classroom.name).all()

    # 1. ค้นหานักเรียนที่อยู่ในห้องนี้แล้ว
    enrolled_students = Student.query.join(Enrollment).filter(
        Enrollment.classroom_id == classroom.id
    ).order_by(Enrollment.roll_number, Student.student_id).all()

    # 2. ค้นหานักเรียนที่ "ยังไม่มีห้อง" ในปีการศึกษานี้
    #    2.1 หา ID ของนักเรียนทั้งหมดที่มีห้องแล้วในปีการศึกษานี้
    students_with_class_ids = db.session.query(Enrollment.student_id).join(Classroom).filter(
        Classroom.academic_year_id == classroom.academic_year_id
    ).distinct().subquery()

    #    2.2 หานักเรียนทั้งหมดที่ ID ไม่อยู่ในลิสต์ข้างบน
    unassigned_students = Student.query.filter(
        Student.id.notin_(students_with_class_ids)
    ).order_by(Student.student_id).all()

    return render_template('admin/manage_enrollment_new.html', 
                           classroom=classroom,
                           enrolled_students=enrolled_students,
                           unassigned_students=unassigned_students,
                           all_classrooms_in_year=all_classrooms_in_year,
                           title=f'จัดการนักเรียนห้อง {classroom.name}')

# เส้นทางสำหรับ "เพิ่ม" นักเรียนเข้าห้อง
@bp.route('/enrollment/add/<int:classroom_id>/<int:student_id>', methods=['POST'])
def add_enrollment(classroom_id, student_id):
    roll_number = request.form.get('roll_number')
    enrollment = Enrollment(
        classroom_id=classroom_id, 
        student_id=student_id, 
        roll_number=int(roll_number) if roll_number else None
    )
    db.session.add(enrollment)
    db.session.commit()
    flash('เพิ่มนักเรียนเข้าห้องเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.manage_enrollment', classroom_id=classroom_id))

# เส้นทางสำหรับ "ลบ" นักเรียนออกจากห้อง
@bp.route('/enrollment/remove/<int:classroom_id>/<int:student_id>', methods=['POST'])
def remove_enrollment(classroom_id, student_id):
    Enrollment.query.filter_by(classroom_id=classroom_id, student_id=student_id).delete()
    db.session.commit()
    flash('นำนักเรียนออกจากห้องเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.manage_enrollment', classroom_id=classroom_id))

@bp.route('/students/execute-import', methods=['GET', 'POST'])
@login_required
def execute_student_import():
    # 1. รับหมายเลข Batch และหาไฟล์
    batch = request.args.get('batch', 1, type=int)
    temp_filename = session.get('import_filename')
    
    if not temp_filename:
        flash('ไม่พบข้อมูลสำหรับนำเข้า หรือ Session หมดอายุ', 'warning')
        return redirect(url_for('admin.import_students'))

    json_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

    if not os.path.exists(json_filepath):
         flash(f'ไม่พบไฟล์นำเข้าชั่วคราว ({temp_filename}) กรุณาลองอัปโหลดใหม่อีกครั้ง', 'danger')
         session.pop('import_filename', None)
         return redirect(url_for('admin.import_students'))

    try:
        # 3. อ่านข้อมูลและคำนวณ Batch
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_items = len(data)
        if total_items == 0:
            _cleanup_file(json_filepath)
            flash('ไฟล์ข้อมูลว่างเปล่า', 'info')
            session.pop('import_filename', None)
            return redirect(url_for('admin.list_students'))

        total_batches = math.ceil(total_items / BATCH_SIZE)
        start_index = (batch - 1) * BATCH_SIZE
        end_index = min(batch * BATCH_SIZE, total_items)
        batch_data = data[start_index:end_index]

        current_app.logger.info(f"Processing student import batch {batch}/{total_batches} ({start_index+1} to {end_index})")

        # 4. ประมวลผลข้อมูล (Logic จาก tasks.py)
        # Get current academic year ID *once*
        current_semester = Semester.query.filter_by(is_current=True).first()
        if not current_semester:
             raise Exception("Cannot run student import: No current semester is set.")
        current_academic_year_id = current_semester.academic_year_id
        
        # Pre-load classrooms for the current year into a map
        classrooms_in_year = Classroom.query.filter_by(academic_year_id=current_academic_year_id).all()
        classroom_map = {c.name: c for c in classrooms_in_year}

        new_count = request.args.get('new', 0, type=int)
        update_count = request.args.get('upd', 0, type=int)
        error_count = request.args.get('err', 0, type=int)
        skipped_count = request.args.get('skip', 0, type=int)

        for record in batch_data:
            try:
                # Skip rows with warnings (ที่มาจากหน้า preview)
                if any(w for w in record['warnings']):
                    skipped_count += 1
                    continue

                student_id_str = record['student_id']
                classroom_name = record['classroom_name']

                # --- Upsert Student ---
                student = Student.query.filter_by(student_id=student_id_str).first()
                if not student:
                    student = Student(student_id=student_id_str)
                    status = 'New'
                else:
                     status = 'Update'
                
                student.name_prefix = record['name_prefix']
                student.first_name = record['first_name']
                student.last_name = record['last_name']
                if status == 'New':
                     student.status = 'กำลังศึกษา' 
                db.session.add(student)
                db.session.flush() # Ensure student has ID

                # --- Upsert Enrollment ---
                classroom = classroom_map.get(classroom_name)
                if classroom:
                    Enrollment.query.filter(
                        Enrollment.student_id == student.id,
                        Enrollment.classroom_id.in_(
                            db.session.query(Classroom.id).filter_by(academic_year_id=current_academic_year_id)
                        )
                    ).delete(synchronize_session=False)

                    roll_number_val = None
                    if pd.notna(record['roll_number']):
                         try:
                             roll_number_val = int(float(record['roll_number']))
                         except (ValueError, TypeError):
                              pass
                              
                    enrollment = Enrollment(
                        student=student,
                        classroom=classroom,
                        roll_number=roll_number_val
                    )
                    db.session.add(enrollment)
                    
                    if status == 'New': new_count += 1
                    else: update_count += 1
                else:
                    error_count += 1
                    current_app.logger.warning(f"Row {record.get('row_num', '?')} ({student_id_str}): Classroom '{classroom_name}' not found during execution.")
                    db.session.rollback() # Rollback student add/update for this record
                    continue

            except Exception as rec_err:
                 db.session.rollback()
                 error_count += 1
                 current_app.logger.error(f"Error processing student import record {record.get('student_id','?')}: {rec_err}", exc_info=True)
                 continue

        db.session.commit() # Commit หลังจากจบ Batch

        # 5. ตัดสินใจขั้นตอนต่อไป
        if batch >= total_batches:
            _cleanup_file(json_filepath)
            session.pop('import_filename', None)
            flash(f'นำเข้าข้อมูลนักเรียนสำเร็จ! (ใหม่: {new_count}, อัปเดต: {update_count}, ข้าม: {skipped_count}, ผิดพลาด: {error_count})', 'success')
            return redirect(url_for('admin.list_students'))
        else:
            flash(f'กำลังประมวลผล... (ส่วนที่ {batch}/{total_batches} - {end_index}/{total_items} รายการ)', 'info')
            next_url = url_for('admin.execute_student_import', 
                               batch=batch + 1, 
                               new=new_count, 
                               upd=update_count, 
                               err=error_count, 
                               skip=skipped_count)
            return redirect(next_url)

    except Exception as e:
        db.session.rollback()
        _cleanup_file(json_filepath)
        session.pop('import_filename', None)
        current_app.logger.error(f"Critical error during student import batch {batch}: {e}", exc_info=True)
        flash(f'เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผลส่วนที่ {batch}: {e}', 'danger')
        return redirect(url_for('admin.import_students'))

# เส้นทางสำหรับดาวน์โหลดไฟล์ Template
@bp.route('/students/download-template')
def download_student_template():
    try:
        return send_from_directory(
            os.path.join(current_app.root_path, 'static', 'templates'),
            'student_import_template.csv',
            as_attachment=True
        )
    except FileNotFoundError:
        flash('ไม่พบไฟล์ Template', 'danger')
        return redirect(url_for('admin.list_students'))

def _read_uploaded_file_to_df(file):
    """
    Helper function to read an uploaded file (.csv or .xlsx) into a pandas DataFrame.
    Handles common CSV encodings (UTF-8 and TIS-620).
    Returns a DataFrame on success, or None on failure.
    """
    try:
        if file.filename.endswith('.csv'):
            # Ensure reading from the start of the file stream
            file.seek(0)
            try:
                # 1. Try reading with the universal standard (UTF-8)
                df = pd.read_csv(file, encoding='utf-8')
            except UnicodeDecodeError:
                # 2. If it fails, rewind and try the Thai standard (TIS-620)
                file.seek(0)
                df = pd.read_csv(file, encoding='tis-620')
        else:
            file.seek(0)
            df = pd.read_excel(file)
        return df
    except Exception as e:
        # Log the error for debugging purposes
        current_app.logger.error(f"Error reading uploaded file '{file.filename}': {e}")
        return None

# เส้นทางสำหรับหน้า Import (เวอร์ชันอัปเดต)
@bp.route('/students/import', methods=['GET', 'POST'])
def import_students():
    form = FlaskForm()
    if form.validate_on_submit():
        if 'file' not in request.files or request.files['file'].filename == '':
            flash('กรุณาเลือกไฟล์ที่ต้องการอัปโหลด', 'warning')
            return redirect(request.url)
        
        file = request.files['file']
        
        if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            flash('ประเภทไฟล์ไม่ถูกต้อง กรุณาอัปโหลดไฟล์ .csv หรือ .xlsx เท่านั้น', 'danger')
            return redirect(request.url)

        df = _read_uploaded_file_to_df(file)
        if df is None:
            flash('เกิดข้อผิดพลาดในการอ่านไฟล์ อาจมีรูปแบบไม่ถูกต้อง', 'danger')
            return redirect(request.url)

        preview_data = []
        required_columns = ['student_id', 'name_prefix', 'first_name', 'last_name', 'classroom_name', 'roll_number']
        
        if not all(col in df.columns for col in required_columns):
            flash(f'ไฟล์ขาดคอลัมน์ที่จำเป็น กรุณาใช้คอลัมน์เหล่านี้: {", ".join(required_columns)}', 'danger')
            return redirect(request.url)

        for index, row in df.iterrows():
            student_id = str(row['student_id'])
            classroom_name = str(row['classroom_name'])
            roll_number = row['roll_number']
            
            existing_student = Student.query.filter_by(student_id=student_id).first()
            classroom = Classroom.query.filter_by(name=classroom_name).first()
            
            record = {
                'row_num': index + 2,
                'student_id': student_id,
                'name_prefix': row['name_prefix'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'classroom_name': classroom_name,
                'roll_number': roll_number,
                'status': 'Update' if existing_student else 'New',
                'classroom_found': bool(classroom),
                'warnings': []
            }
            if not classroom:
                record['warnings'].append(f'ไม่พบห้องเรียน "{classroom_name}"')

            if pd.notna(roll_number) and not str(roll_number).replace('.0', '').isnumeric():
                record['warnings'].append(f'เลขที่ "{roll_number}" ไม่ใช่ตัวเลข')

            preview_data.append(record)
        
        temp_filename = f"import_{uuid.uuid4().hex}.json"
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(preview_data, f)
        
        session['import_filename'] = temp_filename
        form = FlaskForm()
        return render_template('admin/import_preview.html', 
                            title='นำเข้าข้อมูลนักเรียน',
                            icon_class='bi-people-fill',
                            required_columns='`student_id`, `name_prefix`, `first_name`, `last_name`, `classroom_name`, `roll_number`',
                            download_url=url_for('admin.download_student_template'),
                            data=preview_data,
                            form=form)

    return render_template('admin/import_students.html', title='นำเข้าข้อมูลนักเรียน', form=form)

# เส้นทางสำหรับดาวน์โหลดไฟล์ Template ครู
@bp.route('/teachers/download-template')
def download_teacher_template():
    try:
        return send_from_directory(
            os.path.join(current_app.root_path, 'static', 'templates'),
            'teacher_import_template.csv',
            as_attachment=True
        )
    except FileNotFoundError:
        flash('ไม่พบไฟล์ Template', 'danger')
        return redirect(url_for('admin.list_users'))

@bp.route('/teachers/import', methods=['GET', 'POST'])
def import_teachers():
    form = FlaskForm()
    if form.validate_on_submit():
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('กรุณาเลือกไฟล์ที่ต้องการอัปโหลด', 'warning')
            return redirect(request.url)
        
        df = _read_uploaded_file_to_df(file)
        if df is None:
            flash('เกิดข้อผิดพลาดในการอ่านไฟล์ อาจมีรูปแบบไม่ถูกต้อง', 'danger')
            return redirect(request.url)

        if df.empty:
            flash('ไฟล์ที่อัปโหลดไม่มีข้อมูลอยู่ภายใน กรุณาตรวจสอบไฟล์อีกครั้ง', 'warning')
            return redirect(request.url)
        
        preview_data = []
        required_columns = ['temp_id', 'name_prefix', 'first_name', 'last_name']
        if not all(col in df.columns for col in required_columns):
            flash(f'ไฟล์ขาดคอลัมน์ที่จำเป็น: {", ".join(required_columns)}', 'danger')
            return redirect(request.url)

        for index, row in df.iterrows():
            username = str(row['temp_id'])
            email = str(row.get('email', '')) if pd.notna(row.get('email')) else ''
            existing_user = User.query.filter((User.username == username) | ((User.email == email) & (User.email != ''))).first()
            
            record = {
                'row_num': index + 2, 'username': username, 'name_prefix': row['name_prefix'],
                'first_name': row['first_name'], 'last_name': row['last_name'], 'email': email,
                'status': 'Update' if existing_user else 'New',
                'roles': [r.strip() for r in str(row.get('roles', '')).split(',') if r.strip()],
                'homeroom_classroom': str(row.get('homeroom_classroom', '')) if pd.notna(row.get('homeroom_classroom')) else '',
                'department_head_of': str(row.get('department_head_of', '')) if pd.notna(row.get('department_head_of')) else '',
                'subject_group_member_of': str(row.get('subject_group_member_of', '')) if pd.notna(row.get('subject_group_member_of')) else '',
                'warnings': []
            }
            preview_data.append(record)
        
        # --- (ส่วนของการบันทึกไฟล์ชั่วคราวและแสดงผลเหมือนเดิม) ---
        temp_filename = f"teacher_import_{uuid.uuid4().hex}.json"
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(preview_data, f)
        
        session['teacher_import_filename'] = temp_filename
        
        return render_template('admin/import_teachers_preview.html',
                            title='ตรวจสอบข้อมูลครูก่อนนำเข้า',
                            icon_class='bi-person-plus',
                            required_columns='`temp_id`, `name_prefix`, `first_name`, `last_name`, `email`, `roles`, `homeroom_classroom`, `department_head_of`, `subject_group_member_of`',
                            download_url=url_for('admin.download_teacher_template'),
                            data=preview_data,
                            form=form)
    return render_template('admin/import_teachers.html', title='นำเข้าข้อมูลครู', form=form)

@bp.route('/teachers/execute-import', methods=['GET', 'POST'])
@login_required # Make sure login_required is here
def execute_teacher_import():
    # 1. รับหมายเลข Batch และหาไฟล์
    batch = request.args.get('batch', 1, type=int)
    temp_filename = session.get('teacher_import_filename')
    
    if not temp_filename:
        flash('ไม่พบข้อมูลสำหรับนำเข้า หรือ Session หมดอายุ', 'warning')
        return redirect(url_for('admin.import_teachers'))

    json_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

    if not os.path.exists(json_filepath):
         flash(f'ไม่พบไฟล์นำเข้าชั่วคราว ({temp_filename}) กรุณาลองอัปโหลดใหม่อีกครั้ง', 'danger')
         session.pop('teacher_import_filename', None)
         return redirect(url_for('admin.import_teachers'))

    try:
        # 3. อ่านข้อมูลและคำนวณ Batch
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_items = len(data)
        if total_items == 0:
            _cleanup_file(json_filepath)
            flash('ไฟล์ข้อมูลว่างเปล่า', 'info')
            session.pop('teacher_import_filename', None)
            return redirect(url_for('admin.list_users'))

        total_batches = math.ceil(total_items / BATCH_SIZE)
        start_index = (batch - 1) * BATCH_SIZE
        end_index = min(batch * BATCH_SIZE, total_items)
        batch_data = data[start_index:end_index]

        current_app.logger.info(f"Processing teacher import batch {batch}/{total_batches} ({start_index+1} to {end_index})")

        # 4. ประมวลผลข้อมูล
        new_count = request.args.get('new', 0, type=int)
        update_count = request.args.get('err', 0, type=int) 
        error_count = request.args.get('skip', 0, type=int) 

        # --- [ START FIX SAWarning V6 ] ---
        # Pre-load all existing Roles, Classrooms, and Groups *once* per batch (or even once globally if preferred)
        # This prevents querying inside the loop, which stops the autoflush warning.
        
        # 1. Pre-load Roles
        all_roles_in_db = Role.query.all()
        role_map = {role.name: role for role in all_roles_in_db}

        # 2. Pre-load Classrooms (Ideally, filter by current year if possible)
        all_classrooms_in_db = Classroom.query.all()
        classroom_map = {c.name: c for c in all_classrooms_in_db}
        
        # 3. Pre-load SubjectGroups
        all_groups_in_db = SubjectGroup.query.all()
        group_map = {g.name: g for g in all_groups_in_db}
        # --- [ END FIX SAWarning V6 ] ---


        for record in batch_data:
            try:
                username = record['username']
                email = record.get('email', '') if pd.notna(record.get('email')) and record.get('email') else None

                query = db.session.query(User)
                if email:
                    user = query.filter(or_(User.username == username, User.email == email)).first()
                else:
                    user = query.filter(User.username == username).first()

                if user:
                    # Update existing user
                    user.name_prefix = record['name_prefix'] if pd.notna(record['name_prefix']) else None
                    user.first_name = record['first_name'] if pd.notna(record['first_name']) else ''
                    user.last_name = record['last_name'] if pd.notna(record['last_name']) else ''
                    user.email = email
                    update_count += 1
                else:
                    # Create new user
                    user = User(
                        username=username,
                        name_prefix=record['name_prefix'] if pd.notna(record['name_prefix']) else None,
                        first_name=record['first_name'] if pd.notna(record['first_name']) else '',
                        last_name=record['last_name'] if pd.notna(record['last_name']) else '',
                        email=email,
                        must_change_username=True,
                        must_change_password=True
                    )
                    db.session.add(user)
                    user.set_password('ntu1234') # (ต้องใช้ pbkdf2 จาก models.py)
                    new_count += 1
                
                # --- [ START FIX SAWarning V6 ] ---
                # --- Handle Roles (using the pre-loaded map) ---
                user.roles.clear() 
                for role_name in record.get('roles', []):
                    role = role_map.get(role_name) # Get from map (no query)
                    if not role:
                        # Create new role if not in map
                        role = Role(name=role_name, description=f"{role_name} Role")
                        db.session.add(role)
                        role_map[role_name] = role # Add to map for this batch
                    if role not in user.roles:
                         user.roles.append(role)
                
                db.session.flush() # Flush *after* adding new roles, before linking advisors

                # --- Handle Homeroom Advisor (using map) ---
                homeroom_name = record.get('homeroom_classroom')
                if homeroom_name:
                    classroom = classroom_map.get(homeroom_name) # Get from map
                    if classroom and user not in classroom.advisors:
                        classroom.advisors.append(user)

                # --- Handle Department Head (using map) ---
                dept_head_name = record.get('department_head_of')
                if dept_head_name:
                    group = group_map.get(dept_head_name) # Get from map
                    if group:
                        if user not in group.members: group.members.append(user)
                        group.head = user

                # --- Handle Subject Group Member (using map) ---
                member_groups_str = record.get('subject_group_member_of')
                if member_groups_str:
                    group_names = [g.strip() for g in member_groups_str.split(',') if g.strip()]
                    for group_name in group_names:
                        subj_group = group_map.get(group_name) # Get from map
                        if subj_group and user not in subj_group.members:
                            subj_group.members.append(user)
                # --- [ END FIX SAWarning V6 ] ---

            except IntegrityError as ie:
                db.session.rollback() # Rollback record ที่ซ้ำ
                error_count += 1
                current_app.logger.warning(f"Teacher import skipped duplicate: {username} or {email}. Error: {ie}")
            except Exception as user_err:
                db.session.rollback() # Rollback record ที่มีปัญหา
                error_count += 1
                error_msg = f"Row {record.get('row_num', '?')} ({record.get('username','?')}) Error: {user_err}"
                current_app.logger.error(f"Error processing teacher import record: {error_msg}", exc_info=True)
                continue # ข้ามไปทำรายการถัดไปใน Batch

        db.session.commit() # Commit หลังจากจบ Batch

        # 5. ตัดสินใจขั้นตอนต่อไป
        if batch >= total_batches:
            # Batch สุดท้าย: ลบไฟล์และกลับหน้าหลัก
            _cleanup_file(json_filepath)
            session.pop('teacher_import_filename', None)
            flash(f'นำเข้าข้อมูลครูสำเร็จ! (ใหม่: {new_count}, อัปเดต: {update_count}, ข้าม/ผิดพลาด: {error_count})', 'success')
            return redirect(url_for('admin.list_users'))
        else:
            # ยังมี Batch ต่อไป: Redirect ไปยัง Batch ถัดไป
            flash(f'กำลังประมวลผล... (ส่วนที่ {batch}/{total_batches} - {end_index}/{total_items} รายการ)', 'info')
            next_url = url_for('admin.execute_teacher_import', 
                               batch=batch + 1, 
                               new=new_count, 
                               err=update_count, 
                               skip=error_count) 
            return redirect(next_url)

    except Exception as e:
        db.session.rollback()
        _cleanup_file(json_filepath)
        session.pop('teacher_import_filename', None)
        current_app.logger.error(f"Critical error during teacher import batch {batch}: {e}", exc_info=True)
        flash(f'เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผลส่วนที่ {batch}: {e}', 'danger')
        return redirect(url_for('admin.import_teachers'))

# --- ศูนย์บัญชาการกลุ่มสาระฯ (แทนที่ assign_heads เดิม) ---
@bp.route('/subject-group/<int:group_id>/manage')
def manage_subject_group(group_id):
    group = SubjectGroup.query.get_or_404(group_id)
    
    current_members = group.members
    current_member_ids = [user.id for user in current_members]

    # 1. ค้นหาครูที่ยังไม่ได้เป็นสมาชิกของ "กลุ่มนี้"
    available_teachers_query = User.query.filter(User.id.notin_(current_member_ids)).order_by(User.first_name)

    # 2. ประมวลผลข้อมูลเพื่อส่งไปหน้าเว็บ
    available_teachers_list = []
    for teacher in available_teachers_query.all():
        # ค้นหากลุ่มสาระฯ ทั้งหมดที่ครูคนนี้สังกัดอยู่
        groups_text = ", ".join([g.name for g in teacher.member_of_groups])
        
        available_teachers_list.append({
            'id': teacher.id,
            'full_name': f"{teacher.name_prefix or ''}{teacher.first_name} {teacher.last_name}",
            'groups_text': groups_text if groups_text else None # ส่งเป็น None ถ้าไม่มีสังกัด
        })

    return render_template('admin/manage_subject_group.html', 
                           group=group,
                           current_members=current_members,
                           available_teachers=available_teachers_list,
                           title=f'จัดการกลุ่มสาระฯ: {group.name}')

# --- Action Routes (เพิ่ม/ลบ สมาชิก, ตั้งค่าหัวหน้า) ---
@bp.route('/subject-group/<int:group_id>/add-member/<int:user_id>', methods=['POST'])
def add_member_to_group(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user not in group.members:
        group.members.append(user)
        db.session.commit()
        flash(f'เพิ่ม {user.first_name} เป็นสมาชิกเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.manage_subject_group', group_id=group_id))

@bp.route('/subject-group/<int:group_id>/remove-member/<int:user_id>', methods=['POST'])
def remove_member_from_group(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user == group.head:
        flash('ไม่สามารถนำหัวหน้ากลุ่มสาระฯ ออกจากสมาชิกได้ (กรุณาเปลี่ยนหัวหน้าก่อน)', 'danger')
    elif user in group.members:
        group.members.remove(user)
        db.session.commit()
        flash(f'นำ {user.first_name} ออกจากกลุ่มเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.manage_subject_group', group_id=group_id))

@bp.route('/subject-group/<int:group_id>/set-head', methods=['POST'])
def set_head_for_group(group_id):
    group = SubjectGroup.query.get_or_404(group_id)
    new_head_id = request.form.get('head_id')
    
    # --- START: Smart Assignment Logic ---
    
    # 1. ค้นหา Role "หัวหน้ากลุ่มสาระฯ"
    head_role = Role.query.filter_by(name='DepartmentHead').first()
    if not head_role:
        flash('ไม่พบ Role "หัวหน้ากลุ่มสาระฯ" ในระบบ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('admin.manage_subject_group', group_id=group_id))

    # 2. จัดการกับหัวหน้าคนเก่า (ถ้ามี)
    old_head = group.head
    if old_head:
        # ตรวจสอบว่าหัวหน้าคนเก่า ยังเป็นหัวหน้าของกลุ่มสาระฯ อื่นอยู่หรือไม่
        other_groups_led = SubjectGroup.query.filter(
            SubjectGroup.head_id == old_head.id,
            SubjectGroup.id != group_id
        ).count()
        
        # ถ้าไม่ได้เป็นหัวหน้าของที่อื่นอีกแล้ว ให้ถอน Role ออก
        if other_groups_led == 0 and head_role in old_head.roles:
            old_head.roles.remove(head_role)

    # 3. จัดการกับหัวหน้าคนใหม่ (ถ้ามี)
    if new_head_id and new_head_id.isdigit():
        new_head = User.query.get(int(new_head_id))
        if new_head and new_head in group.members:
            group.head = new_head
            # เพิ่ม Role "หัวหน้ากลุ่มสาระฯ" ให้กับหัวหน้าคนใหม่ หากยังไม่มี
            if head_role not in new_head.roles:
                new_head.roles.append(head_role)
            flash(f'ตั้งค่า {new_head.first_name} เป็นหัวหน้ากลุ่มสาระเรียบร้อยแล้ว', 'success')
        else:
            flash('หัวหน้าที่เลือกต้องเป็นสมาชิกของกลุ่มสาระฯ ก่อน', 'danger')
    
    elif not new_head_id or new_head_id == '':
        # กรณี "ยกเลิก" การกำหนดหัวหน้า
        group.head = None
        flash('ยกเลิกการกำหนดหัวหน้ากลุ่มสาระเรียบร้อยแล้ว', 'info')
        
    db.session.commit()
    
    # --- END: Smart Assignment Logic ---
    
    return redirect(url_for('admin.manage_subject_group', group_id=group_id))

# เพิ่ม Route ใหม่สำหรับ "เพิ่ม" หัวหน้ากลุ่มสาระฯ
@bp.route('/head/add/<int:group_id>/<int:user_id>', methods=['POST'])
def add_head(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if group.head is None:
        group.head = user
        db.session.commit()
        flash(f'มอบหมาย {user.first_name} เป็นหัวหน้ากลุ่มสาระฯ เรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.assign_heads', group_id=group_id))

# เพิ่ม Route ใหม่สำหรับ "ลบ" หัวหน้ากลุ่มสาระฯ
@bp.route('/head/remove/<int:group_id>/<int:user_id>', methods=['POST'])
def remove_head(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if group.head == user:
        group.head = None
        db.session.commit()
        flash(f'ถอดถอน {user.first_name} จากการเป็นหัวหน้ากลุ่มสาระฯ เรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.assign_heads', group_id=group_id))

# เพิ่มสมาชิกกลุ่มสาระฯ
@bp.route('/member/add/<int:group_id>/<int:user_id>', methods=['POST'])
def add_member(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user not in group.members:
        group.members.append(user)
        db.session.commit()
        flash(f'เพิ่ม {user.first_name} เป็นสมาชิกกลุ่มสาระฯ เรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.assign_heads', group_id=group_id))

# ลบสมาชิกกลุ่มสาระฯ
@bp.route('/member/remove/<int:group_id>/<int:user_id>', methods=['POST'])
def remove_member(group_id, user_id):
    group = SubjectGroup.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user in group.members:
        group.members.remove(user)
        db.session.commit()
        flash(f'ลบ {user.first_name} ออกจากสมาชิกกลุ่มสาระฯ เรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.assign_heads', group_id=group_id))

# เส้นทางสำหรับมอบหมายครูที่ปรึกษา
@bp.route('/classroom/<int:classroom_id>/assign-advisors', methods=['GET'])
def assign_advisors(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    
    # 1. ค้นหาครูที่เป็นที่ปรึกษาของห้องนี้แล้ว
    current_advisors = classroom.advisors
    current_advisor_ids = [user.id for user in current_advisors]

    # 2. ค้นหาครูทั้งหมดที่สามารถเป็นที่ปรึกษาได้ (และยังไม่ได้เป็นของห้องนี้)
    available_teachers_query = User.query.filter(User.id.notin_(current_advisor_ids)).order_by(User.first_name)
    
    # --- ส่วนที่เพิ่มเข้ามา: เตรียมข้อมูลสำหรับแสดงผลใน Dropdown ---
    available_teachers_list = []
    for teacher in available_teachers_query.all():
        # หาว่าครูคนนี้เป็นที่ปรึกษาห้องอื่นอยู่หรือไม่
        advised_class = next((c for c in teacher.advised_classrooms if c.academic_year_id == classroom.academic_year_id), None)
        advised_class_name = f" (ที่ปรึกษา: {advised_class.name})" if advised_class else ""
        
        available_teachers_list.append({
            'id': teacher.id,
            'text': f"{teacher.name_prefix}{teacher.first_name} {teacher.last_name} ({teacher.username}){advised_class_name}"
        })
    # --------------------------------------------------------------------

    # 3. ค้นหาห้องเรียนทั้งหมดในปีการศึกษาเดียวกัน เพื่อทำ Dropdown สลับห้อง
    all_classrooms_in_year = Classroom.query.filter_by(
        academic_year_id=classroom.academic_year_id
    ).order_by(Classroom.name).all()

    return render_template('admin/assign_advisors_new.html', 
                           classroom=classroom,
                           current_advisors=current_advisors,
                           available_teachers=available_teachers_list, #<-- ส่ง List ที่ประมวลผลแล้วไปแทน
                           all_classrooms_in_year=all_classrooms_in_year,
                           title=f'มอบหมายครูที่ปรึกษาห้อง {classroom.name}')

# เพิ่ม Route ใหม่สำหรับ "เพิ่ม" ครูที่ปรึกษา
@bp.route('/advisor/add/<int:classroom_id>/<int:user_id>', methods=['POST'])
def add_advisor(classroom_id, user_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    user = User.query.get_or_404(user_id)
    if user not in classroom.advisors:
        classroom.advisors.append(user)
        db.session.commit()
        flash(f'มอบหมาย {user.first_name} เป็นครูที่ปรึกษาเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.assign_advisors', classroom_id=classroom_id))


# เพิ่ม Route ใหม่สำหรับ "ลบ" ครูที่ปรึกษา
@bp.route('/advisor/remove/<int:classroom_id>/<int:user_id>', methods=['POST'])
def remove_advisor(classroom_id, user_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    user = User.query.get_or_404(user_id)
    if user in classroom.advisors:
        classroom.advisors.remove(user)
        db.session.commit()
        flash(f'ถอดถอน {user.first_name} จากการเป็นครูที่ปรึกษาเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.assign_advisors', classroom_id=classroom_id))

# --- ส่วนจัดการการนำเข้ารายวิชา (Subject Import Management) ---

@bp.route('/subjects/download-template')
def download_subject_template():
    return send_from_directory(
        os.path.join(current_app.root_path, 'static', 'templates'),
        'subject_import_template.csv', as_attachment=True
    )

@bp.route('/subjects/import', methods=['GET', 'POST'])
def import_subjects():
    form = FlaskForm()
    if form.validate_on_submit():
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('กรุณาเลือกไฟล์ที่ต้องการอัปโหลด', 'warning')
            return redirect(request.url)
        
        df = _read_uploaded_file_to_df(file)
        if df is None:
            flash('เกิดข้อผิดพลาดในการอ่านไฟล์ อาจมีรูปแบบไม่ถูกต้อง', 'danger')
            return redirect(request.url)

        preview_data = []
        required_columns = ['subject_code', 'name', 'credit', 'subject_group', 'subject_type', 'grade_levels']
        if not all(col in df.columns for col in required_columns):
            flash(f'ไฟล์ขาดคอลัมน์ที่จำเป็น: {", ".join(required_columns)}', 'danger')
            return redirect(request.url)

        for index, row in df.iterrows():
            record = { 'row_num': index + 2, 'warnings': [], 'data': row.to_dict() }
            
            if Subject.query.filter_by(subject_code=str(row['subject_code'])).first():
                record['warnings'].append('รหัสวิชานี้มีอยู่แล้วในระบบ')
            if not SubjectGroup.query.filter_by(name=str(row['subject_group'])).first():
                record['warnings'].append(f"ไม่พบกลุ่มสาระฯ '{row['subject_group']}'")
            if not SubjectType.query.filter_by(name=str(row['subject_type'])).first():
                record['warnings'].append(f"ไม่พบประเภทวิชา '{row['subject_type']}'")
            
            grade_levels_str = str(row.get('grade_levels', ''))
            grade_short_names = [g.strip() for g in grade_levels_str.split(',') if g.strip()]
            found_grades = GradeLevel.query.filter(GradeLevel.short_name.in_(grade_short_names)).all()
            if len(found_grades) != len(grade_short_names):
                record['warnings'].append('พบชื่อย่อระดับชั้นบางส่วนที่ไม่มีอยู่จริง')

            preview_data.append(record)
        
        # --- (ส่วนของการบันทึกไฟล์ชั่วคราวและแสดงผลเหมือนเดิม) ---
        temp_filename = f"subject_import_{uuid.uuid4().hex}.json"
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(preview_data, f)
        session['subject_import_filename'] = temp_filename
        
        return render_template('admin/import_subjects_preview.html', title='ตรวจสอบข้อมูลรายวิชาก่อนนำเข้า', data=preview_data, form=form)
            
    return render_template('admin/import_subjects.html',
                        title='นำเข้าข้อมูลรายวิชา',
                        icon_class='bi-file-earmark-plus',
                        required_columns='`subject_code`, `name`, `credit`, `subject_group`, `subject_type`, `grade_levels`',
                        download_url=url_for('admin.download_subject_template'),
                        upload_form=FlaskForm(),
                        form=form)

@bp.route('/subjects/execute-import', methods=['GET', 'POST'])
@login_required # Make sure login_required is here
def execute_subject_import():
    # 1. รับหมายเลข Batch และหาไฟล์
    batch = request.args.get('batch', 1, type=int)
    temp_filename = session.get('subject_import_filename')
    
    if not temp_filename:
        flash('ไม่พบข้อมูลสำหรับนำเข้า หรือ Session หมดอายุ', 'warning')
        return redirect(url_for('admin.import_subjects'))

    json_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

    if not os.path.exists(json_filepath):
         flash(f'ไม่พบไฟล์นำเข้าชั่วคราว ({temp_filename}) กรุณาลองอัปโหลดใหม่อีกครั้ง', 'danger')
         session.pop('subject_import_filename', None)
         return redirect(url_for('admin.import_subjects'))

    try:
        # 3. อ่านข้อมูลและคำนวณ Batch
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_items = len(data)
        if total_items == 0:
            _cleanup_file(json_filepath)
            flash('ไฟล์ข้อมูลว่างเปล่า', 'info')
            session.pop('subject_import_filename', None)
            return redirect(url_for('admin.list_subjects'))

        total_batches = math.ceil(total_items / BATCH_SIZE)
        start_index = (batch - 1) * BATCH_SIZE
        end_index = min(batch * BATCH_SIZE, total_items)
        batch_data = data[start_index:end_index]

        current_app.logger.info(f"Processing subject import batch {batch}/{total_batches} ({start_index+1} to {end_index})")

        # 4. ประมวลผลข้อมูล (Logic จาก tasks.py)
        imported_count = request.args.get('new', 0, type=int)
        skipped_count = request.args.get('skip', 0, type=int)
        error_count = request.args.get('err', 0, type=int)
        
        # Pre-load lookups
        all_groups = {g.name: g for g in SubjectGroup.query.all()}
        all_types = {t.name: t for t in SubjectType.query.all()}
        all_grades = {gl.short_name: gl for gl in GradeLevel.query.all()}

        for record in batch_data:
            try:
                # Skip rows with warnings (except for 'already exists')
                if any(w != 'รหัสวิชานี้มีอยู่แล้วในระบบ' for w in record['warnings']):
                    skipped_count += 1
                    continue

                data_row = record['data']
                subject_code_str = str(data_row['subject_code'])

                if Subject.query.filter_by(subject_code=subject_code_str).first():
                    skipped_count += 1
                    continue

                subject_group = all_groups.get(str(data_row['subject_group']))
                subject_type = all_types.get(str(data_row['subject_type']))
                grade_levels_str = str(data_row.get('grade_levels', ''))
                grade_short_names = [g.strip() for g in grade_levels_str.split(',') if g.strip()]
                grades = [all_grades.get(g_name) for g_name in grade_short_names if all_grades.get(g_name)]

                if not subject_group or not subject_type or len(grades) != len(grade_short_names):
                     error_count += 1
                     current_app.logger.warning(f"Row {record.get('row_num', '?')} ({subject_code_str}): Related data missing in DB (Group, Type, or Grade).")
                     continue

                new_subject = Subject(
                    subject_code=subject_code_str,
                    name=str(data_row['name']),
                    credit=float(data_row['credit']),
                    subject_group=subject_group,
                    subject_type=subject_type,
                    grade_levels=grades
                )
                db.session.add(new_subject)
                imported_count += 1

            except Exception as rec_err:
                 db.session.rollback()
                 error_count += 1
                 current_app.logger.error(f"Error processing subject import record {record['data'].get('subject_code','?')}: {rec_err}", exc_info=True)
                 continue

        db.session.commit() # Commit หลังจากจบ Batch

        # 5. ตัดสินใจขั้นตอนต่อไป
        if batch >= total_batches:
            _cleanup_file(json_filepath)
            session.pop('subject_import_filename', None)
            flash(f'นำเข้าข้อมูลรายวิชาสำเร็จ! (ใหม่: {imported_count}, ข้าม: {skipped_count}, ผิดพลาด: {error_count})', 'success')
            return redirect(url_for('admin.list_subjects'))
        else:
            flash(f'กำลังประมวลผล... (ส่วนที่ {batch}/{total_batches} - {end_index}/{total_items} รายการ)', 'info')
            next_url = url_for('admin.execute_subject_import', 
                               batch=batch + 1, 
                               new=imported_count, 
                               skip=skipped_count, 
                               err=error_count)
            return redirect(next_url)

    except Exception as e:
        db.session.rollback()
        _cleanup_file(json_filepath)
        session.pop('subject_import_filename', None)
        current_app.logger.error(f"Critical error during subject import batch {batch}: {e}", exc_info=True)
        flash(f'เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผลส่วนที่ {batch}: {e}', 'danger')
        return redirect(url_for('admin.import_subjects'))

@bp.route('/assignments', methods=['GET'])
# @login_required # หมายเหตุ: หากระบบ login พร้อมใช้งานแล้ว สามารถเปิดใช้งานบรรทัดนี้ได้
def manage_assignments():
    form = FlaskForm()
    """Renders the main page for course assignment."""
    # ดึงค่าปีและเทอมล่าสุดมาเป็นค่าเริ่มต้น
    current_semester = Semester.query.filter_by(is_current=True).first()
    # ควรจะดึงเฉพาะปีที่มีภาคเรียนเท่านั้น เพื่อประสิทธิภาพ
    all_years = AcademicYear.query.join(Semester).distinct().order_by(AcademicYear.year.desc()).all()

    # สร้าง Dictionary ของ Semesters ที่จัดกลุ่มตาม Year ID เพื่อให้ JavaScript ใช้งานง่าย
    semesters_by_year = {}
    all_semesters = Semester.query.order_by(Semester.term).all()
    for sem in all_semesters:
        if sem.academic_year_id not in semesters_by_year:
            semesters_by_year[sem.academic_year_id] = []
        semesters_by_year[sem.academic_year_id].append({'id': sem.id, 'term': sem.term})


    return render_template('admin/manage_assignments.html', 
                           title='มอบหมายภาระการสอน',
                           form=form,
                           all_years=all_years,
                           current_semester=current_semester,
                           semesters_by_year_json=json.dumps(semesters_by_year))

@bp.route('/api/assignments-data')
@login_required
def get_assignments_data():
    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        return jsonify({'error': 'Missing semester_id'}), 400

    semester = db.session.get(Semester, semester_id)
    if not semester:
        return jsonify({'error': 'Invalid semester_id'}), 404
    academic_year_id = semester.academic_year_id

    # 1. Fetch all relevant classrooms WITH their program_id and grade_level info
    classrooms_query = Classroom.query.filter_by(
        academic_year_id=academic_year_id
    ).options(
        joinedload(Classroom.grade_level), # Need grade_level info
        joinedload(Classroom.program)     # Need program info
    ).order_by(Classroom.grade_level_id, Classroom.name).all()

    # Group classrooms by grade_level_id
    classrooms_by_grade = defaultdict(list)
    for c in classrooms_query:
        classrooms_by_grade[c.grade_level_id].append(c)

    # 2. Fetch all curriculum entries for the semester + subject credits/group
    curriculum_query = db.session.query(
        Curriculum.grade_level_id,
        Curriculum.program_id,
        Subject.id,
        Subject.subject_code,
        Subject.name,
        Subject.credit,
        Subject.subject_group_id # Need group for teacher dropdown later
    ).join(Subject, Curriculum.subject_id == Subject.id).filter(
        Curriculum.semester_id == semester_id
    ).order_by(Subject.subject_code).all()

    # Organize curriculum by grade and program
    curriculum_by_grade_program = defaultdict(lambda: defaultdict(list))
    credits_by_grade_program = defaultdict(lambda: defaultdict(float))
    for gl_id, p_id, s_id, s_code, s_name, s_credit, sg_id in curriculum_query:
        subject_data = {'id': s_id, 'code': s_code, 'name': s_name, 'credit': (s_credit or 0), 'group_id': sg_id}
        curriculum_by_grade_program[gl_id][p_id].append(subject_data)
        credits_by_grade_program[gl_id][p_id] += (s_credit or 0)

    # 3. Fetch existing assignments (Courses) for the relevant classrooms
    classroom_ids = [c.id for c in classrooms_query]
    if not classroom_ids: # Handle case with no classrooms
         existing_courses = []
    else:
        existing_courses = Course.query.options(
            joinedload(Course.teachers) # Eager load teachers for assignment info
        ).filter(
            Course.semester_id == semester_id,
            Course.classroom_id.in_(classroom_ids)
        ).all()
    assignments = {f"{c.subject_id}-{c.classroom_id}": [t.id for t in c.teachers] for c in existing_courses}

    # 4. Fetch teacher data (grouped by subject group)
    all_subject_groups = SubjectGroup.query.options(joinedload(SubjectGroup.members)).all()
    teachers_by_group = {
         group.id: [{'id': m.id, 'name': m.full_name} for m in group.members]
         for group in all_subject_groups
    }


    # 5. Build response structure
    response_data = {'grades': [], 'teachers_by_group': teachers_by_group}

    # Get all grade levels involved and sort them
    grade_ids = sorted(classrooms_by_grade.keys())
    # Fetch GradeLevel objects efficiently
    grade_levels_map = {g.id: g for g in GradeLevel.query.filter(GradeLevel.id.in_(grade_ids)).order_by(GradeLevel.id).all()}


    for grade_id in grade_ids:
        grade = grade_levels_map.get(grade_id)
        if not grade: continue # Skip if grade level somehow doesn't exist

        grade_data = {
            'id': grade.id,
            'name': grade.name,
            'classrooms': [],
            'subjects_by_program': defaultdict(list), # Restructured subjects
            'assignments': {} # Filtered assignments for this grade
        }

        # Populate classrooms data and calculate their specific total credits
        for classroom in classrooms_by_grade[grade_id]:
            program_id = classroom.program_id
            # Credits for this specific program/grade, or 0.0 if no program assigned
            total_credits = credits_by_grade_program.get(grade_id, {}).get(program_id, 0.0) if program_id else 0.0
            grade_data['classrooms'].append({
                'id': classroom.id,
                'name': classroom.name,
                'program_id': program_id, # Send program_id for frontend logic
                'program_name': classroom.program.name if classroom.program else "ไม่ได้กำหนด", # Send program name for display
                'total_credits': total_credits
            })

        # Populate subjects, grouped by program_id for this grade from pre-fetched curriculum
        grade_data['subjects_by_program'] = curriculum_by_grade_program.get(grade_id, {})

        # Filter assignments relevant ONLY to this grade's classrooms and subjects
        # Find all subject IDs relevant to any program within this grade level
        subjects_in_grade = {s['id'] for prog_id in grade_data['subjects_by_program']
                                   for s in grade_data['subjects_by_program'][prog_id]}
        classrooms_in_grade_ids = {c['id'] for c in grade_data['classrooms']}

        grade_data['assignments'] = {
             key: value for key, value in assignments.items()
             # Ensure both subject and classroom IDs from the key belong to the current grade
             if int(key.split('-')[0]) in subjects_in_grade and int(key.split('-')[1]) in classrooms_in_grade_ids
        }

        response_data['grades'].append(grade_data)

    return jsonify(response_data)

@bp.route('/api/update-assignment', methods=['POST'])
@login_required
def update_assignment():
    """API endpoint to save a single course assignment."""
    data = request.json
    semester_id = data.get('semester_id')
    subject_id = data.get('subject_id')
    classroom_id = data.get('classroom_id')
    teacher_ids = data.get('teacher_ids', [])

    if not all([semester_id, subject_id, classroom_id]):
        return jsonify({'status': 'error', 'message': 'Missing required data'}), 400

    course = Course.query.filter_by(
        semester_id=semester_id,
        subject_id=subject_id,
        classroom_id=classroom_id
    ).first()

    if not teacher_ids:
        print(f"DEBUG: Attempting to remove teachers from course {course.id if course else 'N/A'} (Subject: {subject_id}, Classroom: {classroom_id})") # DEBUG PRINT
        if course:
            print(f"DEBUG: Found course {course.id}. Current teachers: {[t.id for t in course.teachers]}") # DEBUG PRINT
            try:
                course.teachers = [] # ล้างรายชื่อ
                db.session.commit() # ลอง commit ทันที
                print(f"DEBUG: Successfully cleared teachers and committed for course {course.id}.") # DEBUG PRINT
                return jsonify({'status': 'success', 'message': 'นำครูผู้สอนออกแล้ว', 'teacher_ids': []})
            except Exception as e:
                db.session.rollback()
                print(f"ERROR: Failed to commit teacher removal for course {course.id}: {e}") # DEBUG PRINT
                return jsonify({'status': 'error', 'message': f'Database error on removal: {e}'}), 500
        else:
             print(f"DEBUG: Course not found for removal. Subject: {subject_id}, Classroom: {classroom_id}") # DEBUG PRINT
             # Course doesn't exist, which is fine if removing teachers
             return jsonify({'status': 'success', 'message': 'Course does not exist, no teachers to remove.', 'teacher_ids': []})
        
    if not course:
        # Before creating, ensure a lesson plan exists for this subject/year
        # This prevents errors if a plan wasn't auto-created
        classroom = Classroom.query.get(classroom_id)
        lesson_plan = LessonPlan.query.filter_by(
            subject_id=subject_id,
            academic_year_id=classroom.academic_year_id
        ).first()
        if not lesson_plan:
            # Create a lesson plan on-the-fly if it's missing
            lesson_plan = LessonPlan(subject_id=subject_id, academic_year_id=classroom.academic_year_id)
            db.session.add(lesson_plan)
            # We don't need to commit here, SQLAlchemy will handle the order

        course = Course(
            semester_id=semester_id, 
            subject_id=subject_id, 
            classroom_id=classroom_id,
            lesson_plan=lesson_plan
        )
        db.session.add(course)

    # Update the list of teachers for the course
    teachers = User.query.filter(User.id.in_(teacher_ids)).all()
    course.teachers = teachers

    # 1. เตรียมข้อมูลสำหรับส่งกลับ (Response) ก่อนที่จะ commit
    teacher_ids_for_response = [t.id for t in course.teachers]
    
    # 2. บันทึกการเปลี่ยนแปลงลงฐานข้อมูล
    db.session.commit()

    # 3. ส่งข้อมูลที่เตรียมไว้กลับไป
    return jsonify({'status': 'success', 'teacher_ids': teacher_ids_for_response})

@bp.route('/dimensions')
# @login_required
def list_dimensions():
    dimensions = AssessmentDimension.query.order_by(AssessmentDimension.code).all()
    return render_template('admin/assessment_dimensions.html', dimensions=dimensions, title='จัดการมิติการประเมิน (KPA)')

@bp.route('/dimensions/add', methods=['GET', 'POST'])
# @login_required
def add_dimension():
    form = AssessmentDimensionForm()
    if form.validate_on_submit():
        dimension = AssessmentDimension(code=form.code.data, name=form.name.data, description=form.description.data)
        db.session.add(dimension)
        db.session.commit()
        flash('เพิ่มมิติการประเมินใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_dimensions'))
    return render_template('admin/assessment_dimension_form.html', form=form, title='เพิ่มมิติการประเมินใหม่')

@bp.route('/dimensions/edit/<int:dim_id>', methods=['GET', 'POST'])
# @login_required
def edit_dimension(dim_id):
    dimension = AssessmentDimension.query.get_or_404(dim_id)
    form = AssessmentDimensionForm(obj=dimension)
    if form.validate_on_submit():
        dimension.code = form.code.data
        dimension.name = form.name.data
        dimension.description = form.description.data
        db.session.commit()
        flash('แก้ไขข้อมูลเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_dimensions'))
    return render_template('admin/assessment_dimension_form.html', form=form, title='แก้ไขมิติการประเมิน')

@bp.route('/dimensions/delete/<int:dim_id>', methods=['POST'])
# @login_required
def delete_dimension(dim_id):
    dimension = AssessmentDimension.query.get_or_404(dim_id)
    # ในอนาคตควรเพิ่มเงื่อนไขป้องกันการลบ หากมีข้อมูลอื่นผูกอยู่
    db.session.delete(dimension)
    db.session.commit()
    flash('ลบมิติการประเมินเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_dimensions'))

@bp.route('/assessment-templates')
# @login_required
def list_assessment_templates():
    templates = AssessmentTemplate.query.order_by(AssessmentTemplate.name).all()
    return render_template('admin/assessment_templates.html', templates=templates, title='คลังแม่แบบการประเมิน')

@bp.route('/assessment-templates/add', methods=['GET', 'POST'])
# @login_required
def add_assessment_template():
    form = AssessmentTemplateForm()
    if form.validate_on_submit():
        new_template = AssessmentTemplate(name=form.name.data, description=form.description.data)
        db.session.add(new_template)
        db.session.commit()
        flash('สร้างแม่แบบใหม่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_assessment_templates'))
    return render_template('admin/assessment_template_form.html', form=form, title='สร้างแม่แบบการประเมินใหม่')

@bp.route('/assessment-templates/edit/<int:tpl_id>', methods=['GET', 'POST'])
# @login_required
def edit_assessment_template(tpl_id):
    tpl = AssessmentTemplate.query.get_or_404(tpl_id)
    form = AssessmentTemplateForm(obj=tpl)
    if form.validate_on_submit():
        tpl.name = form.name.data
        tpl.description = form.description.data
        db.session.commit()
        flash('แก้ไขข้อมูลแม่แบบเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.list_assessment_templates'))
    return render_template('admin/assessment_template_form.html', form=form, title='แก้ไขแม่แบบการประเมิน')

@bp.route('/assessment-templates/delete/<int:tpl_id>', methods=['POST'])
# @login_required
def delete_assessment_template(tpl_id):
    tpl = AssessmentTemplate.query.get_or_404(tpl_id)
    db.session.delete(tpl)
    db.session.commit()
    flash('ลบแม่แบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.list_assessment_templates'))

@bp.route('/assessment-templates/<int:tpl_id>/manage')
# @login_required
def manage_assessment_template(tpl_id):
    tpl = AssessmentTemplate.query.get_or_404(tpl_id)
    rubric_form = RubricLevelForm()
    topic_form = AssessmentTopicForm()
    return render_template('admin/manage_assessment_template.html', 
                           tpl=tpl, 
                           rubric_form=rubric_form,
                           topic_form=topic_form,
                           title=f'จัดการแม่แบบ: {tpl.name}')

@bp.route('/api/templates/<int:tpl_id>/rubrics', methods=['POST'])
# @login_required
def add_rubric_level(tpl_id):
    form = RubricLevelForm()
    if form.validate_on_submit():
        level = RubricLevel(template_id=tpl_id, label=form.label.data, value=form.value.data)
        db.session.add(level)
        db.session.commit()
        return jsonify({'status': 'success', 'level': {'id': level.id, 'label': level.label, 'value': level.value}}), 201
    return jsonify({'status': 'error', 'errors': form.errors}), 400

@bp.route('/api/rubric-levels/<int:level_id>', methods=['DELETE'])
# @login_required
def delete_rubric_level(level_id):
    level = RubricLevel.query.get_or_404(level_id)
    db.session.delete(level)
    db.session.commit()
    return jsonify({'status': 'success'})

@bp.route('/api/templates/<int:tpl_id>/topics', methods=['POST'])
# @login_required
def add_topic(tpl_id):
    parent_id = request.json.get('parent_id')
    form = AssessmentTopicForm()
    if form.validate_on_submit():
        topic = AssessmentTopic(template_id=tpl_id, name=form.name.data, parent_id=parent_id)
        db.session.add(topic)
        db.session.commit()
        return jsonify({'status': 'success', 'topic': {'id': topic.id, 'name': topic.name, 'parent_id': topic.parent_id}}), 201
    return jsonify({'status': 'error', 'errors': form.errors}), 400

@bp.route('/api/topics/<int:topic_id>', methods=['DELETE'])
# @login_required
def delete_topic(topic_id):
    topic = AssessmentTopic.query.get_or_404(topic_id)
    db.session.delete(topic)
    db.session.commit()
    return jsonify({'status': 'success'})

# --- NEW ROUTES FOR STANDARDS AND INDICATORS ---
class UploadFileForm(FlaskForm):
    file = FileField('File', validators=[DataRequired()])
    
class DummyForm(FlaskForm):
    csrf_token = HiddenField()


# ====== แสดงหน้าคลังมาตรฐาน ======
@bp.route('/standards')
@login_required
def manage_standards():
    form = FlaskForm()
    subject_groups = SubjectGroup.query.options(
        db.joinedload(SubjectGroup.learning_strands)
        .joinedload(LearningStrand.standards)
        .joinedload(Standard.indicators)
    ).order_by(SubjectGroup.name).all()
    return render_template('admin/manage_standards.html', subject_groups=subject_groups, form=form)

@bp.route('/import-standards', methods=['GET', 'POST'])
@login_required # <-- เพิ่ม @login_required ถ้ายังไม่มี
def import_standards():
    # *** สร้าง Form Instance "ครั้งเดียว" นอก if ***
    form = UploadFileForm() 

    if form.validate_on_submit(): # ใช้ form ตัวนี้ validate ตอน POST
        file = form.file.data # เข้าถึงไฟล์ผ่าน form.file.data
        if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            flash('ประเภทไฟล์ไม่ถูกต้อง กรุณาอัปโหลดไฟล์ .csv หรือ .xlsx เท่านั้น', 'danger')
            return redirect(request.url)

        df = _read_uploaded_file_to_df(file)
        if df is None:
            flash('เกิดข้อผิดพลาดในการอ่านไฟล์ อาจมีรูปแบบไม่ถูกต้อง', 'danger')
            return redirect(request.url)
        if df.empty:
            flash('ไฟล์ที่อัปโหลดไม่มีข้อมูลอยู่ภายใน กรุณาตรวจสอบไฟล์อีกครั้ง', 'warning')
            return redirect(request.url)

        required_columns = ['subject_group', 'strand', 'standard_code', 'standard_description', 'indicator_code', 'indicator_description']
        if not all(col in df.columns for col in required_columns):
            flash('ไฟล์ Excel ต้องมีคอลัมน์: ' + ', '.join(required_columns), 'danger')
            return redirect(url_for('admin.import_standards')) # ใช้ redirect(url_for(...))

        preview_data = []
        for index, row in df.iterrows():
            record = {
                'row_num': index + 2,
                'subject_group': str(row['subject_group']),
                'strand': str(row['strand']),
                'standard_code': str(row['standard_code']),
                'standard_description': str(row['standard_description']),
                'indicator_code': str(row['indicator_code']),
                'indicator_description': str(row['indicator_description']),
                'warnings': []
            }
            # *** ตรวจสอบ Standard ซ้ำ (Logic เดิม) ***
            # (ตรวจสอบ Standard ซ้ำที่นี่...)
            standard = Standard.query.filter_by(code=record['standard_code']).first()
            if standard:
                 # Check if the existing standard belongs to the *same* strand and group
                 strand = LearningStrand.query.filter_by(name=record['strand']).join(SubjectGroup).filter(SubjectGroup.name==record['subject_group']).first()
                 if strand and standard.learning_strand_id == strand.id:
                      # Now check indicator
                      indicator = Indicator.query.filter_by(standard_id=standard.id, code=record['indicator_code']).first()
                      if indicator:
                           record['warnings'].append(f"มาตรฐาน/ตัวชี้วัด {record['standard_code']}/{record['indicator_code']} มีอยู่แล้ว")
                 # If strand doesn't match, it's potentially okay, but maybe add a different warning?
            
            preview_data.append(record)

        temp_filename = f"standards_import_{uuid.uuid4().hex}.json"
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)
        # *** ตรวจสอบและสร้างโฟลเดอร์ (Logic เดิม) ***
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True) 
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(preview_data, f)
        
        session['import_temp_file'] = temp_filename
        return redirect(url_for('admin.import_standards_preview')) # Redirect หลัง POST สำเร็จ
            
    # *** ส่ง form ตัวเดียวกันนี้ไปให้ Template ตอน GET ***
    return render_template('admin/import_standards.html', 
                           form=form, 
                           title='นำเข้าคลังมาตรฐานและตัวชี้วัด')

@bp.route('/import-standards/preview', methods=['GET'])
# @login_required
def import_standards_preview():
    temp_filename = session.get('import_temp_file')
    if not temp_filename:
        flash('ไม่พบข้อมูลสำหรับแสดงตัวอย่าง', 'warning')
        return redirect(url_for('admin.import_standards'))
        
    temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)
    try:
        with open(temp_filepath, 'r', encoding='utf-8') as f:
            # โหลดข้อมูลดิบ (เป็น list of dictionaries)
            raw_data = json.load(f)

        # แปลงโครงสร้างข้อมูลให้เข้ากับ Template เวอร์ชันเก่า
        preview_data_for_template = {
            'headers': [],
            'rows': []
        }
        if raw_data: # ตรวจสอบว่ามีข้อมูลหรือไม่
            # ใช้ข้อมูลแถวแรกสุดเพื่อสร้าง Headers
            preview_data_for_template['headers'] = list(raw_data[0].keys())
            # สร้าง list ของ list สำหรับ Rows
            for record in raw_data:
                preview_data_for_template['rows'].append(list(record.values()))
        
        form = DummyForm()
        # ส่งตัวแปรชื่อ 'preview_data' ที่มีโครงสร้างถูกต้องไปให้ Template
        return render_template('admin/import_standards_preview.html', 
                               preview_data=preview_data_for_template, # <--- แก้ไขชื่อตัวแปรตรงนี้
                               form=form, 
                               title='ตรวจสอบข้อมูลก่อนนำเข้า')

    except Exception as e:
        # เพิ่มการแสดง Error ที่แท้จริงเพื่อช่วยในการดีบัก
        current_app.logger.error(f"Error rendering preview page: {e}")
        flash(f'เกิดข้อผิดพลาดในการแสดงผลตัวอย่าง: {e}', 'danger')
        return redirect(url_for('admin.import_standards'))

@bp.route('/execute-import-standards', methods=['GET', 'POST']) # <-- ตรวจสอบว่ามี GET, POST
@login_required
def execute_import_standards():

    # --- [ START V21.1 FIX ] ---
    # ตรวจสอบ CSRF เฉพาะเมื่อเป็น POST request (Batch 1) เท่านั้น
    if request.method == 'POST':
        form = DummyForm() # สร้าง Form เฉพาะตอน POST
        if not form.validate_on_submit():
            flash('CSRF Token ไม่ถูกต้อง หรือ Session หมดอายุ', 'danger')
            return redirect(url_for('admin.import_standards'))
    # --- [ END V21.1 FIX ] ---

    # --- ส่วน Logic การทำงาน Batch (เหมือนเดิม) ---
    batch = request.args.get('batch', 1, type=int)
    temp_filename = session.get('import_temp_file')

    if not temp_filename:
        flash('ไม่พบข้อมูลสำหรับนำเข้า หรือ Session หมดอายุ', 'warning')
        return redirect(url_for('admin.import_standards'))

    json_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

    if not os.path.exists(json_filepath):
         flash(f'ไม่พบไฟล์นำเข้าชั่วคราว ({temp_filename}) กรุณาลองอัปโหลดใหม่อีกครั้ง', 'danger')
         session.pop('import_temp_file', None)
         return redirect(url_for('admin.import_standards'))

    try:
        # อ่านข้อมูลและคำนวณ Batch
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        total_items = len(data)
        if total_items == 0:
            _cleanup_file(json_filepath)
            flash('ไฟล์ข้อมูลว่างเปล่า', 'info')
            session.pop('import_temp_file', None)
            return redirect(url_for('admin.manage_standards'))

        total_batches = math.ceil(total_items / BATCH_SIZE)
        start_index = (batch - 1) * BATCH_SIZE
        end_index = min(batch * BATCH_SIZE, total_items)
        batch_data = data[start_index:end_index]

        current_app.logger.info(f"Processing standard import batch {batch}/{total_batches} ({start_index+1} to {end_index})")

        # ประมวลผลข้อมูล
        imported_count = request.args.get('new', 0, type=int)
        skipped_count = request.args.get('skip', 0, type=int)
        error_count = request.args.get('err', 0, type=int)

        all_groups = {g.name: g for g in SubjectGroup.query.all()}
        all_strands = {(s.name, s.subject_group_id): s for s in LearningStrand.query.all()}
        all_standards = {(s.code, s.learning_strand_id): s for s in Standard.query.all()}

        for row in batch_data:
            try:
                if 'warnings' in row and row['warnings']:
                    skipped_count += 1
                    continue

                group_name = row.get('subject_group')
                subject_group = all_groups.get(group_name)
                if not subject_group:
                    subject_group = SubjectGroup(name=group_name)
                    db.session.add(subject_group)
                    db.session.flush()
                    all_groups[group_name] = subject_group

                strand_name = row.get('strand')
                strand = all_strands.get((strand_name, subject_group.id))
                if not strand:
                    strand = LearningStrand(name=strand_name, subject_group=subject_group)
                    db.session.add(strand)
                    db.session.flush()
                    all_strands[(strand_name, subject_group.id)] = strand

                std_code = row.get('standard_code')
                standard = all_standards.get((std_code, strand.id))
                if not standard:
                    standard = Standard(code=std_code, description=row.get('standard_description'), learning_strand=strand)
                    db.session.add(standard)
                    db.session.flush()
                    all_standards[(std_code, strand.id)] = standard

                indicator_code = row.get('indicator_code')
                existing_indicator = Indicator.query.filter_by(standard_id=standard.id, code=indicator_code).first()
                if existing_indicator:
                     skipped_count += 1
                     continue

                indicator = Indicator(
                    standard_id=standard.id,
                    code=indicator_code,
                    description=row.get('indicator_description'),
                    creator_type='ADMIN'
                )
                db.session.add(indicator)
                imported_count += 1

            except Exception as rec_err:
                 db.session.rollback()
                 error_count += 1
                 current_app.logger.error(f"Error processing standard import record {row.get('standard_code','?')}: {rec_err}", exc_info=True)
                 continue

        db.session.commit()

        # ตัดสินใจขั้นตอนต่อไป
        if batch >= total_batches:
            _cleanup_file(json_filepath)
            session.pop('import_temp_file', None)
            flash(f'นำเข้าข้อมูลมาตรฐานสำเร็จ! (ใหม่: {imported_count}, ข้าม: {skipped_count}, ผิดพลาด: {error_count})', 'success')
            return redirect(url_for('admin.manage_standards'))
        else:
            flash(f'กำลังประมวลผล... (ส่วนที่ {batch}/{total_batches} - {end_index}/{total_items} รายการ)', 'info')
            next_url = url_for('admin.execute_import_standards',
                               batch=batch + 1,
                               new=imported_count,
                               skip=skipped_count,
                               err=error_count)
            return redirect(next_url)

    except Exception as e:
        db.session.rollback()
        _cleanup_file(json_filepath)
        session.pop('import_temp_file', None)
        current_app.logger.error(f"Critical error during standard import batch {batch}: {e}", exc_info=True)
        flash(f'เกิดข้อผิดพลาดร้ายแรงระหว่างประมวลผลส่วนที่ {batch}: {e}', 'danger')
        return redirect(url_for('admin.import_standards'))

@bp.route('/download-indicator-template')
# @login_required
def download_indicator_template():
    data = {'subject_group': ['ศิลปะ'],'strand': ['สาระที่ 1: ทัศนศิลป์'],'standard_code': ['ศ 1.1'],'standard_description': ['สร้างสรรค์งานทัศนศิลป์ตามจินตนาการ และความคิดสร้างสรรค์'],'indicator_code': ['ม.3/1'],'indicator_description': ['อธิบายทัศนธาตุในด้านรูปแบบและแนวคิดของงานทัศนศิลป์']}
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, index=False, sheet_name='indicators')
    output.seek(0)
    return send_file(output, download_name='indicator_template.xlsx', as_attachment=True)

# --- STRAND CRUD ---
@bp.route('/strand/add', methods=['POST'])
# @login_required
def add_strand():
    data = request.get_json()
    subject_group_id, name = data.get('subject_group_id'), data.get('name')
    if not all([subject_group_id, name]): 
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400
    new_strand = LearningStrand(name=name, subject_group_id=subject_group_id)
    db.session.add(new_strand)
    db.session.commit()
    flash('เพิ่มสาระการเรียนรู้เรียบร้อย', 'success')
    return jsonify({'status': 'success'})

@bp.route('/strand/<int:strand_id>/delete', methods=['POST'])
# @login_required
def delete_strand(strand_id):
    strand = LearningStrand.query.get_or_404(strand_id)
    db.session.delete(strand)
    db.session.commit()
    flash(f'ลบสาระการเรียนรู้ "{strand.name}" เรียบร้อย', 'success')
    return jsonify({'status': 'success'})

# --- STANDARD CRUD ---
@bp.route('/standard/add', methods=['POST'])
# @login_required
def add_standard():
    data = request.get_json()
    learning_strand_id, code, description = data.get('learning_strand_id'), data.get('code'), data.get('description')
    if not all([learning_strand_id, code, description]): 
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400
    new_standard = Standard(code=code, description=description, learning_strand_id=learning_strand_id)
    db.session.add(new_standard)
    db.session.commit()
    flash('เพิ่มมาตรฐานการเรียนรู้เรียบร้อย', 'success')
    return jsonify({'status': 'success'})

@bp.route('/standard/<int:standard_id>/delete', methods=['POST'])
# @login_required
def delete_standard(standard_id):
    standard = Standard.query.get_or_404(standard_id)
    db.session.delete(standard)
    db.session.commit()
    flash(f'ลบมาตรฐานการเรียนรู้ "{standard.code}" เรียบร้อย', 'success')
    return jsonify({'status': 'success'})

@bp.route('/indicator/add', methods=['POST'])
@login_required
def add_indicator():
    data = request.get_json()
    standard_id = data.get('standard_id')
    code = data.get('code')
    description = data.get('description')
    if not all([standard_id, code, description]):
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400
    
    indicator = Indicator(
        standard_id=standard_id,
        code=code,
        description=description,
        creator_type='ADMIN'
    )
    db.session.add(indicator)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'เพิ่มตัวชี้วัดใหม่เรียบร้อย'})

@bp.route('/positions', methods=['GET'])
@login_required
def manage_positions():
    # ดึงข้อมูลตำแหน่งผู้อำนวยการ
    director_id_setting = Setting.query.filter_by(key='director_user_id').first()
    director_id = int(director_id_setting.value) if director_id_setting and director_id_setting.value else None

    # ดึงรายชื่อบุคลากรทั้งหมดสำหรับ Dropdown
    users = User.query.order_by(User.first_name).all()

    # ดึงข้อมูลฝ่ายงานบริหารทั้งหมด
    departments = AdministrativeDepartment.query.options(
        joinedload(AdministrativeDepartment.head),
        joinedload(AdministrativeDepartment.vice_director),
        selectinload(AdministrativeDepartment.members)
    ).order_by(AdministrativeDepartment.name).all()
    
    # ******** START: ส่วนที่เพิ่มเข้ามาเพื่อวินิจฉัย ********
    print("--- DEBUG: manage_positions ---")
    print(f"Found {len(departments)} department(s):")
    for dept in departments:
        print(f"- ID: {dept.id}, Name: {dept.name}")
    print("-----------------------------")
    # ******** END: ส่วนที่เพิ่มเข้ามาเพื่อวินิจฉัย ********
    
    subject_groups = SubjectGroup.query.options(
        joinedload(SubjectGroup.head),
        selectinload(SubjectGroup.members)
    ).order_by(SubjectGroup.name).all()

    all_roles = Role.query.order_by(Role.name).all()

    return render_template('admin/manage_positions.html', 
                           title='ผังองค์กรและการมอบหมายตำแหน่ง',
                           users=users,
                           director_id=director_id,
                           departments=departments,
                           subject_groups=subject_groups,
                           all_roles=all_roles)

@bp.route('/api/position-details')
@login_required
def get_position_details():
    entity_type = request.args.get('type')
    if not entity_type:
        abort(400, "Request must include a 'type'.")

    all_users = User.query.order_by(User.first_name).all()
    all_users_data = [{'value': u.id, 'text': u.full_name} for u in all_users]
    
    if entity_type == 'director':
        director_setting = Setting.query.filter_by(key='director_user_id').first()
        director_id = int(director_setting.value) if director_setting and director_setting.value else None
        return jsonify({
            'name': 'ผู้อำนวยการสถานศึกษา',
            'all_users': all_users_data,
            'director_id': director_id
        })

    entity_id = request.args.get('id', type=int)
    if not entity_id:
        abort(400, "Request for this type requires an 'id'.")
    
    if entity_type == 'department':
        dept = AdministrativeDepartment.query.options(selectinload(AdministrativeDepartment.members)).get_or_404(entity_id)
        return jsonify({
            'name': dept.name,
            'head_id': dept.head_id,
            'vice_id': dept.vice_director_id,
            'member_ids': [m.id for m in dept.members],
            'all_users': all_users_data,
            'potential_heads': all_users_data
        })
    elif entity_type == 'subject_group':
        group = SubjectGroup.query.options(selectinload(SubjectGroup.members)).get_or_404(entity_id)
        members_data = [{'value': m.id, 'text': m.full_name} for m in group.members]
        return jsonify({
            'name': group.name,
            'head_id': group.head_id,
            'member_ids': [m.id for m in group.members],
            'potential_heads': members_data,
            'is_subject_group': True
        })
    else:
        abort(404, "Unknown entity type.")
        
def _assign_role_smart(user, role_name):
    """ Helper function to assign a role if it doesn't exist. """
    if not user or not role_name: return
    role = Role.query.filter_by(name=role_name).first()
    if role and not user.has_role(role_name):
        user.roles.append(role)

def _remove_role_smart(user, role_name):
    """ Helper function to remove a role if it exists. """
    if not user or not role_name: return
    role = Role.query.filter_by(name=role_name).first()
    if role and user.has_role(role_name):
        user.roles.remove(role)

@bp.route('/positions/director', methods=['POST'])
@login_required
def update_director():
    """
    UPDATED: Now handles AJAX requests to update the director.
    Reads and returns JSON.
    """
    # รับข้อมูลจาก JSON ที่ส่งมา
    data = request.get_json()
    new_director_id_str = data.get('user_id')
    new_director_id = int(new_director_id_str) if new_director_id_str else None

    director_role = Role.query.filter_by(name='ผู้อำนวยการ').first()
    if not director_role:
        director_role = Role(name='ผู้อำนวยการ', description='ตำแหน่งผู้อำนวยการโรงเรียน')
        db.session.add(director_role)

    # --- Smart Assignment Logic ---
    setting = Setting.query.filter_by(key='director_user_id').first()
    
    # 1. Remove role from the old director
    if setting and setting.value:
        try:
            old_director = User.query.get(int(setting.value))
            if old_director and old_director.has_role('ผู้อำนวยการ'):
                old_director.roles.remove(director_role)
        except (ValueError, TypeError):
            pass

    # 2. Add role to the new director
    if new_director_id:
        new_director = User.query.get(new_director_id)
        if new_director and not new_director.has_role('ผู้อำนวยการ'):
            new_director.roles.append(director_role)

    # 3. Update the setting
    if setting:
        setting.value = str(new_director_id) if new_director_id else ''
    else:
        setting = Setting(key='director_user_id', value=str(new_director_id) if new_director_id else '')
        db.session.add(setting)
        
    db.session.commit()
    
    # ส่งผลลัพธ์กลับเป็น JSON แทนการ redirect
    return jsonify({'status': 'success', 'message': 'อัปเดตตำแหน่งผู้อำนวยการเรียบร้อยแล้ว'})

@bp.route('/positions/departments/add', methods=['POST'])
@login_required
def add_department():
    # [แก้ไข] รับค่าจากฟอร์มที่ส่งมา
    name = request.form.get('name')
    head_role_id = request.form.get('head_role_id')
    vice_role_id = request.form.get('vice_role_id')
    member_role_id = request.form.get('member_role_id')

    if name and not AdministrativeDepartment.query.filter_by(name=name).first():
        new_dept = AdministrativeDepartment(
            name=name,
            # [ใหม่] บันทึก Role ID ที่ผูกไว้ (ถ้ามี)
            head_role_id=int(head_role_id) if head_role_id else None,
            vice_role_id=int(vice_role_id) if vice_role_id else None,
            member_role_id=int(member_role_id) if member_role_id else None
        )
        db.session.add(new_dept)
        db.session.commit()
        flash(f'สร้างฝ่ายงาน "{name}" เรียบร้อยแล้ว', 'success')
    else:
        flash(f'ไม่สามารถสร้างฝ่ายงานได้ เนื่องจากชื่อ "{name}" ซ้ำซ้อนหรือว่างเปล่า', 'danger')
    return redirect(url_for('admin.manage_positions'))

# [ใหม่] Route สำหรับแก้ไขชื่อฝ่ายงาน
@bp.route('/positions/department/<int:dept_id>/update-name', methods=['POST'])
@login_required
def update_department_name(dept_id):
    dept = AdministrativeDepartment.query.get_or_404(dept_id)
    new_name = request.form.get('name', '').strip()
    
    if not new_name:
        flash('ชื่อฝ่ายงานห้ามว่างเปล่า', 'danger')
        return redirect(url_for('admin.manage_positions'))

    old_name = dept.name
    if old_name == new_name:
        flash('ชื่อไม่มีการเปลี่ยนแปลง', 'info')
        return redirect(url_for('admin.manage_positions'))
    
    # ตรวจสอบชื่อซ้ำ
    if AdministrativeDepartment.query.filter(AdministrativeDepartment.name == new_name, AdministrativeDepartment.id != dept_id).first():
        flash(f'ชื่อฝ่ายงาน "{new_name}" มีอยู่แล้ว', 'danger')
        return redirect(url_for('admin.manage_positions'))

    try:
        # === [ข้อควรระวัง] ===
        # โค้ดของคุณ (routes.py บรรทัด 1509) มีการใช้ Role ที่ผูกกับ "ชื่อ" (f"Head of {dept.name}")
        # ซึ่งถ้าเปลี่ยนชื่อตรงนี้ Role เก่าจะไม่ถูกอัปเดต และระบบจะพัง
        # คุณต้องเลือกใช้มาตรฐานเดียว (เช่น f"DEPT_HEAD_{dept.id}" ที่ใช้ในบรรทัด 1478)
        # โค้ดด้านล่างนี้จะทำงานโดยสมมติว่าคุณใช้ Role ที่ผูกกับ ID
        
        dept.name = new_name
        db.session.commit()
        log_action("Update Department Name", model=AdministrativeDepartment, record_id=dept.id, old_value={'name': old_name}, new_value={'name': new_name})
        db.session.commit()
        flash(f'อัปเดตชื่อฝ่ายงานเป็น "{new_name}" เรียบร้อยแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการอัปเดตชื่อ: {e}', 'danger')
        
    return redirect(url_for('admin.manage_positions'))

# [ใหม่] Route สำหรับลบฝ่ายงาน
@bp.route('/positions/department/<int:dept_id>/delete', methods=['POST'])
@login_required
def delete_department(dept_id):
    form = FlaskForm()
    if not form.validate_on_submit():
         flash('CSRF Token ไม่ถูกต้อง', 'danger')
         return redirect(url_for('admin.manage_positions'))
         
    dept = AdministrativeDepartment.query.options(
        selectinload(AdministrativeDepartment.members)
    ).get_or_404(dept_id)
    
    dept_name = dept.name # เก็บชื่อไว้ log
    
    # [ลบ] โค้ดที่ค้นหา Role (role_names_to_delete, roles_to_delete) ทิ้งไป

    try:
        # 1. ล้างค่าตำแหน่ง
        dept.head_id = None
        dept.vice_director_id = None
        
        # 2. ลบสมาชิก (M-M relationship)
        dept.members.clear()
        
        # 3. ลบตัวฝ่ายงาน
        db.session.delete(dept)
        
        # 4. [ลบ] โค้ดที่ลบ Role (for role in roles_to_delete) ทิ้งไป
            
        db.session.commit()
        log_action("Delete Department", model=AdministrativeDepartment, record_id=dept_id, old_value={'name': dept_name})
        db.session.commit()
        flash(f'ลบฝ่ายงาน "{dept_name}" เรียบร้อยแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการลบฝ่ายงาน: {e}', 'danger')
        
    return redirect(url_for('admin.manage_positions'))

@bp.route('/positions/department/<int:dept_id>/positions', methods=['POST'])
@login_required
def update_department_positions(dept_id):
    # [แก้ไข] Eager load Role ที่ผูกไว้ด้วย
    dept = AdministrativeDepartment.query.options(
        joinedload(AdministrativeDepartment.head_role),
        joinedload(AdministrativeDepartment.vice_role),
        joinedload(AdministrativeDepartment.member_role)
    ).get_or_404(dept_id)
    
    data = request.get_json()
    new_head_id = int(data.get('head_id')) if data.get('head_id') else None
    new_vice_id = int(data.get('vice_director_id')) if data.get('vice_director_id') else None
    new_member_ids = {int(m_id) for m_id in data.get('member_ids', [])}

    # --- [แก้ไข] ส่ง Role Object (dept.head_role) แทน Role Name ---
    _handle_position_change(dept.head, new_head_id, dept.head_role) # 👈
    dept.head_id = new_head_id
    
    # --- [แก้ไข] ส่ง Role Object (dept.vice_role) แทน Role Name ---
    _handle_position_change(dept.vice_director, new_vice_id, dept.vice_role) # 👈
    dept.vice_director_id = new_vice_id

    # --- [แก้ไข] Smart Assignment for Members ---
    member_role = dept.member_role # 👈 ดึง Role ของสมาชิกที่ผูกไว้
    current_member_ids = {member.id for member in dept.members}

    # 1. Add new members
    ids_to_add = new_member_ids - current_member_ids
    for user_id in ids_to_add:
        user = User.query.get(user_id)
        if user and user not in dept.members:
            dept.members.append(user)
            _assign_role_smart(user, member_role.name if member_role else None) # 👈 ใช้ชื่อ Role ที่ผูกไว้
    
    # 2. Remove old members
    ids_to_remove = current_member_ids - new_member_ids
    for user_id in ids_to_remove:
        if user_id == dept.head_id or user_id == dept.vice_director_id:
            continue
        user = User.query.get(user_id)
        if user and user in dept.members:
            dept.members.remove(user)
            _remove_role_smart(user, member_role.name if member_role else None) # 👈 ใช้ชื่อ Role ที่ผูกไว้

    # 3. Auto-add Head/Vice to members (เหมือนเดิม แต่ใช้ Role ที่ผูกไว้)
    if new_head_id and new_head_id not in current_member_ids:
        head_user = User.query.get(new_head_id)
        if head_user and head_user not in dept.members:
            dept.members.append(head_user)
            _assign_role_smart(head_user, member_role.name if member_role else None) # 👈
    
    if new_vice_id and new_vice_id not in current_member_ids:
        vice_user = User.query.get(new_vice_id)
        if vice_user and vice_user not in dept.members:
            dept.members.append(vice_user)
            _assign_role_smart(vice_user, member_role.name if member_role else None) # 👈

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'อัปเดตฝ่ายงาน {dept.name} เรียบร้อยแล้ว'})

@bp.route('/positions/department/<int:dept_id>/update', methods=['POST'])
@login_required
def update_department_heads(dept_id):
    """
    UPDATED: Now handles AJAX requests to update department head and vice director.
    Reads and returns JSON.
    """
    dept = AdministrativeDepartment.query.get_or_404(dept_id)
    data = request.get_json()
    
    # ดึงค่า ID ใหม่จาก JSON ที่ส่งมา
    new_head_id = data.get('head_id')
    new_vice_id = data.get('vice_director_id')
    
    # --- Smart Assignment for Head ---
    head_role_name = f"Head of {dept.name}"
    old_head = dept.head
    if old_head and (not new_head_id or old_head.id != int(new_head_id)):
        _remove_role_smart(old_head, head_role_name)

    if new_head_id:
        new_head = User.query.get(int(new_head_id))
        _assign_role_smart(new_head, head_role_name)
        dept.head_id = new_head.id
    else:
        dept.head_id = None
        
    # --- Smart Assignment for Vice Director ---
    vice_role_name = f"Vice Director of {dept.name}"
    old_vice = dept.vice_director
    if old_vice and (not new_vice_id or old_vice.id != int(new_vice_id)):
        _remove_role_smart(old_vice, vice_role_name)

    if new_vice_id:
        new_vice = User.query.get(int(new_vice_id))
        _assign_role_smart(new_vice, vice_role_name)
        dept.vice_director_id = new_vice.id
    else:
        dept.vice_director_id = None

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'อัปเดตฝ่ายงาน {dept.name} เรียบร้อยแล้ว'})

@bp.route('/positions/department/<int:dept_id>/members', methods=['POST'])
@login_required
def update_department_members(dept_id):
    dept = AdministrativeDepartment.query.get_or_404(dept_id)
    data = request.get_json()
    new_member_ids = set(data.get('user_ids', []))

    # --- Smart Assignment Logic for Members ---
    member_role_name = f"Member of {dept.name}"
    member_role = Role.query.filter_by(name=member_role_name).first()

    if not member_role:
        # Failsafe in case the role wasn't created by the event
        return jsonify({'status': 'error', 'message': f'Role "{member_role_name}" not found!'}), 500

    current_member_ids = {member.id for member in dept.members}

    # 1. Find users to add
    ids_to_add = new_member_ids - current_member_ids
    for user_id in ids_to_add:
        user = User.query.get(user_id)
        if user:
            dept.members.append(user)
            _assign_role_smart(user, member_role_name)

    # 2. Find users to remove
    ids_to_remove = current_member_ids - new_member_ids
    for user_id in ids_to_remove:
        user = User.query.get(user_id)
        if user:
            dept.members.remove(user)
            _remove_role_smart(user, member_role_name)

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'อัปเดตสมาชิกเรียบร้อยแล้ว'})

@bp.route('/positions/subject-group/<int:group_id>/head', methods=['POST'])
@login_required
def update_subject_group_head(group_id):
    group = SubjectGroup.query.get_or_404(group_id)
    data = request.get_json()
    new_head_id = data.get('head_id')
    
    # --- Auto-add Head to members if not already a member ---
    if new_head_id:
        head_user = User.query.get(int(new_head_id))
        if head_user and head_user not in group.members:
            group.members.append(head_user)
            flash(f'เพิ่ม {head_user.full_name} เป็นสมาชิกของกลุ่มสาระฯ โดยอัตโนมัติ', 'info')

    _handle_position_change(group.head, new_head_id, "DepartmentHead")
    group.head_id = new_head_id

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'อัปเดตหัวหน้ากลุ่มสาระฯ {group.name} เรียบร้อยแล้ว'})

def _handle_position_change(old_user, new_user_id, role_to_apply): # [แก้ไข] รับ Role Object
    """ Helper for smart role assignment. 'role_to_apply' is now a Role object. """
    
    # 0. ถ้าไม่มี Role ผูกไว้ ก็ไม่ต้องทำอะไร
    if not role_to_apply:
        return

    # 1. Remove role from old user
    if old_user and (not new_user_id or old_user.id != int(new_user_id)):
        # ใช้ role_to_apply.name (จาก object ที่ส่งมา)
        _remove_role_smart(old_user, role_to_apply.name) 
    
    # 2. Add role to new user
    if new_user_id:
        new_user = User.query.get(int(new_user_id))
        # ใช้ role_to_apply.name (จาก object ที่ส่งมา)
        _assign_role_smart(new_user, role_to_apply.name)

@bp.route('/timeslots/manage/<int:semester_id>', methods=['GET', 'POST'])
@login_required
def manage_timeslots(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    if request.method == 'POST':
        # This handles Add, Edit, and Delete
        action = request.form.get('action')

        if action == 'add' or action == 'edit':
            period_number = request.form.get('period_number')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            is_teaching_period = 'is_teaching_period' in request.form
            activity_name = request.form.get('activity_name') if not is_teaching_period else None

            # Convert time strings to time objects
            try:
                start_time = datetime.strptime(start_time_str, '%H:%M').time()
                end_time = datetime.strptime(end_time_str, '%H:%M').time()
            except ValueError:
                flash('รูปแบบเวลาไม่ถูกต้อง (HH:MM)', 'danger')
                return redirect(url_for('admin.manage_timeslots', semester_id=semester_id))

            if action == 'add':
                new_slot = TimeSlot(semester_id=semester_id, period_number=period_number, 
                                    start_time=start_time, end_time=end_time,
                                    is_teaching_period=is_teaching_period, activity_name=activity_name)
                db.session.add(new_slot)
                flash('เพิ่มคาบเรียนใหม่เรียบร้อยแล้ว', 'success')

            elif action == 'edit':
                slot_id = request.form.get('slot_id')
                slot = TimeSlot.query.get_or_404(slot_id)
                slot.period_number = period_number
                slot.start_time = start_time
                slot.end_time = end_time
                slot.is_teaching_period = is_teaching_period
                slot.activity_name = activity_name
                flash('อัปเดตข้อมูลคาบเรียนเรียบร้อยแล้ว', 'success')

        elif action == 'delete':
            slot_id = request.form.get('slot_id')
            slot = TimeSlot.query.get_or_404(slot_id)
            db.session.delete(slot)
            flash('ลบคาบเรียนเรียบร้อยแล้ว', 'info')

        db.session.commit()
        return redirect(url_for('admin.manage_timeslots', semester_id=semester_id))

    # GET request logic
    time_slots = TimeSlot.query.filter_by(semester_id=semester_id).order_by(TimeSlot.period_number).all()
    return render_template('admin/manage_timeslots.html', 
                           semester=semester,
                           time_slots=time_slots,
                           title=f'จัดการคาบเรียน ภาคเรียน {semester.term}/{semester.academic_year.year}')

@bp.route('/timeslots-semesters')
@login_required
# Add role check for Admin if necessary
def list_semesters_for_timeslots():
    semesters = Semester.query.join(AcademicYear).order_by(AcademicYear.year.desc(), Semester.term.desc()).all()
    return render_template('admin/list_semesters_for_timeslots.html', 
                           semesters=semesters, 
                           title='เลือกภาคเรียนเพื่อจัดการคาบเรียน')

@bp.route('/schedules-semesters')
@login_required
def list_semesters_for_schedules():
    semesters = Semester.query.join(AcademicYear).order_by(AcademicYear.year.desc(), Semester.term.desc()).all()
    return render_template('admin/list_semesters_for_schedules.html', 
                           semesters=semesters, 
                           title='เลือกภาคเรียนเพื่อจัดการตารางสอน')

@bp.route('/schedules/manage/<int:semester_id>', methods=['GET'])
@login_required
def manage_weekly_schedule(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    slots = WeeklyScheduleSlot.query.filter_by(semester_id=semester_id).options(
        joinedload(WeeklyScheduleSlot.grade_level)
    ).all()
    grade_levels = GradeLevel.query.order_by(GradeLevel.id).all()

    # สร้าง Dictionary จาก list ของ slots เพื่อให้ Template ค้นหาข้อมูลได้ง่าย
    slots_by_grade_day_period = {
        f"[{s.grade_level_id},{s.day_of_week},{s.period_number}]": {
            "id": s.id,
            "start_time": s.start_time.strftime('%H:%M:%S'),
            "end_time": s.end_time.strftime('%H:%M:%S'),
            "is_teaching_period": s.is_teaching_period,
            "activity_name": s.activity_name
        } for s in slots
    }
    
    form = FlaskForm()
    all_semesters_for_dropdown = Semester.query.join(AcademicYear).options(
        joinedload(Semester.academic_year) # Eager load year info for display
    ).order_by(AcademicYear.year.desc(), Semester.term.desc()).all()
    return render_template('admin/manage_weekly_schedule.html', 
                            semester=semester,
                            grade_levels=grade_levels,
                            slots_data=slots_by_grade_day_period, # ส่งข้อมูลด้วยชื่อ 'slots_data'
                            form=form,
                            all_semesters_for_dropdown=all_semesters_for_dropdown,
                            title=f'จัดการตารางสอนประจำสัปดาห์ ภาคเรียน {semester.term}/{semester.academic_year.year}')

@bp.route('/schedules/manage', methods=['GET'])
@login_required
def manage_weekly_schedule_redirect():
     current_semester = Semester.query.filter_by(is_current=True).first()
     if not current_semester:
          # Fallback: get the latest semester if current is not set
          current_semester = Semester.query.join(AcademicYear).order_by(AcademicYear.year.desc(), Semester.term.desc()).first()

     if not current_semester:
          flash("ไม่พบข้อมูลภาคเรียน", "warning")
          # Redirect to a page where semesters can be managed or selected
          return redirect(url_for('admin.manage_semesters')) # Adjust route name if needed
     return redirect(url_for('admin.manage_weekly_schedule', semester_id=current_semester.id))

@bp.route('/api/schedules/slot', methods=['POST'])
@login_required
def add_schedule_slot():
    data = request.get_json()
    slots_to_process = data if isinstance(data, list) else [data]

    for slot_data in slots_to_process:
        if not all(k in slot_data for k in ['semester_id', 'day_of_week', 'period_number', 'start_time', 'end_time']):
            return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400
        
        try:
            start_t = time.fromisoformat(slot_data['start_time'])
            end_t = time.fromisoformat(slot_data['end_time'])
        except ValueError:
            return jsonify({'status': 'error', 'message': 'รูปแบบเวลาไม่ถูกต้อง'}), 400

        grade_level_ids = slot_data.get('grade_level_ids', [])
        
        # ถ้าไม่ได้เลือกระดับชั้นมา ให้ส่ง Error กลับไป
        if not grade_level_ids:
            return jsonify({'status': 'error', 'message': 'กรุณาเลือกระดับชั้นอย่างน้อย 1 ระดับ'}), 400

        # วนลูปเพื่อสร้าง Slot แยกสำหรับแต่ละ Grade Level ID ที่ส่งมา
        for grade_id in grade_level_ids:
            # ตรวจสอบว่ามี Slot นี้อยู่แล้วหรือไม่
            existing_slot = WeeklyScheduleSlot.query.filter_by(
                semester_id=slot_data['semester_id'],
                grade_level_id=grade_id,
                day_of_week=slot_data['day_of_week'],
                period_number=slot_data['period_number']
            ).first()

            if existing_slot:
                # ถ้ามีอยู่แล้ว ให้อัปเดตข้อมูลแทนการสร้างใหม่
                existing_slot.start_time = start_t
                existing_slot.end_time = end_t
                existing_slot.is_teaching_period = slot_data.get('is_teaching_period', True)
                existing_slot.activity_name = slot_data.get('activity_name')
            else:
                # ถ้ายังไม่มี ให้สร้างใหม่
                new_slot = WeeklyScheduleSlot(
                    semester_id=slot_data['semester_id'],
                    day_of_week=slot_data['day_of_week'],
                    period_number=slot_data['period_number'],
                    start_time=start_t,
                    end_time=end_t,
                    is_teaching_period=slot_data.get('is_teaching_period', True),
                    activity_name=slot_data.get('activity_name'),
                    grade_level_id=grade_id # <-- ใช้ grade_id ทีละค่า
                )
                db.session.add(new_slot)
    
    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'บันทึกคาบเรียนเรียบร้อยแล้ว'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

@bp.route('/api/schedules/slot/<int:slot_id>', methods=['DELETE'])
@login_required
def delete_schedule_slot(slot_id):
    slot = WeeklyScheduleSlot.query.get_or_404(slot_id)
    db.session.delete(slot)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'ลบคาบเรียนแล้ว'})

# ค้นหาฟังก์ชัน manage_rooms และแทนที่ด้วยโค้ดนี้
@bp.route('/rooms', methods=['GET'])
@login_required
def manage_rooms():
    form = FlaskForm()
    rooms = Room.query.order_by(Room.name).all()
    return render_template('admin/manage_rooms.html',
                           rooms=rooms,
                           form=form,
                           title='จัดการห้องเรียนและสถานที่')

@bp.route('/rooms/save', methods=['POST'])
@login_required
def save_room():
    form = FlaskForm()
    if form.validate_on_submit():
        room_id = request.form.get('room_id')
        name = request.form.get('name')
        capacity = request.form.get('capacity')
        room_type = request.form.get('room_type')

        if not name:
            flash('ชื่อห้องเรียนห้ามว่างเปล่า', 'danger')
            return redirect(url_for('admin.manage_rooms'))

        if room_id: # แก้ไขห้องเดิม
            room = Room.query.get_or_404(room_id)
            room.name = name
            room.capacity = int(capacity) if capacity else None
            room.room_type = room_type
            flash('อัปเดตข้อมูลห้องเรียนเรียบร้อยแล้ว', 'success')
        else: # เพิ่มห้องใหม่
            if Room.query.filter_by(name=name).first():
                flash(f'ชื่อห้อง "{name}" มีอยู่แล้วในระบบ', 'danger')
                return redirect(url_for('admin.manage_rooms'))

            new_room = Room(name=name,
                            capacity=int(capacity) if capacity else None,
                            room_type=room_type)
            db.session.add(new_room)
            flash('เพิ่มห้องเรียนใหม่เรียบร้อยแล้ว', 'success')

        db.session.commit()
    return redirect(url_for('admin.manage_rooms'))

@bp.route('/rooms/delete/<int:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    form = FlaskForm()
    if form.validate_on_submit():
        room = Room.query.get_or_404(room_id)
        # ในอนาคตควรเพิ่มเงื่อนไขป้องกันการลบห้องที่ถูกใช้งานในตารางสอน
        db.session.delete(room)
        db.session.commit()
        flash('ลบห้องเรียนเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin.manage_rooms'))

@bp.route('/api/student/<int:student_id>/details')
@login_required
# @admin_required # You might want to add a permission check decorator here
def get_student_details_for_status(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'status': 'error', 'message': 'ไม่พบนักเรียน'}), 404
    return jsonify({
        'status': 'success',
        'student': {
            'id': student.id,
            'full_name': f"{student.first_name} {student.last_name}",
            'current_status': student.status
        }
    })

@bp.route('/api/student/<int:student_id>/update-status', methods=['POST'])
@login_required
# @admin_required
def update_student_status(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'status': 'error', 'message': 'ไม่พบนักเรียน'}), 404

    data = request.get_json()
    new_status = data.get('status')
    notes = data.get('notes', '(ไม่มีหมายเหตุ)')

    if not new_status:
        return jsonify({'status': 'error', 'message': 'กรุณาระบุสถานะใหม่'}), 400

    old_status = student.status
    # --- Only proceed if the status has actually changed ---
    if old_status != new_status:
        student.status = new_status

        audit_log = AuditLog(
            user_id=current_user.id,
            action="Update Student Status",
            model_name="Student",
            record_id=student.id,
            old_value=f"Status: {old_status}",
            new_value=f"Status: {new_status}. Notes: {notes}"
        )
        db.session.add(audit_log)

    # --- Notification Logic ---
    teachers_to_notify = set()
    current_semester = Semester.query.filter_by(is_current=True).first()
    if current_semester:
        enrollment = student.enrollments.filter(Enrollment.classroom.has(academic_year_id=current_semester.academic_year_id)).first()
        if enrollment:
            for advisor in enrollment.classroom.advisors:
                teachers_to_notify.add(advisor)
            
            courses_in_classroom = Course.query.filter_by(classroom_id=enrollment.classroom_id, semester_id=current_semester.id).all()
            for course in courses_in_classroom:
                for teacher in course.teachers:
                    teachers_to_notify.add(teacher)
    
    title = "แจ้งเตือนการเปลี่ยนแปลงสถานะนักเรียน"
    message = f"สถานะของนักเรียน {student.first_name} {student.last_name} ได้เปลี่ยนจาก '{old_status}' เป็น '{new_status}'\nหมายเหตุ: {notes}"
    url = url_for('admin.list_students', action='edit_status', student_id=student.id, _external=True) # Example URL

    for user in teachers_to_notify:
        notification = Notification(user_id=user.id, title=title, message=message, url=url, notification_type='STUDENT_STATUS')
        db.session.add(notification)
    # --- End Notification Logic ---

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'อัปเดตสถานะนักเรียนเป็น "{new_status}" เรียบร้อยแล้ว'})

@bp.route('/audit-log')
@login_required
# @admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return render_template('admin/audit_log.html', title="ประวัติการใช้งานระบบ", logs=logs)

@bp.route('/student/<int:student_id>')
@login_required
def view_student_profile(student_id):
    # ตรวจสอบสิทธิ์การเข้าถึงเฉพาะแอดมิน
    if not current_user.has_role('Admin'):
        abort(403)

    student = db.session.get(Student, student_id)
    if not student:
        abort(404)

    # --- คัดลอกตรรกะการดึงข้อมูลทั้งหมดจาก advisor/routes.py ---
    active_warnings = AttendanceWarning.query.filter_by(student_id=student.id, status='ACTIVE').options(joinedload(AttendanceWarning.course).joinedload(Course.subject)).all()
    current_semester = Semester.query.filter_by(is_current=True).first()
    academic_summary = []
    current_enrollment = None
    enrolled_courses = []

    if current_semester:
        current_enrollment = student.enrollments.filter(Enrollment.classroom.has(academic_year_id=current_semester.academic_year_id)).first()
        if current_enrollment:
            enrolled_courses = Course.query.filter_by(classroom_id=current_enrollment.classroom_id, semester_id=current_semester.id).options(joinedload(Course.subject), joinedload(Course.teachers), joinedload(Course.lesson_plan).joinedload(LessonPlan.learning_units)).all()
            
            course_ids = {c.id for c in enrolled_courses}
            
            student_course_grades = [cg for cg in student.course_grades if cg.course_id in course_ids]
            grades_map = {cg.course_id: cg for cg in student_course_grades}

            def map_to_grade(p):
                if p >= 80: return '4'
                if p >= 75: return '3.5'
                if p >= 70: return '3'
                if p >= 65: return '2.5'
                if p >= 60: return '2'
                if p >= 55: return '1.5'
                if p >= 50: return '1'
                return '0'

            for course in enrolled_courses:
                grade_obj = grades_map.get(course.id)
                course_summary = {
                    'course': course, 'collected_score': 0, 'max_collected_score': 0,
                    'midterm_score': grade_obj.midterm_score if grade_obj else None,
                    'final_score': grade_obj.final_score if grade_obj else None,
                    'attendance': {'PRESENT': 0, 'LATE': 0, 'ABSENT': 0, 'LEAVE': 0}
                }
                
                total_midterm_max = 0
                total_final_max = 0

                if course.lesson_plan:
                    graded_items = GradedItem.query.join(LearningUnit).filter(
                        LearningUnit.lesson_plan_id == course.lesson_plan.id
                    ).all()
                    if graded_items:
                        item_ids = [i.id for i in graded_items]
                        scores = Score.query.filter(
                            Score.student_id == student.id,
                            Score.graded_item_id.in_(item_ids)
                        ).all()
                        course_summary['collected_score'] = sum(s.score for s in scores if s.score is not None)
                        course_summary['max_collected_score'] = sum(i.max_score for i in graded_items if i.max_score is not None)
                    
                    total_midterm_max = sum(unit.midterm_score for unit in course.lesson_plan.learning_units if unit.midterm_score)
                    total_final_max = sum(unit.final_score for unit in course.lesson_plan.learning_units if unit.final_score)

                student_total_score = (course_summary['collected_score'] or 0) + (course_summary['midterm_score'] or 0) + (course_summary['final_score'] or 0)
                grand_max_score = (course_summary['max_collected_score'] or 0) + total_midterm_max + total_final_max
                
                percentage = (student_total_score / grand_max_score * 100) if grand_max_score > 0 else 0
                
                course_summary['total_score'] = student_total_score
                course_summary['grand_max_score'] = grand_max_score
                course_summary['grade'] = map_to_grade(percentage)
                course_summary['max_midterm_score'] = total_midterm_max
                course_summary['max_final_score'] = total_final_max

                entry_ids = [e.id for e in course.timetable_entries]
                if entry_ids:
                    attendance_counts = db.session.query(
                        AttendanceRecord.status, func.count(AttendanceRecord.id)
                    ).filter(
                        AttendanceRecord.student_id == student.id,
                        AttendanceRecord.timetable_entry_id.in_(entry_ids)
                    ).group_by(AttendanceRecord.status).all()
                    for status, count in attendance_counts:
                        if status in course_summary['attendance']:
                            course_summary['attendance'][status] = count
                
                course_summary['total_attendance'] = course_summary['attendance']['PRESENT']
                
                academic_summary.append(course_summary)

    return render_template('admin/student_profile.html',
                           title=f"ข้อมูลนักเรียน: {student.first_name}",
                           student=student,
                           warnings=active_warnings,
                           academic_summary=academic_summary,
                           current_enrollment=current_enrollment,
                           courses=enrolled_courses)

@bp.route('/grade-level-heads')
@login_required
# @admin_required # <-- You can uncomment this if you have the decorator
def manage_grade_level_heads():
    grade_levels = GradeLevel.query.order_by(GradeLevel.id).all()
    
    data = []
    for gl in grade_levels:
        # Find all advisors within this grade level
        potential_heads = db.session.query(User).join(
            User.advised_classrooms
        ).filter(
            Classroom.grade_level_id == gl.id
        ).distinct().order_by(User.first_name).all()
        
        data.append({
            'grade_level': gl,
            'potential_heads': potential_heads
        })

    return render_template('admin/manage_grade_level_heads.html',
                           title="จัดการหัวหน้าสายชั้น",
                           data=data)

@bp.route('/api/grade-level/<int:grade_level_id>/set-head', methods=['POST'])
@login_required
# @admin_required
def update_grade_level_head(grade_level_id):
    grade_level = db.session.get(GradeLevel, grade_level_id)
    if not grade_level:
        return jsonify({'status': 'error', 'message': 'Grade Level not found'}), 404

    data = request.get_json()
    new_head_id = data.get('user_id')
    new_head = db.session.get(User, new_head_id) if new_head_id else None
    
    role_name = f'GRADE_HEAD_{grade_level.id}'
    head_role = Role.query.filter_by(name=role_name).first()

    if not head_role:
        # Failsafe in case the role wasn't created automatically
        head_role = Role(name=role_name, description=f"Head of Grade Level ID {grade_level.id}")
        db.session.add(head_role)

    # Remove role from the old head, if one exists
    if grade_level.head and head_role in grade_level.head.roles:
        grade_level.head.roles.remove(head_role)

    # Add role to the new head
    if new_head and head_role not in new_head.roles:
        new_head.roles.append(head_role)

    grade_level.head_id = new_head_id
    db.session.commit()

    return jsonify({'status': 'success', 'message': f'อัปเดตหัวหน้าสายชั้น {grade_level.name} เรียบร้อยแล้ว'})

@bp.route('/promote-students', methods=['GET', 'POST'])
@login_required
# @admin_required
def promote_students_page():
    form = FlaskForm() # Use a simple form for CSRF protection
    academic_years = AcademicYear.query.order_by(AcademicYear.year.desc()).all()

    if request.method == 'POST':
        source_year_id = request.form.get('source_year_id', type=int)
        target_year_id = request.form.get('target_year_id', type=int)

        if not source_year_id or not target_year_id:
            flash('กรุณาเลือกปีการศึกษาต้นทางและปลายทาง', 'danger')
            return redirect(url_for('admin.promote_students_page'))
        if source_year_id == target_year_id:
            flash('ปีการศึกษาต้นทางและปลายทางต้องแตกต่างกัน', 'danger')
            return redirect(url_for('admin.promote_students_page'))

        # Store IDs in session to pass to the execution step
        session['promotion_source_year_id'] = source_year_id
        session['promotion_target_year_id'] = target_year_id

        # Redirect to a confirmation/execution page or directly execute
        # For simplicity, let's redirect to an execution route
        return redirect(url_for('admin.execute_promotion'))

    # GET request: Render the selection form
    return render_template('admin/promote_students.html',
                           title='เลื่อนชั้นนักเรียนข้ามปีการศึกษา',
                           form=form,
                           academic_years=academic_years)

@bp.route('/promote-students/execute', methods=['GET']) # Use GET for simplicity, POST recommended for actions
@login_required
# @admin_required
def execute_promotion():
    source_year_id = session.get('promotion_source_year_id')
    target_year_id = session.get('promotion_target_year_id')

    if not source_year_id or not target_year_id:
        flash('ไม่พบข้อมูลปีการศึกษาสำหรับดำเนินการเลื่อนชั้น', 'warning')
        return redirect(url_for('admin.promote_students_page'))

    # Clear session variables
    session.pop('promotion_source_year_id', None)
    session.pop('promotion_target_year_id', None)

    # Call the service function
    result = promote_students_to_next_year(source_year_id, target_year_id)

    # Display results
    if result.get('errors'):
        for error in result['errors']:
            flash(f'ข้อผิดพลาด: {error}', 'danger')
    else:
        flash(f"ดำเนินการเลื่อนชั้นสำเร็จ: เลื่อนชั้น {result.get('promoted', 0)} คน, "
              f"จบการศึกษา {result.get('graduated', 0)} คน, "
              f"รอพิจารณาซ้ำชั้น {result.get('flagged_repeat', 0)} คน", 'success')

    # Redirect back to the list of students or another appropriate page
    return redirect(url_for('admin.list_students'))    

@bp.route('/api/users/simple-list') # Adjust blueprint ('bp') if needed
@login_required # Or remove if public access is intended
def get_simple_user_list():
    """ Returns a simple list of users (ID and Full Name). """
    try:
        users = User.query.order_by(User.first_name, User.last_name).all()
        user_list = [{'id': u.id, 'full_name': u.full_name} for u in users]
        return jsonify(user_list)
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error fetching simple user list: {e}")
        return jsonify({'status': 'error', 'message': 'Could not retrieve user list'}), 500
    
# --- Route for the Backup/Restore Page ---
@bp.route('/backup-restore')
@login_required
# @admin_required
def backup_restore_page():
    """Renders the main backup and restore management page for admins."""
    return render_template('admin/backup_restore.html', title="สำรองและกู้คืนข้อมูล")

# --- API Route for Creating a Backup ---
@bp.route('/api/backup/create', methods=['POST'])
@login_required
# @admin_required
def backup_create_api():
    """Creates a backup zip containing the database and uploaded files."""
    # --- [START LOG] Log backup start ---
    log_action("Backup Started")
    try:
        db.session.commit() # Commit start log immediately
    except Exception as log_err:
        db.session.rollback()
        current_app.logger.error(f"Failed to commit backup start log: {log_err}")
    # --- [END LOG] ---

    backup_stage_path = None # Define for potential cleanup in except block
    final_zip_path = None    # Define for potential cleanup in except block

    try:
        # --- Configuration ---
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        uploads_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, 'static', 'uploads'))
        backup_temp_dir = os.path.join(current_app.instance_path, 'backup_temp')

        # --- Timestamp and Temp Directory ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename_base = f"edhub_backup_{timestamp}"
        os.makedirs(backup_temp_dir, exist_ok=True)
        backup_stage_path = os.path.join(backup_temp_dir, backup_filename_base)
        os.makedirs(backup_stage_path, exist_ok=True)

        db_backup_successful = False
        db_backup_filename = None

        # --- 1. Backup Database ---
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.split('sqlite:///')[-1]
            if os.path.exists(db_path):
                db_backup_filename = f"database_{timestamp}.db"
                shutil.copy2(db_path, os.path.join(backup_stage_path, db_backup_filename))
                db_backup_successful = True
            else:
                 current_app.logger.error(f"SQLite DB file not found at: {db_path}")
                 raise ValueError("ไม่พบไฟล์ฐานข้อมูล SQLite")
        # --- Add logic for PostgreSQL/MySQL ---
        else:
             raise NotImplementedError("ประเภทฐานข้อมูลนี้ยังไม่รองรับการสำรองข้อมูลอัตโนมัติ")

        if not db_backup_successful:
             raise ValueError("ไม่สามารถสำรองข้อมูลฐานข้อมูลได้")

        # --- 2. Backup Uploaded Files ---
        files_backup_filename = f"uploads_{timestamp}.zip"
        files_zip_path = os.path.join(backup_stage_path, files_backup_filename)
        if os.path.exists(uploads_folder) and os.path.isdir(uploads_folder):
            with zipfile.ZipFile(files_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(uploads_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, uploads_folder)
                        zipf.write(file_path, arcname)
        else:
            with zipfile.ZipFile(files_zip_path, 'w') as zipf: pass # Create empty zip
            current_app.logger.warning(f"Uploads folder not found: {uploads_folder}. Created empty zip.")

        # --- 3. Combine into a single Zip file ---
        final_zip_filename = f"{backup_filename_base}.zip"
        final_zip_path = os.path.join(backup_temp_dir, final_zip_filename)
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
             zipf.write(os.path.join(backup_stage_path, db_backup_filename), arcname=db_backup_filename)
             zipf.write(files_zip_path, arcname=files_backup_filename)

        # --- Clean up staged files ---
        shutil.rmtree(backup_stage_path)

        # --- [START LOG] Log backup success ---
        log_action("Backup Success", new_value={'filename': final_zip_filename})
        try:
            db.session.commit() # Commit success log
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit backup success log: {log_err}")
        # --- [END LOG] ---

        # --- 4. Send the final Zip file for download ---
        return send_file(final_zip_path, as_attachment=True, download_name=final_zip_filename)

    except Exception as e:
        current_app.logger.error(f"Backup creation failed: {e}", exc_info=True)
        # Clean up temporary files on error
        if backup_stage_path and os.path.exists(backup_stage_path):
             shutil.rmtree(backup_stage_path)
        if final_zip_path and os.path.exists(final_zip_path):
             os.remove(final_zip_path)

        # --- [START LOG] Log backup failure ---
        log_action(f"Backup Failed: {type(e).__name__}", new_value={'error': str(e)})
        try:
            db.session.commit() # Commit failure log
        except Exception as log_err:
             db.session.rollback()
             current_app.logger.error(f"Failed to commit backup failure log: {log_err}")
        # --- [END LOG] ---

        return jsonify({"status": "error", "message": f"การสร้างไฟล์สำรองข้อมูลล้มเหลว: {str(e)}"}), 500

# --- API Route for Restoring Data ---
@bp.route('/api/backup/restore', methods=['POST'])
@login_required
# @admin_required
def backup_restore_api():
    restore_temp_dir = os.path.join(current_app.instance_path, 'restore_temp')
    filename = None # Define filename early for logging

    # --- [START LOG] Log restore start ---
    log_action("Restore Started")
    try:
        db.session.commit() # Commit start log immediately
    except Exception as log_err:
        db.session.rollback()
        current_app.logger.error(f"Failed to commit restore start log: {log_err}")
    # --- [END LOG] ---

    try:
        # --- Security & Confirmation ---
        confirmation_text = request.form.get('confirmation_text', '')
        if confirmation_text.upper() != 'CONFIRM RESTORE':
            raise ValueError("ข้อความยืนยันไม่ถูกต้อง การกู้คืนถูกยกเลิก") # Use ValueError for flow

        backup_zip_file = request.files.get('backup_zip')
        if not backup_zip_file or not backup_zip_file.filename.endswith('.zip'):
             raise ValueError("กรุณาเลือกไฟล์ .zip ที่ได้จากการสำรองข้อมูล") # Use ValueError

        filename = secure_filename(backup_zip_file.filename) # Store filename for logging

        # --- Configuration ---
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        uploads_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, 'static', 'uploads'))

        # --- Prepare Temp Directory ---
        if os.path.exists(restore_temp_dir):
            shutil.rmtree(restore_temp_dir)
        os.makedirs(restore_temp_dir, exist_ok=True)

        # --- Use Stream Processing and Validation ---
        extracted_db_path = None
        extracted_uploads_zip_path = None
        with zipfile.ZipFile(backup_zip_file.stream, 'r') as zip_ref:
            current_app.logger.info(f"Successfully opened uploaded zip file: {filename}")
            extracted_files = zip_ref.namelist()
            for fname in extracted_files:
                if fname.endswith(('.db', '.sql')):
                    extracted_db_path = os.path.join(restore_temp_dir, fname)
                elif fname.startswith('uploads_') and fname.endswith('.zip'):
                    extracted_uploads_zip_path = os.path.join(restore_temp_dir, fname)
            zip_ref.extractall(restore_temp_dir)
            current_app.logger.info(f"Extracted contents to: {restore_temp_dir}")

        if not extracted_db_path or not os.path.exists(extracted_db_path):
             raise ValueError("ไม่พบไฟล์ฐานข้อมูล (.db หรือ .sql) หลังจากแตกไฟล์ Zip")

        # --- !! DANGER ZONE: Perform Restore !! ---
        # 1. Restore Database
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.split('sqlite:///')[-1]
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            # Make a backup of the current DB before overwriting (optional but recommended)
            current_db_backup_path = f"{db_path}.before_restore_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if os.path.exists(db_path): shutil.copy2(db_path, current_db_backup_path)
            # Replace
            shutil.move(extracted_db_path, db_path)
            current_app.logger.info(f"SQLite DB restored from {os.path.basename(extracted_db_path)} to {db_path}")
        # --- Add logic for PostgreSQL/MySQL ---
        else:
             raise NotImplementedError("ประเภทฐานข้อมูลนี้ยังไม่รองรับการกู้คืนข้อมูลอัตโนมัติ")

        # 2. Restore Uploaded Files
        if extracted_uploads_zip_path and os.path.exists(extracted_uploads_zip_path):
            if os.path.exists(uploads_folder): shutil.rmtree(uploads_folder) # Clear existing
            os.makedirs(uploads_folder, exist_ok=True)
            with zipfile.ZipFile(extracted_uploads_zip_path, 'r') as zip_ref:
                 zip_ref.extractall(uploads_folder)
            current_app.logger.info(f"Uploaded files restored from {os.path.basename(extracted_uploads_zip_path)} to {uploads_folder}")
        else:
             current_app.logger.warning("Uploads zip file not found. Skipping file restore.")

        # --- Clean up Temp Directory ---
        shutil.rmtree(restore_temp_dir)

        # --- [START LOG] Log restore success ---
        log_action("Restore Success", new_value={'filename': filename})
        try:
            db.session.commit() # Commit success log
        except Exception as log_err:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit restore success log: {log_err}")
        # --- [END LOG] ---

        flash('กู้คืนข้อมูลสำเร็จ! ระบบอาจต้องใช้เวลาสักครู่ในการโหลดข้อมูลใหม่', 'success')
        return jsonify({"status": "success", "message": "กู้คืนข้อมูลสำเร็จ"})

    # --- Catch specific Zip errors ---
    except zipfile.BadZipFile as bzfe:
        current_app.logger.error(f"Restore failed - Bad Zip File: {bzfe}", exc_info=True)
        if os.path.exists(restore_temp_dir): shutil.rmtree(restore_temp_dir)
        # --- [START LOG] Log failure ---
        log_action(f"Restore Failed: BadZipFile", new_value={'filename': filename, 'error': str(bzfe)})
        try: db.session.commit()
        except: db.session.rollback()
        # --- [END LOG] ---
        return jsonify({"status": "error", "message": "ไฟล์ ZIP ไม่ถูกต้องหรือเสียหาย"}), 400
    # --- Catch validation errors (like wrong confirmation) ---
    except ValueError as ve:
         current_app.logger.warning(f"Restore validation failed: {ve}")
         if os.path.exists(restore_temp_dir): shutil.rmtree(restore_temp_dir)
         # Log validation failure
         log_action(f"Restore Failed: Validation", new_value={'filename': filename, 'error': str(ve)})
         try: db.session.commit()
         except: db.session.rollback()
         return jsonify({"status": "error", "message": str(ve)}), 400
    # --- Catch other general errors ---
    except Exception as e:
        current_app.logger.error(f"Restore operation failed: {e}", exc_info=True)
        if os.path.exists(restore_temp_dir): shutil.rmtree(restore_temp_dir)
        # --- [START LOG] Log general failure ---
        log_action(f"Restore Failed: {type(e).__name__}", new_value={'filename': filename, 'error': str(e)})
        try: db.session.commit()
        except: db.session.rollback()
        # --- [END LOG] ---
        return jsonify({"status": "error", "message": f"การกู้คืนข้อมูลล้มเหลว: {str(e)}"}), 500
    
@bp.route('/api/schedule/copy-structure', methods=['POST'])
@login_required
# @admin_required # Add role check if needed
def copy_schedule_structure_api():
    """ API endpoint to copy schedule structure from one semester to another. """
    if not current_user.has_role('Admin'): # Example role check
         abort(403)

    data = request.get_json()
    source_semester_id = data.get('source_semester_id')
    target_semester_id = data.get('target_semester_id')

    if not source_semester_id or not target_semester_id:
        return jsonify({'status': 'error', 'message': 'Missing source or target semester ID'}), 400

    if source_semester_id == target_semester_id:
        return jsonify({'status': 'error', 'message': 'ภาคเรียนต้นทางและปลายทางต้องแตกต่างกัน'}), 400

    success, message = copy_schedule_structure(source_semester_id, target_semester_id)

    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        # Use 500 for internal server errors during copy, 400 for logical issues like 'not found'
        status_code = 500 if "ผิดพลาด" in message else 400
        return jsonify({'status': 'error', 'message': message}), status_code
# --- [END ADDITION] ---

# --- [START ADDITION] API Endpoint for Semester List Dropdown ---
@bp.route('/api/semesters-list')
@login_required
# @admin_required
def get_semesters_list_api():
      """ Returns a list of all semesters for selection dropdowns. """
      if not current_user.has_role('Admin'): # Example role check
           abort(403)
      try:
           semesters = Semester.query.join(AcademicYear).options(
               joinedload(Semester.academic_year)
           ).order_by(AcademicYear.year.desc(), Semester.term.desc()).all()

           results = [{
               'id': s.id,
               'name': f"{s.term}/{s.academic_year.year}" # Format as "YYYY/T"
           } for s in semesters]
           return jsonify(results)
      except Exception as e:
           current_app.logger.error(f"Error fetching semester list: {e}")
           return jsonify({"status": "error", "message": "ไม่สามารถดึงข้อมูลภาคเรียนได้"}), 500
# --- [END ADDITION] ---

# Route 1: List Programs
@bp.route('/programs')
@login_required
#@admin_required # <-- เปิดใช้ decorator ที่เหมาะสม
def list_programs():
    programs = Program.query.order_by(Program.name).all()
    form = FlaskForm() # For delete CSRF
    return render_template('admin/programs.html', title='จัดการสายการเรียน', programs=programs, form=form)

# Route 2: Add Program (GET)
@bp.route('/programs/add', methods=['GET'])
@login_required
#@admin_required
def add_program_get():
    form = ProgramForm()
    return render_template('admin/program_form.html', title='เพิ่มสายการเรียนใหม่', form=form)

# Route 3: Add Program (POST)
@bp.route('/programs/add', methods=['POST'])
@login_required
#@admin_required
def add_program_post():
    form = ProgramForm()
    if form.validate_on_submit():
        program = Program(name=form.name.data, description=form.description.data)
        db.session.add(program)
        try:
            db.session.commit()
            log_action("Create Program", model=Program, record_id=program.id, new_value={'name': program.name})
            db.session.commit() # Commit log
            flash('เพิ่มสายการเรียนใหม่สำเร็จ', 'success')
            return redirect(url_for('admin.list_programs'))
        except IntegrityError:
            db.session.rollback()
            flash('ชื่อสายการเรียนนี้มีอยู่แล้ว กรุณาใช้ชื่ออื่น', 'danger')
        except Exception as e:
            db.session.rollback()
            log_action(f"Create Program Failed: {type(e).__name__}", model=Program)
            try: db.session.commit()
            except: db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการบันทึก: {e}', 'danger')
            current_app.logger.error(f"Error adding program: {e}", exc_info=True)
            
    return render_template('admin/program_form.html', title='เพิ่มสายการเรียนใหม่', form=form)

# Route 4: Edit Program (GET, POST)
@bp.route('/programs/edit/<int:program_id>', methods=['GET', 'POST'])
@login_required
#@admin_required
def edit_program(program_id):
    program = Program.query.get_or_404(program_id)
    form = ProgramForm(obj=program)
    
    if form.validate_on_submit():
        old_values = {'name': program.name, 'description': program.description}
        program.name = form.name.data
        program.description = form.description.data
        try:
            db.session.commit()
            new_values = {'name': program.name, 'description': program.description}
            log_action("Update Program", model=Program, record_id=program.id, old_value=old_values, new_value=new_values)
            db.session.commit() # Commit log
            flash('แก้ไขข้อมูลสายการเรียนสำเร็จ', 'success')
            return redirect(url_for('admin.list_programs'))
        except IntegrityError:
            db.session.rollback()
            flash('ชื่อสายการเรียนนี้มีอยู่แล้ว กรุณาใช้ชื่ออื่น', 'danger')
        except Exception as e:
            db.session.rollback()
            log_action(f"Update Program Failed: {type(e).__name__}", model=Program, record_id=program.id)
            try: db.session.commit()
            except: db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการบันทึก: {e}', 'danger')
            current_app.logger.error(f"Error editing program {program_id}: {e}", exc_info=True)

    return render_template('admin/program_form.html', title='แก้ไขสายการเรียน', form=form, program=program)

# Route 5: Delete Program (POST)
@bp.route('/programs/delete/<int:program_id>', methods=['POST'])
@login_required
#@admin_required
def delete_program(program_id):
    # ใช้ FlaskForm เปล่าสำหรับ CSRF check เท่านั้น
    form = FlaskForm() 
    if not form.validate_on_submit():
         flash('CSRF Token ไม่ถูกต้อง', 'danger')
         return redirect(url_for('admin.list_programs'))
         
    program = Program.query.get_or_404(program_id)
    
    # ตรวจสอบว่ามี Classroom หรือ Curriculum ผูกอยู่หรือไม่
    if program.classrooms.first() or Curriculum.query.filter_by(program_id=program.id).first():
        flash('ไม่สามารถลบสายการเรียนนี้ได้ เนื่องจากมีห้องเรียนหรือหลักสูตรผูกอยู่', 'danger')
        return redirect(url_for('admin.list_programs'))
        
    try:
        old_values = {'name': program.name} # Log name before delete
        db.session.delete(program)
        db.session.commit()
        log_action("Delete Program", model=Program, record_id=program_id, old_value=old_values)
        db.session.commit() # Commit log
        flash('ลบสายการเรียนสำเร็จ', 'info')
    except Exception as e:
        db.session.rollback()
        log_action(f"Delete Program Failed: {type(e).__name__}", model=Program, record_id=program_id)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการลบ: {e}', 'danger')
        current_app.logger.error(f"Error deleting program {program_id}: {e}", exc_info=True)
        
    return redirect(url_for('admin.list_programs'))