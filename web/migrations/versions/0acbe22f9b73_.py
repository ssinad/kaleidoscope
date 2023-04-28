"""empty message

Revision ID: 0acbe22f9b73
Revises: 
Create Date: 2023-03-16 18:22:41.716092

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0acbe22f9b73"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('model_instance',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('state_name', sa.Enum('PENDING', 'LAUNCHING', 'LOADING', 'ACTIVE', 'FAILED', 'COMPLETED', name='modelinstancestates'), nullable=False),
    sa.Column('host', sa.String(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('model_instance_generation',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('model_instance_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['model_instance_id'], ['model_instance.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('model_instance_generation')
    op.drop_table('model_instance')
    # ### end Alembic commands ###
