"""SQLAlchemy models for the Formula 1 data imported from Jolpica."""

from datetime import date

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Race(Base):
    """A Grand Prix in a season, identified by season and round.

    Attributes:
        id: Surrogate primary key.
        season: Championship year, for example 2024.
        round: Round number within the season, starting at 1.
        name: Official race name, for example "Bahrain Grand Prix".
        race_date: Date of the race.
        circuit_id: Jolpica circuit identifier.
        circuit_name: Human-readable circuit name.
    """

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
    """A driver, shared across seasons.

    Attributes:
        id: Jolpica driver identifier, for example "max_verstappen".
        given_name: Driver's given name.
        family_name: Driver's family name.
        nationality: Nationality as published by Jolpica, if known.
    """

    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    given_name: Mapped[str] = mapped_column(String(100))
    family_name: Mapped[str] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Constructor(Base):
    """A constructor (team), shared across seasons.

    Attributes:
        id: Jolpica constructor identifier, for example "mclaren".
        name: Team name.
        nationality: Nationality as published by Jolpica, if known.
    """

    __tablename__ = "constructors"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)


class RaceResult(Base):
    """One driver's Grand Prix result in one car.

    In early seasons a driver could race two cars in the same Grand Prix, so a
    result is identified by race, driver, and car number.

    Attributes:
        id: Surrogate primary key.
        race_id: The race this result belongs to.
        driver_id: The classified driver.
        number: Car number, or None for rows imported before it was stored.
        constructor_id: The team the driver raced for in this race.
        position: Finishing position, or None when the driver was not
            classified (for example retired or disqualified).
        position_text: Position as published, for example "1", "R" or "D".
        points: Championship points scored in this race (Grand Prix only;
            sprint points are reflected in the standings tables).
        status: Finishing status, for example "Finished" or "+1 Lap".
    """

    __tablename__ = "race_results"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", "number", name="uq_result_race_driver_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    constructor_id: Mapped[str] = mapped_column(ForeignKey("constructors.id"))
    position: Mapped[int | None] = mapped_column(nullable=True)
    position_text: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(100))


class DriverStanding(Base):
    """Official driver championship standings after the latest imported round.

    Mirrors Jolpica's published table, so totals include sprint points,
    penalties, and exclusions.

    Attributes:
        id: Surrogate primary key.
        season: Championship year.
        round: The round these standings reflect.
        driver_id: The driver.
        position: Championship position, or None for excluded drivers.
        position_text: Position as published, for example "1" or "E".
        points: Championship points.
        wins: Number of race wins.
    """

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
    """Official constructor championship standings after the latest imported round.

    Mirrors Jolpica's published table, so totals include sprint points,
    penalties, and exclusions (for example McLaren in 2007).

    Attributes:
        id: Surrogate primary key.
        season: Championship year.
        round: The round these standings reflect.
        constructor_id: The constructor.
        position: Championship position, or None for excluded constructors.
        position_text: Position as published, for example "1" or "E".
        points: Championship points.
        wins: Number of race wins.
    """

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
