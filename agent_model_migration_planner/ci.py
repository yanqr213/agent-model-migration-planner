from .planner import MigrationPlan

EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_BLOCKED = 2
EXIT_CONFIG_ERROR = 3


def ci_exit_code(plan: MigrationPlan) -> int:
    if plan.config.fail_on_risk and (
        plan.risk_profile.score >= plan.config.risk_threshold or plan.risk_profile.has_blocking
    ):
        return EXIT_BLOCKED
    if plan.config.fail_on_eval_regression:
        evals = plan.eval_comparison
        if evals.score_delta < plan.config.eval_config.pass_threshold_delta:
            return EXIT_BLOCKED
        if evals.regression_rate > plan.config.eval_config.max_regression_rate:
            return EXIT_BLOCKED
    return EXIT_OK
