from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.core.database import Base


class OilSpill(Base):
    __tablename__ = "oil_spills"

    spill_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    detected_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    centroid: Mapped[object] = mapped_column(
        Geometry(
            geometry_type="POINT",
            srid=4326,
            spatial_index=True,
        ),
        nullable=False,
    )

    polygon: Mapped[object] = mapped_column(
        Geometry(
            geometry_type="POLYGON",
            srid=4326,
            spatial_index=True,
        ),
        nullable=False,
    )

    area_km2: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    estimated_age_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )