"""Add level_group to GradeLevel

Revision ID: b3b045a29bf6
Revises: 7b76a297affd
Create Date: 2025-10-12 14:39:27.987592
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b3b045a29bf6'
down_revision = '7b76a297affd'
branch_labels = None
depends_on = None


def upgrade():
    # ✅ เพิ่มคอลัมน์ใหม่ให้กับ grade_level
    with op.batch_alter_table('grade_level', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('level_group', sa.String(length=50), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_grade_level_level_group'), ['level_group'], unique=False
        )

    # ✅ เพิ่มคอลัมน์ ms_remediated_status ให้ course_grade ด้วย (ถ้าต้องการ)
    with op.batch_alter_table('course_grade', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('ms_remediated_status', sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade():
    # ✅ ลบคอลัมน์ออกตามลำดับ
    with op.batch_alter_table('course_grade', schema=None) as batch_op:
        batch_op.drop_column('ms_remediated_status')

    with op.batch_alter_table('grade_level', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_grade_level_level_group'))
        batch_op.drop_column('level_group')
