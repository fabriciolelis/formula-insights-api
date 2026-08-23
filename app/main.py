from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_schema
from app.models import Constructor, Driver, Race, RaceResult


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    yield


app = FastAPI(title="Formula Insights API", version="0.1.0", lifespan=lifespan)


def session_dependency():
    with SessionLocal() as session:
        yield session


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/seasons/{year}/races")
def season_races(year: int, session: Session = Depends(session_dependency)):
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
    statement = (
        select(Driver.id, Driver.given_name, Driver.family_name, func.sum(RaceResult.points).label("points"))
        .join(RaceResult, RaceResult.driver_id == Driver.id)
        .join(Race, Race.id == RaceResult.race_id)
        .where(Race.season == year)
        .group_by(Driver.id, Driver.given_name, Driver.family_name)
        .order_by(func.sum(RaceResult.points).desc())
    )
    return [dict(row._mapping) for row in session.execute(statement)]


@app.get("/seasons/{year}/standings/constructors")
def constructor_standings(year: int, session: Session = Depends(session_dependency)):
    statement = (
        select(Constructor.id, Constructor.name, func.sum(RaceResult.points).label("points"))
        .join(RaceResult, RaceResult.constructor_id == Constructor.id)
        .join(Race, Race.id == RaceResult.race_id)
        .where(Race.season == year)
        .group_by(Constructor.id, Constructor.name)
        .order_by(func.sum(RaceResult.points).desc())
    )
    return [dict(row._mapping) for row in session.execute(statement)]


@app.get("/seasons/{year}/races/{round_number}/results")
def race_results(year: int, round_number: int, session: Session = Depends(session_dependency)):
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
