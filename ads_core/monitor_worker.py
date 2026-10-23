"""Dedicated Docker/server monitoring worker; no public listener and no Ads writes."""
import asyncio
from .monitoring import run_background

if __name__=='__main__':
    asyncio.run(run_background())
