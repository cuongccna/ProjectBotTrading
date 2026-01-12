"""
Orchestrator Package - System Coordination Layer.

============================================================
PACKAGE OVERVIEW
============================================================
This package provides the orchestration layer for the crypto trading system.
It is the SINGLE ENTRYPOINT that controls startup, shutdown, and execution flow.

============================================================
CORE PRINCIPLES
============================================================
1. The orchestrator has NO business logic
2. It does NOT modify trading decisions
3. It does NOT bypass any safety authority
4. It ONLY coordinates execution
5. Default behavior on uncertainty is NO TRADE

============================================================
ARCHITECTURE
============================================================

    +-----------------------------------------------------+
    |                     Orchestrator                    |
    |-----------------------------------------------------|
    |  RuntimeMode    |  7 modes of operation            |
    |  ExecutionStage |  17 stages in strict order       |
    |  ModuleRegistry |  Module lifecycle management     |
    |  Pipeline       |  Stage execution coordination    |
    |  CLI            |  Command-line interface          |
    +-----------------------------------------------------+

============================================================
RUNTIME MODES
============================================================
- ingest   : Run data ingestion only
- process  : Run data processing only
- risk     : Run risk aggregation only
- trade    : Full pipeline with execution
- backtest : Replay historical data
- monitor  : Monitoring and alerting only
- full     : Full live system in order

============================================================
EXECUTION STAGES (17 in strict order)
============================================================
 1. LOAD_CONFIG              - Load configuration
 2. INIT_LOGGING             - Initialize logging
 3. INIT_DATABASE            - Initialize database
 4. INIT_HEALTH              - Initialize health checks
 5. INIT_COLLECTORS          - Initialize data collectors
 6. RUN_INGESTION            - Run ingestion modules
 7. RUN_PROCESSING           - Run processing pipelines
 8. RUN_MARKET_CLASSIFICATION - Classify market conditions
 9. RUN_RISK_SCORING         - Run risk aggregation
10. RUN_RISK_BUDGET          - Run risk budget manager
11. RUN_STRATEGY             - Run strategy engine
12. RUN_TRADE_GUARD          - Run trade guard absolute
13. RUN_RISK_CONTROLLER      - Run system risk controller
14. RUN_EXECUTION            - Run execution engine
15. SEND_NOTIFICATIONS       - Send notifications
16. PERSIST_RESULTS          - Persist all results
17. UPDATE_MONITORING        - Update monitoring state

============================================================
QUICK START
============================================================
Command line usage::

    # Run full system
    python app.py --mode full
    
    # Single cycle in dry-run
    python app.py --mode trade --single-cycle --dry-run
    
    # Backtest historical data
    python app.py --mode backtest --start-date 2024-01-01 --end-date 2024-01-31
    
    # Show stages for a mode
    python app.py --mode full --show-stages

PM2 usage::

    pm2 start app.py --interpreter python --name crypto-trader -- --mode full

Programmatic usage::

    import asyncio
    from orchestrator import (
        Orchestrator,
        OrchestratorConfig,
        RuntimeMode,
        ExecutionStage,
    )
    
    async def main():
        config = OrchestratorConfig(
            mode=RuntimeMode.TRADE,
            dry_run=True,
        )
        
        orchestrator = Orchestrator(config=config)
        
        # Register modules
        orchestrator.register_module(
            name="my_module",
            module_class=MyModule,
            dependencies=["database"],
            required_stages=[ExecutionStage.RUN_PROCESSING],
        )
        
        # Register handlers
        orchestrator.register_stage_handler(
            ExecutionStage.RUN_PROCESSING,
            my_handler,
        )
        
        # Run
        await orchestrator.run_forever()
    
    asyncio.run(main())

============================================================
EXPORTS
============================================================
"""

# ============================================================
# Models
# ============================================================
from orchestrator.models import (
    # Enums
    RuntimeMode,
    ExecutionStage,
    ModuleStatus,
    
    # Results
    StageResult,
    CycleResult,
    
    # Module definitions
    ModuleDefinition,
    ModuleInstance,
    
    # Configuration
    OrchestratorConfig,
    
    # Safety
    SafetyContext,
)

# ============================================================
# Registry
# ============================================================
from orchestrator.registry import (
    # Protocol
    ModuleProtocol,
    
    # Registry
    ModuleRegistry,
    
    # Dependency management
    DependencyGraph,
    
    # Factory
    ModuleFactory,
)

# ============================================================
# Pipeline
# ============================================================
from orchestrator.pipeline import (
    # Types
    StageHandler,
    
    # Execution
    StageExecutor,
    ExecutionPipeline,
    
    # Builder
    PipelineBuilder,
    
    # History
    CycleHistory,
)

# ============================================================
# Core
# ============================================================
from orchestrator.core import (
    # Main orchestrator
    Orchestrator,
    
    # Factory function
    create_orchestrator,
    
    # Logging setup
    setup_logging,
)

# ============================================================
# CLI
# ============================================================
from orchestrator.cli import (
    # Parser
    create_parser,
    
    # Validation
    validate_args,
    
    # Configuration
    build_config,
    
    # Display
    show_stages,
    print_banner,
    
    # Entry points
    main,
    async_main,
)

# ============================================================
# Package metadata
# ============================================================
__version__ = "1.0.0"
__author__ = "Trading System Team"

__all__ = [
    # Models - Enums
    "RuntimeMode",
    "ExecutionStage",
    "ModuleStatus",
    
    # Models - Results
    "StageResult",
    "CycleResult",
    
    # Models - Module definitions
    "ModuleDefinition",
    "ModuleInstance",
    
    # Models - Configuration
    "OrchestratorConfig",
    
    # Models - Safety
    "SafetyContext",
    
    # Registry - Protocol
    "ModuleProtocol",
    
    # Registry - Registry
    "ModuleRegistry",
    
    # Registry - Dependency management
    "DependencyGraph",
    
    # Registry - Factory
    "ModuleFactory",
    
    # Pipeline - Types
    "StageHandler",
    
    # Pipeline - Execution
    "StageExecutor",
    "ExecutionPipeline",
    
    # Pipeline - Builder
    "PipelineBuilder",
    
    # Pipeline - History
    "CycleHistory",
    
    # Core - Main orchestrator
    "Orchestrator",
    
    # Core - Factory function
    "create_orchestrator",
    
    # Core - Logging setup
    "setup_logging",
    
    # CLI - Parser
    "create_parser",
    
    # CLI - Validation
    "validate_args",
    
    # CLI - Configuration
    "build_config",
    
    # CLI - Display
    "show_stages",
    "print_banner",
    
    # CLI - Entry points
    "main",
    "async_main",
]
