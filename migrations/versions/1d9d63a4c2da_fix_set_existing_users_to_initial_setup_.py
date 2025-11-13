"""Fix: Set existing users to initial_setup_complete=true

Revision ID: 1d9d63a4c2da
Revises: e662279ecbc1
Create Date: 2025-11-13 16:37:31.070214

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d9d63a4c2da'
down_revision = 'e662279ecbc1'
branch_labels = None
depends_on = None


def upgrade():
    # --- [FIX] ---
    # เราจะตั้งค่าให้ผู้ใช้ "ทุกคน" ที่มีอยู่ในปัจจุบัน
    # มีสถานะ initial_setup_complete = true (เพราะถือเป็นผู้ใช้เก่า)
    # (ใช้ 'true' สำหรับ PostgreSQL)
    op.execute('UPDATE "user" SET initial_setup_complete = true')
    # --- [END FIX] ---


def downgrade():
    # --- [FIX] ---
    # (คำสั่งย้อนกลับ คือตั้งค่าให้เป็น false เหมือนเดิม)
    op.execute('UPDATE "user" SET initial_setup_complete = false')
    # --- [END FIX] ---