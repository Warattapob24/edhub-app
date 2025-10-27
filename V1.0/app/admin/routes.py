# app/admin/routes.py (ฉบับสมบูรณ์)

from flask import render_template, flash, redirect, url_for, request, session
from flask_login import login_required
from app import db
from app.admin import bp
from app.decorators import admin_required
from app.models import (Role, User, Subject, Course, ActivityLog, Setting, 
                        Student, ClassGroup, GradeLevel, EvaluationTopic, SchoolPeriod, 
                        TimetableBlock, Curriculum, Room, CourseAssignment, SchedulingRule,
                        TimetableSlot)
from app.forms import (RoleForm, EditRoleForm, CreateUserForm, EditUserForm, SubjectForm, 
                       SchoolSettingsForm, ImportStudentsForm, GradeLevelForm, ClassGroupForm, 
                       StudentForm, EvaluationTopicForm, SchoolPeriodForm, TimetableBlockForm, 
                       CurriculumForm, RoomForm, RestoreForm)
import pandas as pd
from datetime import datetime
import json, io, zipfile, csv
from app.services.scheduler import generate_timetable
from flask import send_file

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def school_settings():
    form = SchoolSettingsForm()
    if form.validate_on_submit():
        # บันทึกข้อมูลแบบ Key-Value
        school_name = Setting.query.filter_by(key='school_name').first() or Setting(key='school_name')
        school_name.value = form.school_name.data
        db.session.add(school_name)
        
        school_director = Setting.query.filter_by(key='school_director').first() or Setting(key='school_director')
        school_director.value = form.school_director.data
        db.session.add(school_director)
        
        db.session.commit()
        flash('บันทึกข้อมูลโรงเรียนเรียบร้อยแล้ว')
        return redirect(url_for('admin.school_settings'))

    # ดึงข้อมูลเดิมมาแสดงในฟอร์ม
    school_name = Setting.query.filter_by(key='school_name').first()
    school_director = Setting.query.filter_by(key='school_director').first()
    if school_name: form.school_name.data = school_name.value
    if school_director: form.school_director.data = school_director.value
        
    return render_template('admin/school_settings.html', title='ตั้งค่าข้อมูลโรงเรียน', form=form)

@bp.route('/roles', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_roles():
    form = RoleForm()
    if form.validate_on_submit():
        new_role = Role(key=form.key.data.lower(), label=form.label.data)
        db.session.add(new_role)
        db.session.commit()
        flash('สร้างบทบาทใหม่เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_roles'))
    roles = Role.query.order_by(Role.id).all()
    return render_template('admin/manage_roles.html', title='จัดการบทบาท', roles=roles, form=form)

@bp.route('/roles/add', methods=['POST'])
@login_required
@admin_required
def add_role():
    form = RoleForm()
    if form.validate_on_submit():
        new_role = Role(key=form.key.data, label=form.label.data)
        db.session.add(new_role)
        db.session.commit()
        flash('สร้างบทบาทใหม่เรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_roles'))

@bp.route('/roles/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_role(id):
    role = Role.query.get_or_404(id)
    form = EditRoleForm(obj=role)
    if form.validate_on_submit():
        role.label = form.label.data
        db.session.commit()
        flash('บันทึกการเปลี่ยนแปลงเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_roles'))
    return render_template('admin/edit_role.html', title='แก้ไขบทบาท', form=form, role=role)

@bp.route('/roles/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_role(id):
    role_to_delete = Role.query.get_or_404(id)
    if role_to_delete.users.first():
        flash('ไม่สามารถลบได้ เนื่องจากมีผู้ใช้งานในบทบาทนี้อยู่', 'danger')
        return redirect(url_for('admin.manage_roles'))
    db.session.delete(role_to_delete)
    db.session.commit()
    flash('ลบบทบาทเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_roles'))

@bp.route('/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/manage_users.html', title='จัดการผู้ใช้งาน', users=users)

@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    form = CreateUserForm()
    form.roles.choices = [(r.id, r.label) for r in Role.query.order_by('label')]
    depts = db.session.query(Subject.department).distinct().order_by(Subject.department).all()
    form.department.choices = [('', '- ไม่ระบุ -')] + [(d.department, d.department) for d in depts]

    if form.validate_on_submit():
        new_user = User(username=form.username.data, 
                        full_name=form.full_name.data,
                        department=form.department.data)
        new_user.set_password(form.password.data)
        
        # --- Logic ใหม่: เพิ่ม Role จาก List ---
        selected_roles = Role.query.filter(Role.id.in_(form.roles.data)).all()
        new_user.roles.extend(selected_roles)

        db.session.add(new_user)
        db.session.commit()
        flash(f'สร้างผู้ใช้ "{new_user.username}" เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_users'))
        
    return render_template('admin/create_user.html', title='เพิ่มผู้ใช้ใหม่', form=form)

@bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)
    form.roles.choices = [(r.id, r.label) for r in Role.query.order_by('label')]
    depts = db.session.query(Subject.department).distinct().order_by(Subject.department).all()
    form.department.choices = [('', '- ไม่ระบุ -')] + [(d.department, d.department) for d in depts]

    if request.method == 'GET':
        form.roles.data = [role.id for role in user.roles] # <-- แสดง role เดิมที่เคยเลือกไว้
        form.status.data = user.status

    if form.validate_on_submit():
        user.username = form.username.data
        user.full_name = form.full_name.data
        user.department = form.department.data
        user.status = form.status.data
        user.max_periods_per_day = form.max_periods_per_day.data
        user.max_periods_per_week = form.max_periods_per_week.data

    if form.password.data:
        user.set_password(form.password.data)
            
        # --- Logic ใหม่: อัปเดต Role จาก List ---
        user.roles.clear()
        selected_roles = Role.query.filter(Role.id.in_(form.roles.data)).all()
        user.roles.extend(selected_roles)

        db.session.commit()
        flash('อัปเดตข้อมูลผู้ใช้เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_users'))
    
    elif request.method == 'POST':
        # --- ✨ คาถาประกาศคำสาป! ✨ ---
        # (ส่วนนี้จะทำงานเมื่อกด POST แต่การตรวจสอบ 'ไม่ผ่าน')
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"ข้อมูลผิดพลาดในช่อง '{getattr(form, field).label.text}': {error}", 'warning')

    if request.method == 'GET':
        form.roles.data = [role.id for role in user.roles]
        form.department.data = user.department
        form.status.data = user.status
        
    return render_template('admin/edit_user.html', title='แก้ไขผู้ใช้งาน', form=form, user=user)

@bp.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user_to_delete = User.query.get_or_404(id)
    # (ในอนาคต อาจต้องเพิ่มการตรวจสอบว่าผู้ใช้คนนี้มีความสัมพันธ์กับข้อมูลอื่นหรือไม่)
    db.session.delete(user_to_delete)
    db.session.commit()
    flash('ลบผู้ใช้งานเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_users'))

@bp.route('/subjects')
@login_required
@admin_required
def manage_subjects():
    subjects = Subject.query.order_by(Subject.subject_code).all()
    return render_template('admin/manage_subjects.html', title='จัดการคลังรายวิชา', subjects=subjects)

@bp.route('/subjects/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_subject():
    form = SubjectForm()
    if form.validate_on_submit():
        new_subject = Subject(subject_code=form.subject_code.data, name=form.name.data, department=form.department.data, default_credits=form.default_credits.data)
        db.session.add(new_subject)
        db.session.commit()
        flash('เพิ่มรายวิชาใหม่ในคลังเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_subjects'))
    return render_template('admin/subject_form.html', title='เพิ่มวิชาใหม่ในคลัง', form=form)

@bp.route('/subjects/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    form = SubjectForm(obj=subject)
    if form.validate_on_submit():
        subject.subject_code = form.subject_code.data
        subject.name = form.name.data
        subject.department = form.department.data
        subject.default_credits = form.default_credits.data
        subject.required_room_type = form.required_room_type.data
        db.session.commit()
        flash('อัปเดตข้อมูลรายวิชาเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_subjects'))
    return render_template('admin/subject_form.html', title='แก้ไขรายวิชา', form=form)

@bp.route('/subjects/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    if subject.course_offerings.first():
        flash('ไม่สามารถลบได้ เนื่องจากมีคลาสเรียนที่ใช้รายวิชานี้อยู่', 'error')
        return redirect(url_for('admin.manage_subjects'))
    db.session.delete(subject)
    db.session.commit()
    flash('ลบรายวิชาออกจากคลังเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_subjects'))

@bp.route('/class_groups', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_class_groups():
    grade_form = GradeLevelForm()
    class_form = ClassGroupForm()
    
    # --- แก้ไข Query ตรงนี้ ---
    teachers = User.query.filter(User.roles.any(key='teacher')).order_by(User.full_name).all()
    class_form.advisors.choices = [(t.id, t.full_name) for t in teachers]

    if grade_form.validate_on_submit() and 'submit_grade' in request.form:
        new_grade = GradeLevel(name=grade_form.name.data)
        db.session.add(new_grade)
        db.session.commit()
        flash(f'สร้างสายชั้น "{new_grade.name}" เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_class_groups'))

    grade_levels = GradeLevel.query.order_by(GradeLevel.id).all()
    return render_template('admin/manage_class_groups.html', 
                           title='จัดการสายชั้นและห้องเรียน',
                           grade_levels=grade_levels,
                           grade_form=grade_form,
                           class_form=class_form)

@bp.route('/grade-level/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_grade_level(id):
    grade = GradeLevel.query.get_or_404(id)
    form = GradeLevelForm(obj=grade)
    if form.validate_on_submit():
        grade.name = form.name.data
        db.session.commit()
        flash('อัปเดตชื่อสายชั้นเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_class_groups'))
    return render_template('admin/edit_grade_level.html', title='แก้ไขสายชั้น', form=form)

@bp.route('/grade-level/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_grade_level(id):
    grade = GradeLevel.query.get_or_404(id)
    if grade.class_groups.first():
        flash('ไม่สามารถลบได้ เนื่องจากมีห้องเรียนอยู่ในสายชั้นนี้', 'danger')
        return redirect(url_for('admin.manage_class_groups'))
    db.session.delete(grade)
    db.session.commit()
    flash('ลบสายชั้นเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_class_groups'))

@bp.route('/class_groups/add/<int:grade_id>', methods=['POST'])
@login_required
@admin_required
def add_class_group(grade_id):
    form = ClassGroupForm()
    teachers = User.query.filter(User.roles.any(key='teacher')).order_by(User.full_name).all()
    form.advisors.choices = [(t.id, t.full_name) for t in teachers]

    if form.validate_on_submit():
        new_class_group = ClassGroup(
            room_number=form.room_number.data,
            academic_year=form.academic_year.data,
            grade_level_id=grade_id
        )
        
        advisors_list = User.query.filter(User.id.in_(form.advisors.data)).all()
        new_class_group.advisors.extend(advisors_list)
        
        db.session.add(new_class_group)
        db.session.commit()
        flash('เพิ่มห้องเรียนใหม่เรียบร้อยแล้ว')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"ข้อมูลผิดพลาดในช่อง '{getattr(form, field).label.text}': {error}", 'danger')

    return redirect(url_for('admin.manage_class_groups'))

@bp.route('/class_group/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_class_group(id):
    class_group = ClassGroup.query.get_or_404(id)
    form = ClassGroupForm(obj=class_group)
    
    # --- แก้ไข Query ตรงนี้ ---
    teachers = User.query.filter(User.roles.any(key='teacher')).order_by(User.full_name).all()
    form.advisors.choices = [(t.id, t.full_name) for t in teachers]

    if request.method == 'GET':
        form.advisors.data = [a.id for a in class_group.advisors]

    if form.validate_on_submit():
        class_group.room_number = form.room_number.data
        class_group.academic_year = form.academic_year.data
        
        # Update advisors
        class_group.advisors.clear()
        advisors_list = User.query.filter(User.id.in_(form.advisors.data)).all()
        class_group.advisors.extend(advisors_list)

        db.session.commit()
        flash('อัปเดตข้อมูลห้องเรียนเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_class_groups'))
        
    return render_template('admin/edit_class_group.html', title='แก้ไขห้องเรียน', form=form, class_group=class_group)

@bp.route('/class_group/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_class_group(id):
    class_group = ClassGroup.query.get_or_404(id)
    if class_group.students.first():
        flash('ไม่สามารถลบได้ เนื่องจากมีนักเรียนอยู่ในห้องเรียนนี้', 'danger')
        return redirect(url_for('admin.manage_class_groups'))
    db.session.delete(class_group)
    db.session.commit()
    flash('ลบห้องเรียนเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_class_groups'))

@bp.route('/approvals')
@login_required
@admin_required
def manage_approvals():
    pending_courses = Course.query.filter_by(status='pending_approval').order_by(Course.academic_year.desc()).all()
    return render_template('admin/manage_approvals.html', title='อนุมัติผลการเรียน', courses=pending_courses)

@bp.route('/approve_course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def approve_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.status = 'approved'
    db.session.commit()
    log_activity('COURSE_APPROVED', f'Admin approved course: {course.subject.name} (ID: {course.id})')
    flash(f'อนุมัติผลการเรียนวิชา {course.subject.name} เรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_approvals'))

@bp.route('/reject_course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def reject_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.status = 'rejected' # หรือ 'draft' ก็ได้ ถ้าต้องการให้ครูกลับไปแก้ไขได้เลย
    db.session.commit()
    flash(f'ส่งผลการเรียนวิชา {course.subject.name} กลับไปให้ครูแก้ไข')
    return redirect(url_for('admin.manage_approvals'))

@bp.route('/logs')
@login_required
@admin_required
def view_logs():
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    return render_template('admin/view_logs.html', title='บันทึกกิจกรรม', logs=logs)

@bp.route('/students')
@login_required
@admin_required
def manage_students():
    # รับค่า filter จาก URL
    class_group_id = request.args.get('class_group_id', type=int)
    
    query = Student.query
    if class_group_id:
        query = query.filter(Student.class_group_id == class_group_id)

    students = query.join(ClassGroup).join(GradeLevel).order_by(
        GradeLevel.name, ClassGroup.room_number, Student.class_number
    ).all()
    
    # ส่งข้อมูลห้องเรียนทั้งหมดไปให้ template เพื่อสร้าง filter
    all_class_groups = ClassGroup.query.join(GradeLevel).order_by(GradeLevel.name, ClassGroup.room_number).all()
    
    return render_template('admin/manage_students.html', 
                           title='จัดการข้อมูลนักเรียน', 
                           students=students,
                           all_class_groups=all_class_groups,
                           selected_class_group_id=class_group_id)

@bp.route('/students/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_students():
    form = ImportStudentsForm()
    if form.validate_on_submit():
        try:
            file = form.upload_file.data
            filename = file.filename
            
            # ตรวจสอบนามสกุลไฟล์แล้วใช้ pandas อ่านให้เหมาะสม
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                flash('ไฟล์ไม่รองรับ', 'danger')
                return redirect(url_for('admin.import_students'))

            imported_count = 0
            skipped_count = 0
            
            required_columns = ['student_id', 'prefix', 'first_name', 'last_name', 'class_number', 'grade_level_name', 'room_number', 'academic_year']
            if not all(col in df.columns for col in required_columns):
                flash(f'ไฟล์ขาดคอลัมน์ที่จำเป็น: {required_columns}', 'danger')
                return redirect(url_for('admin.import_students'))

            for index, row in df.iterrows():
                student_id = str(row['student_id'])
                # ตรวจสอบว่ามีนักเรียนคนนี้ในระบบหรือยัง
                exists = Student.query.filter_by(student_id=student_id).first()
                if not exists:
                    # ค้นหาห้องเรียนจากข้อมูลในไฟล์
                    class_group = ClassGroup.query.join(GradeLevel).filter(
                        GradeLevel.name == row['grade_level_name'],
                        ClassGroup.room_number == str(row['room_number']),
                        ClassGroup.academic_year == int(row['academic_year'])
                    ).first()
                    
                    if class_group:
                        student = Student(
                            student_id=student_id,
                            prefix=row['prefix'],
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            class_number=int(row['class_number']),
                            class_group_id=class_group.id,
                            status='กำลังศึกษา'
                        )
                        db.session.add(student)
                        imported_count += 1
                    else:
                        skipped_count += 1 # ข้ามไปเพราะหาห้องเรียนไม่เจอ
                else:
                    skipped_count += 1 # ข้ามไปเพราะมีรหัสนักเรียนนี้แล้ว

            db.session.commit()
            flash(f'นำเข้าข้อมูลนักเรียนใหม่ {imported_count} คนเรียบร้อยแล้ว (ข้าม {skipped_count} รายการที่มีอยู่แล้ว/หาห้องไม่เจอ)', 'success')
            return redirect(url_for('admin.manage_students'))
        except Exception as e:
            db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการประมวลผลไฟล์: {e}', 'danger')
            return redirect(url_for('admin.import_students'))
            
    return render_template('admin/import_students.html', title='นำเข้าข้อมูลนักเรียน', form=form)

@bp.route('/student/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(id):
    student = Student.query.get_or_404(id)
    form = StudentForm(obj=student)
    form.class_group.choices = [
        (c.id, f"{c.grade_level.name} / ห้อง {c.room_number} ({c.academic_year})") 
        for c in ClassGroup.query.join(GradeLevel).order_by(GradeLevel.id, ClassGroup.room_number)
    ]
    if request.method == 'GET':
        form.class_group.data = student.class_group_id

    if form.validate_on_submit():
        student.student_id = form.student_id.data
        student.prefix = form.prefix.data
        student.first_name = form.first_name.data
        student.last_name = form.last_name.data
        student.class_number = form.class_number.data
        student.class_group_id = form.class_group.data
        student.status = form.status.data
        db.session.commit()
        flash('อัปเดตข้อมูลนักเรียนเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_students'))
        
    return render_template('admin/edit_student.html', title='แก้ไขข้อมูลนักเรียน', form=form, student=student)

@bp.route('/student/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    db.session.delete(student)
    db.session.commit()
    flash('ลบข้อมูลนักเรียนเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_students'))

@bp.route('/settings/grading', methods=['GET', 'POST'])
@login_required
@admin_required
def grading_settings():
    if request.method == 'POST':
        grades = request.form.getlist('grade')
        min_scores = request.form.getlist('min_score')
        
        # สร้าง list ของ dicts จากข้อมูลฟอร์ม
        grading_scale_data = [
            {'grade': g, 'min_score': int(s)} 
            for g, s in zip(grades, min_scores) if g and s
        ]
        # เรียงลำดับจากคะแนนสูงสุดไปต่ำสุด
        grading_scale_data.sort(key=lambda x: x['min_score'], reverse=True)
        
        # บันทึกเป็น JSON string
        scale_setting = Setting.query.filter_by(key='grading_scale').first() or Setting(key='grading_scale')
        scale_setting.value = json.dumps(grading_scale_data)
        db.session.add(scale_setting)
        db.session.commit()
        
        flash('บันทึกเกณฑ์การตัดเกรดเรียบร้อยแล้ว')
        return redirect(url_for('admin.grading_settings'))

    # ดึงข้อมูลเดิมมาแสดง
    scale_setting = Setting.query.filter_by(key='grading_scale').first()
    grading_scale = json.loads(scale_setting.value) if scale_setting and scale_setting.value else []
    
    return render_template('admin/grading_settings.html', title='ตั้งค่าเกณฑ์เกรด', grading_scale=grading_scale)

@bp.route('/evaluations', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_evaluations():
    form = EvaluationTopicForm()
    # Logic สำหรับเพิ่ม "หัวข้อหลัก"
    if form.validate_on_submit() and 'submit_main' in request.form:
        topic = EvaluationTopic(
            assessment_type=form.assessment_type.data,
            name=form.name.data,
            display_order=form.display_order.data
        )
        db.session.add(topic)
        db.session.commit()
        flash('เพิ่มหัวข้อหลักเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_evaluations'))
    
    # ดึงข้อมูลมาจัดกลุ่ม
    topics_by_type = {
        'คุณลักษณะอันพึงประสงค์': EvaluationTopic.query.filter_by(assessment_type='คุณลักษณะอันพึงประสงค์', parent_id=None).order_by('display_order').all(),
        'การอ่าน คิดวิเคราะห์ และเขียน': EvaluationTopic.query.filter_by(assessment_type='การอ่าน คิดวิเคราะห์ และเขียน', parent_id=None).order_by('display_order').all(),
        'สมรรถนะ': EvaluationTopic.query.filter_by(assessment_type='สมรรถนะ', parent_id=None).order_by('display_order').all()
    }
    return render_template('admin/manage_evaluations.html', title='ตั้งค่าหัวข้อการประเมิน', form=form, topics_by_type=topics_by_type)

@bp.route('/evaluations/add-subtopic/<int:parent_id>', methods=['POST'])
@login_required
@admin_required
def add_subtopic(parent_id):
    parent_topic = EvaluationTopic.query.get_or_404(parent_id)
    # เราจะรับค่าจากฟอร์มโดยตรง ไม่ต้องสร้าง instance ของฟอร์ม
    name = request.form.get('name')
    display_order = request.form.get('display_order', type=int)

    if name and display_order is not None:
        sub_topic = EvaluationTopic(
            assessment_type=parent_topic.assessment_type,
            name=name,
            display_order=display_order,
            parent_id=parent_id
        )
        db.session.add(sub_topic)
        db.session.commit()
        flash('เพิ่มตัวชี้วัดย่อยเรียบร้อยแล้ว')
    else:
        flash('ข้อมูลตัวชี้วัดย่อยไม่ถูกต้อง', 'danger')
    return redirect(url_for('admin.manage_evaluations'))

@bp.route('/evaluations/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_evaluation_topic(id):
    topic = EvaluationTopic.query.get_or_404(id)
    # ลบ sub-topics ทั้งหมดก่อน (ถ้ามี)
    for sub in topic.sub_topics:
        db.session.delete(sub)
    db.session.delete(topic)
    db.session.commit()
    flash('ลบหัวข้อเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_evaluations'))

@bp.route('/students/promote', methods=['GET'])
@login_required
@admin_required
def promote_students_page():
    # ดึงข้อมูลห้องเรียนทั้งหมดที่มีนักเรียนอยู่ มาแสดงเพื่อยืนยัน
    # เราจะสมมติว่าเป็นการเลื่อนชั้นจากปีการศึกษาล่าสุดที่มีข้อมูล
    latest_year = db.session.query(db.func.max(ClassGroup.academic_year)).scalar()
    class_groups = ClassGroup.query.filter_by(academic_year=latest_year).order_by(ClassGroup.id).all()
    
    return render_template('admin/promote_students.html',
                           title='ยืนยันการเลื่อนชั้น',
                           class_groups=class_groups,
                           latest_year=latest_year)

@bp.route('/students/promote/execute', methods=['POST'])
@login_required
@admin_required
def execute_promotion():
    from_year = request.form.get('from_year', type=int)
    if not from_year:
        flash('ไม่พบปีการศึกษาที่จะเลื่อนชั้น', 'danger')
        return redirect(url_for('admin.promote_students_page'))

    to_year = from_year + 1
    promoted_count = 0
    graduated_count = 0

    # ดึงนักเรียนทั้งหมดจากปีการศึกษาล่าสุด
    students_to_promote = Student.query.join(ClassGroup).filter(ClassGroup.academic_year == from_year, Student.status == 'กำลังศึกษา').all()

    for student in students_to_promote:
        current_class_group = student.class_group
        current_grade = current_class_group.grade_level
        
        # สมมติว่าชื่อสายชั้นมี "มัธยมศึกษาปีที่ " นำหน้า
        try:
            current_grade_num = int(current_grade.name.split(' ')[-1])
        except (ValueError, IndexError):
            continue # ข้ามถ้าชื่อสายชั้นไม่เป็นไปตามรูปแบบ

        # นักเรียนชั้นสูงสุด -> สำเร็จการศึกษา
        if current_grade_num == 6:
            student.status = 'สำเร็จการศึกษา'
            graduated_count += 1
        else:
            # หาสายชั้นใหม่
            new_grade_num = current_grade_num + 1
            new_grade_name = f"มัธยมศึกษาปีที่ {new_grade_num}"
            next_grade = GradeLevel.query.filter_by(name=new_grade_name).first()

            if next_grade:
                # หาห้องเรียนใหม่ในปีการศึกษาถัดไป (สมมติว่าใช้ room_number เดิม)
                next_class_group = ClassGroup.query.filter_by(
                    grade_level_id=next_grade.id,
                    room_number=current_class_group.room_number,
                    academic_year=to_year
                ).first()
                
                # ถ้ายังไม่มีห้องเรียนใหม่ ให้สร้างขึ้นมา
                if not next_class_group:
                    next_class_group = ClassGroup(
                        grade_level_id=next_grade.id,
                        room_number=current_class_group.room_number,
                        academic_year=to_year
                    )
                    db.session.add(next_class_group)
                    db.session.flush() # เพื่อให้ next_class_group.id พร้อมใช้งาน
                
                student.class_group_id = next_class_group.id
                promoted_count += 1

    db.session.commit()
    flash(f'เลื่อนชั้นนักเรียน {promoted_count} คน และสำเร็จการศึกษา {graduated_count} คน ไปยังปีการศึกษา {to_year} เรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.manage_students'))

@bp.route('/periods', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_school_periods():
    form = SchoolPeriodForm()
    if form.validate_on_submit():
        new_period = SchoolPeriod(
            period_number=form.period_number.data,
            name=form.name.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data
        )
        db.session.add(new_period)
        db.session.commit()
        flash('สร้างคาบเรียนมาตรฐานใหม่เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_school_periods'))
    
    periods = SchoolPeriod.query.order_by(SchoolPeriod.period_number).all()
    return render_template('admin/manage_school_periods.html', 
                           title='จัดการคาบเรียนมาตรฐาน', 
                           form=form, 
                           periods=periods)

@bp.route('/periods/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_school_period(id):
    period = SchoolPeriod.query.get_or_404(id)
    form = SchoolPeriodForm(obj=period)
    if form.validate_on_submit():
        period.period_number = form.period_number.data
        period.name = form.name.data
        period.start_time = form.start_time.data
        period.end_time = form.end_time.data
        db.session.commit()
        flash('อัปเดตข้อมูลคาบเรียนเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_school_periods'))
    return render_template('admin/edit_school_period.html', title='แก้ไขคาบเรียน', form=form)

@bp.route('/periods/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_school_period(id):
    period = SchoolPeriod.query.get_or_404(id)
    # อาจเพิ่มเงื่อนไขตรวจสอบว่าคาบเรียนนี้ถูกใช้งานอยู่หรือไม่ในอนาคต
    db.session.delete(period)
    db.session.commit()
    flash('ลบคาบเรียนเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_school_periods'))

@bp.route('/time-blocks', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_time_blocks():
    form = TimetableBlockForm()
    # ดึงข้อมูลสายชั้นทั้งหมดมาใส่ใน Choice ของฟอร์ม
    form.applies_to_grade_levels.choices = [
        (g.id, g.name) for g in GradeLevel.query.order_by('id').all()
    ]
    # --- ส่วนที่เพิ่ม: ดึงข้อมูล Role มาใส่ในฟอร์ม ---
    form.applies_to_roles.choices = [
        (r.id, r.label) for r in Role.query.order_by('id').all()
    ]

    if form.validate_on_submit():
        new_block = TimetableBlock(
            name=form.name.data,
            days_of_week=[int(d) for d in form.days_of_week.data],
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            academic_year=form.academic_year.data
        )
        
        # บันทึกความสัมพันธ์กับสายชั้น (ถ้ามี)
        selected_grades = GradeLevel.query.filter(GradeLevel.id.in_(form.applies_to_grade_levels.data)).all()
        new_block.applies_to_grade_levels.extend(selected_grades)

        # --- ส่วนที่เพิ่ม: บันทึกความสัมพันธ์กับ Role (ถ้ามี) ---
        selected_roles = Role.query.filter(Role.id.in_(form.applies_to_roles.data)).all()
        new_block.applies_to_roles.extend(selected_roles)

        db.session.add(new_block)
        db.session.commit()
        flash('สร้างกฎการบล็อกเวลาใหม่เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_time_blocks'))

    # ดึงข้อมูลทั้งหมดมาแสดง (ส่วนนี้ไม่ต้องแก้ไข)
    blocks = TimetableBlock.query.order_by('academic_year', 'start_time').all()
    return render_template('admin/manage_time_blocks.html',
                           title='จัดการกฎการบล็อกเวลา',
                           form=form,
                           blocks=blocks)

@bp.route('/time-blocks/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_time_block(id):
    block = TimetableBlock.query.get_or_404(id)
    db.session.delete(block)
    db.session.commit()
    flash('ลบกฎการบล็อกเวลาเรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_time_blocks'))

@bp.route('/curriculum', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_curriculum():
    form = CurriculumForm()
    form.grade_level.choices = [(g.id, g.name) for g in GradeLevel.query.order_by('id').all()]
    form.subjects.choices = [(s.id, f"{s.subject_code} - {s.name}") for s in Subject.query.order_by('subject_code').all()]

    if form.validate_on_submit():
        grade_id = form.grade_level.data
        year = form.academic_year.data
        sem = form.semester.data
        
        for subject_id in form.subjects.data:
            # ตรวจสอบว่ามีข้อมูลซ้ำหรือไม่ ก่อนเพิ่มเข้าไป
            exists = Curriculum.query.filter_by(
                academic_year=year,
                semester=sem,
                grade_level_id=grade_id,
                subject_id=subject_id
            ).first()
            if not exists:
                entry = Curriculum(
                    academic_year=year,
                    semester=sem,
                    grade_level_id=grade_id,
                    subject_id=subject_id
                )
                db.session.add(entry)
        
        db.session.commit()
        flash('บันทึกข้อมูลหลักสูตรเรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_curriculum'))

    # จัดกลุ่มข้อมูลเพื่อแสดงผล
    curriculum_data = {}
    entries = Curriculum.query.order_by(Curriculum.academic_year.desc(), Curriculum.semester, Curriculum.grade_level_id).all()
    for entry in entries:
        year_key = (entry.academic_year, entry.semester)
        if year_key not in curriculum_data:
            curriculum_data[year_key] = {}
        if entry.grade_level not in curriculum_data[year_key]:
            curriculum_data[year_key][entry.grade_level] = []
        curriculum_data[year_key][entry.grade_level].append(entry.subject)

        # เราจะส่งข้อมูลดิบทั้งหมดไปแทนการจัดกลุ่ม
    entries = Curriculum.query.order_by(
        Curriculum.academic_year.desc(), 
        Curriculum.semester, 
        Curriculum.grade_level_id, 
        Subject.name
    ).join(Subject).all()

    return render_template('admin/manage_curriculum.html',
                           title='จัดการหลักสูตรแกนกลาง',
                           form=form,
                           curriculum_data=curriculum_data,
                           entries=entries)

@bp.route('/curriculum/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_curriculum_entry(id):
    entry = Curriculum.query.get_or_404(id)
    # (ในอนาคต อาจต้องเพิ่มเงื่อนไขตรวจสอบว่าวิชานี้ถูกสร้างเป็นคลาสเรียนไปแล้วหรือยัง)
    db.session.delete(entry)
    db.session.commit()
    flash('ลบรายวิชาออกจากหลักสูตรแล้ว')
    return redirect(url_for('admin.manage_curriculum'))

@bp.route('/scheduler')
@login_required
@admin_required
def scheduler_dashboard():
    now = datetime.now()
    conflicts = session.pop('scheduler_conflicts', None)
    return render_template('admin/scheduler.html',
                           title='เครื่องมือจัดตารางสอน',
                           now=now,
                           conflicts=conflicts)

@bp.route('/scheduler/run', methods=['POST'])
@login_required
@admin_required
def run_scheduler():
    year = request.form.get('academic_year', type=int)
    semester = request.form.get('semester', type=int)

    if not (year and semester):
        flash('กรุณาระบุปีการศึกษาและภาคเรียน', 'danger')
        return redirect(url_for('admin.scheduler_dashboard'))

    conflicts = generate_timetable(year, semester)

    if conflicts:
        conflicts_data = [
            {
                'subject_name': task['course'].subject.name,
                'class_group_name': f"{task['class_group'].grade_level.name}/{task['class_group'].room_number}"
            }
            for task in conflicts
        ]
        session['scheduler_conflicts'] = conflicts_data
        flash(f'จัดตารางสอนเสร็จสิ้น แต่พบข้อขัดแย้ง {len(conflicts_data)} รายการ', 'warning')
    else:
        session['scheduler_conflicts'] = []
        flash('จัดตารางสอนอัตโนมัติสำเร็จ! ไม่พบข้อขัดแย้งใดๆ', 'success')

    return redirect(url_for('admin.scheduler_dashboard'))

@bp.route('/rooms', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_rooms():
    form = RoomForm()
    if form.validate_on_submit():
        new_room = Room(name=form.name.data, room_type=form.room_type.data)
        db.session.add(new_room)
        db.session.commit()
        flash('เพิ่มสถานที่ใหม่เรียบร้อยแล้ว')
        return redirect(url_for('admin.manage_rooms'))

    rooms = Room.query.order_by('name').all()
    return render_template('admin/manage_rooms.html',
                           title='จัดการสถานที่เรียน',
                           form=form,
                           rooms=rooms)

@bp.route('/rooms/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_room(id):
    room = Room.query.get_or_404(id)
    # (ในอนาคต อาจต้องเพิ่มการตรวจสอบว่าห้องถูกใช้งานอยู่หรือไม่)
    db.session.delete(room)
    db.session.commit()
    flash('ลบสถานที่เรียบร้อยแล้ว')
    return redirect(url_for('admin.manage_rooms'))

@bp.route('/backup')
@login_required
@admin_required
def backup_restore_page():
    """แสดงหน้าสำหรับ Backup และ Restore"""
    restore_form = RestoreForm() # <-- สร้างฟอร์ม
    return render_template('admin/backup_restore.html', 
                           title='สำรองและกู้คืนข้อมูล',
                           restore_form=restore_form)

@bp.route('/backup/execute', methods=['POST'])
@login_required
@admin_required
def execute_backup():
    """คาถาผนึกความทรงจำ (Backup)"""
    memory_file = io.BytesIO()

    # --- รายชื่อคัมภีร์ที่ต้องการผนึก ---
    models_to_backup = [
        Role, User, GradeLevel, ClassGroup, Room, Subject, Curriculum, 
        CourseAssignment, EvaluationTopic, Course, SchedulingRule
        # (เพิ่ม Model อื่นๆ ที่สำคัญได้ตามต้องการ)
    ]

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for model_class in models_to_backup:
            model_name = model_class.__tablename__
            records = model_class.query.all()
            if not records: continue

            # สร้าง CSV ใน memory
            output = io.StringIO()
            writer = csv.writer(output)

            # เขียน Header
            writer.writerow(records[0].__table__.columns.keys())
            # เขียนข้อมูล
            for record in records:
                writer.writerow([getattr(record, c) for c in records[0].__table__.columns.keys()])

            # เพิ่มไฟล์ CSV เข้าไปใน Zip
            zf.writestr(f"{model_name}.csv", output.getvalue())

    memory_file.seek(0)

    return send_file(
        memory_file,
        download_name=f'backup_{datetime.now().strftime("%Y-%m-%d")}.zip',
        as_attachment=True
    )

@bp.route('/restore/execute', methods=['POST'])
@login_required
@admin_required
def execute_restore():
    form = RestoreForm()
    if form.validate_on_submit():
        file = form.backup_file.data
        memory_file = io.BytesIO(file.read())

        try:
            with db.session.no_autoflush:
                # --- ลำดับการลบ (จากลูกไปหาพ่อ) ---
                delete_order = [SchedulingRule, CourseAssignment, Curriculum, Course, Subject, 
                                Room, ClassGroup, GradeLevel, User, Role, EvaluationTopic]
                print("--- Starting data cleanse ---")
                for model in delete_order:
                    model.query.delete()
                    print(f"Cleared {model.__tablename__}")

                db.session.commit()

                # --- ลำดับการเพิ่ม (จากพ่อไปหาลูก) ---
                import_order = [
                    ('role.csv', Role), ('user.csv', User), ('grade_level.csv', GradeLevel),
                    ('class_group.csv', ClassGroup), ('room.csv', Room), ('subject.csv', Subject),
                    ('curriculum.csv', Curriculum), ('course_assignment.csv', CourseAssignment),
                    ('evaluation_topic.csv', EvaluationTopic), ('course.csv', Course),
                    ('scheduling_rule.csv', SchedulingRule)
                ]

                with zipfile.ZipFile(memory_file, 'r') as zf:
                    for filename, model_class in import_order:
                        if filename in zf.namelist():
                            print(f"Importing {filename}...")
                            df = pd.read_csv(zf.open(filename))
                            # แปลงค่าว่างจาก pandas (nan) ให้เป็น None
                            df = df.where(pd.notnull(df), None)

                            for row in df.to_dict(orient='records'):
                                row.pop('id', None)
                                record = model_class(**row)
                                db.session.add(record)
                            db.session.commit()

            flash('กู้คืนข้อมูลสำเร็จ!', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'เกิดข้อผิดพลาดร้ายแรงระหว่างการกู้คืน: {e}', 'danger')

        return redirect(url_for('admin.backup_restore_page'))

    # ถ้าฟอร์มไม่ผ่าน validation
    flash('ไฟล์ที่อัปโหลดไม่ถูกต้อง', 'danger')
    return redirect(url_for('admin.backup_restore_page'))