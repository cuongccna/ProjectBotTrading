#!/bin/bash
# ============================================================
# Quick Database Setup Script
# ============================================================
# Usage: 
#   chmod +x scripts/setup_database.sh
#   sudo ./scripts/setup_database.sh
# ============================================================

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load database credentials from .env file
ENV_FILE="${PROJECT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading configuration from .env..."
    # Extract DATABASE_URL_SYNC and parse it
    DB_URL=$(grep -E "^DATABASE_URL_SYNC=" "$ENV_FILE" | cut -d'=' -f2-)
    
    # Parse: postgresql://user:password@host:port/database
    DB_URL_CLEAN=$(echo "$DB_URL" | sed 's|postgresql://||')
    
    DB_USER=$(echo "$DB_URL_CLEAN" | cut -d':' -f1)
    DB_PASSWORD=$(echo "$DB_URL_CLEAN" | cut -d':' -f2 | cut -d'@' -f1)
    DB_HOST=$(echo "$DB_URL_CLEAN" | cut -d'@' -f2 | cut -d':' -f1)
    DB_PORT=$(echo "$DB_URL_CLEAN" | cut -d':' -f3 | cut -d'/' -f1)
    DB_NAME=$(echo "$DB_URL_CLEAN" | cut -d'/' -f2)
else
    echo "ERROR: .env file not found at ${ENV_FILE}"
    echo "Please create .env file with DATABASE_URL_SYNC variable."
    echo ""
    echo "Example .env:"
    echo "  DATABASE_URL_SYNC=postgresql://crypto_user:password@localhost:5432/crypto_trading"
    exit 1
fi

echo "============================================================"
echo "  PostgreSQL Database Setup"
echo "============================================================"

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Installing PostgreSQL..."
    apt update
    apt install -y postgresql postgresql-contrib libpq-dev
fi

# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Create database and user
echo "Creating database and user..."
sudo -u postgres psql <<EOF
-- Drop if exists (for clean reinstall)
DROP DATABASE IF EXISTS ${DB_NAME};
DROP USER IF EXISTS ${DB_USER};

-- Create user with password
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';

-- Create database
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};

-- Connect and setup
\c ${DB_NAME}
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};
EOF

echo ""
echo "============================================================"
echo "  DATABASE CREATED SUCCESSFULLY!"
echo "============================================================"
echo ""
echo "Connection details:"
echo "  Host:     localhost"
echo "  Port:     5432"
echo "  Database: ${DB_NAME}"
echo "  User:     ${DB_USER}"
echo "  Password: ${DB_PASSWORD}"
echo ""
echo "Connection string:"
echo "  postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"
echo ""
echo "Test connection:"
echo "  psql -h localhost -U ${DB_USER} -d ${DB_NAME}"
echo "============================================================"
