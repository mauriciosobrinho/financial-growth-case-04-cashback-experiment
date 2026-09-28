import unittest

import numpy as np
import pandas as pd

from src.experiment_utils import (
    approximate_binary_mde,
    campaign_roi,
    cuped_adjust,
    holm_adjust,
    standardized_mean_difference,
)


class ExperimentUtilityTests(unittest.TestCase):
    def test_smd_is_zero_for_equal_samples(self):
        values = pd.Series([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(standardized_mean_difference(values, values), 0.0)

    def test_holm_adjustment_preserves_original_order(self):
        adjusted = holm_adjust([0.04, 0.01, 0.03])
        np.testing.assert_allclose(adjusted, [0.06, 0.03, 0.06])

    def test_cuped_reduces_variance_for_correlated_covariate(self):
        x = pd.Series(np.arange(100, dtype=float))
        y = 2 * x + pd.Series(np.tile([-1.0, 1.0], 50))
        adjusted, theta, reduction = cuped_adjust(y, x)
        self.assertGreater(theta, 1.9)
        self.assertGreater(reduction, 0.99)
        self.assertLess(adjusted.var(), y.var())

    def test_mde_decreases_with_sample_size(self):
        small = approximate_binary_mde(0.25, 1_000, 1_000)
        large = approximate_binary_mde(0.25, 10_000, 10_000)
        self.assertGreater(small, large)

    def test_roi_uses_total_campaign_cost(self):
        self.assertAlmostEqual(campaign_roi(200.0, 100.0), 2.0)


if __name__ == "__main__":
    unittest.main()

