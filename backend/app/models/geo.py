"""Reference geography used by campaign targeting and company normalisation."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Country(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "countries"

    iso2: Mapped[str] = mapped_column(String(2), unique=True, nullable=False, index=True)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    continent: Mapped[str] = mapped_column(String(60), nullable=False)
    phone_code: Mapped[str | None] = mapped_column(String(10))
    default_language: Mapped[str | None] = mapped_column(String(10))
    is_supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    regions: Mapped[list["Region"]] = relationship(back_populates="country")


class Region(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "regions"

    country_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20))

    country: Mapped[Country] = relationship(back_populates="regions")
    cities: Mapped[list["City"]] = relationship(back_populates="region")


class City(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cities"

    region_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="CASCADE"), index=True
    )
    country_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    population: Mapped[int | None] = mapped_column()

    region: Mapped[Region | None] = relationship(back_populates="cities")


class Industry(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "industries"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_slug: Mapped[str | None] = mapped_column(String(120))
    naics_code: Mapped[str | None] = mapped_column(String(12))
    # Comma-separated search seeds used by the discovery agent for this vertical.
    search_keywords: Mapped[str | None] = mapped_column(String(1000))
    ai_fit_baseline: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
