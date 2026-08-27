# app/models/db_models.py
from sqlalchemy import Column, String, Float, DateTime
from geoalchemy2 import Geometry
from app.database import Base

class OilSpill(Base):
    __tablename__ = "oil_spills"

    spill_id = Column(String, primary_key=True, index=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Store geospatial data strictly as EPSG:4326 (WGS 84 - Lon/Lat)
    centroid = Column(Geometry(geometry_type='POINT', srid=4326))
    polygon = Column(Geometry(geometry_type='POLYGON', srid=4326))
    
    area_km2 = Column(Float)
    estimated_age_hours = Column(Float)
    confidence_score = Column(Float)