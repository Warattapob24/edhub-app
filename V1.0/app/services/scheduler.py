# app/services/scheduler.py (หรือ app/scheduler.py)

from app.models import (Course, ClassGroup, User, SchoolPeriod, TimetableBlock, 
                        SchedulingRule, Curriculum, CourseAssignment, GradeLevel, Subject, Role, TimetableSlot)
from app import db
import random

def find_best_slot(task, teacher_board, class_group_board, school_periods, teacher_daily_load, debug=False):
    """
    ฟังก์ชัน "สมอง" ที่จะหาช่องว่างที่ดีที่สุดสำหรับภารกิจ (คาบเรียน) หนึ่งๆ
    """
    course = task['course']
    teacher = course.teacher
    class_group_to_check = task['class_group']
    required_room_type = course.subject.required_room_type
    rules = {r.rule_type: r.value for r in course.scheduling_rules.all()} # แปลง "คำขอพร" ให้อ่านง่าย

    possible_slots = []

    # วนลูปหาในทุกๆ ช่องที่เป็นไปได้
    for day in range(5): # 0-4 Mon-Fri
        for period in school_periods:
            possible_slots.append({
                'day': day,
                'period': period,
                'class_group': class_group_to_check,
                'score': 0
            })

                # --- 1. ตรวจสอบ "กฎเหล็ก" (Hard Constraints) ---
                # ถ้าไม่ผ่านข้อใดข้อหนึ่ง จะข้ามช่องนี้ไปทันที
                
                # 1.1 ครูว่างหรือไม่?
            if teacher_board[teacher.id][day][period.period_number] is not None:
                    if debug: print(f"    - ปฏิเสธ: วัน {day} คาบ {period.period_number} -> ครูไม่ว่าง")
                    continue
                
                # 1.2 ห้องเรียนว่างหรือไม่?
            if class_group_board[class_group_to_check.id][day][period.period_number] is not None:
                    if debug: print(f"    - ปฏิเสธ: วัน {day} คาบ {period.period_number} -> ห้องไม่ว่าง")
                    continue

                # 1.3 ประเภทห้องถูกต้องหรือไม่?
            if required_room_type and class_group_to_check.room_type != required_room_type:
                    if debug: print(f"    - ปฏิเสธ: วัน {day} คาบ {period.period_number} -> ประเภทห้องไม่ตรง ({class_group_to_check.room_type})")
                    continue

                # 1.4 ตรวจสอบภาระงานครู
            if teacher.max_periods_per_day and teacher_daily_load[teacher.id][day] >= teacher.max_periods_per_day:
                    if debug: print(f"    - ปฏิเสธ: วัน {day} คาบ {period.period_number} -> ภาระงานครูเต็มแล้ว ({teacher_daily_load[teacher.id][day]})")
                    continue

                # --- 2. "ให้คะแนน" ตาม "คำขอพร" (Soft Constraints) ---
                # ถ้าผ่านมาถึงนี่ได้ แสดงว่าเป็นช่องที่ "สามารถจัดได้"
                
            current_score = 0
                
                # 2.1 ให้คะแนนตามช่วงเวลาที่แนะนำ
            if 'prefer_morning' in rules and period.start_time.hour < 12:
                    current_score += 10
            if 'prefer_afternoon' in rules and period.start_time.hour >= 12:
                    current_score += 10
                
                # 2.2 ให้คะแนนหากได้สอนติดกัน (ตามคำขอ)
            if 'group_together' in rules:
                    # ตรวจสอบคาบก่อนหน้าในวันเดียวกัน
                    if period.period_number > 1 and teacher_board[teacher.id][day][period.period_number - 1] == course:
                        current_score += 50 # ให้คะแนนสูงมาก!

                # 2.3 ให้คะแนน (ติดลบ) หากสอนวิชาเดียวกันในวันเดียวกัน (ตามคำขอ)
            if 'spread_out' in rules:
                    # ตรวจสอบว่าในวันนั้นๆ มีการสอนวิชานี้ไปแล้วหรือยัง
                    for p_num in teacher_board[teacher.id][day]:
                        if teacher_board[teacher.id][day][p_num] == course:
                            current_score -= 50 # ให้คะแนนติดลบเพื่อหลีกเลี่ยง
                            break

                # --- 3. ตัดสินใจ ---
            possible_slots.append({
                    'day': day,
                    'period': period,
                    'class_group': class_group_to_check,
                    'score': current_score
                })

        # --- 4. ตัดสินใจเลือกบ้านที่ดีที่สุดหลังดูครบหมดแล้ว ---
        if not possible_slots:
            if debug: print("    - สรุป: ไม่พบช่องที่สามารถจัดลงได้เลยตลอดทั้งสัปดาห์")
            return None # ไม่มีบ้านว่างเลย

        # เรียงลำดับบ้านทั้งหมดจากคะแนนสูงสุดไปต่ำสุด
        possible_slots.sort(key=lambda x: x['score'], reverse=True)
    
        # หากมีบ้านที่คะแนนสูงสุดเท่ากันหลายหลัง ให้สุ่มเลือกเพื่อความหลากหลาย
        max_score = possible_slots[0]['score']
        top_choices = [slot for slot in possible_slots if slot['score'] == max_score]
    
        return random.choice(top_choices) # <-- คืนค่าบ้านที่ดีที่สุด (ที่ผ่านการสุ่ม)

def generate_timetable(academic_year, semester):
    """
    คาถาหลักในการจัดตารางสอนอัตโนมัติ
    """
    print("--- เริ่มร่ายมหาเวทจัดตารางสอน ---")

    # --- ส่วนที่ 1: รวบรวมวัตถุดิบทั้งหมด ---
    print("ขั้นตอนที่ 1: กำลังรวบรวมวัตถุดิบเวทมนตร์...")
    
    # 1.1 คาบเรียนมาตรฐานทั้งหมด
    school_periods = SchoolPeriod.query.order_by('start_time').all()
    
    # 1.2 กฎการบล็อกเวลาทั้งหมด (พัก, กิจกรรม)
    time_blocks = TimetableBlock.query.filter_by(academic_year=academic_year).all()
    
    # 1.3 คลาสเรียนทั้งหมดที่ต้องจัดในเทอมนี้
    courses_to_schedule = Course.query.filter_by(
        academic_year=academic_year, 
        semester=semester
    ).all()
    
    # 1.4 ห้องเรียนทั้งหมดที่มี
    all_class_groups = ClassGroup.query.filter_by(academic_year=academic_year).all()
    
    # 1.5 ครูทั้งหมดพร้อมขีดจำกัดภาระงาน
    all_teachers = User.query.filter(User.roles.any(key='teacher')).all()

    print(f"พบ {len(courses_to_schedule)} คลาสเรียนที่ต้องจัด...")

    # --- ส่วนที่ 2: เตรียมกระดานหมากรุกแห่งเวลา ---
    print("ขั้นตอนที่ 2: กำลังเตรียมกระดานหมากรุกแห่งเวลา...")
    
    # สร้างกระดานเปล่าสำหรับครูทุกคน
    # โครงสร้าง: teacher_board[teacher_id][day][period] = None (ว่าง)
    teacher_board = {
        teacher.id: {day: {p.period_number: None for p in school_periods} for day in range(5)} # 0-4 for Mon-Fri
        for teacher in all_teachers
    }

    teacher_daily_load = {
        teacher.id: {day: 0 for day in range(5)}
        for teacher in all_teachers
    }    
    
    # สร้างกระดานเปล่าสำหรับทุกห้องเรียน
    # โครงสร้าง: class_group_board[class_group_id][day][period] = None (ว่าง)
    class_group_board = {
        cr.id: {day: {p.period_number: None for p in school_periods} for day in range(5)}
        for cr in all_class_groups
    }

    # นำ "กฎการบล็อกเวลา" (เวลาพัก, กิจกรรม) มาประทับตราลงบนกระดาน
    for block in time_blocks:
        for day_str in block.days_of_week: # <-- รับค่ามาเป็นตัวอักษรก่อน
            try:
                day = int(day_str) # <-- แปลงให้เป็นตัวเลข
                # หาคาบเรียนที่อยู่ในช่วงเวลาของบล็อก
                for period in school_periods:
                    if block.start_time <= period.start_time and block.end_time >= period.end_time:
                        # กรณีบล็อกด้วยสายชั้น
                        for grade_level in block.applies_to_grade_levels:
                            for class_group in grade_level.class_groups:
                                if class_group.id in class_group_board:
                                    class_group_board[class_group.id][day][period.period_number] = 'BLOCKED'
                    # กรณีบล็อกด้วยบทบาท
                        for role in block.applies_to_roles:
                            for user in role.users:
                                if user.id in teacher_board:
                                    teacher_board[user.id][day][period.period_number] = 'BLOCKED'
            except (ValueError, TypeError):
                continue # ถ้าแปลงเป็นตัวเลขไม่ได้ ให้ข้ามไป
    
    print("เตรียมกระดานและประทับตรากฎการบล็อกเวลาเสร็จสิ้น!")


    # --- ส่วนที่ 3: เริ่มการจัดเรียง ---
    print("ขั้นตอนที่ 3: เริ่มจัดเรียงสรรพสิ่ง...")

    # 3.1 สร้าง "รายการภารกิจ" ที่ต้องจัด
    tasks = []
    for course in courses_to_schedule:
        periods_needed = int(course.subject.default_credits * 2)
        # วนลูปสำหรับทุกห้องที่คอร์สนี้ต้องสอน
        for class_group in course.class_groups:
            for i in range(periods_needed):
                tasks.append({
                    'course': course,
                    'class_group': class_group, # <-- เพิ่มห้องเรียนสำหรับภารกิจนี้
                    'task_id': f"{course.id}-{class_group.id}-{i+1}"
                })

    print(f"สร้างภารกิจทั้งหมด {len(tasks)} ภารกิจ")

    # 3.2 จัดลำดับความสำคัญของภารกิจ (สำคัญมาก!)
    # เราควรจัดวิชาที่มีเงื่อนไขเยอะๆ (เช่น ต้องการห้องพิเศษ) ก่อน
    def task_priority(task):
        priority = 0
        if task['course'].subject.required_room_type:
            priority += 10 # ให้ความสำคัญกับวิชาที่ต้องการห้องพิเศษ
        # เพิ่มเงื่อนไขอื่นๆ ได้ในอนาคต
        return priority

    tasks.sort(key=task_priority, reverse=True)

    # 3.3 เริ่มวนลูปหาบ้านให้แต่ละภารกิจ
    conflicts = [] 

    # --- ส่วนที่ 4: คืนผลลัพธ์ ---
    # สุดท้าย ฟังก์ชันนี้จะบันทึกผลลัพธ์ลง TimetableSlot และคืน "รายการข้อขัดแย้ง"

    # --- คาถาล้างตารางสอนเก่าฉบับใหม่ (2 จังหวะ) ---
    print("กำลังชำระล้างตารางสอนเก่า...")
    # จังหวะที่ 1: ค้นหา ID ทั้งหมดที่ต้องลบ
    slot_ids_to_delete = [
        s.id for s in TimetableSlot.query.with_entities(TimetableSlot.id).join(Course).filter(
            Course.academic_year == academic_year,
            Course.semester == semester
        )
    ]
    
    # จังหวะที่ 2: ลบตาม ID ที่หามาได้
    if slot_ids_to_delete:
        TimetableSlot.query.filter(
            TimetableSlot.id.in_(slot_ids_to_delete)
        ).delete(synchronize_session=False)
        db.session.flush() # ยืนยันการลบใน session ก่อนไปต่อ
        print(f"ชำระล้างตารางสอนเก่า {len(slot_ids_to_delete)} รายการสำเร็จ")
    # --- สิ้นสุดคาถาฉบับใหม่ ---

    for task in tasks:
        course = task['course']
        teacher = course.teacher
        print(f"  -> กำลังหาบ้านให้: {course.subject.name} ห้อง {task['class_group'].room_number}")

        # 1. เรียกใช้ "สมอง" เพื่อหาช่องที่ดีที่สุด
        best_slot = find_best_slot(task, teacher_board, class_group_board, school_periods, teacher_daily_load, debug=False)

        # 2. ถ้า "สมอง" หาทางออกเจอ
        if best_slot:
            # 2.1 "จอง" ช่องนั้นในกระดานหมากรุกของเราทันที
            day = best_slot['day']
            period = best_slot['period']
            class_group = best_slot['class_group']
            
            teacher_board[teacher.id][day][period.period_number] = course
            class_group_board[class_group.id][day][period.period_number] = course
            teacher_daily_load[teacher.id][day] += 1

            # 2.2 สร้าง "บันทึก" ลงในฐานข้อมูลจริง
            new_slot = TimetableSlot(
                day_of_week=day,
                start_time=period.start_time,
                end_time=period.end_time,
                course_id=course.id,
                class_group_id=class_group.id
            )

            db.session.add(new_slot)
            
            print(f"จัดตารางสำเร็จ: {task['course'].subject.name}  -> วัน{day} คาบ{period.period_number} ห้อง{task['class_group'].room_number}")
            best_slot = find_best_slot(task, teacher_board, class_group_board, school_periods, teacher_daily_load, debug=True)

        # 3. ถ้า "สมอง" หาทางออกไม่ได้
        else:
            conflicts.append(task)
            print(f"!!! พบข้อขัดแย้ง: ไม่สามารถจัดคาบสำหรับ {task['course'].subject.name}")

            print("--- กำลังตรวจสอบสาเหตุของข้อขัดแย้ง... ---")
            # เรียกใช้สมองอีกครั้ง แต่ครั้งนี้เปิด "ตาทิพย์"
            find_best_slot(task, teacher_board, class_group_board, school_periods, teacher_daily_load, debug=True)
            print("--- สิ้นสุดการตรวจสอบ ---")

    db.session.commit()
    print("--- การร่ายมหาเวทเสร็จสิ้น ---")
    
    return conflicts
