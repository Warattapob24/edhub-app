PRAGMA foreign_keys=off;

CREATE TABLE course_grade_temp AS SELECT * FROM course_grade;
DROP TABLE course_grade;

CREATE TABLE course_grade (
    -- ใส่คอลัมน์ทั้งหมดเดิม ยกเว้น ms_remediated_status
    id INTEGER PRIMARY KEY,
    ... -- (ใส่ schema เดิม)
);

INSERT INTO course_grade (SELECT * FROM course_grade_temp);
DROP TABLE course_grade_temp;

PRAGMA foreign_keys=on;
