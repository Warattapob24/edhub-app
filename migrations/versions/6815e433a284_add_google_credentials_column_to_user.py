"""Add google_credentials column to User

Revision ID: 6815e433a284
Revises: 7a57f17885e0
Create Date: 2025-11-12 14:54:46.435288
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6815e433a284'
down_revision = '7a57f17885e0'
branch_labels = None
depends_on = None


def upgrade():
    # เพิ่มคอลัมน์แบบ nullable ก่อน
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('initial_setup_complete', sa.Boolean(), nullable=True))

    # ตั้งค่า default สำหรับ record เดิม
    op.execute('UPDATE "user" SET initial_setup_complete = false')

    # เปลี่ยนคอลัมน์ให้เป็น NOT NULL หลังจากอัปเดตค่าแล้ว
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('initial_setup_complete', nullable=False)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('initial_setup_complete')
