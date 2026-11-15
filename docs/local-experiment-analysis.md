# Local experiment analysis — partial feature #73

This code extends AURA with a small, actual offline scientific analysis primitive implemented entirely with the Python 3.13 standard library. `describe_sample`, `compare_independent_samples`, and `describe_paired_changes` compute bounded descriptive statistics for at most 10,000 finite values. The functions report sample variance, standard deviation, standard error, min/max, median and a reproducible input SHA-256. Single observations correctly report variance/SEM as unavailable.

No p-values, confidence intervals, statistical significance, causal assertions, model inference or scientific validity claims are produced. Data are explicitly marked untrusted. There is no external API, package dependency, filesystem write, execution, MCP capability, agent action or physical device control.

Feature #73 is not complete: experimental design metadata, provenance, confidence intervals under validated assumptions, interactive reporting, independent scientific validation and real research datasets remain to be integrated. No lab hardware was tested.

Run `cd core && uv run pytest -q tests/test_local_experiment_statistics.py`, full AURA Core Assurance and release-lock verification. Use existing JAS architecture rather than a new scientific authority layer.

## Simple linear modelling (partial feature #67)

`fit_simple_linear_model(x, y)` fits a bounded ordinary least-squares line (intercept, slope, descriptive R², residual standard error) from paired finite observations. `predict` returns arithmetic extrapolation only; it **does not** establish causal effect, statistical significance, reliable prediction outside the observed domain or model safety. Constant predictors fail closed, and constant outcomes report R² unavailable.

Test with `cd core && uv run pytest -q tests/test_local_linear_model.py`. No imported math-science package or paid API is required. Both #67 and #73 remain partial until integration and scientific validation.
