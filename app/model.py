import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

from .features import FEATURE_KEYS, vector

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "model.json"
MODEL_VERSION = 1


def sigmoid(value):
    value = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def solve(matrix, values):
    size = len(values)
    a = [row[:] + [values[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(a[row][column]))
        if abs(a[pivot][column]) < 1e-12:
            continue
        a[column], a[pivot] = a[pivot], a[column]
        divisor = a[column][column]
        for index in range(column, size + 1):
            a[column][index] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = a[row][column]
            if abs(factor) < 1e-15:
                continue
            for index in range(column, size + 1):
                a[row][index] -= factor * a[column][index]
    return [a[index][size] for index in range(size)]


def standardized(rows, means, stds):
    result = []
    for row in rows:
        result.append([(value - means[index]) / stds[index] for index, value in enumerate(row)])
    return result


def fit(rows, seed=5, l2=1.6, iterations=14):
    rng = random.Random(seed)
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    split = int(len(rows) * 0.75)
    train_rows = [rows[index] for index in indices[:split]]
    test_rows = [rows[index] for index in indices[split:]]

    raw_train = [vector(row) for row in train_rows]
    labels = [int(row["churned"]) for row in train_rows]
    dimensions = len(FEATURE_KEYS)

    means = [sum(row[index] for row in raw_train) / len(raw_train) for index in range(dimensions)]
    stds = []
    for index in range(dimensions):
        variance = sum((row[index] - means[index]) ** 2 for row in raw_train) / len(raw_train)
        stds.append(max(math.sqrt(variance), 1e-6))

    features = standardized(raw_train, means, stds)
    count = len(features)
    beta = [0.0] * (dimensions + 1)

    for _ in range(iterations):
        gradient = [0.0] * (dimensions + 1)
        hessian = [[0.0] * (dimensions + 1) for _ in range(dimensions + 1)]

        for row_index in range(count):
            row = features[row_index]
            score = beta[0]
            for index in range(dimensions):
                score += beta[index + 1] * row[index]
            probability = sigmoid(score)
            weight = max(probability * (1 - probability), 1e-6)
            residual = labels[row_index] - probability

            gradient[0] += residual
            hessian[0][0] += weight
            for a in range(dimensions):
                value_a = row[a]
                gradient[a + 1] += residual * value_a
                hessian[0][a + 1] += weight * value_a
                hessian[a + 1][0] += weight * value_a
                for b in range(a, dimensions):
                    hessian[a + 1][b + 1] += weight * value_a * row[b]

        for a in range(dimensions + 1):
            for b in range(a + 1, dimensions + 1):
                hessian[b][a] = hessian[a][b]

        for index in range(1, dimensions + 1):
            hessian[index][index] += l2
            gradient[index] -= l2 * beta[index]

        delta = solve(hessian, gradient)
        beta = [beta[index] + delta[index] for index in range(dimensions + 1)]
        if max(abs(value) for value in delta) < 1e-7:
            break

    raw_test = [vector(row) for row in test_rows]
    test_features = standardized(raw_test, means, stds)
    test_labels = [int(row["churned"]) for row in test_rows]
    scores = []
    for row in test_features:
        score = beta[0]
        for index in range(dimensions):
            score += beta[index + 1] * row[index]
        scores.append(sigmoid(score))

    metrics = evaluate(test_labels, scores)
    metrics["train_size"] = count
    metrics["test_size"] = len(test_rows)
    metrics["churn_rate"] = round(sum(int(row["churned"]) for row in rows) / len(rows), 4)

    return {
        "version": MODEL_VERSION,
        "feature_keys": FEATURE_KEYS,
        "means": means,
        "stds": stds,
        "beta": beta,
        "metrics": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }


def evaluate(labels, scores):
    positives = sum(labels)
    negatives = len(labels) - positives

    order = sorted(range(len(scores)), key=lambda index: scores[index])
    ranks = [0.0] * len(scores)
    position = 0
    while position < len(order):
        end = position
        while end < len(order) and scores[order[end]] == scores[order[position]]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for index in range(position, end):
            ranks[order[index]] = average_rank
        position = end

    if positives and negatives:
        rank_sum = sum(ranks[index] for index in range(len(labels)) if labels[index] == 1)
        auc = (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    else:
        auc = 0.5

    best_threshold = 0.5
    best_f1 = -1.0
    for step in range(5, 96):
        candidate = step / 100.0
        tp = sum(1 for label, score in zip(labels, scores) if label == 1 and score >= candidate)
        fp = sum(1 for label, score in zip(labels, scores) if label == 0 and score >= candidate)
        fn = positives - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        candidate_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if candidate_f1 > best_f1:
            best_f1 = candidate_f1
            best_threshold = candidate

    threshold = best_threshold
    true_positive = false_positive = true_negative = false_negative = 0
    for label, score in zip(labels, scores):
        predicted = 1 if score >= threshold else 0
        if label == 1 and predicted == 1:
            true_positive += 1
        elif label == 1:
            false_negative += 1
        elif predicted == 1:
            false_positive += 1
        else:
            true_negative += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (true_positive + true_negative) / len(labels) if labels else 0.0
    brier = sum((score - label) ** 2 for label, score in zip(labels, scores)) / len(labels) if labels else 0.0

    return {
        "auc": round(auc, 4),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "brier": round(brier, 4),
        "threshold": threshold,
        "confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
    }


class Model:
    def __init__(self, payload):
        self.feature_keys = payload["feature_keys"]
        self.means = payload["means"]
        self.stds = payload["stds"]
        self.beta = payload["beta"]
        self.metrics = payload["metrics"]
        self.trained_at = payload["trained_at"]
        self.dimensions = len(self.feature_keys)

    def score(self, customer):
        values = vector(customer)
        result = self.beta[0]
        for index in range(self.dimensions):
            result += self.beta[index + 1] * (values[index] - self.means[index]) / self.stds[index]
        return sigmoid(result)

    def contributions(self, customer):
        values = vector(customer)
        result = []
        for index, key in enumerate(self.feature_keys):
            z_value = (values[index] - self.means[index]) / self.stds[index]
            result.append((key, self.beta[index + 1] * z_value))
        return result


def load_or_train(rows, path=MODEL_PATH):
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") == MODEL_VERSION and payload.get("feature_keys") == FEATURE_KEYS:
                return Model(payload)
        except (ValueError, KeyError):
            pass

    payload = fit(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return Model(payload)
