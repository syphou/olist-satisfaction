"""Découverte des données Olist.

Affiche, pour chaque fichier : à quoi il sert, sa taille, ses colonnes et
quelques exemples. Puis suit UNE commande à travers toutes les tables.

Usage :  python src/explore.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 12)
pd.set_option("display.max_colwidth", 25)

TABLES = {
    "customers": ("olist_customers_dataset.csv", "Les clients : qui achète, et où il habite."),
    "orders": ("olist_orders_dataset.csv", "Les commandes : statut et dates (achat, livraison prévue, livraison réelle)."),
    "order_items": ("olist_order_items_dataset.csv", "Les articles de chaque commande : produit, vendeur, prix, frais de port."),
    "products": ("olist_products_dataset.csv", "Les produits : catégorie, poids, dimensions."),
    "sellers": ("olist_sellers_dataset.csv", "Les vendeurs : où ils sont situés."),
    "order_payments": ("olist_order_payments_dataset.csv", "Les paiements : moyen de paiement, nombre d'échéances, montant."),
    "order_reviews": ("olist_order_reviews_dataset.csv", "Les avis clients : la note de 1 à 5 laissée après la commande."),
    "category_translation": ("product_category_name_translation.csv", "Traduction des catégories (portugais -> anglais)."),
    "geolocation": ("olist_geolocation_dataset.csv", "Coordonnées GPS des codes postaux."),
}


def title(text: str) -> None:
    print("\n" + "=" * 90)
    print(text)
    print("=" * 90)


def main() -> None:
    dfs = {}
    for name, (file, desc) in TABLES.items():
        df = pd.read_csv(RAW_DIR / file)
        dfs[name] = df
        title(f"TABLE {name.upper()}  ->  {desc}")
        print(f"{len(df):,} lignes x {df.shape[1]} colonnes".replace(",", " "))
        print("Colonnes :", ", ".join(df.columns))
        print("\nExemples :")
        print(df.head(3).to_string(index=False))

    # ---- Suivre une commande livrée, avec un seul article et un avis ----
    o, it, rv = dfs["orders"], dfs["order_items"], dfs["order_reviews"]
    single = it.groupby("order_id").size().loc[lambda s: s == 1].index
    candidates = o[(o.order_status == "delivered") & o.order_id.isin(single) & o.order_id.isin(rv.order_id)]
    order = candidates.iloc[0]
    oid = order.order_id

    title(f"L'HISTOIRE D'UNE COMMANDE  (order_id = {oid})")
    cust = dfs["customers"].set_index("customer_id").loc[order.customer_id]
    item = it[it.order_id == oid].iloc[0]
    prod = dfs["products"].set_index("product_id").loc[item.product_id]
    sell = dfs["sellers"].set_index("seller_id").loc[item.seller_id]
    pay = dfs["order_payments"][dfs["order_payments"].order_id == oid].iloc[0]
    rev = rv[rv.order_id == oid].iloc[0]

    achat = pd.to_datetime(order.order_purchase_timestamp)
    prevue = pd.to_datetime(order.order_estimated_delivery_date)
    reelle = pd.to_datetime(order.order_delivered_customer_date)
    retard = (reelle.normalize() - prevue.normalize()).days

    print(f"1. CUSTOMERS      Un client de {cust.customer_city.title()} ({cust.customer_state})")
    print(f"2. ORDERS         passe commande le {achat:%d/%m/%Y}")
    print(f"3. ORDER_ITEMS    achète 1 article à {item.price:.2f} R$ (+ {item.freight_value:.2f} R$ de port)")
    print(f"4. PRODUCTS       catégorie : {prod.product_category_name}")
    print(f"5. SELLERS        envoyé par un vendeur de {sell.seller_city.title()} ({sell.seller_state})")
    print(f"6. PAYMENTS       payé par {pay.payment_type} en {pay.payment_installments} fois")
    print(f"7. ORDERS         livraison prévue le {prevue:%d/%m/%Y}, reçue le {reelle:%d/%m/%Y}"
          f"  -> {'en retard de ' + str(retard) + ' jours' if retard > 0 else 'à l’heure'}")
    print(f"8. ORDER_REVIEWS  le client met la note : {rev.review_score} / 5")

    # ---- Premier aperçu de la question du projet ----
    title("PREMIER INDICE POUR NOTRE QUESTION : le retard influence-t-il la note ?")
    d = o[o.order_status == "delivered"].merge(rv[["order_id", "review_score"]], on="order_id")
    d["en_retard"] = pd.to_datetime(d.order_delivered_customer_date).dt.normalize() > \
        pd.to_datetime(d.order_estimated_delivery_date).dt.normalize()
    res = d.groupby("en_retard").review_score.agg(["count", "mean"])
    res.index = res.index.map({False: "Livrée à l'heure", True: "Livrée en retard"})
    res.columns = ["Nombre de commandes", "Note moyenne"]
    print(res.round(2).to_string())


if __name__ == "__main__":
    main()
