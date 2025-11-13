"""Manually add all Google columns

Revision ID: e662279ecbc1
Revises: 7a57f17885e0
Create Date: 2025-11-13 13:55:41.287895

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e662279ecbc1'
down_revision = '7a57f17885e0'
branch_labels = None
depends_on = None


def upgrade():
    # === ส่วนที่ 1: อัปเดตตาราง "user" (สำหรับ Google Auth) ===
    
    # [FIX] ขั้นตอนที่ 1.1: เพิ่มคอลัมน์ทั้งหมดแบบ Nullable=True ก่อน
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('initial_setup_complete', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('google_credentials_json', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_user_google_id'), ['google_id'], unique=True)

    # [FIX] ขั้นตอนที่ 1.2: ตั้งค่า Default 'false' ให้กับแถวที่มีอยู่ (สำหรับ PostgreSQL)
    op.execute('UPDATE "user" SET initial_setup_complete = false')

    # [FIX] ขั้นตอนที่ 1.3: เปลี่ยนคอลัมน์เป็น Non-Nullable
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('initial_setup_complete',
               existing_type=sa.BOOLEAN(),
               nullable=False)

    # === ส่วนที่ 2: อัปเดตตาราง "course" (สำหรับ Form กลางภาค/ปลายภาค) ===
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.add_column(sa.Column('midterm_google_form_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('midterm_google_sheet_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('final_google_form_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('final_google_sheet_id', sa.String(length=255), nullable=True))

    # === ส่วนที่ 3: อัปเดตตาราง "graded_item" (สำหรับ Form คะแนนเก็บ) ===
    # (นี่คือคอลัมน์ที่ `autogenerate` ของท่านสร้าง แต่เราต้องเพิ่มเอง)
    with op.batch_alter_table('graded_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_form_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('google_sheet_id', sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f('ix_graded_item_google_form_id'), ['google_form_id'], unique=False)


def downgrade():
    # Downgrade ในลำดับย้อนกลับ
    with op.batch_alter_table('graded_item', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_graded_item_google_form_id'))
        batch_op.drop_column('google_sheet_id')
        batch_op.drop_column('google_form_id')

    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.drop_column('final_google_sheet_id')
        batch_op.drop_column('final_google_form_id')
        batch_op.drop_column('midterm_google_sheet_id')
        batch_op.drop_column('midterm_google_form_id')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_google_id'))
        batch_op.drop_column('google_credentials_json')
        batch_op.drop_column('initial_setup_complete')
        batch_op.drop_column('google_id')