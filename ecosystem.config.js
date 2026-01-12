// PM2 Ecosystem Configuration
// Usage: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    // Main Trading Bot
    {
      name: 'crypto-trader',
      script: 'app.py',
      interpreter: './.venv/bin/python',
      args: '--mode full',
      cwd: '/var/www/ProjectBotTrading',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        TICK_INTERVAL_SECONDS: '3600'  //1 hour
      },
      error_file: './logs/trader-error.log',
      out_file: './logs/trader-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      
      // Restart delays
      restart_delay: 5000,
      exp_backoff_restart_delay: 100,
      
      // Cron restart (optional - restart daily at 4 AM)
      // cron_restart: '0 4 * * *'
    },
    
    // Dashboard API Server
    {
      name: 'crypto-dashboard',
      script: 'run_dashboard.py',
      interpreter: './.venv/bin/python',
      cwd: '/var/www/ProjectBotTrading',
      instances: 1,
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PORT: '9000'
      },
      error_file: './logs/dashboard-error.log',
      out_file: './logs/dashboard-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    }
  ]
};
