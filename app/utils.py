# FILE: app/utils.py

from .models import Score, GradedItem, LearningUnit, Enrollment

def get_grade_from_score(percentage):
    if percentage >= 80: return 4.0
    if percentage >= 75: return 3.5
    if percentage >= 70: return 3.0
    if percentage >= 65: return 2.5
    if percentage >= 60: return 2.0
    if percentage >= 55: return 1.5
    if percentage >= 50: return 1.0
    return 0.0

def calculate_student_final_score(student_id, plan_id):
    # 1. หาคะแนนเต็มทั้งหมดของแผนการสอนนี้
    learning_unit_ids = [unit.id for unit in LearningUnit.query.filter_by(lesson_plan_id=plan_id).all()]
    total_max_score = db.session.query(db.func.sum(GradedItem.max_score)).filter(GradedItem.learning_unit_id.in_(learning_unit_ids)).scalar() or 0

    # (เพิ่มคะแนนเต็มของกลางภาค/ปลายภาค หากมี)
    # TODO: This logic needs to be expanded to include exam max scores from LearningUnit model

    if total_max_score == 0:
        return {'score': 0, 'percentage': 0, 'grade': 0.0, 'is_pass': False}

    # 2. หารคะแนนรวมที่นักเรียนทำได้
    student_total_score = db.session.query(db.func.sum(Score.score)).filter(
        Score.student_id == student_id,
        Score.graded_item_id.isnot(None) # รวมเฉพาะคะแนนเก็บก่อน
    ).scalar() or 0

    # (เพิ่มคะแนนสอบของนักเรียน หากมี)
    # TODO: This logic needs to be expanded to include student's exam scores from Enrollment model

    percentage = (student_total_score / total_max_score) * 100 if total_max_score > 0 else 0
    grade = get_grade_from_score(percentage)
    is_pass = grade >= 1.0

    return {
        'score': student_total_score,
        'percentage': percentage,
        'grade': grade,
        'is_pass': is_pass
    }