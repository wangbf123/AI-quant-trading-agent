import numpy as np
import pandas as pd
import pytest

from quantaalpha.backtest.runner import BacktestIntegrityError, BacktestRunner


@pytest.mark.parametrize("prediction", [None, pd.Series(dtype=float), pd.Series([np.nan]), pd.Series([np.inf])])
def test_empty_or_invalid_predictions_cannot_be_success(prediction):
    with pytest.raises(BacktestIntegrityError):
        BacktestRunner._validate_predictions(prediction)


def test_partial_ic_metrics_cannot_be_a_completed_backtest():
    with pytest.raises(BacktestIntegrityError, match="missing"):
        BacktestRunner._require_portfolio_metrics({"IC": 0.1})
    with pytest.raises(BacktestIntegrityError, match="non-finite"):
        BacktestRunner._require_portfolio_metrics({"annualized_return": np.inf, "information_ratio": 1, "max_drawdown": -0.1})
    BacktestRunner._require_portfolio_metrics({"annualized_return": -0.03, "information_ratio": -0.4, "max_drawdown": -0.1})


def test_upstream_feedback_reports_net_before_gross():
    from quantaalpha.factors.feedback import process_results
    result = pd.DataFrame({"0": {"1day.excess_return_with_cost.annualized_return": -0.1, "1day.excess_return_without_cost.annualized_return": 0.2, "IC": 0.01}})
    text = process_results(result, None)
    assert "with_cost" in text and "without_cost" in text
    assert text.index("with_cost") < text.index("without_cost")
