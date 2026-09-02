from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spill import OilSpillDetection


class SpillRepository:

    @staticmethod
    async def create_spill(
        db: AsyncSession,
        spill_data: dict,
    ) -> OilSpillDetection:

        new_spill = OilSpillDetection(
            **spill_data
        )

        try:
            db.add(new_spill)

            await db.commit()

            await db.refresh(new_spill)

            return new_spill

        except IntegrityError as exc:
            await db.rollback()

            raise ValueError(
                f"Spill with ID "
                f"'{spill_data.get('spill_id')}' "
                f"already exists."
            ) from exc

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_spill(
        db: AsyncSession,
        spill_id: str,
    ) -> OilSpillDetection | None:

        result = await db.execute(
            select(OilSpillDetection).where(
                OilSpillDetection.spill_id == spill_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_spills(
        db: AsyncSession,
    ) -> list[OilSpillDetection]:

        result = await db.execute(
            select(OilSpillDetection).order_by(
                OilSpillDetection.detected_at.asc()
            )
        )

        return list(result.scalars().all())