from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spill import OilSpill


class SpillRepository:
    @staticmethod
    async def create_spill(
        db: AsyncSession,
        spill_data: dict,
    ) -> OilSpill:
        new_spill = OilSpill(**spill_data)

        try:
            db.add(new_spill)
            await db.commit()
            await db.refresh(new_spill)

            return new_spill

        except IntegrityError as exc:
            await db.rollback()
            raise ValueError(
                f"Spill with ID '{spill_data.get('spill_id')}' already exists."
            ) from exc

        except Exception:
            await db.rollback()
            raise