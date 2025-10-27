# path: app/department/routes.py

from flask import render_template, flash, redirect, url_for, Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.decorators import role_required
from app.models import Course, LearningArea, TeacherAssignment, User, Role, CourseSection, AcademicYear, GradeLevel
from app.department.forms import MultiTeacherAssignmentForm

department_bp = Blueprint('department', __name__, template_folder='templates')

@department_bp.route('/dashboard')
@login_required
@role_required('DepartmentHead')
def dashboard():
    # --- ส่วนตรวจสอบสิทธิ์และหาปีการศึกษาปัจจุบัน (คงเดิม) ---
    if not hasattr(current_user, 'headed_area') or not current_user.headed_area:
        flash('คุณไม่ได้รับมอบหมายให้เป็นหัวหน้ากลุ่มสาระฯ', 'warning')
        return redirect(url_for('main.index'))

    area = current_user.headed_area[0]
    active_year = AcademicYear.query.filter_by(is_active=True).first()

    if not active_year:
        flash('ยังไม่มีการกำหนดปีการศึกษาที่ใช้งานในระบบ', 'danger')
        return render_template('department/dashboard.html', title='แดชบอร์ดกลุ่มสาระฯ', area=area, sections=[], teachers=[], assignments={}, summary={})

    # --- [ปรับปรุง] เปลี่ยนจากการดึง Course มาเป็น CourseSection ---
    # ดึงข้อมูลเฉพาะ Section ในปีการศึกษาปัจจุบันและในกลุ่มสาระนี้เท่านั้น
    sections_in_area = db.session.query(CourseSection).join(Course).filter(
        CourseSection.academic_year_id == active_year.id,
        Course.learning_area_id == area.id,
        Course.semester == active_year.semester
    ).order_by(Course.grade_level_id, Course.name_thai).all()
    
    # --- [ปรับปรุง] เตรียมข้อมูลการมอบหมายให้ใช้งานง่ายขึ้น ---
    # ดึงข้อมูลเฉพาะการมอบหมายที่อยู่ใน Section ที่เรากำลังจะแสดงผล
    section_ids = [s.id for s in sections_in_area]
    assignments_query = TeacherAssignment.query.filter(TeacherAssignment.course_section_id.in_(section_ids)).all()
    
    # สร้าง Dictionary เพื่อให้ Template ค้นหาครูตาม Section ได้ง่าย
    # key คือ section.id, value คือ list ของ TeacherAssignment
    assignments_by_section_id = {}
    for assign in assignments_query:
        if assign.course_section_id not in assignments_by_section_id:
            assignments_by_section_id[assign.course_section_id] = []
        assignments_by_section_id[assign.course_section_id].append(assign)

    # --- ส่วนการดึงข้อมูลครูและคำนวณภาระงาน (คงเดิม) ---
    teachers_in_area = User.query.filter_by(learning_area_id=area.id).order_by(User.full_name).all()
    teacher_load = _get_teacher_load_summary(active_year, area)

    return render_template('department/dashboard.html', 
                           title=f'แดชบอร์ดกลุ่มสาระฯ {area.name}',
                           active_year=active_year,
                           area=area,
                           sections=sections_in_area,  # <--- ส่ง sections ไปแทน courses
                           teachers=teachers_in_area,
                           assignments=assignments_by_section_id, # <--- ส่ง dict ที่ใช้งานง่ายไปแทน
                           summary=teacher_load)

def _get_teacher_load_summary(active_year, area):
    # โครงสร้างข้อมูลชั่วคราวเพื่อรวบรวมข้อมูล
    teacher_data = {}

    # ดึงข้อมูลการมอบหมายทั้งหมดที่เกี่ยวข้อง
    assignments = TeacherAssignment.query.join(CourseSection).join(Course).filter(
        Course.learning_area_id == area.id,
        CourseSection.academic_year_id == active_year.id
    ).all()

    # Step 1: วนลูปเพื่อรวบรวม Course IDs ที่ไม่ซ้ำกัน และคำนวณคาบสอนรวม
    for assign in assignments:
        teacher_id = assign.teacher_id
        course = assign.course_section.course
        
        if teacher_id not in teacher_data:
            teacher_data[teacher_id] = {
                'name': assign.teacher.full_name,
                'unique_course_ids': set(),
                'periods': 0
            }
        
        # เพิ่ม ID ของรายวิชาเข้าไปใน set เพื่อให้แน่ใจว่าไม่ซ้ำ
        teacher_data[teacher_id]['unique_course_ids'].add(course.id)
        
        # คำนวณคาบสอนสำหรับ 1 ห้อง (1 assignment) และบวกเพิ่มเข้าไป
        # 1 คาบเรียนปกติคือ 50 นาที, หน่วยกิต*2 จะเท่ากับจำนวนคาบต่อสัปดาห์
        periods_per_class = (course.credits or 0) * 2
        teacher_data[teacher_id]['periods'] += periods_per_class

    # Step 2: สร้างผลลัพธ์สุดท้ายและคำนวณหน่วยกิตรวมจาก Course IDs ที่ไม่ซ้ำ
    summary = {}
    all_involved_course_ids = {cid for data in teacher_data.values() for cid in data['unique_course_ids']}
    
    if all_involved_course_ids:
        # Query ข้อมูล Course ทั้งหมดที่เกี่ยวข้องในครั้งเดียวเพื่อประสิทธิภาพ
        courses_dict = {c.id: c for c in Course.query.filter(Course.id.in_(all_involved_course_ids)).all()}

        for teacher_id, data in teacher_data.items():
            # คำนวณหน่วยกิตรวมจากรายวิชาที่ไม่ซ้ำกัน
            total_credits = sum(courses_dict[cid].credits for cid in data['unique_course_ids'] if cid in courses_dict)
            
            summary[teacher_id] = {
                'name': data['name'],
                'credits': total_credits,
                'periods': data['periods']
            }
            
    # เพิ่มครูที่ยังไม่มีการมอบหมายเข้ามาใน summary ด้วย
    all_teachers_in_area = User.query.filter_by(learning_area_id=area.id).all()
    for teacher in all_teachers_in_area:
        if teacher.id not in summary:
            summary[teacher.id] = {'name': teacher.full_name, 'credits': 0, 'periods': 0}

    return summary

@department_bp.route('/api/assign-teacher', methods=['POST'])
@login_required
@role_required('DepartmentHead')
def api_assign_teacher():
    data = request.get_json()
    
    # --- 1. [แก้ไข] รับ section_id แทน course_id ---
    # เพื่อให้ตรงกับข้อมูลที่ JavaScript ใน Template ส่งมาให้
    section_id = data.get('section_id')
    teacher_id = data.get('teacher_id')

    if not section_id:
        return jsonify({'status': 'error', 'message': 'Section ID is missing from the request'}), 400

    # --- 2. [แก้ไข] ค้นหา Section ที่มีอยู่จริงเท่านั้น ห้ามสร้างใหม่ ---
    # การสร้าง Section เป็นหน้าที่ของ Admin ในหน้า "เปิดรายวิชา"
    # ถ้าหาไม่เจอ แสดงว่ามีบางอย่างผิดปกติ ให้ trả về error 404
    section = db.get_or_404(CourseSection, section_id)
    
    try:
        # ลบการมอบหมายเดิมของ "ทุกห้อง" ใน Section นี้ทิ้ง
        # (เพราะ dropdown นี้เป็นการมอบหมายครูคนเดียวให้ทุกห้อง)
        TeacherAssignment.query.filter_by(course_section_id=section.id).delete()

        # ถ้ามีการเลือกครู (ไม่ใช่ '-- ยังไม่มีผู้สอน --') ให้สร้างการมอบหมายใหม่
        if teacher_id:
            # --- 3. [แก้ไข] เข้าถึงข้อมูล course ผ่าน section ได้โดยตรง ---
            # ไม่ต้องใช้ Course.query.get(course_id) อีกต่อไป
            for classroom in section.course.grade_level.classrooms:
                assignment = TeacherAssignment(
                    course_section_id=section.id,
                    classroom_id=classroom.id,
                    teacher_id=int(teacher_id)
                )
                db.session.add(assignment)
        
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Assignment updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@department_bp.route('/api/assignment-details/<int:course_id>')
@login_required
@role_required('DepartmentHead')
def get_assignment_details(course_id):
    active_year = AcademicYear.query.filter_by(is_active=True).first()
    course = Course.query.get_or_404(course_id)
    section = CourseSection.query.filter_by(course_id=course_id, academic_year_id=active_year.id).first()

    # หาห้องเรียนทั้งหมดที่วิชานี้ต้องสอน
    classrooms = course.grade_level.classrooms.order_by('name').all()
    teachers = User.query.filter_by(learning_area_id=course.learning_area_id).order_by(User.full_name).all()

    # สร้าง dictionary ของการมอบหมายปัจจุบัน {classroom_id: teacher_id}
    current_assignments = {}
    if section:
        for assign in section.teacher_assignments:
            current_assignments[assign.classroom_id] = assign.teacher_id

    return render_template('department/_assignment_form.html', 
                           course=course,
                           classrooms=classrooms,
                           teachers=teachers,
                           current_assignments=current_assignments)

@department_bp.route('/api/assign-multi-teachers/<int:course_id>', methods=['POST'])
@login_required
@role_required('DepartmentHead')
def assign_multi_teachers(course_id):
    active_year = AcademicYear.query.filter_by(is_active=True).first()
    department_id = current_user.headed_area[0].id
    form = MultiTeacherAssignmentForm(department_id=department_id)

    if form.validate_on_submit():
        section = CourseSection.query.filter_by(course_id=course_id, academic_year_id=active_year.id).first()
        if not section:
            section = CourseSection(course_id=course_id, academic_year_id=active_year.id)
            db.session.add(section)
        section.teachers = form.teachers.data
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'บันทึกสำเร็จ'})
    return jsonify({'status': 'error', 'errors': form.errors})

@department_bp.route('/api/save-assignments/<int:course_id>', methods=['POST'])
@login_required
@role_required('DepartmentHead')
def save_assignments(course_id):
    data = request.get_json()
    active_year = AcademicYear.query.filter_by(is_active=True).first()

    section = CourseSection.query.filter_by(course_id=course_id, academic_year_id=active_year.id).first()
    if not section:
        section = CourseSection(course_id=course_id, academic_year_id=active_year.id)
        db.session.add(section)
        db.session.flush() # Ensure section gets an ID

    # ลบของเก่าทิ้งทั้งหมดเพื่อเริ่มใหม่
    TeacherAssignment.query.filter_by(course_section_id=section.id).delete()

    # สร้างการมอบหมายใหม่จากข้อมูลที่ส่งมา
    for classroom_id, teacher_id in data.get('assignments', {}).items():
        if teacher_id: # บันทึกเฉพาะอันที่มีการเลือกครู
            assignment = TeacherAssignment(
                course_section_id=section.id,
                classroom_id=int(classroom_id),
                teacher_id=int(teacher_id)
            )
            db.session.add(assignment)

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'บันทึกการมอบหมายสำเร็จ'})

@department_bp.route('/api/summary')
@login_required
@role_required('DepartmentHead')
def api_get_summary():
    """
    API Endpoint สำหรับดึงข้อมูลสรุปภาระงานสอนเวอร์ชันล่าสุด (HTML)
    """
    try:
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return "<p>ไม่พบปีการศึกษาที่ใช้งาน</p>"

        area = current_user.headed_area[0]
        summary_data = _get_teacher_load_summary(active_year, area)
        
        # ใช้ render_template เพื่อสร้าง HTML จากไฟล์ _summary.html
        return render_template('department/_summary.html', summary=summary_data)
    except Exception as e:
        # ในกรณีเกิดข้อผิดพลาด ให้ส่งข้อความกลับไปแทนที่จะทำให้หน้าเว็บพัง
        return f"<p>เกิดข้อผิดพลาดในการโหลดข้อมูลสรุป: {str(e)}</p>", 500
