# FILE: migrations/versions/6a6946c8575c_add_program_id_to_classroom.py
"""Add program_id to classroom

Revision ID: 6a6946c8575c
Revises: 04f426a09d38
Create Date: 2025-10-31 22:47:22.928992
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6a6946c8575c'
down_revision = '04f426a09d38'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn) # <-- เรียก inspector ไว้ด้านบน

    # --- classroom ---
    # (ส่วนนี้ทำงานถูกต้องแล้วจากครั้งก่อน)
    classroom_columns = [c['name'] for c in inspector.get_columns('classroom')]

    with op.batch_alter_table('classroom', recreate="never") as batch_op:
        
        if 'program_id' not in classroom_columns:
            batch_op.add_column(sa.Column('program_id', sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f('ix_classroom_program_id'), ['program_id'], unique=False)
        else:
            print("Column 'program_id' already exists in 'classroom'. Skipping add_column.")

        if 'room_id' not in classroom_columns:
            batch_op.add_column(sa.Column('room_id', sa.Integer(), nullable=True))
        else:
            print("Column 'room_id' already exists in 'classroom'. Skipping add_column.")

    # --- curriculum ---
    # (ส่วนที่แก้ไขลำดับตรรกะใหม่)
    
    curriculum_columns = [c['name'] for c in inspector.get_columns('curriculum')]

    # ขั้นตอนที่ 1: เพิ่มคอลัมน์ (อนุญาต NULL ชั่วคราว)
    with op.batch_alter_table('curriculum', recreate="never") as batch_op:
        if 'program_id' not in curriculum_columns:
            print("Adding 'program_id' (nullable=True) to 'curriculum'.")
            batch_op.add_column(sa.Column('program_id', sa.Integer(), nullable=True)) # <-- แก้เป็น True
            batch_op.create_index(batch_op.f('ix_curriculum_program_id'), ['program_id'], unique=False)
        else:
            print("Column 'program_id' already exists in 'curriculum'. Skipping add_column.")

    # ขั้นตอนที่ 2: อัปเดตข้อมูลเก่า (เมื่อคอลัมน์มีอยู่แน่นอนแล้ว)
    try:
        print("Updating existing 'curriculum' rows to set program_id=1.")
        op.execute("UPDATE curriculum SET program_id = 1 WHERE program_id IS NULL")
    except Exception as e:
        print(f"Error updating curriculum rows (should not happen now): {e}")

    # ขั้นตอนที่ 3: บังคับ NOT NULL (เมื่อข้อมูลพร้อมแล้ว)
    try:
        with op.batch_alter_table('curriculum', recreate="auto") as batch_op: # ใช้ recreate="auto"
            print("Altering 'program_id' in 'curriculum' to non-nullable.")
            batch_op.alter_column('program_id',
                                  existing_type=sa.Integer(),
                                  nullable=False,
                                  server_default='1') # ระบุ server_default
    except Exception as e:
        print(f"Warning: Could not alter 'program_id' to non-nullable (might be SQLite limitation): {e}")

        
def downgrade():
    # --- curriculum ---
    with op.batch_alter_table('curriculum', recreate="never") as batch_op:
        # batch_op.drop_constraint('fk_curriculum_program_id', type_='foreignkey') # (ไม่มีใน upgrade)
        batch_op.drop_index(batch_op.f('ix_curriculum_program_id'))
        batch_op.drop_column('program_id')
        # constraints เดิมไม่ถูกแก้

    # --- classroom ---
    with op.batch_alter_table('classroom', recreate="never") as batch_op:
        # batch_op.drop_constraint('fk_classroom_program_id', type_='foreignkey') # (ไม่มีใน upgrade)
        # batch_op.drop_constraint('fk_classroom_room_id', type_='foreignkey') # (ไม่มีใน upgrade)
        batch_op.drop_index(batch_op.f('ix_classroom_program_id'))
        batch_op.drop_column('room_id')
        batch_op.drop_column('program_id')