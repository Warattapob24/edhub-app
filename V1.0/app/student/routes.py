from flask import render_template, flash, redirect, url_for, request, session, abort, sessions
from flask_login import login_user, logout_user, current_user, login_required
from app.student import bp
from app.forms import StudentLoginForm
from app.models import Student, Score, CourseComponent, Setting
import json

# เพิ่มฟังก์ชันคำนวณเกรด (เหมือนกับใน course/routes.py)
def calculate_grade(total_score, max_total_score):
    if max_total_score == 0: return "N/A"
    scale_setting = Setting.query.filter_by(key='grading_scale').first()
    if not (scale_setting and scale_setting.value): return "ไม่มีเกณฑ์"
    grading_scale = json.loads(scale_setting.value)
    percentage = (total_score / max_total_score) * 100
    for rule in grading_scale:
        if percentage >= rule['min_score']:
            return rule['grade']
    return "0"

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # --- ส่วนที่แก้ไข: ทำให้การ Logout สมบูรณ์ขึ้น ---
    # ถ้ามี user อื่นที่ไม่ใช่นักเรียน login ค้างอยู่ ให้ logout แล้ว redirect เพื่อเริ่มใหม่
    if current_user.is_authenticated and not isinstance(current_user, Student):
        logout_user()
        return redirect(url_for('student.login'))
    
    # ถ้า login อยู่แล้ว และเป็น Student ให้ไป dashboard เลย
    if current_user.is_authenticated:
        return redirect(url_for('student.dashboard'))
    
    form = StudentLoginForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(student_id=form.student_id.data).first()
        if student is None or not student.check_password(form.password.data):
            flash('รหัสนักเรียนหรือรหัสผ่านไม่ถูกต้อง')
            return redirect(url_for('student.login'))
        
        login_user(student, remember=form.remember_me.data)
        session['user_type'] = 'student' # ระบุประเภท user ใน session
        return redirect(url_for('student.dashboard'))
        
    return render_template('student/login.html', title='Login นักเรียน', form=form)

@bp.route('/dashboard')
@login_required
def dashboard():
    # 1. ตรวจสอบว่าเป็นนักเรียนจริงหรือไม่
    if not isinstance(current_user, Student):
        abort(403)

    student = current_user
    enrolled_courses = student.courses
    
    # --- 2. เพิ่ม Logic การคำนวณเกรดของนักเรียนในแต่ละวิชา ---
    grade_summary = {}
    for course in enrolled_courses:
        # ดึงข้อมูลที่จำเป็นสำหรับคำนวณ
        all_components = course.components.all()
        scores_query = Score.query.filter(Score.student_id == student.id, Score.component_id.in_([c.id for c in all_components])).all()
        scores_dict = {s.component_id: s for s in scores_query}

        # แยกองค์ประกอบคะแนน
        coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
        final_comps = [c for c in all_components if c.exam_type == 'final']
        
        max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
        max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

        # คำนวณคะแนนดิบ
        raw_coursework_score = sum(s.total_points or 0 for c in coursework_comps if (s := scores_dict.get(c.id)))
        raw_final_score = sum(s.total_points or 0 for c in final_comps if (s := scores_dict.get(c.id)))

        # คำนวณคะแนนตามสัดส่วน
        coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
        final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
        
        total_score_100 = coursework_weighted + final_weighted
        grade = calculate_grade(total_score_100, 100)
        
        grade_summary[course.id] = {
            'total_score': round(total_score_100, 2),
            'grade': grade
        }

    return render_template('student/dashboard.html', 
                           title='แดชบอร์ดนักเรียน',
                           courses=enrolled_courses,
                           grade_summary=grade_summary)

@bp.route('/logout')
def logout():
    logout_user()
    session.pop('user_type', None)
    return redirect(url_for('main.welcome'))