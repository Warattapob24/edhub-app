# path: seed.py (ฉบับสมบูรณ์)

from app import db
from app.models import (AssessmentMethod, User, Role, LearningArea, GradeLevel, 
                        DesirableCharacteristic, Competency, ReadingAnalysisWriting)

def seed_data():
    """Seeds the database with ALL initial data required for the app."""
    try:
        print("--- Seeding database... ---")

        # --- ลบข้อมูลเก่าก่อนเพื่อความสะอาด ---
        print("\n[PRE-STEP] Clearing old data...")
        # เรียงลำดับการลบจากตารางที่ไม่มี Foreign Key อ้างอิงไปหาตารางอื่นก่อน
        DesirableCharacteristic.query.delete()
        Competency.query.delete()
        ReadingAnalysisWriting.query.delete()
        AssessmentMethod.query.delete()
        
        # ต้องลบ User ก่อน Role เพราะ User มี Foreign Key ไปหา Role
        # และต้องเคลียร์ learning_area.head ก่อนลบ User
        for area in LearningArea.query.all():
            area.head_id = None
        db.session.commit()

        User.query.delete()
        Role.query.delete()
        LearningArea.query.delete()
        GradeLevel.query.delete()
        
        db.session.commit()
        print("SUCCESS: Old data cleared.")
        
        # --- 1. Seeding Core Data (GradeLevels & LearningAreas) ---
        print("\n[STEP 1] Seeding Core Data...")
        grades = ['มัธยมศึกษาปีที่ 1', 'มัธยมศึกษาปีที่ 2', 'มัธยมศึกษาปีที่ 3']
        for g_name in grades:
            db.session.add(GradeLevel(name=g_name))
        print("  - Grade Levels created.")

        areas = ['ภาษาไทย', 'คณิตศาสตร์', 'วิทยาศาสตร์และเทคโนโลยี', 'สังคมศึกษา ศาสนา และวัฒนธรรม', 'สุขศึกษาและพลศึกษา', 'ศิลปะ', 'การงานอาชีพ', 'ภาษาต่างประเทศ']
        for a_name in areas:
            db.session.add(LearningArea(name=a_name))
        print("  - Learning Areas created.")
        db.session.commit()
        print("SUCCESS: Core data committed.")

        # --- 2. Seeding Roles ---
        print("\n[STEP 2] Seeding Roles...")
        roles_to_create = ['Admin', 'DepartmentHead', 'Teacher', 'Student']
        for r_name in roles_to_create:
            db.session.add(Role(name=r_name))
        print(f"  - Roles {roles_to_create} created.")
        db.session.commit()
        print("SUCCESS: Roles committed.")

        # --- 3. Seeding Users ---
        print("\n[STEP 3] Seeding Users...")
        admin_role = Role.query.filter_by(name='Admin').first()
        head_role = Role.query.filter_by(name='DepartmentHead').first()
        teacher_role = Role.query.filter_by(name='Teacher').first()

        admin_user = User(username='admin', full_name='System Administrator')
        admin_user.set_password('admin123')
        admin_user.roles.append(admin_role)
        db.session.add(admin_user)
        print("  - User 'admin' created.")

        head_user = User(username='head_sci', full_name='หัวหน้าสาระวิทย์')
        head_user.set_password('1234')
        head_user.roles.append(head_role)
        db.session.add(head_user)
        print("  - User 'head_sci' created.")

        teacher_a = User(username='teacher_a', full_name='ครู A')
        teacher_a.set_password('1234')
        teacher_a.roles.append(teacher_role)
        db.session.add(teacher_a)
        print("  - User 'teacher_a' created.")
            
        db.session.commit()
        print("SUCCESS: Users committed.")

        # --- 4. Assigning Head to Area ---
        print("\n[STEP 4] Assigning Head to Learning Area...")
        science_area = LearningArea.query.filter_by(name='วิทยาศาสตร์และเทคโนโลยี').first()
        head_user_to_assign = User.query.filter_by(username='head_sci').first()
        if science_area and head_user_to_assign:
            science_area.head = head_user_to_assign
            db.session.commit()
            print("SUCCESS: Assigned 'head_sci' to 'วิทยาศาสตร์และเทคโนโลยี'.")
        
        # --- 5. Seeding Assessment Data ---
        print("\n[STEP 5] Seeding Assessment Data...")
        desirable_characteristics = {
            'รักชาติ ศาสน์ กษัตริย์': ['เป็นพลเมืองดีของชาติ', 'ธำรงไว้ซึ่งความเป็นชาติไทย', 'ศรัทธา ยึดมั่น และปฏิบัติตนตามหลักของศาสนา', 'เคารพเทิดทูนสถาบันพระมหากษัตริย์'],
            'ซื่อสัตย์สุจริต': ['ประพฤติตรงตามความเป็นจริงต่อตนเองทั้งทางกาย วาจา ใจ', 'ประพฤติตรงตามความเป็นจริงต่อผู้อื่นทั้งทางกาย วาจา ใจ'],
            'มีวินัย': ['ปฏิบัติตามข้อตกลง กฎเกณฑ์ ระเบียบ ข้อบังคับของครอบครัว โรงเรียน และสังคม'],
            'ใฝ่เรียนรู้': ['ตั้งใจ เพียรพยายามในการเรียน และเข้าร่วมกิจกรรมการเรียนรู้', 'แสวงหาความรู้จากแหล่งเรียนรู้ต่างๆ'],
            'อยู่อย่างพอเพียง': ['ดำเนินชีวิตอย่างพอประมาณ มีเหตุผล รอบคอบ มีคุณธรรม', 'มีภูมิคุ้มกันในตัวที่ดี ปรับตัวเพื่ออยู่ในสังคมได้อย่างมีความสุข'],
            'มุ่งมั่นในการทำงาน': ['ตั้งใจและรับผิดชอบในการปฏิบัติหน้าที่การงาน', 'ทำงานด้วยความเพียรพยายาม และอดทนเพื่อให้งานสำเร็จตามเป้าหมาย'],
            'รักความเป็นไทย': ['ภาคภูมิใจในขนบธรรมเนียมประเพณี ศิลปะ วัฒนธรรมไทย และมีความกตัญญูกตเวที', 'เห็นคุณค่าและใช้ภาษาไทยในการสื่อสาร', 'อนุรักษ์และสืบทอดภูมิปัญญาไทย'],
            'มีจิตสาธารณะ': ['ช่วยเหลือผู้อื่นด้วยความเต็มใจโดยไม่หวังผลตอบแทน', 'เข้าร่วมกิจกรรมที่เป็นประโยชน์ต่อโรงเรียน ชุมชน และสังคม']
        }
        for name, indicators in desirable_characteristics.items():
            db.session.add(DesirableCharacteristic(name=name, indicators=indicators))
        
        competencies = {
            'สมรรถนะการจัดการตนเอง': [], 'สมรรถนะการคิดขั้นสูง': [], 'สมรรถนะการสื่อสาร': [],
            'สมรรถนะการรวมพลังทำงานเป็นทีม': [], 'สมรรถนะการเป็นพลเมืองที่เข้มแข็ง': [],
            'สมรรถนะการอยู่ร่วมกับธรรมชาติและวิทยาการอย่างยั่งยืน': []
        }
        for name, indicators in competencies.items():
            db.session.add(Competency(name=name, indicators=indicators))

        reading_analysis_writing = {
            'การอ่าน': ['อ่านเพื่อหาข้อมูลและสารสนเทศ', 'จับประเด็นสำคัญจากเรื่องที่อ่าน', 'ประเมินความน่าเชื่อถือของสิ่งที่อ่าน'],
            'การคิดวิเคราะห์': ['วิเคราะห์และตีความข้อมูล', 'เชื่อมโยงความรู้และประสบการณ์', 'แสดงความคิดเห็นและเสนอแนวทางแก้ปัญหา'],
            'การเขียน': ['เขียนถ่ายทอดความเข้าใจและความคิด', 'เขียนแสดงความคิดเห็นพร้อมเหตุผล', 'เขียนถูกต้องตามหลักภาษา']
        }
        for name, sub_categories in reading_analysis_writing.items():
            db.session.add(ReadingAnalysisWriting(name=name, sub_categories=sub_categories))
        
        assessment_methods = {
            'แบบทดสอบ': 'ใช้ประเมินความรู้ความเข้าใจในเนื้อหาทางวิชาการ...',
            'รูบริก': 'ใช้ประเมินผลงานหรือการปฏิบัติที่มีความซับซ้อน...',
            'แฟ้มสะสมผลงาน': 'ใช้รวบรวมผลงานเพื่อแสดงพัฒนาการ...',
        }
        for name, desc in assessment_methods.items():
            db.session.add(AssessmentMethod(name=name, description=desc))

        db.session.commit()
        print("SUCCESS: Assessment data committed.")
        print("\n--- Database seeding finished successfully! ---")

    except Exception as e:
        db.session.rollback()
        print(f"\nAN ERROR OCCURRED: {e}")
        print("INFO: Database transaction has been rolled back.")