# app/main/routes.py

from flask import render_template, redirect, url_for, request
from flask_login import login_required, current_user
from datetime import datetime
from app.main import bp
from app.models import User, Student, Course, ClassGroup, SchoolPeriod, GradeLevel, TimetableBlock, TimetableSlot

@bp.route('/')
@bp.route('/index')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('main.welcome'))
    
    # Logic การส่งต่อไปยัง Dashboard ที่ถูกต้อง
    if isinstance(current_user, Student):
        return redirect(url_for('student.dashboard'))
    
    # --- ปรับปรุงคาถาประตูมิติสำหรับครู ---
    user_roles_keys = [role.key for role in current_user.roles]
    if 'admin' in user_roles_keys:
        return redirect(url_for('admin.manage_users'))
    if 'manager' in user_roles_keys:
        return redirect(url_for('manager.dashboard'))
    
    # หากเป็นครู ให้ส่งไปที่แดชบอร์ดใหม่ของเรา!
    if 'teacher' in user_roles_keys:
        return redirect(url_for('main.dashboard'))
    
    # เงื่อนไขสำหรับครูที่ปรึกษา (อาจจะต้องปรับลำดับตามความสำคัญ)
    if current_user.advised_class_groups:
        return redirect(url_for('advisor.dashboard'))
        
    # หากไม่มีบทบาทเฉพาะเจาะจง ให้ไปหน้าหลัก
    return render_template('index.html', title='หน้าหลัก')

# --- สร้างห้องโถงใหม่สำหรับ "คันฉ่องส่องตารางสอน" ---
@bp.route('/dashboard')
@login_required
def dashboard():
    today_weekday = datetime.today().weekday()

    teacher_schedule = (
        TimetableSlot.query
        .join(Course, TimetableSlot.block_id == Course.id)  # หรือปรับ join ให้ถูกต้องตามโครงสร้างจริง
        .join(SchoolPeriod, TimetableSlot.period_id == SchoolPeriod.id)
        .filter(
            Course.teacher_id == current_user.id,
            TimetableSlot.day_of_week == today_weekday
        )
        .order_by(SchoolPeriod.start_time)
        .all()
    )

    return render_template(
        'main/dashboard.html',
        title='Dashboard',
        schedule=teacher_schedule,
        now=datetime.now()  # ✅ ส่ง now ให้ template
    )

@bp.route('/welcome')
def welcome():
    return render_template('main/welcome.html', title='ยินดีต้อนรับ')

@bp.route('/timetable')
@login_required
def view_timetable():
    # รับค่าว่าจะดูของใครจาก URL
    class_group_id = request.args.get('class_group_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)

    # เตรียมข้อมูลสำหรับ dropdown
    all_class_groups = ClassGroup.query.join(GradeLevel).order_by(GradeLevel.id, ClassGroup.room_number).all()
    all_teachers = User.query.filter(User.roles.any(key='teacher')).order_by(User.full_name).all()
    school_periods = SchoolPeriod.query.order_by('start_time').all()

    slots_query = TimetableSlot.query
    viewing_target = None

    if class_group_id:
        slots_query = slots_query.filter_by(class_group_id=class_group_id)
        viewing_target = ClassGroup.query.get(class_group_id)
    elif teacher_id:
        # ต้อง join กับ Course เพื่อหา teacher_id
        slots_query = slots_query.join(Course).filter(Course.teacher_id == teacher_id)
        viewing_target = User.query.get(teacher_id)

    # แปลงข้อมูลที่ดึงมาให้อยู่ในรูปแบบ Grid ที่แสดงผลง่าย
    # 1. สร้าง Grid เปล่า
    timetable_grid = {day: {p.period_number: None for p in school_periods} for day in range(5)}
    viewing_target = None

    # 2. นำ TimetableBlock มาแสดงผลก่อน
    time_blocks = TimetableBlock.query.all()
    for block in time_blocks:
        for day_str in block.days_of_week:
            try:
                day = int(day_str)
                if day not in timetable_grid: continue

                for period in school_periods:
                    if block.start_time <= period.start_time and block.end_time >= period.end_time:
                        is_relevant = False
                        if class_group_id:
                            # ตรวจสอบว่าห้องเรียนนี้อยู่ในสายชั้นที่ถูกบล็อกหรือไม่
                            class_group = ClassGroup.query.get(class_group_id)
                            if class_group and class_group.grade_level in block.applies_to_grade_levels:
                                is_relevant = True
                        if teacher_id:
                            # ตรวจสอบว่าครูคนนี้มีบทบาทที่ถูกบล็อกหรือไม่
                            teacher = User.query.get(teacher_id)
                            if teacher and any(role in block.applies_to_roles for role in teacher.roles):
                                is_relevant = True

                        if is_relevant:
                            timetable_grid[day][period.period_number] = block.name
            except (ValueError, TypeError):
                continue # ข้ามถ้าแปลงเป็นตัวเลขไม่ได้

    # 3. นำ TimetableSlot มาวางทับ
    slots_query = TimetableSlot.query
    if class_group_id:
        slots_query = slots_query.filter_by(class_group_id=class_group_id)
        viewing_target = ClassGroup.query.get(class_group_id)
    elif teacher_id:
        slots_query = slots_query.join(Course).filter(Course.teacher_id == teacher_id)
        viewing_target = User.query.get(teacher_id)

    for slot in slots_query.all():
        timetable_grid[slot.day_of_week][slot.course.subject.course_offerings[0].teacher_id] = slot

    return render_template('main/timetable.html',
                           title='ดูตารางสอน',
                           all_class_groups=all_class_groups,
                           all_teachers=all_teachers,
                           school_periods=school_periods,
                           timetable_grid=timetable_grid,
                           selected_class_group_id=class_group_id,
                           selected_teacher_id=teacher_id,
                           viewing_target=viewing_target)
