from app.data import generate_customers
from app.features import FEATURE_KEYS, vector
from app.model import Model, fit


def test_model_quality():
    rows = generate_customers(count=1200, seed=99)
    payload = fit(rows, seed=11)
    model = Model(payload)

    metrics = payload["metrics"]
    assert 0.75 < metrics["auc"] < 0.99
    assert 0.65 < metrics["accuracy"] < 0.95
    assert metrics["brier"] < 0.18
    assert metrics["confusion"]["true_positive"] > 0
    assert metrics["confusion"]["true_negative"] > 0


def test_scores_are_probabilities():
    rows = generate_customers(count=200, seed=5)
    payload = fit(rows, seed=3)
    model = Model(payload)
    for customer in rows[:50]:
        score = model.score(customer)
        assert 0.0 <= score <= 1.0


def test_feature_vector_shape():
    rows = generate_customers(count=10, seed=1)
    for customer in rows:
        assert len(vector(customer)) == len(FEATURE_KEYS)
        assert all(isinstance(value, float) for value in vector(customer))


def test_contributions_explain_score():
    rows = generate_customers(count=200, seed=7)
    payload = fit(rows, seed=9)
    model = Model(payload)
    customer = rows[0]
    contributions = model.contributions(customer)
    assert len(contributions) == len(FEATURE_KEYS)
    assert all(isinstance(value, float) for _, value in contributions)
