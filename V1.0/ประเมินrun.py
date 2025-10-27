# run.py (ฉบับแก้ไขลำดับ)

from app import create_app, db
from app.models import (
    User, Role, Student, Course, CourseComponent, Score, ActivityLog,
    Subject, GradeLevel, ClassGroup, EvaluationTopic, AdditionalAssessment,
    AttendanceRecord, Setting
)

# --- ย้ายบรรทัดนี้ขึ้นมาไว้บนสุด ---
app = create_app()

@app.shell_context_processor
def make_shell_context():
    """
    ทำให้เราสามารถเข้าถึง db และ models ผ่าน `flask shell` ได้โดยไม่ต้อง import เอง
    """
    return {
        'db': db, 'User': User, 'Role': Role, 'Student': Student, 'Course': Course,
        'CourseComponent': CourseComponent, 'Score': Score, 'ActivityLog': ActivityLog,
        'Subject': Subject, 'GradeLevel': GradeLevel, 'Classroom': Classroom,
        'EvaluationTopic': EvaluationTopic, 'AdditionalAssessment': AdditionalAssessment,
        'AttendanceRecord': AttendanceRecord, 'Setting': Setting
    }

@app.cli.command("seed-evaluations")
def seed_evaluations():
    """Adds standard evaluation topics to the database."""
    print("Seeding evaluation topics...")
    
    # ล้างข้อมูลเก่า
    EvaluationTopic.query.delete()
    db.session.commit()

    topics_data = {
        'คุณลักษณะอันพึงประสงค์': {
            'รักชาติ ศาสน์ กษัตริย์': ['เป็นพลเมืองดีของชาติ', 'ธำรงไว้ซึ่งความเป็นชาติไทย', 'ศรัทธา ยึดมั่น และปฏิบัติตนตามหลักของศาสนา', 'เคารพเทิดทูนสถาบันพระมหากษัตริย์'],
            'ซื่อสัตย์สุจริต': ['ประพฤติตรงตามความเป็นจริงต่อตนเองทั้งทางกาย วาจา ใจ', 'ประพฤติตรงตามความเป็นจริงต่อผู้อื่นทั้งทางกาย วาจา ใจ'],
            'มีวินัย': ['ปฏิบัติตามข้อตกลง กฎเกณฑ์ ระเบียบ ข้อบังคับของครอบครัว โรงเรียน และสังคม'],
            'ใฝ่เรียนรู้': ['ตั้งใจ เพียรพยายามในการเรียน และเข้าร่วมกิจกรรมการเรียนรู้', 'แสวงหาความรู้จากแหล่งเรียนรู้ต่างๆ'],
            'อยู่อย่างพอเพียง': ['ดำเนินชีวิตอย่างพอประมาณ มีเหตุผล รอบคอบ มีคุณธรรม', 'มีภูมิคุ้มกันในตัวที่ดี ปรับตัวเพื่ออยู่ในสังคมได้อย่างมีความสุข'],
            'มุ่งมั่นในการทำงาน': ['ตั้งใจและรับผิดชอบในการปฏิบัติหน้าที่การงาน', 'ทำงานด้วยความเพียรพยายาม และอดทนเพื่อให้งานสำเร็จตามเป้าหมาย'],
            'รักความเป็นไทย': ['ภาคภูมิใจในขนบธรรมเนียมประเพณี ศิลปะ วัฒนธรรมไทย และมีความกตัญญูกตเวที', 'เห็นคุณค่าและใช้ภาษาไทยในการสื่อสาร', 'อนุรักษ์และสืบทอดภูมิปัญญาไทย'],
            'มีจิตสาธารณะ': ['ช่วยเหลือผู้อื่นด้วยความเต็มใจโดยไม่หวังผลตอบแทน', 'เข้าร่วมกิจกรรมที่เป็นประโยชน์ต่อโรงเรียน ชุมชน และสังคม']
        },
    'สมรรถนะ': {
        'สมรรถนะการจัดการตนเอง': [],
        'สมรรถนะการคิดขั้นสูง': [],
        'สมรรถนะการสื่อสาร': [],
        'สมรรถนะการรวมพลังทำงานเป็นทีม': [],
        'สมรรถนะการเป็นพลเมืองที่เข้มแข็ง': [],
        'สมรรถนะการอยู่ร่วมกับธรรมชาติและวิทยาการอย่างยั่งยืน': []
    },
    'การอ่าน คิดวิเคราะห์ และเขียน': {
    'การอ่าน': [
        'อ่านเพื่อหาข้อมูลและสารสนเทศ',
        'จับประเด็นสำคัญจากเรื่องที่อ่าน',
        'ประเมินความน่าเชื่อถือของสิ่งที่อ่าน'
    ],
    'การคิดวิเคราะห์': [
        'วิเคราะห์และตีความข้อมูล',
        'เชื่อมโยงความรู้และประสบการณ์',
        'แสดงความคิดเห็นและเสนอแนวทางแก้ปัญหา'
    ],
    'การเขียน': [
        'เขียนถ่ายทอดความเข้าใจและความคิด',
        'เขียนแสดงความคิดเห็นพร้อมเหตุผล',
        'เขียนถูกต้องตามหลักภาษา'
    ]
}
}

    for assessment_type, main_topics in topics_data.items():
        main_order = 1
        for main_name, sub_names in main_topics.items():
            main_topic = EvaluationTopic(
                assessment_type=assessment_type,
                name=main_name,
                display_order=main_order
            )
            db.session.add(main_topic)
            print(f"Added Main: {main_name}")
            db.session.flush()

            sub_order = 1
            for sub_name in sub_names:
                sub_topic = EvaluationTopic(
                    assessment_type=assessment_type,
                    name=sub_name,
                    display_order=sub_order,
                    parent_id=main_topic.id
                )
                db.session.add(sub_topic)
                print(f"  - Added Sub: {sub_name}")
                sub_order += 1
            main_order += 1
            
    db.session.commit()
    print("Seeding complete!")

if __name__ == '__main__':
    app.run(debug=True)