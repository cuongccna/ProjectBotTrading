"""
Orchestrator - CLI.

============================================================
RESPONSIBILITY
============================================================
Command-line interface for the trading system.

- Provides argparse-based CLI
- Supports all runtime modes
- Loads configuration from CLI and environment
- Entry point for the application

============================================================
USAGE
============================================================
python -m orchestrator.cli --mode full
python -m orchestrator.cli --mode ingest --dry-run
python -m orchestrator.cli --mode backtest --start-date 2025-01-01 --end-date 2025-01-10

============================================================
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import RuntimeMode, OrchestratorConfig, ExecutionStage
from .core import Orchestrator, create_orchestrator


# ============================================================
# CLI ARGUMENT PARSER
# ============================================================

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="crypto-trading-system",
        description="Institutional-grade crypto trading system orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Runtime Modes:
  ingest    - Run data ingestion only (no processing, no trading)
  process   - Run data processing only (no ingestion, no trading)
  risk      - Run risk aggregation and scoring (no execution)
  trade     - Full pipeline including execution (subject to guards)
  backtest  - Replay historical data with identical logic
  monitor   - Run monitoring and alerting only
  full      - Run full live system in correct order

Examples:
  %(prog)s --mode full                    # Run full live system
  %(prog)s --mode ingest --dry-run        # Test ingestion without side effects
  %(prog)s --mode backtest --start-date 2025-01-01 --end-date 2025-01-10
  %(prog)s --mode monitor                 # Monitoring only
        """
    )
    
    # --------------------------------------------------------
    # Mode Selection
    # --------------------------------------------------------
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=[m.value for m in RuntimeMode],
        default="full",
        help="Runtime mode (default: full)",
    )
    
    # --------------------------------------------------------
    # Execution Options
    # --------------------------------------------------------
    execution_group = parser.add_argument_group("Execution Options")
    
    execution_group.add_argument(
        "--tick-interval",
        type=int,
        default=3600,
        metavar="SECONDS",
        help="Main loop tick interval in seconds (default: 3600 = 1 hour)",
    )
    
    execution_group.add_argument(
        "--single-cycle",
        action="store_true",
        help="Run a single cycle and exit (no loop)",
    )
    
    execution_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - no actual trades executed",
    )
    
    execution_group.add_argument(
        "--require-confirmation",
        action="store_true",
        help="Require confirmation before each trade",
    )
    
    # --------------------------------------------------------
    # Backtest Options
    # --------------------------------------------------------
    backtest_group = parser.add_argument_group("Backtest Options")
    
    backtest_group.add_argument(
        "--start-date",
        type=str,
        metavar="YYYY-MM-DD",
        help="Backtest start date (required for backtest mode)",
    )
    
    backtest_group.add_argument(
        "--end-date",
        type=str,
        metavar="YYYY-MM-DD",
        help="Backtest end date (required for backtest mode)",
    )
    
    backtest_group.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Backtest replay speed multiplier (default: 1.0)",
    )
    
    # --------------------------------------------------------
    # Logging Options
    # --------------------------------------------------------
    logging_group = parser.add_argument_group("Logging Options")
    
    logging_group.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    
    logging_group.add_argument(
        "--log-format",
        type=str,
        choices=["json", "text"],
        default="json",
        help="Logging format (default: json)",
    )
    
    # --------------------------------------------------------
    # System Options
    # --------------------------------------------------------
    system_group = parser.add_argument_group("System Options")
    
    system_group.add_argument(
        "--state-file",
        type=str,
        metavar="PATH",
        help="Path to state persistence file",
    )
    
    system_group.add_argument(
        "--no-state-persistence",
        action="store_true",
        help="Disable state persistence",
    )
    
    system_group.add_argument(
        "--shutdown-timeout",
        type=int,
        default=30,
        metavar="SECONDS",
        help="Shutdown timeout in seconds (default: 30)",
    )
    
    system_group.add_argument(
        "--health-check-interval",
        type=int,
        default=30,
        metavar="SECONDS",
        help="Health check interval in seconds (default: 30)",
    )
    
    # --------------------------------------------------------
    # Version/Info
    # --------------------------------------------------------
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 1.0.0",
    )
    
    parser.add_argument(
        "--show-stages",
        action="store_true",
        help="Show execution stages for selected mode and exit",
    )
    
    return parser


# ============================================================
# CLI VALIDATION
# ============================================================

def validate_args(args: argparse.Namespace) -> List[str]:
    """
    Validate CLI arguments.
    
    Args:
        args: Parsed arguments
        
    Returns:
        List of validation errors
    """
    errors = []
    
    mode = RuntimeMode(args.mode)
    
    # Validate backtest arguments
    if mode == RuntimeMode.BACKTEST:
        if not args.start_date:
            errors.append("--start-date is required for backtest mode")
        if not args.end_date:
            errors.append("--end-date is required for backtest mode")
        
        if args.start_date and args.end_date:
            try:
                start = datetime.fromisoformat(args.start_date)
                end = datetime.fromisoformat(args.end_date)
                if start >= end:
                    errors.append("--start-date must be before --end-date")
            except ValueError as e:
                errors.append(f"Invalid date format: {e}")
    
    # Validate intervals
    if args.tick_interval < 1:
        errors.append("--tick-interval must be at least 1 second")
    
    if args.shutdown_timeout < 1:
        errors.append("--shutdown-timeout must be at least 1 second")
    
    if args.speed <= 0:
        errors.append("--speed must be positive")
    
    return errors


# ============================================================
# CLI CONFIGURATION BUILDER
# ============================================================

def build_config(args: argparse.Namespace) -> OrchestratorConfig:
    """
    Build orchestrator configuration from CLI arguments.
    
    Args:
        args: Parsed arguments
        
    Returns:
        OrchestratorConfig instance
    """
    return OrchestratorConfig(
        mode=RuntimeMode(args.mode),
        tick_interval_seconds=args.tick_interval,
        shutdown_timeout_seconds=args.shutdown_timeout,
        health_check_interval_seconds=args.health_check_interval,
        state_persistence_enabled=not args.no_state_persistence,
        state_persistence_path=args.state_file,
        log_level=args.log_level,
        dry_run=args.dry_run,
        require_confirmation=args.require_confirmation,
        backtest_start_date=args.start_date,
        backtest_end_date=args.end_date,
        backtest_speed_multiplier=args.speed,
    )


# ============================================================
# SHOW STAGES
# ============================================================

def show_stages(mode: RuntimeMode) -> None:
    """Print execution stages for a mode."""
    print(f"\nExecution stages for mode: {mode.value}")
    print("=" * 60)
    
    stages = ExecutionStage.get_stages_for_mode(mode)
    
    for i, stage in enumerate(stages, 1):
        print(f"  {i:2d}. [{stage.order:02d}] {stage.stage_id:30s} - {stage.description}")
    
    print()


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def async_main(args: argparse.Namespace) -> int:
    """
    Async main entry point.
    
    Args:
        args: Parsed arguments
        
    Returns:
        Exit code
    """
    # Build configuration
    config = build_config(args)
    
    # Create orchestrator
    orchestrator = Orchestrator(config=config)
    
    # Register default stage handlers (placeholder implementations)
    # In production, these would be wired to actual module implementations
    orchestrator.register_stage_handler(
        ExecutionStage.LOAD_CONFIG,
        lambda: _default_stage_handler("load_config"),
    )
    orchestrator.register_stage_handler(
        ExecutionStage.INIT_LOGGING,
        lambda: _default_stage_handler("init_logging"),
    )
    orchestrator.register_stage_handler(
        ExecutionStage.INIT_DATABASE,
        lambda: _default_stage_handler("init_database"),
    )
    orchestrator.register_stage_handler(
        ExecutionStage.INIT_HEALTH,
        lambda: _default_stage_handler("init_health"),
    )
    orchestrator.register_stage_handler(
        ExecutionStage.UPDATE_MONITORING,
        lambda: _default_stage_handler("update_monitoring"),
    )
    
    try:
        if args.single_cycle:
            # Run single cycle
            result = await orchestrator.run_single_cycle()
            return 0 if result.success else 1
        else:
            # Run forever
            await orchestrator.run_forever()
            return 0
            
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1
    finally:
        await orchestrator.stop()


async def _default_stage_handler(stage_name: str) -> dict:
    """Default placeholder stage handler."""
    return {"stage": stage_name, "status": "completed"}


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main CLI entry point.
    
    Args:
        argv: Command line arguments (default: sys.argv[1:])
        
    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # Show stages if requested
    if args.show_stages:
        show_stages(RuntimeMode(args.mode))
        return 0
    
    # Validate arguments
    errors = validate_args(args)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    
    # Print startup banner
    print_banner(args)
    
    # Run async main
    return asyncio.run(async_main(args))


def print_banner(args: argparse.Namespace) -> None:
    """Print startup banner."""
    print()
    print("=" * 60)
    print("  CRYPTO TRADING SYSTEM")
    print("  Institutional-Grade Orchestrator")
    print("=" * 60)
    print(f"  Mode:       {args.mode}")
    print(f"  Dry Run:    {args.dry_run}")
    print(f"  Log Level:  {args.log_level}")
    print(f"  Interval:   {args.tick_interval}s")
    if args.mode == "backtest":
        print(f"  Start Date: {args.start_date}")
        print(f"  End Date:   {args.end_date}")
        print(f"  Speed:      {args.speed}x")
    print("=" * 60)
    print()


# ============================================================
# MODULE EXECUTION
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
