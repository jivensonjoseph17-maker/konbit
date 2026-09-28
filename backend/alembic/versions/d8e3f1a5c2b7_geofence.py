"""Zòn otorize (geofence): paramèt biznis + distans sou chak pwentaj

Revision ID: d8e3f1a5c2b7
Revises: c7d2e9a4b1f6
Create Date: 2026-09-28

organizations: geofence_mode ("off" | "flag" | "block"), geofence_lat,
geofence_lng, geofence_radius_m.
time_entries: clock_in_distance_m, clock_out_distance_m, outside_zone.
Gade routers/geofence.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "d8e3f1a5c2b7"
down_revision = "c7d2e9a4b1f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column(
        "geofence_mode", sa.String(length=10), nullable=False, server_default="off"))
    op.add_column("organizations", sa.Column("geofence_lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("organizations", sa.Column("geofence_lng", sa.Numeric(10, 7), nullable=True))
    op.add_column("organizations", sa.Column("geofence_radius_m", sa.Integer(), nullable=True))

    op.add_column("time_entries", sa.Column("clock_in_distance_m", sa.Integer(), nullable=True))
    op.add_column("time_entries", sa.Column("clock_out_distance_m", sa.Integer(), nullable=True))
    op.add_column("time_entries", sa.Column(
        "outside_zone", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    # batch: SQLite pa ka retire yon kolòn san rekreye tab la.
    with op.batch_alter_table("time_entries") as batch:
        batch.drop_column("outside_zone")
        batch.drop_column("clock_out_distance_m")
        batch.drop_column("clock_in_distance_m")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("geofence_radius_m")
        batch.drop_column("geofence_lng")
        batch.drop_column("geofence_lat")
        batch.drop_column("geofence_mode")
