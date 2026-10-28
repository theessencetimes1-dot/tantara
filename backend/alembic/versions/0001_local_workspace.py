"""Legacy revision marker retained so existing local workspaces can upgrade.

The previous revision performed an init_db call rather than recording a real
schema migration. This no-op marker is the parent of the real baseline revision.
"""

revision = "0001_local_workspace"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
