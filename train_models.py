
import pandas as pd
import numpy as np
import joblib          
import json
import os
import warnings

warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing   import StandardScaler, LabelEncoder
from sklearn.ensemble        import RandomForestClassifier, GradientBoostingClassifier
from sklearn.tree            import DecisionTreeClassifier
from sklearn.linear_model    import LogisticRegression
from sklearn.metrics         import accuracy_score, f1_score, classification_report

BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
MDL_DIR  = os.path.join(BASE, "models")

os.makedirs(MDL_DIR, exist_ok=True)




def banner(text):
    print("\n" + "═" * 65)
    print(f"  {text}")
    print("═" * 65)


def train_and_compare(X_tr, X_te, y_tr, y_te,
                      X_all_scaled, y_all,
                      label="Model", class_weight=None):
    """
    Train 4 classifiers, compare by CV F1, return the best model.
    Decision Tree is overridden by Random Forest to ensure smooth
    probability distributions (DT gives hard 0/1 probs).
    """
    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, random_state=42),
        "Decision Tree":       DecisionTreeClassifier(
            random_state=42),
        "Random Forest":       RandomForestClassifier(
            n_estimators=200, random_state=42, n_jobs=-1,
            class_weight=class_weight),
        "Gradient Boosting":   GradientBoostingClassifier(
            n_estimators=150, random_state=42),
    }

    results = {}
    print(f"\n  {'Algorithm':<22} {'Accuracy':>9} {'F1':>9} "
          f"{'CV Mean':>9} {'CV Std':>8}")
    print("  " + "-" * 62)

    for name, model in models.items():
        model.fit(X_tr, y_tr)
        preds   = model.predict(X_te)
        acc     = accuracy_score(y_te, preds) * 100
        f1      = f1_score(y_te, preds, average="weighted") * 100
        cv      = cross_val_score(model, X_all_scaled, y_all,
                                  cv=5, scoring="f1_weighted")
        results[name] = dict(
            model=model, acc=acc, f1=f1,
            cv_mean=cv.mean() * 100, cv_std=cv.std() * 100,
        )
        print(f"  {name:<22} {acc:>8.2f}% {f1:>8.2f}% "
              f"{cv.mean()*100:>8.2f}% {cv.std()*100:>7.2f}%")

    best_name = max(results, key=lambda k: results[k]["cv_mean"])
    best      = results[best_name]

    if best_name == "Decision Tree":
        print(f"\n  ⚠️  Decision Tree gives hard 0/1 probabilities.")
        print(f"  ✅  Overriding to Random Forest for smooth confidence scores.")
        best_name = "Random Forest"
        best      = results["Random Forest"]

    print(f"\n  ✅ WINNER ({label}): {best_name}")
    print(f"     Accuracy : {best['acc']:.2f}%")
    print(f"     F1-Score : {best['f1']:.2f}%")
    print(f"     CV       : {best['cv_mean']:.2f}% ± {best['cv_std']:.2f}%")

    return best_name, best["model"], results




EXCLUDE = {
    "almond", "apricot", "asparagus", "barley", "beetroot", "blueberry",
    "boysenberry", "cherry", "elderberry", "gooseberry", "kiwi", "oat",
    "peach", "pear", "plum", "raspberry", "strawberry", "walnut", "wheat",
    "linseed", "rapeseed", "safflower", "castor", "ragi", "jowar",
    "blackpepper", "cardamom", "coriander", "drumstick", "horsegram",
    "horse_gram", "jackfruit", "jute", "turmeric", "taro", "yam",
    "zucchini", "squash", "brinjal", "ladyfinger", "french_bean",
    "lettuce", "radish", "turnip", "spinach", "celery", "broccoli",
    "cauliflower", "carrot", "moth_beans", "mothbeans",
    "bottle_gourd", "bottlegourd", "bittergourd",
    "lychee", "pomegranate", "grapes", "mustard", "pineapple",
    "apple", "blackberry",
}




np.random.seed(42)

def gen(mean, std):
    return float(np.clip(np.random.normal(mean, std), 0, None))


crop_params = {
    "cassava":     dict(N=(25, 8),  P=(15, 6),  K=(30,10), T=(28,3),  H=(75, 5), pH=(6.0,0.5), R=(1100,150)),
    "groundnuts":  dict(N=(20, 6),  P=(45,10),  K=(40,10), T=(27,3),  H=(65, 6), pH=(6.2,0.4), R=(900, 150)),
    "soybean":     dict(N=(20, 5),  P=(50,12),  K=(40,10), T=(25,3),  H=(70, 5), pH=(6.5,0.3), R=(950, 120)),
    "millet":      dict(N=(40,10),  P=(25, 8),  K=(25, 8), T=(32,4),  H=(45,10), pH=(6.5,0.5), R=(500, 120)),
    "sweetpotato": dict(N=(30, 8),  P=(45,10),  K=(60,15), T=(26,3),  H=(70, 5), pH=(6.2,0.3), R=(1000,120)),
    "beans":       dict(N=(20, 5),  P=(60,12),  K=(40,10), T=(24,3),  H=(65, 6), pH=(6.8,0.3), R=(850, 120)),
    "sorghum":     dict(N=(35,10),  P=(25, 8),  K=(25, 8), T=(32,4),  H=(40,10), pH=(6.3,0.5), R=(550, 120)),
    "tobacco":     dict(N=(40,10),  P=(35, 8),  K=(55,12), T=(24,3),  H=(65, 5), pH=(6.0,0.4), R=(950, 130)),
    "cowpea":      dict(N=(15, 5),  P=(40,10),  K=(30, 8), T=(28,4),  H=(55, 8), pH=(6.2,0.4), R=(700, 130)),
}

synthetic_rows = []
for crop, p in crop_params.items():
    for _ in range(100):
        synthetic_rows.append({
            "n":           gen(*p["N"]),
            "p":           gen(*p["P"]),
            "k":           gen(*p["K"]),
            "temperature": gen(*p["T"]),
            "humidity":    gen(*p["H"]),
            "ph":          gen(*p["pH"]),
            "rainfall":    gen(*p["R"]),
            "label":       crop,
        })

df_synthetic = pd.DataFrame(synthetic_rows)




banner("Building Merged Crop Dataset")

# Dataset A
df_a = pd.read_csv(os.path.join(DATA_DIR, "Crop_recommendation.csv"))
df_a.columns = df_a.columns.str.lower().str.strip()
df_a = df_a[["n","p","k","temperature","humidity","ph","rainfall","label"]].copy()
df_a["label"] = df_a["label"].str.lower().str.strip()
print(f"\n  Dataset A (Crop_recommendation)       : {len(df_a):>6} rows, "
      f"{df_a['label'].nunique()} crops")


df_b = pd.read_csv(os.path.join(DATA_DIR, "crop_recommendation_dataset.csv"))
df_b.columns = df_b.columns.str.lower().str.strip()
df_b = df_b[["n","p","k","temperature","humidity","ph","rainfall","label"]].copy()
df_b["label"] = df_b["label"].str.lower().str.strip()
df_b["label"] = df_b["label"].replace({
    "black_gram":   "blackgram",
    "kidney_beans": "kidneybeans",
    "pigeon_peas":  "pigeonpeas",
    "sweet_potato": "sweetpotato",
    "pearl_millet": "millet",
    "soyabean":     "soybean",
    "corn":         "maize",
    "peanut":       "groundnuts",
    "moong":        "mungbean",
})
print(f"  Dataset B (crop_recommendation_dataset): {len(df_b):>6} rows, "
      f"{df_b['label'].nunique()} crops")

# Dataset C
df_c = pd.read_csv(os.path.join(DATA_DIR, "Crop_Recm_Data.csv"))
df_c.columns = df_c.columns.str.lower().str.strip()
df_c = df_c[["n","p","k","temperature","humidity","ph","rainfall","label"]].copy()
df_c["label"] = df_c["label"].str.lower().str.strip()
print(f"  Dataset C (Crop_Recm_Data)             : {len(df_c):>6} rows, "
      f"{df_c['label'].nunique()} crops")

print(f"  Synthetic (Malawi crops, 3× weighted)  : "
      f"{len(df_synthetic) * 3:>6} rows, "
      f"{df_synthetic['label'].nunique()} crops")


df_merged = pd.concat(
    [df_a, df_b, df_c,
     df_synthetic, df_synthetic, df_synthetic],
    ignore_index=True,
)
df_merged = df_merged.dropna()
df_merged["label"] = df_merged["label"].str.lower().str.strip()


df_final = df_merged[~df_merged["label"].isin(EXCLUDE)].copy().reset_index(drop=True)

print(f"\n  After merge + exclusions:")
print(f"  Total rows   : {len(df_final)}")
print(f"  Crop classes : {df_final['label'].nunique()}")
print(f"  Classes      : {sorted(df_final['label'].unique())}")

df_final.to_csv(os.path.join(DATA_DIR, "merged_crop_dataset.csv"), index=False)
print(f"\n  💾 Saved → data/merged_crop_dataset.csv")



banner("Model 1 — Crop Recommendation")

CROP_FEATURES = ["n", "p", "k", "temperature", "humidity", "ph", "rainfall"]

X_crop = df_final[CROP_FEATURES].values
y_raw  = df_final["label"].values

crop_encoder = LabelEncoder()
y_crop       = crop_encoder.fit_transform(y_raw)

X_tr, X_te, y_tr, y_te = train_test_split(
    X_crop, y_crop,
    test_size=0.20, random_state=42,
    stratify=y_crop if int(np.bincount(y_crop).min()) >= 2 else None,
)

crop_scaler = StandardScaler()
X_tr_sc     = crop_scaler.fit_transform(X_tr)
X_te_sc     = crop_scaler.transform(X_te)
X_all_sc    = crop_scaler.transform(X_crop)

print(f"\n  Train: {len(X_tr)} | Test: {len(X_te)}")
print(f"  Features: {CROP_FEATURES}")

crop_best_name, crop_model, crop_results = train_and_compare(
    X_tr_sc, X_te_sc, y_tr, y_te,
    X_all_sc, y_crop,
    label="Crop",
    class_weight="balanced",
)

print("\n  Probability spot-check (top 3 per sample):")
for i, row in enumerate(crop_model.predict_proba(X_te_sc[:3])):
    top3 = sorted(zip(crop_encoder.classes_, row), key=lambda x: -x[1])[:3]
    print(f"    Sample {i+1}: " + " | ".join(f"{c}: {p*100:.1f}%" for c, p in top3))

print("\n  Per-crop Classification Report:")
print(classification_report(y_te, crop_model.predict(X_te_sc),
                             target_names=crop_encoder.classes_))

if hasattr(crop_model, "feature_importances_"):
    print("  Feature Importance:")
    for f, imp in sorted(zip(CROP_FEATURES, crop_model.feature_importances_),
                         key=lambda x: -x[1]):
        print(f"    {f:<12} {'█' * int(imp * 50)} {imp*100:.1f}%")

joblib.dump(crop_model,   os.path.join(MDL_DIR, "best_crop_model.pkl"),    compress=3)
joblib.dump(crop_scaler,  os.path.join(MDL_DIR, "crop_scaler.pkl"),        compress=3)
joblib.dump(crop_encoder, os.path.join(MDL_DIR, "crop_label_encoder.pkl"), compress=3)
print("\n  💾 Saved (joblib, compress=3):")
print("     best_crop_model.pkl | crop_scaler.pkl | crop_label_encoder.pkl")


for fname in ["best_crop_model.pkl", "crop_scaler.pkl", "crop_label_encoder.pkl"]:
    path = os.path.join(MDL_DIR, fname)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"     {fname:<35} {size_mb:.2f} MB")




banner("Model 2 — Fertilizer Prediction")

df_fert = pd.read_csv(os.path.join(DATA_DIR, "fertlizer_recommendation_dataset.csv"))
df_fert.columns = df_fert.columns.str.strip()

print(f"\n  Rows        : {len(df_fert)}")
print(f"  Fertilizers : {df_fert['Fertilizer'].nunique()} classes")
print(f"  Labels      : {sorted(df_fert['Fertilizer'].unique())}")
print(f"  Soils       : {sorted(df_fert['Soil'].unique())}")
print(f"  Crops       : {sorted(df_fert['Crop'].unique())}")

print("\n  Fertilizer class distribution:")
for cls, cnt in df_fert["Fertilizer"].value_counts().items():
    print(f"    {cls:<35} {cnt}")

soil_enc_fert = LabelEncoder()
crop_enc_fert = LabelEncoder()
fert_encoder  = LabelEncoder()

df_fert["Soil_enc"] = soil_enc_fert.fit_transform(df_fert["Soil"].str.strip())
df_fert["Crop_enc"] = crop_enc_fert.fit_transform(df_fert["Crop"].str.strip())
y_fert = fert_encoder.fit_transform(df_fert["Fertilizer"].str.strip())

FERT_FEATURES = [
    "Temperature", "Moisture", "Rainfall", "PH",
    "Nitrogen", "Phosphorous", "Potassium",
    "Soil_enc", "Crop_enc",
]
X_fert = df_fert[FERT_FEATURES].values

X_tr_f, X_te_f, y_tr_f, y_te_f = train_test_split(
    X_fert, y_fert,
    test_size=0.20, random_state=42,
    stratify=y_fert if int(np.bincount(y_fert).min()) >= 2 else None,
)

fert_scaler = StandardScaler()
X_tr_f_sc   = fert_scaler.fit_transform(X_tr_f)
X_te_f_sc   = fert_scaler.transform(X_te_f)
X_all_f_sc  = fert_scaler.transform(X_fert)

print(f"\n  Train: {len(X_tr_f)} | Test: {len(X_te_f)}")

fert_best_name, fert_model, fert_results = train_and_compare(
    X_tr_f_sc, X_te_f_sc, y_tr_f, y_te_f,
    X_all_f_sc, y_fert,
    label="Fertilizer",
    class_weight=None,
)

print("\n  Per-Fertilizer Classification Report:")
print(classification_report(y_te_f, fert_model.predict(X_te_f_sc),
                             target_names=fert_encoder.classes_))

# ── Save with joblib (compress=3) ─────────────────────────────────────────
joblib.dump(fert_model,    os.path.join(MDL_DIR, "best_fert_model.pkl"),     compress=3)
joblib.dump(fert_scaler,   os.path.join(MDL_DIR, "fert_scaler.pkl"),         compress=3)
joblib.dump(fert_encoder,  os.path.join(MDL_DIR, "fert_label_encoder.pkl"),  compress=3)
joblib.dump(soil_enc_fert, os.path.join(MDL_DIR, "soil_type_encoder.pkl"),   compress=3)
joblib.dump(crop_enc_fert, os.path.join(MDL_DIR, "crop_type_encoder.pkl"),   compress=3)
print("\n  💾 Saved (joblib, compress=3):")
print("     best_fert_model.pkl | fert_scaler.pkl | fert_label_encoder.pkl")
print("     soil_type_encoder.pkl | crop_type_encoder.pkl")

for fname in ["best_fert_model.pkl", "fert_scaler.pkl", "fert_label_encoder.pkl",
              "soil_type_encoder.pkl", "crop_type_encoder.pkl"]:
    path = os.path.join(MDL_DIR, fname)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"     {fname:<35} {size_mb:.2f} MB")



banner("Exporting Metadata")

metadata = {
    "crop_classes":       list(crop_encoder.classes_),
    "fert_classes":       list(fert_encoder.classes_),
    "soil_types":         list(soil_enc_fert.classes_),
    "crop_types_fert":    list(crop_enc_fert.classes_),

    "crop_model_name":    crop_best_name,
    "fert_model_name":    fert_best_name,
    "training_rows_crop": int(len(df_final)),
    "training_rows_fert": int(len(df_fert)),

    "crop_features":      CROP_FEATURES,
    "fert_features":      FERT_FEATURES,

    "datasets_used": {
        "A": "Crop_recommendation.csv (2200 rows, 22 classes)",
        "B": "crop_recommendation_dataset.csv (30530 rows, 80 classes)",
        "C": "Crop_Recm_Data.csv (10470 rows, 22 classes)",
        "D": f"Synthetic ({len(df_synthetic)} rows, {len(crop_params)} Malawi crops, weighted 3×)",
        "fert": "fertlizer_recommendation_dataset.csv (5410 rows, 10 classes)",
    },

    "crop_model_results": {
        k: {"f1": round(v["f1"], 2), "acc": round(v["acc"], 2),
            "cv": round(v["cv_mean"], 2)}
        for k, v in crop_results.items()
    },
    "fert_model_results": {
        k: {"f1": round(v["f1"], 2), "acc": round(v["acc"], 2),
            "cv": round(v["cv_mean"], 2)}
        for k, v in fert_results.items()
    },
}

with open(os.path.join(MDL_DIR, "model_metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print("\n  💾 Saved: models/model_metadata.json")



banner("Training Complete ✅")

# Total model directory size
total_mb = sum(
    os.path.getsize(os.path.join(MDL_DIR, f)) / (1024 * 1024)
    for f in os.listdir(MDL_DIR)
    if f.endswith(".pkl")
)

print(f"""
  Models saved to:  backend/models/

    ✅ Crop model   → best_crop_model.pkl    ({crop_best_name})
    ✅ Fert model   → best_fert_model.pkl    ({fert_best_name})
    ✅ Metadata     → model_metadata.json

  Crop dataset : {len(df_final)} rows, {df_final['label'].nunique()} classes
  Fert dataset : {len(df_fert)} rows, {df_fert['Fertilizer'].nunique()} classes

  Total .pkl size on disk : {total_mb:.2f} MB  (joblib compress=3)

  ── After training — verify crop classes in ZONE_CROPS ──────────────────
  python -c "
  import joblib
  e = joblib.load('models/crop_label_encoder.pkl')
  print('Crop classes:', list(e.classes_))
  "

  Next step:  python app.py  →  http://localhost:5000
""")