"""
Restricted Docker Agent — CLI Entry Point
Starts the Uvicorn server for the standalone restricted Docker recovery agent.
"""

import uvicorn
from docker_agent.config import settings
from docker_agent.server import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.AGENT_HOST,
        port=settings.AGENT_PORT,
        log_level="info",
    )
