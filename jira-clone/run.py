"""Convenience entrypoint: python run.py"""
import asyncio

from hypercorn.asyncio import serve
from hypercorn.config import Config

from app.main import app

if __name__ == "__main__":
    config = Config()
    config.bind = ["127.0.0.1:5000"]
    asyncio.run(serve(app, config))
