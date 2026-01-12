#!/usr/bin/env python
"""
Dashboard API Server Runner.

Usage:
    python run_dashboard.py
    
Or with PM2:
    pm2 start run_dashboard.py --interpreter python
"""

import os
import sys
import logging
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def main():
    """Run the dashboard API server."""
    # Get configuration from environment
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", os.getenv("PORT", "8000")))
    reload = os.getenv("ENVIRONMENT", "production") == "development"
    
    logger.info(f"Starting Dashboard API on {host}:{port}")
    
    try:
        uvicorn.run(
            "dashboard.api:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
            access_log=True,
        )
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
