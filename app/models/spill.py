from sqlalchemy import Column, Integer, String, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base

class OilSpillDetection(Base):
    __tablename__ = "oil_spill_detections"

    id = Column(Integer, primary_key=True, index=True)
    spill_id = Column(String, unique=True, index=True, nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    centroid_lat = Column(Float, nullable=False)
    centroid_lon = Column(Float, nullable=False)

    # Store polygon as JSONB (list of [lon, lat] pairs)
    polygon = Column(JSONB, nullable=False)

    area_km2 = Column(Float, nullable=False)
    estimated_age_hours = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    cloudinary_url = Column(String, nullable=False)
    source_image_id = Column(String, nullable=True)

    # Keep the exact ML output just in case
    raw_prediction = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())