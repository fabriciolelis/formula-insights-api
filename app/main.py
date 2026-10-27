"""HTTP API serving imported Formula 1 races, results, and standings."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, ensure_schema_ready
from app.models import (
    Constructor,
    ConstructorStanding,
    Driver,
    DriverStanding,
    Race,
    RaceResult,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start unless the database schema is migrated (ADR-007)."""
    ensure_schema_ready()
    yield


app = FastAPI(title="Formula Insights API", version="0.1.0", lifespan=lifespan)


def session_dependency():
    """Provide a database session for one request and close it afterwards.

    Yields:
        A SQLAlchemy session.
    """
    with SessionLocal() as session:
        yield session


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: reports that the process is running, without touching the database."""
    return {"status": "ok"}


@app.get("/seasons/{year}/races")
def season_races(year: int, session: Session = Depends(session_dependency)):
    """Races of a season in round order, with date and circuit."""
    races = session.scalars(select(Race).where(Race.season == year).order_by(Race.round)).all()
    return [
        {
            "season": race.season,
            "round": race.round,
            "name": race.name,
            "date": race.race_date,
            "circuit": {"id": race.circuit_id, "name": race.circuit_name},
        }
        for race in races
    ]


@app.get("/seasons/{year}/standings/drivers")
def driver_standings(year: int, session: Session = Depends(session_dependency)):
    """Official driver standings, including sprint points and penalties, as published upstream."""
    rows = session.execute(
        select(DriverStanding, Driver)
        .join(Driver)
        .where(DriverStanding.season == year)
        .order_by(DriverStanding.position.is_(None), DriverStanding.position)
    ).all()
    return [
        {
            "position": standing.position,
            "position_text": standing.position_text,
            "id": driver.id,
            "given_name": driver.given_name,
            "family_name": driver.family_name,
            "points": standing.points,
            "wins": standing.wins,
        }
        for standing, driver in rows
    ]


@app.get("/seasons/{year}/standings/constructors")
def constructor_standings(year: int, session: Session = Depends(session_dependency)):
    """Official constructor standings, including sprint points and penalties, as published upstream."""
    rows = session.execute(
        select(ConstructorStanding, Constructor)
        .join(Constructor)
        .where(ConstructorStanding.season == year)
        .order_by(ConstructorStanding.position.is_(None), ConstructorStanding.position)
    ).all()
    return [
        {
            "position": standing.position,
            "position_text": standing.position_text,
            "id": constructor.id,
            "name": constructor.name,
            "points": standing.points,
            "wins": standing.wins,
        }
        for standing, constructor in rows
    ]


@app.get("/seasons/{year}/races/{round_number}/results")
def race_results(year: int, round_number: int, session: Session = Depends(session_dependency)):
    """Results of one race in finishing order; returns 404 if the race is unknown."""
    race = session.scalar(select(Race).where(Race.season == year, Race.round == round_number))
    if race is None:
        raise HTTPException(status_code=404, detail="race not found")
    rows = session.execute(
        select(RaceResult, Driver, Constructor)
        .join(Driver)
        .join(Constructor)
        .where(RaceResult.race_id == race.id)
        .order_by(RaceResult.position)
    ).all()
    return [
        {
            "position": result.position,
            "position_text": result.position_text,
            "points": result.points,
            "status": result.status,
            "driver": {
                "id": driver.id,
                "given_name": driver.given_name,
                "family_name": driver.family_name,
            },
            "constructor": {"id": constructor.id, "name": constructor.name},
        }
        for result, driver, constructor in rows
    ]
