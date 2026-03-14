from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.scraper_config import ScraperConfig

router = APIRouter()


class ConfigCreate(BaseModel):
    """Request model for creating scraper configuration."""

    name: str
    target_urls: Optional[str] = None
    keywords: Optional[str] = None
    cooldown_seconds: int = 60
    max_depth: int = 2
    max_pages: int = 100
    timeout_seconds: int = 30
    is_active: bool = True
    use_tor: bool = True


class ConfigUpdate(BaseModel):
    """Request model for updating scraper configuration."""

    target_urls: Optional[str] = None
    keywords: Optional[str] = None
    cooldown_seconds: Optional[int] = None
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None
    use_tor: Optional[bool] = None


class ConfigResponse(BaseModel):
    """Response model for scraper configuration."""

    id: int
    name: str
    target_urls: Optional[str]
    keywords: Optional[str]
    cooldown_seconds: int
    max_depth: int
    max_pages: int
    timeout_seconds: int
    is_active: bool
    use_tor: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db)) -> List[ScraperConfig]:
    """List all scraper configurations."""
    result = await db.execute(select(ScraperConfig).order_by(ScraperConfig.name))
    return result.scalars().all()


@router.get("/{config_id}", response_model=ConfigResponse)
async def get_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
) -> ScraperConfig:
    """Get a specific scraper configuration."""
    result = await db.execute(
        select(ScraperConfig).where(ScraperConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return config


@router.post("/", response_model=ConfigResponse)
async def create_config(
    config_data: ConfigCreate,
    db: AsyncSession = Depends(get_db),
) -> ScraperConfig:
    """Create a new scraper configuration."""
    existing = await db.execute(
        select(ScraperConfig).where(ScraperConfig.name == config_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Configuration with name '{config_data.name}' already exists",
        )

    config = ScraperConfig(**config_data.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return config


@router.put("/{config_id}", response_model=ConfigResponse)
async def update_config(
    config_id: int,
    config_data: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScraperConfig:
    """Update an existing scraper configuration."""
    result = await db.execute(
        select(ScraperConfig).where(ScraperConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)

    return config


@router.delete("/{config_id}")
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Delete a scraper configuration."""
    result = await db.execute(
        select(ScraperConfig).where(ScraperConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    await db.delete(config)
    await db.commit()

    return {"message": f"Configuration '{config.name}' deleted successfully"}
