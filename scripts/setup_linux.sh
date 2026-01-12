#!/bin/bash
# ============================================================
# Linux Server Setup Script - Crypto Trading Platform
# ============================================================
# Usage: 
#   chmod +x scripts/setup_linux.sh
#   sudo ./scripts/setup_linux.sh
# ============================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Crypto Trading Platform - Linux Setup${NC}"
echo -e "${GREEN}============================================================${NC}"

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
PROJECT_DIR="/var/www/ProjectBotTrading"
PYTHON_VERSION="3.11"

# Load database credentials from .env file
ENV_FILE="${PROJECT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}Loading configuration from .env...${NC}"
    # Extract DATABASE_URL_SYNC and parse it
    DB_URL=$(grep -E "^DATABASE_URL_SYNC=" "$ENV_FILE" | cut -d'=' -f2-)
    
    # Parse: postgresql://user:password@host:port/database
    # Remove postgresql:// prefix
    DB_URL_CLEAN=$(echo "$DB_URL" | sed 's|postgresql://||')
    
    # Extract components
    DB_USER=$(echo "$DB_URL_CLEAN" | cut -d':' -f1)
    DB_PASSWORD=$(echo "$DB_URL_CLEAN" | cut -d':' -f2 | cut -d'@' -f1)
    DB_HOST=$(echo "$DB_URL_CLEAN" | cut -d'@' -f2 | cut -d':' -f1)
    DB_PORT=$(echo "$DB_URL_CLEAN" | cut -d':' -f3 | cut -d'/' -f1)
    DB_NAME=$(echo "$DB_URL_CLEAN" | cut -d'/' -f2)
    
    echo -e "  Database: ${DB_NAME}"
    echo -e "  User: ${DB_USER}"
    echo -e "  Host: ${DB_HOST}:${DB_PORT}"
else
    echo -e "${RED}ERROR: .env file not found at ${ENV_FILE}${NC}"
    echo -e "Please create .env file with DATABASE_URL_SYNC variable."
    exit 1
fi

# ------------------------------------------------------------
# 1. Update System
# ------------------------------------------------------------
echo -e "\n${YELLOW}[1/7] Updating system packages...${NC}"
apt update && apt upgrade -y

# ------------------------------------------------------------
# 2. Install System Dependencies
# ------------------------------------------------------------
echo -e "\n${YELLOW}[2/7] Installing system dependencies...${NC}"

# First install basic dependencies
apt install -y \
    software-properties-common \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    build-essential \
    git \
    curl \
    htop \
    nginx \
    supervisor

# Check if Python 3.10+ is available, if not add deadsnakes PPA
PYTHON_CMD=""
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.10 &> /dev/null; then
    PYTHON_CMD="python3.10"
else
    echo -e "${YELLOW}Python 3.10+ not found. Adding deadsnakes PPA...${NC}"
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update
    apt install -y python3.11 python3.11-venv python3.11-dev
    PYTHON_CMD="python3.11"
fi

# Install venv and dev packages for detected Python
PYTHON_VERSION=$(${PYTHON_CMD} --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}Using Python ${PYTHON_VERSION}${NC}"

# Try to install venv package (may already be included)
apt install -y python3-pip python3-venv python3-dev 2>/dev/null || true

# Create python symlink if not exists
if ! command -v python &> /dev/null; then
    ln -sf $(which ${PYTHON_CMD}) /usr/bin/python
fi

# ------------------------------------------------------------
# 3. Setup PostgreSQL
# ------------------------------------------------------------
echo -e "\n${YELLOW}[3/7] Setting up PostgreSQL...${NC}"

# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Create database and user
sudo -u postgres psql <<EOF
-- Drop if exists (for clean reinstall)
DROP DATABASE IF EXISTS ${DB_NAME};
DROP USER IF EXISTS ${DB_USER};

-- Create user
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';

-- Create database
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};

-- Connect to database and setup extensions
\c ${DB_NAME}
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO ${DB_USER};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${DB_USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};

\q
EOF

echo -e "${GREEN}PostgreSQL setup complete!${NC}"
echo -e "  Database: ${DB_NAME}"
echo -e "  User: ${DB_USER}"

# ------------------------------------------------------------
# 4. Setup Python Virtual Environment
# ------------------------------------------------------------
echo -e "\n${YELLOW}[4/7] Setting up Python virtual environment...${NC}"

cd ${PROJECT_DIR}

# Detect Python command again (in case script is run in parts)
if [ -z "$PYTHON_CMD" ]; then
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
    elif command -v python3.11 &> /dev/null; then
        PYTHON_CMD="python3.11"
    elif command -v python3.10 &> /dev/null; then
        PYTHON_CMD="python3.10"
    else
        PYTHON_CMD="python3"
    fi
fi

echo -e "Using: ${PYTHON_CMD} ($(${PYTHON_CMD} --version))"

# Create virtual environment
${PYTHON_CMD} -m venv .venv

# Activate and upgrade pip
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# ------------------------------------------------------------
# 5. Install Python Dependencies
# ------------------------------------------------------------
echo -e "\n${YELLOW}[5/7] Installing Python dependencies...${NC}"

pip install -r requirements.txt

# Install additional production dependencies
pip install gunicorn uvicorn[standard]

echo -e "${GREEN}Python dependencies installed!${NC}"

# ------------------------------------------------------------
# 6. Initialize Database Tables
# ------------------------------------------------------------
echo -e "\n${YELLOW}[6/7] Initializing database tables...${NC}"

# Make sure we're in project directory and venv is activated
cd ${PROJECT_DIR}
source .venv/bin/activate

# Create all tables
python -c "
from database.engine import get_engine, Base
from database.models import *
from risk_committee.models import Base as CommitteeBase
from human_review.models import ReviewBase

engine = get_engine()
Base.metadata.create_all(engine)
CommitteeBase.metadata.create_all(engine)
ReviewBase.metadata.create_all(engine)
print('All database tables created successfully!')
"

# ------------------------------------------------------------
# 7. Setup PM2 for Process Management
# ------------------------------------------------------------
echo -e "\n${YELLOW}[7/7] Setting up PM2...${NC}"

# Install Node.js if not installed (required for PM2)
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt install -y nodejs
fi

# Install PM2
npm install -g pm2

# Create PM2 ecosystem file
cat > ${PROJECT_DIR}/ecosystem.config.js <<EOF
module.exports = {
  apps: [{
    name: 'crypto-trader',
    script: 'app.py',
    interpreter: '${PROJECT_DIR}/.venv/bin/python',
    args: '--mode full',
    cwd: '${PROJECT_DIR}',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      PYTHONUNBUFFERED: '1'
    },
    error_file: '${PROJECT_DIR}/logs/pm2-error.log',
    out_file: '${PROJECT_DIR}/logs/pm2-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  },
  {
    name: 'crypto-dashboard',
    script: 'run_dashboard.py',
    interpreter: '${PROJECT_DIR}/.venv/bin/python',
    cwd: '${PROJECT_DIR}',
    instances: 1,
    autorestart: true,
    watch: false,
    env: {
      NODE_ENV: 'production',
      PYTHONUNBUFFERED: '1'
    },
    error_file: '${PROJECT_DIR}/logs/dashboard-error.log',
    out_file: '${PROJECT_DIR}/logs/dashboard-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};
EOF

# Create logs directory
mkdir -p ${PROJECT_DIR}/logs

# Setup PM2 startup
pm2 startup systemd -u root --hp /root

echo -e "${GREEN}PM2 setup complete!${NC}"

# ------------------------------------------------------------
# Final Summary
# ------------------------------------------------------------
echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}  SETUP COMPLETE!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e ""
echo -e "Database:"
echo -e "  Host: localhost"
echo -e "  Port: 5432"
echo -e "  Name: ${DB_NAME}"
echo -e "  User: ${DB_USER}"
echo -e ""
echo -e "Project:"
echo -e "  Directory: ${PROJECT_DIR}"
echo -e "  Python: ${PROJECT_DIR}/.venv/bin/python"
echo -e ""
echo -e "Commands to run:"
echo -e "  ${YELLOW}cd ${PROJECT_DIR}${NC}"
echo -e "  ${YELLOW}source .venv/bin/activate${NC}"
echo -e ""
echo -e "Start trading bot:"
echo -e "  ${YELLOW}pm2 start ecosystem.config.js${NC}"
echo -e ""
echo -e "Monitor:"
echo -e "  ${YELLOW}pm2 logs crypto-trader${NC}"
echo -e "  ${YELLOW}pm2 monit${NC}"
echo -e ""
echo -e "Save PM2 config (to auto-start on reboot):"
echo -e "  ${YELLOW}pm2 save${NC}"
echo -e ""
echo -e "${GREEN}============================================================${NC}"
