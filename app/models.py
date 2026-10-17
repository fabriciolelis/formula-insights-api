from datetime import date

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Race(Base):
    __tablename__ = "races"
    __table_args__ = (UniqueConstraint("season", "round", name="uq_race_season_round"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(index=True)
    round: Mapped[int]
    name: Mapped[str] = mapped_column(String(255))
    race_date: Mapped[date]
    circuit_id: Mapped[str] = mapped_column(String(100))
    circuit_name: Mapped[str] = mapped_column(String(255))


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    given_name: Mapped[str] = mapped_column(String(100))
    family_name: Mapped[str] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Constructor(Base):
    __tablename__ = "constructors"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)


class RaceResult(Base):
    __tablename__ = "race_results"
    __table_args__ = (UniqueConstraint("race_id", "driver_id", name="uq_result_race_driver"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    constructor_id: Mapped[str] = mapped_column(ForeignKey("constructors.id"))
    position: Mapped[int | None] = mapped_column(nullable=True)
    position_text: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(100))


class DriverStanding(Base):
    """Official driver championship standings after the latest imported round."""

    __tablename__ = "driver_standings"
    __table_args__ = (
        UniqueConstraint("season", "driver_id", name="uq_driver_standing_season_driver"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(index=True)
    round: Mapped[int]
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    position: Mapped[int | None] = mapped_column(nullable=True)
    position_text: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float)
    wins: Mapped[int]


class ConstructorStanding(Base):
    """Official constructor championship standings after the latest imported round."""

    __tablename__ = "constructor_standings"
    __table_args__ = (
        UniqueConstraint(
            "season", "constructor_id", name="uq_constructor_standing_season_constructor"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(index=True)
    round: Mapped[int]
    constructor_id: Mapped[str] = mapped_column(ForeignKey("constructors.id"))
    position: Mapped[int | None] = mapped_column(nullable=True)
    position_text: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float)
    wins: Mapped[int]
