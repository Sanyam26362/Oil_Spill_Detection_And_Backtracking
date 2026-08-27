from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Vessel(Base):
    __tablename__ = "vessels"

    vessel_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    shiptype: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Human-readable broad vessel category.
    # Example: Cargo, Tanker, Fishing, Passenger.
    shiptype_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ais_positions: Mapped[list["AISPosition"]] = relationship(
        back_populates="vessel",
        passive_deletes=True,
    )


class AISPosition(Base):
    __tablename__ = "ais_positions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    vessel_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "vessels.vessel_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    speed: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    course: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    heading: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    geometry: Mapped[object] = mapped_column(
        Geometry(
            geometry_type="POINT",
            srid=4326,
            spatial_index=True,
        ),
        nullable=False,
    )

    # False = real source data
    # True  = generated/synthetic data
    is_synthetic: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    vessel: Mapped["Vessel"] = relationship(
        back_populates="ais_positions",
    )

    __table_args__ = (
        Index(
            "ix_ais_positions_vessel_timestamp",
            "vessel_id",
            "timestamp",
        ),
    )