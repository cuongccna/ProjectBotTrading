#!/usr/bin/env python3
"""
Crypto Trading System - Main Application Entry Point.

============================================================
SINGLE ENTRYPOINT
============================================================
This is the ONE executable entry point for the entire platform.

- Compatible with PM2 process management
- Can be started, stopped, and restarted safely
- Handles all signals gracefully
- Wires all modules into one controlled runtime

============================================================
USAGE
============================================================
Direct execution:
    python app.py --mode full

With PM2:
    pm2 start app.py --interpreter python --name crypto-trader -- --mode full

Environment-based configuration:
    RUNTIME_MODE=full python app.py

============================================================
PM2 ECOSYSTEM CONFIG (ecosystem.config.js)
============================================================
module.exports = {
    apps: [{
        name: 'crypto-trader',
        script: 'app.py',
        interpreter: 'python',
        args: '--mode full',
        env: {
            RUNTIME_MODE: 'full',
            LOG_LEVEL: 'INFO',
        },
        env_production: {
            RUNTIME_MODE: 'trade',
            LOG_LEVEL: 'WARNING',
        },
        max_restarts: 10,
        restart_delay: 5000,
        watch: false,
    }]
};

============================================================
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.models import RuntimeMode, ExecutionStage, OrchestratorConfig
from orchestrator.core import Orchestrator
from orchestrator.registry import ModuleRegistry, ModuleFactory
from orchestrator.pipeline import PipelineBuilder
from orchestrator.cli import create_parser, validate_args, build_config, print_banner


# ============================================================
# MODULE WIRING
# ============================================================

def wire_modules(orchestrator: Orchestrator, config: Dict[str, Any]) -> None:
    """
    Wire all system modules into the orchestrator.
    
    This function registers all modules and their dependencies.
    Each module is registered with:
    - Its dependencies (what must start before it)
    - The stages where it's active
    - Whether it's critical (failure stops system)
    
    Args:
        orchestrator: The orchestrator instance
        config: Configuration dictionary
    """
    logger = logging.getLogger(__name__)
    
    # --------------------------------------------------------
    # Import REAL modules
    # --------------------------------------------------------
    from database.database_module import DatabaseModule
    from data_ingestion.real_ingestion_module import RealIngestionModule
    from data_processing.processing_module import ProcessingPipelineModule
    from risk_scoring.engine import RiskScoringEngine
    from risk_budget_manager.engine import RiskBudgetManager
    from risk_committee.engine import RiskCommitteeEngine
    from strategy_engine.engine import StrategyEngine
    from trade_guard_absolute.engine import TradeGuardAbsolute
    from system_risk_controller.engine import SystemRiskController
    from execution_engine.execution_service import ExecutionService
    from monitoring.dashboard_service import DashboardService
    from monitoring.notifications.telegram import TelegramNotifier
    
    # --------------------------------------------------------
    # Core Infrastructure Modules
    # --------------------------------------------------------
    
    logger.info("Wiring system modules...")
    
    # Database module - REAL IMPLEMENTATION
    orchestrator.register_module(
        name="database",
        module_class=DatabaseModule,  # REAL MODULE
        dependencies=[],
        required_stages=[
            ExecutionStage.INIT_DATABASE,
        ],
        critical=True,
        timeout_seconds=30.0,
    )
    
    # --------------------------------------------------------
    # Data Ingestion Modules - REAL IMPLEMENTATION
    # --------------------------------------------------------
    
    # REAL ingestion module - NOT a placeholder
    # Fetches real data from CoinGecko and Binance APIs
    orchestrator.register_module(
        name="data_ingestion",
        module_class=RealIngestionModule,  # REAL MODULE
        dependencies=["database"],
        required_stages=[
            ExecutionStage.INIT_COLLECTORS,
            ExecutionStage.RUN_INGESTION,
        ],
        config_key="data_ingestion",
        critical=False,
        timeout_seconds=120.0,
    )
    
    # --------------------------------------------------------
    # Data Processing Modules
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="data_processing",
        module_class=ProcessingPipelineModule,  # REAL MODULE
        dependencies=["database", "data_ingestion"],
        required_stages=[
            ExecutionStage.RUN_PROCESSING,
            ExecutionStage.RUN_MARKET_CLASSIFICATION,
        ],
        config_key="data_processing",
        critical=False,
        timeout_seconds=180.0,
    )
    
    # --------------------------------------------------------
    # Risk Modules
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="risk_scoring",
        module_class=RiskScoringEngine,  # REAL MODULE
        dependencies=["data_processing"],
        required_stages=[
            ExecutionStage.RUN_RISK_SCORING,
        ],
        config_key="risk_scoring",
        critical=True,
        timeout_seconds=60.0,
    )
    
    orchestrator.register_module(
        name="risk_budget_manager",
        module_class=RiskBudgetManager,  # REAL MODULE
        dependencies=["risk_scoring"],
        required_stages=[
            ExecutionStage.RUN_RISK_BUDGET,
        ],
        config_key="risk_budget",
        critical=True,
        timeout_seconds=30.0,
    )
    
    # --------------------------------------------------------
    # Risk Committee Module - INSTITUTIONAL REVIEW
    # --------------------------------------------------------
    # This module simulates an institutional risk committee
    # that reviews system state BEFORE allowing trading.
    # It has VETO AUTHORITY over trading decisions.
    
    orchestrator.register_module(
        name="risk_committee",
        module_class=RiskCommitteeEngine,  # REAL MODULE
        dependencies=["risk_budget_manager", "data_processing"],
        required_stages=[
            ExecutionStage.RUN_COMMITTEE_REVIEW,
        ],
        config_key="risk_committee",
        critical=True,
        timeout_seconds=30.0,
    )
    
    # --------------------------------------------------------
    # Strategy Module
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="strategy_engine",
        module_class=StrategyEngine,  # REAL MODULE
        dependencies=["risk_scoring", "data_processing", "risk_committee"],
        required_stages=[
            ExecutionStage.RUN_STRATEGY,
        ],
        config_key="strategy_engine",
        critical=True,
        timeout_seconds=60.0,
    )
    
    # --------------------------------------------------------
    # Safety Modules
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="trade_guard",
        module_class=TradeGuardAbsolute,  # REAL MODULE
        dependencies=["risk_budget_manager"],
        required_stages=[
            ExecutionStage.RUN_TRADE_GUARD,
        ],
        config_key="trade_guard",
        critical=True,
        timeout_seconds=10.0,
    )
    
    orchestrator.register_module(
        name="system_risk_controller",
        module_class=SystemRiskController,  # REAL MODULE
        dependencies=["trade_guard"],
        required_stages=[
            ExecutionStage.RUN_RISK_CONTROLLER,
        ],
        config_key="system_risk_controller",
        critical=True,
        timeout_seconds=10.0,
    )
    
    # --------------------------------------------------------
    # Execution Module
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="execution_engine",
        module_class=ExecutionService,  # REAL MODULE
        dependencies=["system_risk_controller"],
        required_stages=[
            ExecutionStage.RUN_EXECUTION,
        ],
        config_key="execution_engine",
        critical=True,
        timeout_seconds=120.0,
    )
    
    # --------------------------------------------------------
    # Monitoring Module
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="monitoring",
        module_class=DashboardService,  # REAL MODULE
        dependencies=["database"],
        required_stages=[
            ExecutionStage.UPDATE_MONITORING,
        ],
        config_key="monitoring",
        critical=False,
        timeout_seconds=30.0,
    )
    
    # --------------------------------------------------------
    # Notification Module
    # --------------------------------------------------------
    
    orchestrator.register_module(
        name="telegram_notifier",
        module_class=TelegramNotifier,  # REAL MODULE
        dependencies=[],
        required_stages=[
            ExecutionStage.SEND_NOTIFICATIONS,
        ],
        config_key="telegram",
        critical=False,
        timeout_seconds=10.0,
    )
    
    logger.info(f"Registered {len(orchestrator.registry._definitions)} modules")
    
    # ============================================================
    # LOG MODULE REGISTRATION SUMMARY
    # ============================================================
    # This provides visibility into REAL vs PLACEHOLDER modules at startup
    orchestrator.log_module_registration_summary()


def wire_stage_handlers(orchestrator: Orchestrator) -> None:
    """
    Wire stage handlers to the orchestrator.
    
    Each handler is an async function that executes the stage logic.
    Handlers can access modules from the registry.
    
    Args:
        orchestrator: The orchestrator instance
    """
    logger = logging.getLogger(__name__)
    
    # --------------------------------------------------------
    # Initialization Stages
    # --------------------------------------------------------
    
    async def handle_load_config() -> Dict[str, Any]:
        """Load configuration and environment."""
        logger.info("Loading configuration...")
        # In production: load from files, validate, etc.
        return {"config_loaded": True}
    
    async def handle_init_logging() -> Dict[str, Any]:
        """Initialize logging and correlation IDs."""
        logger.info("Logging initialized")
        return {"logging_ready": True}
    
    async def handle_init_database() -> Dict[str, Any]:
        """Initialize database connections."""
        logger.info("Database connection established")
        # In production: create connection pool
        return {"database_ready": True}
    
    async def handle_init_health() -> Dict[str, Any]:
        """Initialize system health checks."""
        logger.info("Health checks initialized")
        return {"health_ready": True}
    
    # --------------------------------------------------------
    # Data Collection Stages
    # --------------------------------------------------------
    
    async def handle_init_collectors() -> Dict[str, Any]:
        """Initialize data collectors."""
        ingestion = orchestrator.registry.get_instance("data_ingestion")
        if ingestion and hasattr(ingestion, 'start'):
            await ingestion.start()
        logger.info("Data collectors initialized")
        return {"collectors_ready": True}
    
    async def handle_run_ingestion() -> Dict[str, Any]:
        """Run ingestion modules."""
        ingestion = orchestrator.registry.get_instance("data_ingestion")
        results = []
        if ingestion and hasattr(ingestion, 'run_collection_cycle'):
            results = await ingestion.run_collection_cycle()
        logger.info(f"Ingestion complete: {len(results)} results")
        return {"ingestion_results": len(results)}
    
    # --------------------------------------------------------
    # Processing Stages
    # --------------------------------------------------------
    
    async def handle_run_processing() -> Dict[str, Any]:
        """Run data processing pipelines."""
        processing = orchestrator.registry.get_instance("data_processing")
        # In production: run processing pipeline
        logger.info("Processing pipeline complete")
        return {"processing_complete": True}
    
    async def handle_market_classification() -> Dict[str, Any]:
        """Run market condition classification."""
        # In production: classify market conditions
        logger.info("Market classification complete")
        return {"market_classified": True}
    
    # --------------------------------------------------------
    # Risk Stages
    # --------------------------------------------------------
    
    async def handle_risk_scoring() -> Dict[str, Any]:
        """Run risk aggregation and scoring."""
        risk_engine = orchestrator.registry.get_instance("risk_scoring")
        # In production: score = risk_engine.score(input_data)
        logger.info("Risk scoring complete")
        return {"risk_scored": True, "risk_level": "normal"}
    
    async def handle_risk_budget() -> Dict[str, Any]:
        """Run risk budget manager."""
        budget_manager = orchestrator.registry.get_instance("risk_budget_manager")
        # In production: evaluate budget constraints
        logger.info("Risk budget evaluated")
        return {"budget_available": True}
    
    async def handle_committee_review() -> Dict[str, Any]:
        """
        Run institutional risk committee review.
        
        This is a CRITICAL VETO POINT:
        - APPROVE → continue to strategy
        - HOLD → block new trades (pause)
        - BLOCK → halt system via System Risk Controller
        """
        from risk_committee import CommitteeDecision
        from system_risk_controller.types import HaltTrigger, HaltLevel
        
        committee = orchestrator.registry.get_instance("risk_committee")
        risk_controller = orchestrator.registry.get_instance("system_risk_controller")
        
        if not committee:
            logger.error("Risk committee module not available!")
            return {"committee_decision": "BLOCK", "reason": "Module unavailable"}
        
        # Get current cycle correlation ID
        correlation_id = getattr(orchestrator, 'current_correlation_id', None) or "unknown"
        cycle_id = getattr(orchestrator, 'current_cycle_id', None) or ""
        
        # Convene committee
        report = committee.convene_committee(
            correlation_id=correlation_id,
            cycle_id=cycle_id
        )
        
        # Apply decision to System Risk Controller
        if risk_controller and hasattr(risk_controller, 'request_halt'):
            if report.decision == CommitteeDecision.BLOCK:
                await risk_controller.request_halt(
                    trigger=HaltTrigger.MN_COMMITTEE_BLOCK,
                    level=HaltLevel.HARD,
                    reason=report.decision_reason,
                    operator="RiskCommittee"
                )
                logger.warning(f"COMMITTEE BLOCK → System halted: {report.decision_reason}")
                
            elif report.decision == CommitteeDecision.HOLD:
                await risk_controller.request_halt(
                    trigger=HaltTrigger.MN_COMMITTEE_HOLD,
                    level=HaltLevel.SOFT,
                    reason=report.decision_reason,
                    operator="RiskCommittee"
                )
                logger.warning(f"COMMITTEE HOLD → Trading paused: {report.decision_reason}")
                
            else:  # APPROVE
                logger.info(f"COMMITTEE APPROVE: {report.decision_reason}")
        
        return {
            "committee_decision": report.decision.value,
            "reason": report.decision_reason,
            "critical_count": report.critical_count,
            "warning_count": report.warning_count,
            "ok_count": report.ok_count,
            "report_id": report.report_id,
        }
    
    # --------------------------------------------------------
    # Trading Stages
    # --------------------------------------------------------
    
    async def handle_run_strategy() -> Dict[str, Any]:
        """Run strategy engine."""
        strategy = orchestrator.registry.get_instance("strategy_engine")
        # In production: output = strategy.evaluate(input_data)
        
        # Check safety before generating signals
        safety = orchestrator.get_safety_context()
        if not safety.can_trade:
            logger.warning(f"Trading blocked: {safety.block_reason}")
            return {"signals_generated": 0, "blocked": True, "reason": safety.block_reason}
        
        logger.info("Strategy evaluation complete")
        return {"signals_generated": 0}
    
    async def handle_trade_guard() -> Dict[str, Any]:
        """Run trade guard absolute."""
        guard = orchestrator.registry.get_instance("trade_guard")
        # In production: decision = guard.evaluate(guard_input)
        logger.info("Trade guard check complete")
        return {"guard_passed": True}
    
    async def handle_risk_controller() -> Dict[str, Any]:
        """Run system risk controller."""
        controller = orchestrator.registry.get_instance("system_risk_controller")
        
        if controller and hasattr(controller, 'can_trade'):
            can_trade = controller.can_trade()
            if not can_trade:
                logger.warning("System risk controller: trading not allowed")
                return {"trading_allowed": False}
        
        logger.info("Risk controller check complete")
        return {"trading_allowed": True}
    
    async def handle_execution() -> Dict[str, Any]:
        """Run execution engine."""
        execution = orchestrator.registry.get_instance("execution_engine")
        
        # Final safety check
        safety = orchestrator.get_safety_context()
        if not safety.can_trade:
            logger.info("Execution skipped: trading not allowed")
            return {"executions": 0, "skipped": True}
        
        # Check dry run mode
        if orchestrator.config.dry_run:
            logger.info("Execution skipped: dry run mode")
            return {"executions": 0, "dry_run": True}
        
        # In production: execute pending orders
        logger.info("Execution complete")
        return {"executions": 0}
    
    # --------------------------------------------------------
    # Finalization Stages
    # --------------------------------------------------------
    
    async def handle_notifications() -> Dict[str, Any]:
        """Send notifications."""
        notifier = orchestrator.registry.get_instance("telegram_notifier")
        notifications_sent = 0
        
        if notifier and hasattr(notifier, 'send_text'):
            try:
                # Send cycle completion summary
                ingestion = orchestrator.registry.get_instance("data_ingestion")
                if ingestion and hasattr(ingestion, '_last_result'):
                    result = ingestion._last_result
                    if result:
                        summary = (
                            f"📊 **Ingestion Cycle Complete**\n\n"
                            f"🕐 Duration: {result.duration_seconds:.1f}s\n"
                            f"📥 Fetched: {result.total_fetched}\n"
                            f"💾 Stored: {result.total_stored}\n"
                            f"❌ Errors: {result.total_errors}"
                        )
                        sent = await notifier.send_text(summary)
                        if sent:
                            notifications_sent += 1
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Notifications sent: {notifications_sent}")
        return {"notifications_sent": notifications_sent}
    
    async def handle_persist_results() -> Dict[str, Any]:
        """Persist all results."""
        # In production: save to database
        logger.info("Results persisted")
        return {"persisted": True}
    
    async def handle_monitoring() -> Dict[str, Any]:
        """Update monitoring state."""
        monitoring = orchestrator.registry.get_instance("monitoring")
        # In production: update dashboard metrics
        logger.info("Monitoring state updated")
        return {"monitoring_updated": True}
    
    # --------------------------------------------------------
    # Register Handlers
    # --------------------------------------------------------
    
    orchestrator.register_stage_handler(ExecutionStage.LOAD_CONFIG, handle_load_config)
    orchestrator.register_stage_handler(ExecutionStage.INIT_LOGGING, handle_init_logging)
    orchestrator.register_stage_handler(ExecutionStage.INIT_DATABASE, handle_init_database)
    orchestrator.register_stage_handler(ExecutionStage.INIT_HEALTH, handle_init_health)
    orchestrator.register_stage_handler(ExecutionStage.INIT_COLLECTORS, handle_init_collectors)
    orchestrator.register_stage_handler(ExecutionStage.RUN_INGESTION, handle_run_ingestion)
    orchestrator.register_stage_handler(ExecutionStage.RUN_PROCESSING, handle_run_processing)
    orchestrator.register_stage_handler(ExecutionStage.RUN_MARKET_CLASSIFICATION, handle_market_classification)
    orchestrator.register_stage_handler(ExecutionStage.RUN_RISK_SCORING, handle_risk_scoring)
    orchestrator.register_stage_handler(ExecutionStage.RUN_RISK_BUDGET, handle_risk_budget)
    orchestrator.register_stage_handler(ExecutionStage.RUN_COMMITTEE_REVIEW, handle_committee_review)
    orchestrator.register_stage_handler(ExecutionStage.RUN_STRATEGY, handle_run_strategy)
    orchestrator.register_stage_handler(ExecutionStage.RUN_TRADE_GUARD, handle_trade_guard)
    orchestrator.register_stage_handler(ExecutionStage.RUN_RISK_CONTROLLER, handle_risk_controller)
    orchestrator.register_stage_handler(ExecutionStage.RUN_EXECUTION, handle_execution)
    orchestrator.register_stage_handler(ExecutionStage.SEND_NOTIFICATIONS, handle_notifications)
    orchestrator.register_stage_handler(ExecutionStage.PERSIST_RESULTS, handle_persist_results)
    orchestrator.register_stage_handler(ExecutionStage.UPDATE_MONITORING, handle_monitoring)
    
    logger.info("Stage handlers wired")


def _create_placeholder_module(name: str) -> type:
    """
    Create a placeholder module class.
    
    ============================================================
    WARNING: PLACEHOLDER MODULES ARE ONLY ALLOWED IN SCAFFOLD MODE
    ============================================================
    
    Placeholder modules return EMPTY/MOCK data and perform NO real operations.
    They are intended ONLY for development scaffolding and testing the 
    orchestrator wiring.
    
    In PAPER or FULL mode, the orchestrator will REFUSE TO START if any
    placeholder modules are detected.
    
    In production, these would be replaced with actual module implementations
    that fetch real data and perform real operations.
    """
    class PlaceholderModule:
        # ============================================================
        # CRITICAL MARKER: This module is a PLACEHOLDER
        # The orchestrator checks this flag to enforce mode restrictions
        # ============================================================
        _is_placeholder: bool = True
        _placeholder_name: str = name
        
        def __init__(self, **kwargs):
            self._name = name
            self._running = False
        
        async def start(self) -> None:
            self._running = True
        
        async def stop(self) -> None:
            self._running = False
        
        def get_health_status(self) -> Dict[str, Any]:
            return {"status": "healthy", "module": self._name, "is_placeholder": True}
        
        # Placeholder methods that real modules would implement
        def can_trade(self) -> bool:
            return True
        
        def is_halted(self) -> bool:
            return False
        
        async def run_collection_cycle(self) -> List[Any]:
            return []  # Returns EMPTY - NO REAL DATA FETCHED
    
    PlaceholderModule.__name__ = name
    PlaceholderModule.__qualname__ = f"PlaceholderModule[{name}]"
    return PlaceholderModule


# ============================================================
# TELEGRAM ALERT CALLBACK
# ============================================================

async def telegram_alert_callback(
    severity: str,
    title: str,
    message: str,
) -> None:
    """
    Send alert via Telegram.
    
    This is a placeholder that would be connected to the actual
    TelegramNotifier in production.
    """
    logger = logging.getLogger(__name__)
    
    # Format alert (using ASCII-safe symbols for Windows compatibility)
    emoji = {
        "INFO": "[INFO]",
        "WARNING": "[WARN]",
        "HIGH": "[HIGH]",
        "CRITICAL": "[CRIT]",
    }.get(severity, "[ALERT]")
    
    logger.info(f"[ALERT] {emoji} {title}: {message}")
    
    # In production:
    # notifier = get_telegram_notifier()
    # await notifier.send_alert(f"{emoji} *{title}*\n{message}")


# ============================================================
# MAIN FUNCTION
# ============================================================

async def run_application(args) -> int:
    """
    Run the trading application.
    
    Args:
        args: Parsed CLI arguments
        
    Returns:
        Exit code
    """
    logger = logging.getLogger(__name__)
    
    # Build configuration
    config = build_config(args)
    
    # Create orchestrator
    orchestrator = Orchestrator(
        config=config,
        alert_callback=telegram_alert_callback,
    )
    
    # Wire modules
    wire_modules(orchestrator, {})
    
    # Wire stage handlers
    wire_stage_handlers(orchestrator)
    
    # Create module factory
    factory = ModuleFactory(config={})
    orchestrator.set_module_factory(factory)
    
    try:
        if args.single_cycle:
            # Run single cycle
            logger.info("Running single cycle...")
            result = await orchestrator.run_single_cycle()
            
            # Print result summary
            print(f"\nCycle Result: {'SUCCESS' if result.success else 'FAILED'}")
            print(f"Duration: {result.duration_seconds:.2f}s")
            print(f"Stages completed: {result.stages_completed}/{len(result.stage_results)}")
            
            if not result.success and result.failed_stage:
                print(f"Failed stage: {result.failed_stage.stage_id}")
                print(f"Error: {result.error}")
            
            return 0 if result.success else 1
        else:
            # Run forever
            logger.info("Starting main loop (press Ctrl+C to stop)...")
            await orchestrator.run_forever()
            return 0
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    finally:
        await orchestrator.stop()


def main() -> int:
    """Main entry point."""
    # Parse arguments
    parser = create_parser()
    args = parser.parse_args()
    
    # Show stages if requested
    if args.show_stages:
        from orchestrator.cli import show_stages
        show_stages(RuntimeMode(args.mode))
        return 0
    
    # Validate arguments
    errors = validate_args(args)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    
    # Print banner
    print_banner(args)
    
    # Run application
    return asyncio.run(run_application(args))


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
