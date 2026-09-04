"""Phase 4 predictive analytics: revenue forecasting. Run as:

    python -m models.revenue_forecast

Writes ANALYTICS.ML_REVENUE_FORECAST. See docs/predictive_analytics.md for
the full write-up, including why this series shows explosive growth (a
still-growing customer base during the Phase 1 generation window, not
seasonal demand) and how that shaped the model choice.

Forecast target: total monthly invoiced revenue (SUM(invoice_amount) from
ANALYTICS.VW_REVENUE_TRENDS, aggregated across all region/segment
combinations) -- the most complete, densest of the four revenue lenses
defined in Phase 2D (see that phase's "never sum these together" note;
here only ONE of the four, invoice_amount, is used, never blended with the
others).

The most recent calendar month in the data is PARTIAL (the warehouse's
reference "today" falls a few days into it) and is excluded from the
monthly series entirely -- comparing a 4-day month's total against full
30-day months would silently distort both backtesting and the forecast
anchor.

Chronological split only: the last 3 complete months are held out as a
test set, with every earlier month used for training -- never a random/
shuffled split, which would leak future values into training for a trend
this strong.
"""

import sys

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from models.common import (
    MODEL_VERSION, fetch_dataframe, get_logger, run_timestamp, save_metrics, save_model, write_table,
)

logger = get_logger("revenue_forecast")

TEST_MONTHS = 3
FORECAST_HORIZON_MONTHS = 3

MONTHLY_SQL = """
SELECT full_date, invoice_amount
FROM ANALYTICS.VW_REVENUE_TRENDS
"""


def load_monthly_series():
    daily = fetch_dataframe(MONTHLY_SQL)
    daily["FULL_DATE"] = pd.to_datetime(daily["FULL_DATE"])
    # Snowflake NUMBER columns come back as Python Decimal via the connector,
    # which pandas stores as object dtype -- statsmodels requires float64.
    daily["INVOICE_AMOUNT"] = daily["INVOICE_AMOUNT"].astype(float)
    daily["YEAR_MONTH"] = daily["FULL_DATE"].dt.to_period("M")

    monthly = daily.groupby("YEAR_MONTH").agg(
        invoice_amount=("INVOICE_AMOUNT", "sum"),
        last_day_observed=("FULL_DATE", "max"),
    ).reset_index()
    monthly = monthly.sort_values("YEAR_MONTH").reset_index(drop=True)

    # Drop a trailing month if the data doesn't reach that month's actual
    # last calendar day -- i.e. it's partial, not yet a complete period.
    last_row = monthly.iloc[-1]
    period_end = last_row["YEAR_MONTH"].end_time.normalize()
    if last_row["last_day_observed"] < period_end:
        logger.info(
            "Dropping partial trailing month %s (data observed through %s, month ends %s)",
            last_row["YEAR_MONTH"], last_row["last_day_observed"].date(), period_end.date(),
        )
        monthly = monthly.iloc[:-1]

    monthly = monthly.set_index(monthly["YEAR_MONTH"].dt.to_timestamp())["invoice_amount"]
    monthly.index.freq = "MS"
    return monthly


def _metrics(actual, predicted, label):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    mae = float(np.mean(np.abs(actual - predicted)))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    mape = float(np.mean(np.abs((actual - predicted) / actual)) * 100) if np.all(actual != 0) else None
    logger.info("[%s] MAE=%.0f RMSE=%.0f MAPE=%s", label, mae, rmse,
                f"{mape:.1f}%" if mape is not None else "n/a")
    return {"mae": mae, "rmse": rmse, "mape_pct": mape}


def seasonal_naive_forecast(train, horizon):
    """value(t) = value(t - 12 months) when that history exists, else the
    last observed value (a defensible fallback for the earliest forecasted
    months, where a full prior year doesn't yet exist)."""
    values = train.values
    preds = []
    for h in range(1, horizon + 1):
        idx = len(values) + h - 1 - 12
        preds.append(values[idx] if 0 <= idx < len(values) else values[-1])
    return np.array(preds)


def moving_average_forecast(train, horizon, window=3):
    avg = train.iloc[-window:].mean()
    return np.full(horizon, avg)


def holt_winters_forecast(train, horizon, seasonal_periods=None):
    kwargs = {"trend": "add"}
    if seasonal_periods:
        kwargs.update(seasonal="add", seasonal_periods=seasonal_periods)
    model = ExponentialSmoothing(train, initialization_method="estimated", **kwargs).fit()
    return model, model.forecast(horizon)


def run():
    series = load_monthly_series()
    logger.info("Monthly series: %d complete months, %s to %s",
                len(series), series.index.min().date(), series.index.max().date())

    train = series.iloc[:-TEST_MONTHS]
    test = series.iloc[-TEST_MONTHS:]
    logger.info("Chronological split: %d train months, %d test months (%s to %s)",
                len(train), len(test), test.index.min().date(), test.index.max().date())

    results = {}

    seasonal_naive_pred = seasonal_naive_forecast(train, TEST_MONTHS)
    results["seasonal_naive"] = _metrics(test.values, seasonal_naive_pred, "seasonal_naive")

    ma_pred = moving_average_forecast(train, TEST_MONTHS)
    results["moving_average_3mo"] = _metrics(test.values, ma_pred, "moving_average_3mo")

    # Only 36 training months (3 years) -- a 12-month seasonal component has
    # exactly 3 cycles to estimate from, marginal but attemptable; tested
    # against a trend-only model and picked on backtest performance, not
    # assumed.
    hw_model_seasonal, hw_pred_seasonal = holt_winters_forecast(train, TEST_MONTHS, seasonal_periods=12)
    results["holt_winters_seasonal"] = _metrics(test.values, hw_pred_seasonal.values, "holt_winters_seasonal")

    hw_model_trend_only, hw_pred_trend_only = holt_winters_forecast(train, TEST_MONTHS, seasonal_periods=None)
    results["holt_winters_trend_only"] = _metrics(test.values, hw_pred_trend_only.values, "holt_winters_trend_only")

    selected_name = min(results, key=lambda k: results[k]["rmse"])
    logger.info("Selected method: %s (lowest backtest RMSE)", selected_name)

    # Refit the selected method on the FULL series (train+test) to produce
    # the actual forward-looking forecast -- backtesting used train-only.
    full_model = None
    if selected_name == "seasonal_naive":
        forecast_values = seasonal_naive_forecast(series, FORECAST_HORIZON_MONTHS)
        residual_std = np.std(test.values - seasonal_naive_pred)
    elif selected_name == "moving_average_3mo":
        forecast_values = moving_average_forecast(series, FORECAST_HORIZON_MONTHS)
        residual_std = np.std(test.values - ma_pred)
    elif selected_name == "holt_winters_seasonal":
        full_model, forecast_series = holt_winters_forecast(series, FORECAST_HORIZON_MONTHS, seasonal_periods=12)
        forecast_values = forecast_series.values
        residual_std = np.std(test.values - hw_pred_seasonal.values)
    else:
        full_model, forecast_series = holt_winters_forecast(series, FORECAST_HORIZON_MONTHS, seasonal_periods=None)
        forecast_values = forecast_series.values
        residual_std = np.std(test.values - hw_pred_trend_only.values)

    # Save whatever the selected method actually is: the fitted statsmodels
    # results object for Holt-Winters, or the training series + window for a
    # baseline (seasonal_naive/moving_average have no fitted object to save).
    save_model({
        "method": selected_name,
        "fitted_model": full_model,
        "training_series": series,
    }, "revenue_forecast")

    forecast_values = np.maximum(forecast_values, 0)  # revenue cannot be negative
    forecast_dates = pd.date_range(series.index.max() + pd.DateOffset(months=1), periods=FORECAST_HORIZON_MONTHS, freq="MS")

    metrics_payload = {
        "model_version": MODEL_VERSION,
        "selected_method": selected_name,
        "methods_compared": results,
        "train_months": len(train),
        "test_months": len(test),
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
        "target": "monthly total invoice_amount (ANALYTICS.VW_REVENUE_TRENDS)",
        "chronological_split": True,
        "train_period": [str(train.index.min().date()), str(train.index.max().date())],
        "test_period": [str(test.index.min().date()), str(test.index.max().date())],
    }
    save_metrics(metrics_payload, "revenue_forecast")

    output = pd.DataFrame({
        "FORECAST_DATE": forecast_dates.date,
        "PREDICTED_REVENUE": forecast_values,
        "LOWER_BOUND": np.maximum(forecast_values - 1.96 * residual_std, 0),
        "UPPER_BOUND": forecast_values + 1.96 * residual_std,
        "MODEL_VERSION": MODEL_VERSION,
        "GENERATED_AT": run_timestamp(),
    })
    write_table(output, "ML_REVENUE_FORECAST")

    logger.info("Forecast:\n%s", output[["FORECAST_DATE", "PREDICTED_REVENUE", "LOWER_BOUND", "UPPER_BOUND"]].to_string(index=False))
    return {"selected_method": selected_name, "metrics": results[selected_name], "forecast": output}


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("revenue_forecast pipeline failed")
        sys.exit(1)
