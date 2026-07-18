import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

required = ["DB_USER", "DB_PASSWORD", "DB_HOST"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    raise RuntimeError(f"Missing required env vars: {missing}")

url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME", "postgres"),
)

engine = create_engine(
    url,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass