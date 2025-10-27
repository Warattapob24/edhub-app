import json

# Sample data mimicking GradeLevel -> Subject relationships
all_grades = [
    { 'id': 1, 'name': 'มัธยมศึกษาปีที่ 1', 'subjects': [
        {'id': 11, 'subject_code': 'ENG101', 'name': 'ภาษาอังกฤษพื้นฐาน', 'type': 'ภาษาต่างประเทศ'},
        {'id': 12, 'subject_code': 'MATH101', 'name': 'คณิตศาสตร์พื้นฐาน', 'type': 'คณิตศาสตร์'}
    ]},
    { 'id': 2, 'name': 'มัธยมศึกษาปีที่ 2', 'subjects': [
        {'id': 21, 'subject_code': 'ENG201', 'name': 'ภาษาอังกฤษต่อเนื่อง', 'type': 'ภาษาต่างประเทศ'}
    ]},
    { 'id': 3, 'name': 'มัธยมศึกษาปีที่ 3', 'subjects': [] }
]

master_by_string = {}
master_by_number = {}
for grade in all_grades:
    entries = []
    for s in grade['subjects']:
        entries.append({
            'id': s['id'],
            'code': s.get('subject_code') or s.get('code',''),
            'name': s['name'],
            'type': s.get('type','ทั่วไป')
        })
    master_by_string[str(grade['id'])] = entries
    master_by_number[grade['id']] = entries

master_curriculum = {
    'by_string': master_by_string,
    'by_number': master_by_number
}

print(json.dumps(master_curriculum, ensure_ascii=False))
