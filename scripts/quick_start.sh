#!/bin/bash
# ============================================================
# Quick Start Script - Install Dependencies & Run
# ============================================================
# Usage:
#   chmod +x scripts/quick_start.sh
#   ./scripts/quick_start.sh
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

echo "============================================================"
echo "  Quick Start - Crypto Trading Platform"
echo "============================================================"
echo "Project directory: ${PROJECT_DIR}"
echo ""

# ------------------------------------------------------------
# 1. Create virtual environment if not exists
# ------------------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[1/4] Virtual environment exists, skipping..."
fi

# ------------------------------------------------------------
# 2. Activate virtual environment
# ------------------------------------------------------------
echo "[2/4] Activating virtual environment..."
source .venv/bin/activate

# ------------------------------------------------------------
# 3. Install/update dependencies
# ------------------------------------------------------------
echo "[3/4] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ------------------------------------------------------------
# 4. Initialize database tables
# ------------------------------------------------------------
echo "[4/4] Initializing database tables..."
python -c "
from database.engine import get_engine, Base
engine = get_engine()

# Import all models to register them
from database import models
Base.metadata.create_all(engine)

# Create risk committee tables
try:
    from risk_committee.models import Base as CommitteeBase
    CommitteeBase.metadata.create_all(engine)
except Exception as e:
    print(f'  Note: risk_committee tables: {e}')

# Create human review tables
try:
    from human_review.models import ReviewBase
    ReviewBase.metadata.create_all(engine)
except Exception as e:
    print(f'  Note: human_review tables: {e}')

print('  Database tables ready!')
"

echo ""
echo "============================================================"
echo "  READY TO START!"
echo "============================================================"
echo ""
echo "Run trading bot:"
echo "  source .venv/bin/activate"
echo "  python app.py --mode full"
echo ""
echo "Or with PM2:"
echo "  pm2 start ecosystem.config.js"
echo ""
echo "============================================================"
