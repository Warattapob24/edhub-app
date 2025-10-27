# app/manager/routes.py

from flask import render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from app import db
from app.manager import bp
from app.models import Course, Subject, Score, CourseComponent, Setting, EvaluationTopic, AdditionalAssessment, Student,  ClassGroup, GradeLevel, ApprovalLog, Curriculum, CourseAssignment, User, Subject
from app.utils import log_activity
from collections import defaultdict
import json, datetime

# ฟังก์ชันคำนวณเกรด (อาจจะย้ายไปไว้ที่ utils.py ในอนาคต)
import json
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

@bp.route('/dashboard')
@login_required
def dashboard():
    # เปลี่ยนจากการ query status แบบเจาะจง มาเป็น status กลางๆ
    pending_courses = Course.query.filter_by(status='pending_approval').order_by(Course.academic_year.desc()).all()
    
    # (ในอนาคต) อาจเพิ่ม Logic คัดกรองคอร์สที่รอให้ user คนนี้อนุมัติตาม Role
    
    return render_template('manager/dashboard.html', title='แดชบอร์ดอนุมัติผล', courses=pending_courses)

@bp.route('/approval/course/<int:course_id>/action', methods=['POST'])
@login_required
def approve_course_action(course_id):
    course = Course.query.get_or_404(course_id)
    action = request.form.get('action')    # รับค่าจากปุ่มที่กด 'approve' หรือ 'reject'
    comments = request.form.get('comments', '') # รับความคิดเห็น

    # --- หัวใจของ Logic การอนุมัติหลายขั้นตอน ---
    latest_log = course.approval_logs.order_by(ApprovalLog.step.desc()).first()
    current_step = latest_log.step if latest_log else 0
    next_step = current_step + 1

    # สมมติว่าในระบบเรามี 3 ขั้นตอนการอนุมัติ: 
    # 1. ครูส่ง -> 2. หัวหน้าสาระฯ อนุมัติ -> 3. ฝ่ายวิชาการอนุมัติ (เป็นขั้นตอนสุดท้าย)
    FINAL_APPROVAL_STEP = 3 

    if action == 'approve':
        new_status = f'Approved (Step {next_step})'
        
        # ตรวจสอบว่านี่คือขั้นตอนสุดท้ายหรือไม่
        if next_step >= FINAL_APPROVAL_STEP:
            course.status = 'approved' # เปลี่ยนสถานะหลักของคอร์สเป็น "อนุมัติ"
            flash(f'อนุมัติผลการเรียนวิชา {course.subject.name} สำเร็จสมบูรณ์!', 'success')
            log_activity('Final Approve Course', f'Course {course.id} approved by {current_user.username}')
        else:
            # ถ้ายังไม่ใช่ขั้นสุดท้าย ให้คงสถานะหลักไว้ และรอขั้นต่อไป
            flash(f'อนุมัติขั้นตอนที่ {next_step} เรียบร้อยแล้ว', 'info')
            log_activity('Approve Course Step', f'Course {course.id} step {next_step} approved by {current_user.username}')

    elif action == 'reject':
        course.status = 'rejected' # ตีกลับสถานะหลักของคอร์ส
        new_status = 'Rejected'
        flash(f'ตีกลับผลการเรียนวิชา {course.subject.name} เรียบร้อยแล้ว', 'warning')
        log_activity('Reject Course', f'Course {course.id} rejected by {current_user.username}. Reason: {comments}')
    else:
        flash('เกิดข้อผิดพลาด: ไม่มีการดำเนินการที่ระบุ', 'danger')
        return redirect(url_for('manager.dashboard'))

    # สร้าง Log การอนุมัติ/ตีกลับในขั้นตอนนี้
    new_log = ApprovalLog(
        status=new_status,
        comments=comments,
        step=next_step if action == 'approve' else current_step, # ถ้าตีกลับให้ใช้ step เดิม
        course_id=course.id,
        user_id=current_user.id
    )
    db.session.add(new_log)
    db.session.commit()
    
    return redirect(url_for('manager.dashboard'))

@bp.route('/academic-summary')
@login_required
def academic_summary():
    # ดึงข้อมูลที่จำเป็นทั้งหมด
    all_approved_courses = Course.query.filter(Course.status == 'approved').all()
    all_subjects = Subject.query.order_by(Subject.department, Subject.name).all()
    
    # สร้าง Cache ของ Scores และ Components เพื่อความเร็ว
    all_scores = Score.query.all()
    scores_dict = {f"{s.student_id}-{s.component_id}": s for s in all_scores}
    
    summary_data = []
    grade_point_map = {'4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5, '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0}

    for subject in all_subjects:
        courses_for_subject = [c for c in all_approved_courses if c.subject_id == subject.id]
        if not courses_for_subject:
            continue

        total_students = 0
        grade_counts = defaultdict(int)
        total_grade_points = 0

        for course in courses_for_subject:
            all_components = course.components.all()
            coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
            final_comps = [c for c in all_components if c.exam_type == 'final']
            
            max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
            max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

            # วนลูปนักเรียนในทุกห้องของคอร์สนี้
            for class_group in course.class_groups:
                for student in class_group.students:
                    total_students += 1
                    
                    # --- Logic การคำนวณเกรด (เหมือนใน ปถ.05) ---
                    raw_coursework_score = sum(score.total_points or 0 for c in coursework_comps if (score := scores_dict.get(f"{student.id}-{c.id}")))
                    raw_final_score = sum(score.total_points or 0 for c in final_comps if (score := scores_dict.get(f"{student.id}-{c.id}")))

                    coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
                    final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
                    
                    total_score_100 = coursework_weighted + final_weighted
                    grade = calculate_grade(total_score_100, 100)
                    
                    grade_counts[grade] += 1
                    total_grade_points += grade_point_map.get(grade, 0)
        
        # คำนวณเกรดเฉลี่ย (GPA)
        gpa = (total_grade_points / total_students) if total_students > 0 else 0

        summary_data.append({
            'subject': subject,
            'teacher': courses_for_subject[0].teacher,
            'total_students': total_students,
            'grade_counts': dict(grade_counts),
            'gpa': gpa
        })

    return render_template('manager/academic_summary.html',
                           title='สรุปผลสัมฤทธิ์ทางการเรียน',
                           summary_data=summary_data)

@bp.route('/progress-dashboard')
@login_required
# @manager_required # ในอนาคตจะเพิ่ม decorator นี้
def progress_dashboard():
    courses = Course.query.order_by(Course.id).all()
    
    progress_data = []
    for course in courses:
        data = { 'course': course }
        
        students = [student for class_group in course.class_groups for student in class_group.students]
        if not students:
            data.update({'score_status': 'ไม่มี นร.', 'assessment_status': 'ไม่มี นร.', 'issue_count': 0})
            progress_data.append(data)
            continue

        student_ids = [s.id for s in students]

        # --- Logic ที่แก้ไขแล้ว ---

        # 1. ตรวจสอบการกรอกคะแนน
        all_components = course.components.all()
        if all_components:
            required_scores = len(all_components) * len(students)
            score_count = Score.query.filter(Score.student_id.in_(student_ids), Score.component.has(course_id=course.id)).count()
            data['score_status'] = '✅ สมบูรณ์' if score_count >= required_scores else '⚠️ ยังไม่ครบ'
        else:
            data['score_status'] = 'ไม่มีองค์ประกอบคะแนน'

        # 2. ตรวจสอบการประเมินเพิ่มเติม
        required_topics = EvaluationTopic.query.count()
        if required_topics > 0:
            required_assessments = required_topics * len(students)
            assessment_count = AdditionalAssessment.query.filter(AdditionalAssessment.student_id.in_(student_ids), AdditionalAssessment.course_id == course.id).count()
            data['assessment_status'] = '✅ สมบูรณ์' if assessment_count >= required_assessments else '⚠️ ยังไม่ครบ'
        else:
            data['assessment_status'] = 'ไม่มีหัวข้อประเมิน'

        # 3. นับจำนวนนักเรียนที่ติด 0, ร, มส (จะเพิ่ม Logic ทีหลัง)
        data['issue_count'] = 0 # Placeholder

        progress_data.append(data)

    return render_template('manager/progress_dashboard.html',
                           title='แดชบอร์ดติดตามความคืบหน้า',
                           progress_data=progress_data)

@bp.route('/reports')
@login_required
# @manager_required
def reports_dashboard():
    # ดึงข้อมูลห้องเรียนทั้งหมดมาเพื่อสร้างตัวเลือก
    class_groups = ClassGroup.query.join(GradeLevel).order_by(GradeLevel.name, ClassGroup.room_number).all()
    return render_template('manager/reports_dashboard.html',
                           title='ศูนย์รายงานเอกสาร',
                           class_groups=class_groups)

@bp.route('/reports/poh02/<int:student_id>')
@login_required
# @manager_required
def poh02_report_student(student_id):
    student = Student.query.get_or_404(student_id)
    enrolled_courses = student.courses

    # --- Logic การคำนวณเกรดของนักเรียนในแต่ละวิชา ---
    grade_summary = {}
    total_credits = 0
    total_grade_points = 0
    grade_point_map = {'4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5, '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0}

    for course in enrolled_courses:
        # (นำ Logic การคำนวณเกรดจาก ปถ.05 มาใช้อย่างสมบูรณ์)
        all_components = course.components.all()
        scores_query = Score.query.filter(Score.student_id == student.id, Score.component_id.in_([c.id for c in all_components])).all()
        scores_dict = {s.component_id: s for s in scores_query}

        coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
        final_comps = [c for c in all_components if c.exam_type == 'final']
        
        max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
        max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

        raw_coursework_score = sum(s.total_points or 0 for c in coursework_comps if (s := scores_dict.get(c.id)))
        raw_final_score = sum(s.total_points or 0 for c in final_comps if (s := scores_dict.get(c.id)))

        coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
        final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
        
        total_score_100 = coursework_weighted + final_weighted
        grade = calculate_grade(total_score_100, 100)
        
        grade_summary[course.id] = {'grade': grade}
        
        # คำนวณเกรดเฉลี่ย (GPA)
        credits = course.subject.default_credits
        grade_point = grade_point_map.get(grade, 0)
        if grade not in ['ร', 'มส']:
            total_credits += credits
            total_grade_points += (grade_point * credits)

    gpa = (total_grade_points / total_credits) if total_credits > 0 else 0

    return render_template('manager/poh02_report_student.html',
                           title=f'ปถ.02 - {student.first_name}',
                           student=student,
                           courses=enrolled_courses,
                           grade_summary=grade_summary,
                           total_credits=total_credits,
                           gpa=gpa)

@bp.route('/reports/poh01/<int:student_id>')
@login_required
# @manager_required
def poh01_report_student(student_id):
    student = Student.query.get_or_404(student_id)

    # --- 1. ค้นหาทุกคอร์สที่นักเรียนเคยลงทะเบียน และจัดกลุ่มตามเทอม ---
    enrolled_courses = student.courses
    results_by_semester = defaultdict(list)
    for course in enrolled_courses:
        semester_key = f"{course.academic_year}/{course.semester}"
        results_by_semester[semester_key].append(course)

    # --- 2. คำนวณเกรดของแต่ละวิชา และเกรดเฉลี่ยสะสม ---
    grade_summary = {}
    gpa_by_semester = {}
    grade_point_map = {'4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5, '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0}
    
    total_credits_all = 0
    total_grade_points_all = 0

    for semester, courses in results_by_semester.items():
        total_credits_semester = 0
        total_grade_points_semester = 0
        
        for course in courses:
            # --- Logic การคำนวณเกรดที่สมบูรณ์ (เหมือนใน ปถ.05) ---
            all_components = course.components.all()
            scores_query = Score.query.filter(Score.student_id == student.id, Score.component_id.in_([c.id for c in all_components])).all()
            scores_dict = {s.component_id: s for s in scores_query}

            coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
            final_comps = [c for c in all_components if c.exam_type == 'final']
            
            max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
            max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

            raw_coursework_score = sum(s.total_points or 0 for c in coursework_comps if (s := scores_dict.get(c.id)))
            raw_final_score = sum(s.total_points or 0 for c in final_comps if (s := scores_dict.get(c.id)))

            coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
            final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
            
            total_score_100 = coursework_weighted + final_weighted
            grade = calculate_grade(total_score_100, 100)
            
            grade_summary[course.id] = {'grade': grade}
            
            # --- คำนวณเกรดเฉลี่ย (GPA) ---
            credits = course.subject.default_credits
            grade_point = grade_point_map.get(grade, 0)
            if grade not in ['ร', 'มส']:
                total_credits_semester += credits
                total_grade_points_semester += (grade_point * credits)

        gpa_semester = (total_grade_points_semester / total_credits_semester) if total_credits_semester > 0 else 0
        gpa_by_semester[semester] = {
            'gpa': gpa_semester,
            'credits': total_credits_semester
        }
        total_credits_all += total_credits_semester
        total_grade_points_all += total_grade_points_semester

    gpax = (total_grade_points_all / total_credits_all) if total_credits_all > 0 else 0

    return render_template('manager/poh01_report_student.html',
                           title=f'ปถ.01 - {student.first_name}',
                           student=student,
                           results_by_semester=dict(sorted(results_by_semester.items())),
                           grade_summary=grade_summary,
                           gpa_by_semester=gpa_by_semester,
                           total_credits_all=total_credits_all,
                           gpax=gpax)

@bp.route('/assign-courses')
@login_required
def assign_courses():
    manager_dept = current_user.department
    if not manager_dept:
        flash('ท่านยังไม่ได้ถูกกำหนดกลุ่มสาระ', 'warning')
        return redirect(url_for('manager.dashboard'))

    teachers_in_dept = User.query.filter_by(department=manager_dept).filter(User.roles.any(key='teacher')).all()

    # --- ▼▼▼ 🚀 คาถาอัปเกรดตัวกรอง (Filter) ▼▼▼ ---

    # 📡 1. รับค่าตัวกรองจาก URL (Query String)
    # ถ้าไม่มีค่าส่งมา ให้ใช้ปีการศึกษาและภาคเรียนปัจจุบันเป็นค่าเริ่มต้น
    current_year = datetime.datetime.now().year + 543
    selected_year = request.args.get('year', default=current_year, type=int)
    # ปกติเทอม 1 เริ่ม พ.ค. (เดือน 5), เทอม 2 เริ่ม พ.ย. (เดือน 11)
    current_month = datetime.datetime.now().month
    default_semester = 2 if current_month >= 11 or current_month < 5 else 1
    selected_semester = request.args.get('semester', default=default_semester, type=int)

    # 🗓️ 2. เตรียมข้อมูลสำหรับ dropdown ปีการศึกษา
    # ดึงปีการศึกษาทั้งหมดที่มีในระบบมาสร้างเป็นตัวเลือก
    years_query = db.session.query(Curriculum.academic_year).distinct().order_by(Curriculum.academic_year.desc()).all()
    available_years = [year[0] for year in years_query]
    # หากปีปัจจุบันยังไม่มีในลิสต์ ให้เพิ่มเข้าไป
    if current_year not in available_years:
        available_years.insert(0, current_year)


    # ⚙️ 3. แก้ไข Query หลักให้ใช้ตัวกรอง
    # ดึงหลักสูตรโดยกรองตาม "กลุ่มสาระ", "ปีการศึกษา" และ "ภาคเรียน" ที่เลือก
    all_curriculums = Curriculum.query.join(Subject).filter(
        Subject.department == manager_dept,
        Curriculum.academic_year == selected_year, # <--- เพิ่ม filter ปี
        Curriculum.semester == selected_semester   # <--- เพิ่ม filter เทอม
    ).order_by('grade_level_id').all()


    # ส่วนการหา assigned_teachers ยังคงเหมือนเดิม
    assignments = CourseAssignment.query.join(Curriculum).join(Subject).filter(
        Subject.department == manager_dept
    ).all()
    assigned_teachers = {}
    for curriculum in all_curriculums:
        teachers_for_this_curriculum = [a.teacher_id for a in assignments if a.curriculum_id == curriculum.id]
        if teachers_for_this_curriculum:
            try:
                most_common_teacher_id = max(set(teachers_for_this_curriculum), key=teachers_for_this_curriculum.count)
                assigned_teachers[curriculum.id] = most_common_teacher_id
            except ValueError:
                assigned_teachers[curriculum.id] = None

    # --- ▲▲▲ สิ้นสุดการอัปเกรด ▲▲▲ ---

    # 📤 4. ส่งตัวแปรใหม่ไปยัง Template
    return render_template('manager/assign_courses.html',
                           title='มอบหมายรายวิชา',
                           curriculums=all_curriculums,
                           assigned_teachers=assigned_teachers,
                           teachers=teachers_in_dept,
                           available_years=available_years,      # <--- ส่งตัวแปรใหม่
                           selected_year=selected_year,        # <--- ส่งตัวแปรใหม่
                           selected_semester=selected_semester)  # <--- ส่งตัวแปรใหม่

@bp.route('/assign-courses/execute-bulk', methods=['POST'])
@login_required
def execute_bulk_assignment():
    form_data = request.form
    
    # ตรวจสอบว่าข้อมูลถูกส่งมาจากหน้า "จัดการรายห้อง" หรือไม่
    is_detailed_page = any(key.startswith('assignment_key-') for key in form_data)

    if is_detailed_page:
        # --- ✅ ตรรกะสำหรับหน้า "จัดการรายห้อง" (ทำงานสมบูรณ์แล้ว) ---
        for key, value in form_data.items():
            if key.startswith('teacher_id-'):
                parts = key.split('-')
                curriculum_id = int(parts[1])
                class_group_id = int(parts[2])
                teacher_id = int(value)

                assignment = CourseAssignment.query.filter_by(
                    curriculum_id=curriculum_id,
                    class_group_id=class_group_id
                ).first()

                if teacher_id == 0:
                    if assignment:
                        db.session.delete(assignment)
                else:
                    if assignment:
                        assignment.teacher_id = teacher_id
                    else:
                        new_assignment = CourseAssignment(
                            curriculum_id=curriculum_id,
                            class_group_id=class_group_id,
                            teacher_id=teacher_id
                        )
                        db.session.add(new_assignment)
    else:
        # --- ▼▼▼ 🚀 อัปเกรดตรรกะสำหรับหน้า "มอบหมายยกกลุ่ม" (หน้าหลัก) ▼▼▼ ---
        for key, curriculum_id_str in form_data.items():
            if key.startswith('curriculum-'):
                curriculum_id = int(curriculum_id_str)
                teacher_id = int(form_data.get(f'teacher-{curriculum_id}', 0))
                
                curriculum = Curriculum.query.get(curriculum_id)
                if not curriculum: continue

                # หาทุกกลุ่มเรียนในสายชั้นนั้น
                groups_in_grade = curriculum.grade_level.class_groups.all()
                for group in groups_in_grade:
                    # ค้นหาการมอบหมายเดิมของแต่ละห้อง
                    assignment = CourseAssignment.query.filter_by(
                        curriculum_id=curriculum_id,
                        class_group_id=group.id
                    ).first()

                    if teacher_id == 0:
                        # 🗑️ ถ้าเลือก "-- ยังไม่มอบหมาย --" ให้ลบการมอบหมายของทุกห้องในสายชั้นนั้น
                        if assignment:
                            db.session.delete(assignment)
                    else:
                        if assignment:
                            # 🔄 ถ้ามีข้อมูลเดิมอยู่แล้ว ให้อัปเดตครูผู้สอน
                            assignment.teacher_id = teacher_id
                        else:
                            # ➕ ถ้ายังไม่มีข้อมูล ให้สร้างการมอบหมายใหม่
                            new_assignment = CourseAssignment(
                                curriculum_id=curriculum_id,
                                class_group_id=group.id,
                                teacher_id=teacher_id
                            )
                            db.session.add(new_assignment)

    db.session.commit()
    flash('บันทึกการเปลี่ยนแปลงทั้งหมดเรียบร้อยแล้ว', 'success')

    # การ Redirect ยังคงทำงานเหมือนเดิม ไม่ต้องแก้ไข
    redirect_url = url_for('manager.assign_courses')
    if is_detailed_page:
        for key in form_data:
            if key.startswith('assignment_key-'):
                curriculum_id = key.split('-')[1]
                redirect_url = url_for('manager.assign_courses_detailed', curriculum_id=curriculum_id)
                break
                
    return redirect(redirect_url)

@bp.route('/assign-courses/detailed/<int:curriculum_id>', methods=['GET'])
@login_required
def assign_courses_detailed(curriculum_id):
    curriculum = Curriculum.query.get_or_404(curriculum_id)
    manager_dept = current_user.department
    teachers_in_dept = User.query.filter_by(department=manager_dept).filter(User.roles.any(key='teacher')).all()

    # ดึงข้อมูลการมอบหมายปัจจุบันสำหรับหลักสูตรนี้
    assignments = CourseAssignment.query.filter_by(curriculum_id=curriculum_id).all()
    assignments_dict = {a.class_group_id: a.teacher_id for a in assignments}

    return render_template('manager/assign_courses_detailed.html',
                           title='จัดการรายห้อง',
                           curriculum=curriculum,
                           teachers=teachers_in_dept,
                           assignments_dict=assignments_dict)