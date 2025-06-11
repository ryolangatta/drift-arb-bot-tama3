# Smart import with fallback
DRIFT_INTEGRATION_AVAILABLE = False
try:
    from modules.drift_integration import DriftIntegration
    DRIFT_INTEGRATION_AVAILABLE = True
    logger.info("✅ Real DriftPy integration available")
except ImportError as e:
    logger.warning(f"⚠️ DriftPy unavailable, using simulation: {e}")

# Use the best available Drift integration
if USE_REAL_DRIFT and DRIFT_INTEGRATION_AVAILABLE:
    logger.info("🚀 Using REAL Drift integration")
    drift_integration = DriftIntegration()
else:
    logger.info("🎯 Using proven simulation")
    from modules.drift_devnet_simple import DriftDevnetSimple
    drift_integration = DriftDevnetSimple()
