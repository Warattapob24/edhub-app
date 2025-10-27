# FILE: run.py (FINAL CORRECTED VERSION)

from app import create_app, db
import click

app = create_app()

# This command is now self-contained with its own imports
@app.cli.command("check-topics")
@click.argument("template_name")
def check_assessment_topics(template_name):
    """
    ตรวจสอบ Parent ID ของหัวข้อทั้งหมดใน Assessment Template ที่ระบุ
    """
    # Imports are moved inside the function
    from app.models import AssessmentTemplate, AssessmentTopic

    template = AssessmentTemplate.query.filter_by(name=template_name).first()

    if not template:
        print(f"!!! ไม่พบ Template ที่ชื่อ '{template_name}'")
        return

    print(f"--- กำลังตรวจสอบ Template: '{template.name}' (ID: {template.id}) ---")
    all_topics = AssessmentTopic.query.filter_by(template_id=template.id).order_by(AssessmentTopic.id).all()

    if not all_topics:
        print("!!! ไม่พบหัวข้อใดๆ สำหรับ Template นี้เลย")
        return

    print("\nหัวข้อทั้งหมดที่พบสำหรับ Template นี้:")
    for topic in all_topics:
        print(f"  ID: {topic.id:<4} | Parent ID: {str(topic.parent_id):<6} | Name: '{topic.name}'")

    print("\n--- ผลการวิเคราะห์ ---")
    main_topics = [t for t in all_topics if t.parent_id is None]
    print(f"พบหัวข้อหลัก (Parent ID is None) ทั้งหมด {len(main_topics)} รายการ:")
    for topic in main_topics:
        print(f"  - '{topic.name}'")

# This context processor is now self-contained with its own imports
@app.shell_context_processor
def make_shell_context():
    # Imports are moved inside the function
    from app.models import (User, Role, GradeLevel, SubjectGroup, SubjectType, 
                            AcademicYear, Semester, Subject, Classroom, AssessmentTemplate, 
                            AssessmentTopic, RubricLevel, AssessmentDimension, LessonPlan)
    return {
        'db': db, 'User': User, 'Role': Role, 'GradeLevel': GradeLevel, 
        'SubjectGroup': SubjectGroup, 'SubjectType': SubjectType, 'AcademicYear': AcademicYear, 
        'Semester': Semester, 'Subject': Subject, 'Classroom': Classroom, 
        'AssessmentTemplate': AssessmentTemplate, 'AssessmentTopic': AssessmentTopic, 
        'RubricLevel': RubricLevel, 'AssessmentDimension': AssessmentDimension, 'LessonPlan': LessonPlan
    }

# This command is now self-contained with its own imports
@app.cli.command('seed-db')
def seed_db():
    """Seeds the database with a complete set of initial data."""
    # Imports are moved inside the function
    from app.models import (User, Role, GradeLevel, SubjectGroup, SubjectType, 
                            AcademicYear, Semester, Subject, Classroom, AssessmentTemplate, 
                            AssessmentTopic, RubricLevel, AssessmentDimension, LessonPlan)
    
    print("Seeding database...")

    # The rest of your seed_db function remains exactly the same...
    # --- 1. Create Roles ---
    roles_data = [
        {'name': 'Admin', 'description': 'ผู้ดูแลระบบสูงสุด'},
        {'name': 'Student Affairs', 'description': 'ฝ่ายกิจการนักเรียน'}, # Added for notification service
        {'name': 'Executive', 'description': 'ผู้บริหาร (อนุมัติ, ดูรายงานทั้งหมด)'},
        {'name': 'Academic', 'description': 'ฝ่ายวิชาการ (จัดการหลักสูตร, นักเรียน)'},
        {'name': 'DepartmentHead', 'description': 'หัวหน้ากลุ่มสาระฯ'},
        {'name': 'GradeLevelHead', 'description': 'หัวหน้าสายชั้น'},
        {'name': 'Advisor', 'description': 'ครูที่ปรึกษา'},
        {'name': 'Teacher', 'description': 'ครูผู้สอน'},
        {'name': 'Student', 'description': 'นักเรียน'},
    ]
    for r_data in roles_data:
        if not Role.query.filter_by(name=r_data['name']).first():
            db.session.add(Role(**r_data))
    db.session.commit()
    print("Roles seeded.")

    # --- 2. Create Grade Levels ---
    grades_data = [
        {'name': 'มัธยมศึกษาปีที่ 1', 'short_name': 'ม.1'},
        {'name': 'มัธยมศึกษาปีที่ 2', 'short_name': 'ม.2'},
        {'name': 'มัธยมศึกษาปีที่ 3', 'short_name': 'ม.3'},
        {'name': 'มัธยมศึกษาปีที่ 4', 'short_name': 'ม.4'},
        {'name': 'มัธยมศึกษาปีที่ 5', 'short_name': 'ม.5'},
        {'name': 'มัธยมศึกษาปีที่ 6', 'short_name': 'ม.6'}
    ]
    for g_data in grades_data:
        if not GradeLevel.query.filter_by(name=g_data['name']).first():
            db.session.add(GradeLevel(**g_data))
    db.session.commit()
    print("Grade Levels seeded.")

    # --- 3. Create Subject Types ---
    subject_types_data = ['รายวิชาพื้นฐาน', 'รายวิชาเพิ่มเติม']
    for st_name in subject_types_data:
        if not SubjectType.query.filter_by(name=st_name).first():
            db.session.add(SubjectType(name=st_name))
    db.session.commit() # <<< Add this line
    print("Subject Types seeded.")

    # --- 4. Create Subject Groups ---
    subject_groups_data = [
        'กลุ่มสาระการเรียนรู้ภาษาไทย', 'กลุ่มสาระการเรียนรู้คณิตศาสตร์',
        'กลุ่มสาระการเรียนรู้วิทยาศาสตร์และเทคโนโลยี', 'กลุ่มสาระการเรียนรู้สังคมศึกษา ศาสนา และวัฒนธรรม',
        'กลุ่มสาระการเรียนรู้สุขศึกษาและพลศึกษา', 'กลุ่มสาระการเรียนรู้ศิลปะ',
        'กลุ่มสาระการเรียนรู้การงานอาชีพ', 'กลุ่มสาระการเรียนรู้ภาษาต่างประเทศ'
    ]
    for sg_name in subject_groups_data:
        if not SubjectGroup.query.filter_by(name=sg_name).first():
            db.session.add(SubjectGroup(name=sg_name))
    db.session.commit()
    print("Subject Groups seeded.")

    # --- 5. Create Academic Year and Semesters ---
    acad_year = AcademicYear.query.filter_by(year=2568).first()
    if not acad_year:
        acad_year = AcademicYear(year=2568)
        db.session.add(acad_year)
        db.session.commit()
        sem1 = Semester(term=1, academic_year_id=acad_year.id, is_current=True)
        sem2 = Semester(term=2, academic_year_id=acad_year.id)
        db.session.add_all([sem1, sem2])
        db.session.commit()
        print("Academic Year 2568 and Semesters seeded.")

    # --- 6. Create Classrooms for each Grade Level ---
    all_grades = GradeLevel.query.all()
    for grade in all_grades:
        for i in range(1, 9): # สร้าง 8 ห้อง (1-8)
            classroom_name = f"{grade.short_name}/{i}"
            if not Classroom.query.filter_by(name=classroom_name, academic_year_id=acad_year.id).first():
                classroom = Classroom(name=classroom_name, grade_level_id=grade.id, academic_year_id=acad_year.id)
                db.session.add(classroom)
    db.session.commit()
    print("Classrooms for all grade levels seeded.")

    # --- 7. Create Admin User ---
    if not User.query.filter_by(username='admin').first():
        admin_role = Role.query.filter_by(name='Admin').first()
        admin_user = User(
            username='admin', email='admin@edhub.com',
            name_prefix='Mr.', first_name='Warattapob', last_name='Tumnahard',
            job_title='ผู้ดูแลระบบ', must_change_password=False
        )
        admin_user.set_password('15012529')
        if admin_role:
            admin_user.roles.append(admin_role)
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user seeded.")

    # --- 8. Create Assessment Dimensions, Templates, Topics, and Rubrics ---
    print("Seeding assessment foundations...")

    # Part 8.1: Seed Assessment Dimensions (KPA)
    dimensions_data = [
        {'code': 'K', 'name': 'Knowledge (ความรู้)'},
        {'code': 'P', 'name': 'Process (กระบวนการ)'},
        {'code': 'A', 'name': 'Attitude (เจตคติ)'},
    ]
    for d_data in dimensions_data:
        if not AssessmentDimension.query.filter_by(code=d_data['code']).first():
            db.session.add(AssessmentDimension(**d_data))
    print("Seeded 'Assessment Dimensions (KPA)'.")

    # Part 8.2: Seed Templates and Rubrics
    rubric_levels_data = [
        {'label': 'ดีเยี่ยม', 'value': 3, 'order': 0},
        {'label': 'ดี', 'value': 2, 'order': 1},
        {'label': 'ผ่าน', 'value': 1, 'order': 2},
        {'label': 'ไม่ผ่าน', 'value': 0, 'order': 3},
    ]
    
    # Template 1: Desirable Characteristics
    char_template = AssessmentTemplate.query.filter_by(name='คุณลักษณะอันพึงประสงค์').first()
    if not char_template:
        char_template = AssessmentTemplate(name='คุณลักษณะอันพึงประสงค์', description='ตามหลักสูตรแกนกลางการศึกษาขั้นพื้นฐาน')
        db.session.add(char_template)
        # db.session.commit()
        for r_data in rubric_levels_data:
            char_template.rubric_levels.append(RubricLevel(**r_data))
        
        # Define topics with sub-topics
        char_topics_data = {
            'รักชาติ ศาสน์ กษัตริย์': ['ยืนตรงเมื่อได้ยินเพลงชาติ ร้องเพลงชาติได้ และบอกความหมายของเพลงชาติ','ปฏิบัติตนตามสิทธิและหน้าที่ของนักเรียน ให้ความร่วมมือ ร่วมใจ ในการทำงานกับสมาชิกในห้องเรียน','เข้าร่วมกิจกรรมที่สร้างความสามัคคี ปรองดอง และเป็นประโยชน์ต่อโรงเรียนและชุมชน','เข้าร่วมกิจกรรมทางศาสนาที่ตนนับถือ ปฏิบัติตนตามหลักของศาสนาและเป็นตัวอย่างที่ดีของศาสนิกชน','เข้าร่วมกิจกรรมและมีส่วนร่วมในการจัดกิจกรรมที่เกี่ยวกับสถาบันพระมหากษัตริย์ตามที่โรงเรียนและชุมชนจัดขึ้น ชื่นชมในพระราชกรณียกิจพระปรีชาสามารถของพระมหากษัตริย์และพระราชวงศ์'],
            'ซื่อสัตย์ สุจริต': ['ให้ข้อมูลที่ถูกต้อง และเป็นจริง', 'ปฏิบัติในสิ่งที่ถูกต้อง ละอาย และเกรงกลัวที่จะทำความผิด ทำตามสัญญาที่ตนให้ไว้กับพ่อแม่หรือผู้ปกครอง และครู','ปฏิบัติตนต่อผู้อื่นด้วยความซื่อตรง และเป็นแบบอย่างที่ดีแก่เพื่อนด้านความซื่อสัตย์'],
            'มีวินัย รับผิดชอบ': ['ปฏิบัติตามข้อตกลง กฎเกณฑ์ ระเบียบ ข้อบังคับของครอบครัวและโรงเรียน มีความตรงต่อเวลาในการปฏิบัติกิจกรรมต่างๆ ในชีวิตประจำวันมีความรับผิดชอบ'],
            'ใฝ่เรียนรู้': ['ตั้งใจเรียน', 'เอาใจใส่ในการเรียน และมีความเพียรพยายามในการเรียน','เข้าร่วมกิจกรรมการเรียนรู้ต่างๆ','ศึกษาค้นคว้า หาความรู้จากหนังสือ เอกสาร สิ่งพิมพ์ สื่อเทคโนโลยีต่างๆแหล่งการเรียนรู้ทั้งภายในและภายนอกโรงเรียน และเลือกใช้สื่อได้อย่างเหมาะสม','บันทึกความรู้ วิเคราะห์ ตรวจสอบบางสิ่งที่เรียนรู้ สรุปเป็นองค์ความรู้','แลกเปลี่ยนความรู้ ด้วยวิธีการต่างๆ และนำไปใช้ในชีวิตประจำวัน'],
            'อยู่อย่างพอเพียง': ['ใช้ทรัพย์สินและสิ่งของของโรงเรียนอย่างประหยัด','ใช้อุปกรณ์การเรียนอย่างประหยัดและรู้คุณค่า','ใช้จ่ายอย่างประหยัดและมีการเก็บออมเงิน'],
            'มุ่งมั่นในการทำงาน': ['มีความตั้งใจและพยายามในการทำงานที่ได้รับมอบหมาย', 'มีความอดทนและไม่ท้อแท้ต่ออุปสรรคเพื่อให้งานสำเร็จ'],
            'รักความเป็นไทย': ['มีจิตสำนึกในการอนุรักษ์วัฒนธรรมและภูมิปัญญาไทย','เห็นคุณค่าและปฏิบัติตนตามวัฒนธรรมไทย'],
            'มีจิตสาธารณะ': ['รู้จักช่วยพ่อแม่ ผู้ปกครอง และครูทำงาน', 'อาสาทำงาน ช่วยคิด ช่วยทำ และแบ่งปันสิ่งของให้ผู้อื่น','รู้จักการดูแล รักษาทรัพย์สมบัติและสิ่งแวดล้อมของห้องเรียน โรงเรียน ชุมชน','เข้าร่วมกิจกรรมเพื่อสังคมและสาธารณประโยชน์ของโรงเรียน']
        }
        for topic_name, sub_topics in char_topics_data.items():
            # สร้าง Parent Topic และ append เข้า relationship
            parent_topic = AssessmentTopic(name=topic_name)
            char_template.topics.append(parent_topic)
            
            # Flush เพื่อให้ parent_topic มี id ก่อนที่จะถูกใช้เป็น parent
            db.session.flush()

            for sub_name in sub_topics:
                # สร้าง Sub-topic โดยระบุ parent แล้ว append เข้า relationship
                sub_topic = AssessmentTopic(name=sub_name, parent=parent_topic)
                char_template.topics.append(sub_topic)
        print("Seeded 'คุณลักษณะอันพึงประสงค์' with sub-topics.")

    # Template 2: Key Competencies
    comp_template = AssessmentTemplate.query.filter_by(name='สมรรถนะสำคัญของผู้เรียน').first()
    if not comp_template:
        comp_template = AssessmentTemplate(name='สมรรถนะสำคัญของผู้เรียน', description='ตามหลักสูตรแกนกลางการศึกษาขั้นพื้นฐาน')
        db.session.add(comp_template)
        # db.session.commit()
        # Add rubric levels to this template
        for r_data in rubric_levels_data:
            comp_template.rubric_levels.append(RubricLevel(**r_data))

        # Add topics for this template
        comp_topics = [
            'ความสามารถในการสื่อสาร', 'ความสามารถในการคิด', 'ความสามารถในการแก้ปัญหา',
            'ความสามารถในการใช้ทักษะชีวิต', 'ความสามารถในการใช้เทคโนโลยี'
        ]
        for topic_name in comp_topics:
            comp_template.topics.append(AssessmentTopic(name=topic_name))
        print("Seeded 'สมรรถนะสำคัญของผู้เรียน'.")
        
    db.session.commit()

    # --- 9. Create Comprehensive Sample Subjects ---
    print("Seeding sample subjects...")
    # (ส่วนนี้เหมือนเดิม แต่ตอนนี้จะทำงานได้ครบถ้วนเพราะข้อมูลพื้นฐานถูก commit ครบแล้ว)
    
    # ดึงข้อมูลพื้นฐานที่ต้องใช้ทั้งหมด
    thai_g = SubjectGroup.query.filter(SubjectGroup.name.like('%ภาษาไทย%')).first()
    math_g = SubjectGroup.query.filter(SubjectGroup.name.like('%คณิตศาสตร์%')).first()
    sci_g = SubjectGroup.query.filter(SubjectGroup.name.like('%วิทยาศาสตร์%')).first()
    social_g = SubjectGroup.query.filter(SubjectGroup.name.like('%สังคมศึกษา%')).first()
    health_g = SubjectGroup.query.filter(SubjectGroup.name.like('%สุขศึกษา%')).first()
    art_g = SubjectGroup.query.filter(SubjectGroup.name.like('%ศิลปะ%')).first()
    work_g = SubjectGroup.query.filter(SubjectGroup.name.like('%การงานอาชีพ%')).first()
    lang_g = SubjectGroup.query.filter(SubjectGroup.name.like('%ภาษาต่างประเทศ%')).first()
    
    base_t = SubjectType.query.filter_by(name='รายวิชาพื้นฐาน').first()
    add_t = SubjectType.query.filter_by(name='รายวิชาเพิ่มเติม').first()

    if not all([base_t, add_t]):
        print("Error: Subject Types 'รายวิชาพื้นฐาน' or 'รายวิชาเพิ่มเติม' not found.")
        return
    
    grades = GradeLevel.query.order_by(GradeLevel.id).all()
    m1, m2, m3, m4, m5, m6 = grades[0], grades[1], grades[2], grades[3], grades[4], grades[5]
    
    acad_year = AcademicYear.query.filter_by(year=2568).first() # Make sure we have the academic year

    subjects_data = [
        {'code': 'ท21101', 'name': 'ภาษาไทย 1', 'credit': 1.5, 'group': thai_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ท22101', 'name': 'ภาษาไทย 3', 'credit': 1.5, 'group': thai_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ท23101', 'name': 'ภาษาไทย 5', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ท24101', 'name': 'ภาษาไทย 7', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ท25101', 'name': 'ภาษาไทย 9', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ท26101', 'name': 'ภาษาไทย 11', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ท27101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ท28101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ท29101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ท31101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 4', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ท32101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ท33101', 'name': 'ภาษาไทยพื้นฐาน ม.ปลาย 6', 'credit': 1.0, 'group': thai_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ค21101', 'name': 'คณิตศาสตร์ 1', 'credit': 1.5, 'group': math_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ค22101', 'name': 'คณิตศาสตร์ 3', 'credit': 1.5, 'group': math_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ค23101', 'name': 'คณิตศาสตร์ 5', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ค24101', 'name': 'คณิตศาสตร์ 7', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ค25101', 'name': 'คณิตศาสตร์ 9', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ค26101', 'name': 'คณิตศาสตร์ 11', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ค20101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ค20101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ค20101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ค31101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ค32101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ค33101', 'name': 'คณิตศาสตร์พื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': math_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ว21101', 'name': 'วิทยาศาสตร์ 1', 'credit': 1.5, 'group': sci_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ว22101', 'name': 'วิทยาศาสตร์ 3', 'credit': 1.5, 'group': sci_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ว23101', 'name': 'วิทยาศาสตร์ 5', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ว24101', 'name': 'วิทยาศาสตร์ 7', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ว25101', 'name': 'วิทยาศาสตร์ 9', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ว26101', 'name': 'วิทยาศาสตร์ 11', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ว20101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ว20101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ว20101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ว31101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ว32101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ว33101', 'name': 'วิทยาศาสตร์พื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': sci_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ส21101', 'name': 'สังคมศึกษา 1', 'credit': 1.5, 'group': social_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ส22101', 'name': 'สังคมศึกษา 3', 'credit': 1.5, 'group': social_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ส23101', 'name': 'สังคมศึกษา 5', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ส24101', 'name': 'สังคมศึกษา 7', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ส25101', 'name': 'สังคมศึกษา 9', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ส26101', 'name': 'สังคมศึกษา 11', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ส20101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ส20101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ส20101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ส31101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ส32101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ส33101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ส21102', 'name': 'สังคมศึกษา 2', 'credit': 1.5, 'group': social_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ส22102', 'name': 'สังคมศึกษา 4', 'credit': 1.5, 'group': social_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ส23102', 'name': 'สังคมศึกษา 6', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ส24102', 'name': 'สังคมศึกษา 8', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ส25102', 'name': 'สังคมศึกษา 10', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ส26102', 'name': 'สังคมศึกษา 12', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ส30101', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m1]},
        {'code': 'ส30102', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 4', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m2]},
        {'code': 'ส30103', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 6', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m3]},
        {'code': 'ส31102', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 2', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m4]},
        {'code': 'ส32102', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 4', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m5]},
        {'code': 'ส33102', 'name': 'สังคมศึกษาพื้นฐาน ม.ปลาย 6', 'credit': 1.0, 'group': social_g, 'type': base_t, 'grades': [m6]},
        {'code': 'พ21101', 'name': 'สุขศึกษาและพลศึกษา 1', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m1]},
        {'code': 'พ22101', 'name': 'สุขศึกษาและพลศึกษา 3', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m2]},
        {'code': 'พ23101', 'name': 'สุขศึกษาและพลศึกษา 5', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m3]},
        {'code': 'พ24101', 'name': 'สุขศึกษาและพลศึกษา 7', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m4]},
        {'code': 'พ25101', 'name': 'สุขศึกษาและพลศึกษา 9', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m5]},
        {'code': 'พ26101', 'name': 'สุขศึกษาและพลศึกษา 11', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m6]},
        {'code': 'พ31101', 'name': 'สุขศึกษาและพลศึกษาพื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m4]},
        {'code': 'พ32101', 'name': 'สุขศึกษาและพลศึกษาพื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m5]},
        {'code': 'พ33101', 'name': 'สุขศึกษาและพลศึกษาพื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': health_g, 'type': base_t, 'grades': [m6]},
        {'code': 'ศ21101', 'name': 'ศิลปะ 1', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m1]},
        {'code': 'ศ22101', 'name': 'ศิลปะ 3', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m2]},
        {'code': 'ศ23101', 'name': 'ศิลปะ 5', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m3]},
        {'code': 'ศ31101', 'name': 'ศิลปะพื้นฐาน ม.ปลาย 1', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m4]},
        {'code': 'ศ32101', 'name': 'ศิลปะพื้นฐาน ม.ปลาย 3', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m5]},
        {'code': 'ศ33101', 'name': 'ศิลปะพื้นฐาน ม.ปลาย 5', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m6]},
        {'code': 'ศ41101', 'name': 'ศิลปะเพิ่มเติม ม.ปลาย 1', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m4]},
        {'code': 'ศ42101', 'name': 'ศิลปะเพิ่มเติม ม.ปลาย 3', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m5]},
        {'code': 'ศ43101', 'name': 'ศิลปะเพิ่มเติม ม.ปลาย 5', 'credit': 1.0, 'group': art_g, 'type': add_t, 'grades': [m6]}
    ]
    
    for s_data in subjects_data:
        if not Subject.query.filter_by(subject_code=s_data['code']).first():
            grades_list = s_data.pop('grades')
            subject = Subject(
                subject_code=s_data['code'],
                name=s_data['name'],
                credit=s_data['credit'],
                subject_group=s_data['group'],
                subject_type=s_data['type']
            )
            subject.grade_levels = grades_list
            db.session.add(subject)

            # VVV Add LessonPlan creation logic here VVV
            # Flush to get the subject ID before creating the lesson plan
            db.session.flush() 

            if acad_year:
                lesson_plan = LessonPlan(
                    subject_id=subject.id,
                    academic_year_id=acad_year.id
                )
                db.session.add(lesson_plan)

    db.session.commit()
    print("Sample subjects and lesson plans seeded.")
    print("Database seeded successfully!")