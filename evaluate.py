"""
SkyGuard AI - Evaluation
--------------------------
Computes Precision / Recall / F1 against the ground-truth labels our own
injector created. Use these numbers in the pitch deck instead of vague
"it works" claims - judges specifically weighted "Detection Accuracy" at 20%.
"""

import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
from anomaly_detector import SkyGuardDetector


def evaluate():
    df = pd.read_csv("data/aws_dataset.csv", parse_dates=["timestamp"])
    detector = SkyGuardDetector().fit(df)
    result = detector.detect(df)

    y_true = result["is_anomaly"]
    y_pred = result["predicted_anomaly"]

    p = precision_score(y_true, y_pred)
    r = recall_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred)

    print("=== Overall Detection Performance ===")
    print(f"Precision: {p:.3f}")
    print(f"Recall:    {r:.3f}")
    print(f"F1 Score:  {f1:.3f}")
    print(f"Confusion Matrix [ [TN FP] [FN TP] ]:\n{cm}")

    print("\n=== Recall by Injected Anomaly Type ===")
    for a_type in result["anomaly_type"].unique():
        if a_type == "none":
            continue
        subset = result[result["anomaly_type"] == a_type]
        recall_type = subset["predicted_anomaly"].mean()
        print(f"{a_type:30s} recall: {recall_type:.3f}  (n={len(subset)})")

    result.to_csv("data/detection_results.csv", index=False)
    return p, r, f1


if __name__ == "__main__":
    evaluate()
