"""Étape 6 – Scoring : les prédictions du modèle dans PostgreSQL, pour Power BI.

Pour chaque commande livrée, le script calcule la probabilité d'avis négatif
avec la forêt aléatoire du notebook 02 (scénarios A « à l'achat » et B « à la livraison »),
puis écrit le résultat dans la table `predictions` de la base olist.

⚠️ Pour être honnête, chaque commande est notée par un modèle qui ne l'a JAMAIS vue
pendant son entraînement : c'est la « prédiction hors échantillon » (cross_val_predict).
Sinon, le modèle noterait des commandes qu'il connaît par cœur, et les résultats
du dashboard seraient trop beaux pour être vrais.

Usage :  python src/scoring.py      (environ 3 à 5 minutes)
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from config import pg_url  # noqa: E402

# Même jeu de données que dans notebooks/02_machine_learning.ipynb
REQUETE = """
    WITH notes AS (
        SELECT order_id, AVG(review_score) AS note
        FROM order_reviews
        GROUP BY order_id
    ),
    articles AS (
        SELECT i.order_id,
               COUNT(*)                                                         AS nb_articles,
               COUNT(DISTINCT i.seller_id)                                      AS nb_vendeurs,
               SUM(i.price)                                                     AS prix_total,
               SUM(i.freight_value)                                             AS frais_port,
               SUM(p.product_weight_g)                                          AS poids_total_g,
               SUM(p.product_length_cm * p.product_height_cm * p.product_width_cm) AS volume_total_cm3
        FROM order_items i
        JOIN products p ON p.product_id = i.product_id
        GROUP BY i.order_id
    ),
    article_principal AS (           -- l'article le plus cher de la commande
        SELECT DISTINCT ON (i.order_id)
               i.order_id, i.seller_id,
               COALESCE(t.product_category_name_english, 'inconnue') AS categorie
        FROM order_items i
        JOIN products p ON p.product_id = i.product_id
        LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
        ORDER BY i.order_id, i.price DESC
    ),
    paiements AS (
        SELECT order_id,
               MAX(payment_installments)                                AS nb_echeances,
               (ARRAY_AGG(payment_type ORDER BY payment_value DESC))[1] AS moyen_paiement
        FROM order_payments
        GROUP BY order_id
    )
    SELECT o.order_id,
           EXTRACT(MONTH FROM o.order_purchase_timestamp)::int                            AS mois_achat,
           o.order_estimated_delivery_date::date - o.order_purchase_timestamp::date       AS delai_promis_jours,
           a.nb_articles, a.nb_vendeurs, a.prix_total, a.frais_port,
           a.poids_total_g, a.volume_total_cm3,
           ap.categorie,
           c.customer_state AS etat_client,
           s.seller_state   AS etat_vendeur,
           gc.lat AS lat_client,  gc.lng AS lng_client,
           gs.lat AS lat_vendeur, gs.lng AS lng_vendeur,
           pm.moyen_paiement, pm.nb_echeances,
           o.order_delivered_customer_date::date - o.order_purchase_timestamp::date      AS delai_jours,
           o.order_delivered_customer_date::date - o.order_estimated_delivery_date::date AS ecart_jours,
           n.note
    FROM orders o
    JOIN notes             n  ON n.order_id  = o.order_id
    JOIN articles          a  ON a.order_id  = o.order_id
    JOIN article_principal ap ON ap.order_id = o.order_id
    JOIN customers         c  ON c.customer_id = o.customer_id
    JOIN sellers           s  ON s.seller_id   = ap.seller_id
    LEFT JOIN geolocation_zip gc ON gc.zip_code_prefix = c.customer_zip_code_prefix
    LEFT JOIN geolocation_zip gs ON gs.zip_code_prefix = s.seller_zip_code_prefix
    LEFT JOIN paiements       pm ON pm.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
"""

FEATURES_NUM_ACHAT = ["delai_promis_jours", "nb_articles", "nb_vendeurs", "prix_total", "frais_port",
                      "poids_total_g", "volume_total_cm3", "distance_km", "meme_etat",
                      "nb_echeances", "mois_achat"]
FEATURES_CAT = ["categorie", "etat_client", "moyen_paiement"]
FEATURES_LIVRAISON = ["delai_jours", "ecart_jours"]
FEATURES_A = FEATURES_NUM_ACHAT + FEATURES_CAT
FEATURES_B = FEATURES_NUM_ACHAT + FEATURES_LIVRAISON + FEATURES_CAT


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def preparer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["distance_km"] = haversine_km(df["lat_client"], df["lng_client"], df["lat_vendeur"], df["lng_vendeur"])
    df["meme_etat"] = (df["etat_client"] == df["etat_vendeur"]).astype(int)
    df["avis_negatif"] = (df["note"] <= 2).astype(int)
    return df


def construire_pipeline(features: list[str]) -> Pipeline:
    num = [f for f in features if f not in FEATURES_CAT]
    cat = [f for f in features if f in FEATURES_CAT]
    preparation = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")),
                          ("scaler", StandardScaler())]), num),
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=100), cat),
    ])
    foret = RandomForestClassifier(n_estimators=150, max_depth=12, min_samples_leaf=20,
                                   class_weight="balanced_subsample", n_jobs=-1, random_state=42)
    return Pipeline([("preparation", preparation), ("modele", foret)])


def probabilites_hors_echantillon(df: pd.DataFrame, features: list[str], nom: str) -> np.ndarray:
    """Probabilité d'avis négatif, chaque commande étant prédite par un modèle qui ne l'a pas vue."""
    t0 = time.time()
    plis = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    proba = cross_val_predict(construire_pipeline(features), df[features], df["avis_negatif"],
                              cv=plis, method="predict_proba")[:, 1]
    auc = roc_auc_score(df["avis_negatif"], proba)
    print(f"   {nom:<28} ROC-AUC = {auc:.3f}   ({time.time() - t0:.0f} s)")
    return proba


def niveau_de_risque(proba: pd.Series) -> pd.Series:
    """Élevé = les 10 % de commandes les plus à risque ; Moyen = les 20 % suivants ; Faible = le reste."""
    seuil_eleve, seuil_moyen = proba.quantile(0.90), proba.quantile(0.70)
    return pd.Series(np.select([proba >= seuil_eleve, proba >= seuil_moyen],
                               ["1. Élevé", "2. Moyen"], "3. Faible"), index=proba.index)


def main() -> None:
    from sqlalchemy import create_engine

    t0 = time.time()
    engine = create_engine(pg_url())

    print("[1/3] Lecture des commandes livrées dans PostgreSQL")
    df = preparer(pd.read_sql(REQUETE, engine))
    print(f"   {len(df):,} commandes".replace(",", " "))

    print("[2/3] Entraînement de la forêt aléatoire (validation croisée 5 plis)")
    df["proba_achat"] = probabilites_hors_echantillon(df, FEATURES_A, "Scénario A (à l'achat)")
    df["proba_livraison"] = probabilites_hors_echantillon(df, FEATURES_B, "Scénario B (à la livraison)")
    df["niveau_risque"] = niveau_de_risque(df["proba_livraison"])

    predictions = df[["order_id", "proba_achat", "proba_livraison", "niveau_risque", "avis_negatif"]].copy()
    predictions[["proba_achat", "proba_livraison"]] = predictions[["proba_achat", "proba_livraison"]].round(4)

    print("[3/3] Écriture de la table 'predictions'")
    predictions.to_sql("predictions", engine, if_exists="replace", index=False,
                       method="multi", chunksize=5000)

    # Contrôle : le modèle doit bien séparer les commandes
    controle = (predictions.groupby("niveau_risque")
                .agg(nb_commandes=("order_id", "size"),
                     pct_avis_negatifs_reels=("avis_negatif", lambda s: round(100 * s.mean(), 1))))
    print("\n" + controle.to_string())
    print(f"\nTerminé en {time.time() - t0:.0f} s. Dans Power BI : Accueil > Obtenir les données > "
          "PostgreSQL > table 'predictions'.")


if __name__ == "__main__":
    main()
