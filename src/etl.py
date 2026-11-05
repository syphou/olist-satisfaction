"""Étape 2 – ETL : CSV Olist -> nettoyage + contrôles qualité -> PostgreSQL.

    E (Extract)   : lecture des 9 CSV de data/raw/
    T (Transform) : typage, nettoyage, dédoublonnage, contrôles qualité
    L (Load)      : création du schéma (sql/01_schema.sql) puis chargement
                    rapide avec COPY, en UNE transaction (tout ou rien)

Un rapport qualité est écrit dans reports/quality_report.md.

Usage :
    python src/etl.py            # pipeline complet
    python src/etl.py --no-db    # sans base : écrit les CSV nettoyés dans data/processed/
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import PG, PROCESSED_DIR, RAW_DIR, ROOT  # noqa: E402

SCHEMA_FILE = ROOT / "sql" / "01_schema.sql"
REPORT_FILE = ROOT / "reports" / "quality_report.md"

# Ordre de chargement : une table "parent" doit être chargée avant ses "enfants"
LOAD_ORDER = [
    "customers", "sellers", "category_translation", "products", "orders",
    "order_items", "order_payments", "order_reviews", "geolocation", "geolocation_zip",
]

# Journal des contrôles qualité : (table, contrôle, nb lignes concernées, action)
QUALITY_LOG: list[tuple[str, str, int, str]] = []


def fmt(n: int) -> str:
    """1234567 -> '1 234 567' (séparateur de milliers à la française)."""
    return f"{n:,}".replace(",", " ")


def log(table: str, check: str, n: int, action: str) -> None:
    QUALITY_LOG.append((table, check, int(n), action))
    flag = "  " if n == 0 else "->"
    print(f"   {flag} {table:<20} {check:<55} {fmt(n):>8}  {action if n else ''}")


# =====================================================================
# EXTRACT
# =====================================================================
FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# Codes postaux lus en texte pour ne pas perdre les zéros en tête ("01037" et pas 1037)
ZIP_COLS = {
    "customer_zip_code_prefix": str,
    "seller_zip_code_prefix": str,
    "geolocation_zip_code_prefix": str,
}


def extract() -> dict[str, pd.DataFrame]:
    print("\n[1/3] EXTRACT – lecture des CSV")
    dfs = {}
    for name, file in FILES.items():
        df = pd.read_csv(RAW_DIR / file, dtype=ZIP_COLS)
        df.columns = df.columns.str.strip()
        dfs[name] = df
        print(f"   {name:<22} {fmt(len(df)):>10} lignes")
    return dfs


# =====================================================================
# TRANSFORM – fonctions utilitaires
# =====================================================================
def to_datetime(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")


def to_int(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")


def clean_text(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        df[c] = df[c].astype("string").str.strip()


def clean_zip(df: pd.DataFrame, col: str) -> None:
    df[col] = df[col].astype("string").str.strip().str.zfill(5)


def drop_duplicate_keys(df: pd.DataFrame, table: str, key: list[str]) -> pd.DataFrame:
    n = df.duplicated(subset=key).sum()
    log(table, f"Doublons sur la clé ({', '.join(key)})", n, "supprimés")
    return df.drop_duplicates(subset=key)


def drop_orphans(child: pd.DataFrame, table: str, col: str,
                 parent: pd.DataFrame, parent_col: str, parent_name: str) -> pd.DataFrame:
    """Supprime les lignes dont la clé étrangère n'existe pas dans la table parent."""
    mask = child[col].notna() & ~child[col].isin(parent[parent_col])
    log(table, f"{col} absent de {parent_name}", mask.sum(), "lignes supprimées")
    return child[~mask]


def report_nulls(df: pd.DataFrame, table: str) -> None:
    for col, n in df.isna().sum().items():
        if n:
            log(table, f"Valeurs manquantes : {col}", n, "conservées (NULL)")


# =====================================================================
# TRANSFORM
# =====================================================================
def transform(dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    print("\n[2/3] TRANSFORM – nettoyage et contrôles qualité")
    out: dict[str, pd.DataFrame] = {}

    # ---------- customers ----------
    c = dfs["customers"].copy()
    clean_zip(c, "customer_zip_code_prefix")
    clean_text(c, ["customer_city", "customer_state"])
    c = drop_duplicate_keys(c, "customers", ["customer_id"])
    out["customers"] = c

    # ---------- sellers ----------
    s = dfs["sellers"].copy()
    clean_zip(s, "seller_zip_code_prefix")
    clean_text(s, ["seller_city", "seller_state"])
    s = drop_duplicate_keys(s, "sellers", ["seller_id"])
    out["sellers"] = s

    # ---------- products ----------
    p = dfs["products"].copy()
    # Correction de la faute de frappe du dataset d'origine
    p = p.rename(columns=lambda col: col.replace("lenght", "length"))
    to_int(p, ["product_name_length", "product_description_length", "product_photos_qty",
               "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"])
    clean_text(p, ["product_category_name"])
    p = drop_duplicate_keys(p, "products", ["product_id"])
    report_nulls(p, "products")
    out["products"] = p

    # ---------- category_translation ----------
    t = dfs["category_translation"].copy()
    clean_text(t, ["product_category_name", "product_category_name_english"])
    t = drop_duplicate_keys(t, "category_translation", ["product_category_name"])
    # Des catégories utilisées par les produits n'ont pas de traduction -> on les ajoute
    missing = sorted(set(p["product_category_name"].dropna()) - set(t["product_category_name"]))
    log("category_translation", "Catégories de products sans traduction", len(missing),
        f"ajoutées ({', '.join(missing)})")
    if missing:
        t = pd.concat([t, pd.DataFrame({"product_category_name": missing,
                                        "product_category_name_english": missing})])
    out["category_translation"] = t

    # ---------- orders ----------
    o = dfs["orders"].copy()
    date_cols = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                 "order_delivered_customer_date", "order_estimated_delivery_date"]
    to_datetime(o, date_cols)
    clean_text(o, ["order_status"])
    o = drop_duplicate_keys(o, "orders", ["order_id"])
    o = drop_orphans(o, "orders", "customer_id", c, "customer_id", "customers")
    report_nulls(o, "orders")

    # Contrôles de cohérence des dates (signalés, PAS supprimés : à analyser plus tard)
    delivered = o["order_status"] == "delivered"
    log("orders", "Statut 'delivered' sans date de livraison",
        (delivered & o["order_delivered_customer_date"].isna()).sum(), "signalé")
    log("orders", "Date de livraison mais statut != 'delivered'",
        (~delivered & o["order_delivered_customer_date"].notna()).sum(), "signalé")
    log("orders", "Livraison client AVANT l'achat",
        (o["order_delivered_customer_date"] < o["order_purchase_timestamp"]).sum(), "signalé")
    log("orders", "Remise au transporteur AVANT l'achat",
        (o["order_delivered_carrier_date"] < o["order_purchase_timestamp"]).sum(), "signalé")
    log("orders", "Livraison client AVANT remise au transporteur",
        (o["order_delivered_customer_date"] < o["order_delivered_carrier_date"]).sum(), "signalé")
    out["orders"] = o

    # ---------- order_items ----------
    it = dfs["order_items"].copy()
    to_datetime(it, ["shipping_limit_date"])
    to_int(it, ["order_item_id"])
    it = drop_duplicate_keys(it, "order_items", ["order_id", "order_item_id"])
    it = drop_orphans(it, "order_items", "order_id", o, "order_id", "orders")
    it = drop_orphans(it, "order_items", "product_id", p, "product_id", "products")
    it = drop_orphans(it, "order_items", "seller_id", s, "seller_id", "sellers")
    neg = (it["price"] < 0) | (it["freight_value"] < 0)
    log("order_items", "Prix ou frais de port négatifs", neg.sum(), "lignes supprimées")
    it = it[~neg]
    log("order_items", "Articles à prix nul (0)", (it["price"] == 0).sum(), "signalé")
    out["order_items"] = it

    # ---------- order_payments ----------
    pay = dfs["order_payments"].copy()
    to_int(pay, ["payment_sequential", "payment_installments"])
    clean_text(pay, ["payment_type"])
    pay = drop_duplicate_keys(pay, "order_payments", ["order_id", "payment_sequential"])
    pay = drop_orphans(pay, "order_payments", "order_id", o, "order_id", "orders")
    log("order_payments", "Moyen de paiement 'not_defined'",
        (pay["payment_type"] == "not_defined").sum(), "signalé")
    log("order_payments", "Paiement en 0 échéance",
        (pay["payment_installments"] == 0).sum(), "signalé")
    out["order_payments"] = pay

    # ---------- order_reviews ----------
    r = dfs["order_reviews"].copy()
    to_datetime(r, ["review_creation_date", "review_answer_timestamp"])
    to_int(r, ["review_score"])
    r = drop_duplicate_keys(r, "order_reviews", ["review_id", "order_id"])
    r = drop_orphans(r, "order_reviews", "order_id", o, "order_id", "orders")
    bad = ~r["review_score"].between(1, 5)
    log("order_reviews", "Note hors de l'intervalle 1-5", bad.sum(), "lignes supprimées")
    r = r[~bad]
    n_multi = r.groupby("order_id").size().gt(1).sum()
    log("order_reviews", "Commandes ayant plusieurs avis", n_multi, "signalé")
    log("order_reviews", "Avis sans commentaire écrit",
        r["review_comment_message"].isna().sum(), "normal (commentaire facultatif)")
    out["order_reviews"] = r

    # ---------- geolocation ----------
    g = dfs["geolocation"].copy()
    clean_zip(g, "geolocation_zip_code_prefix")
    clean_text(g, ["geolocation_city", "geolocation_state"])
    n_dup = g.duplicated().sum()
    log("geolocation", "Lignes en double exact", n_dup, "supprimées")
    g = g.drop_duplicates()
    # Le Brésil est compris entre ces latitudes / longitudes
    outside = ~(g["geolocation_lat"].between(-34, 5.5) & g["geolocation_lng"].between(-74, -34))
    log("geolocation", "Points GPS hors du Brésil", outside.sum(), "lignes supprimées")
    g = g[~outside]
    out["geolocation"] = g

    # Un seul point par code postal (médiane) : pratique pour les cartes Power BI
    gz = (g.groupby("geolocation_zip_code_prefix")
           .agg(lat=("geolocation_lat", "median"), lng=("geolocation_lng", "median"),
                state=("geolocation_state", lambda x: x.mode().iat[0]))
           .reset_index().rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"}))
    no_geo = ~c["customer_zip_code_prefix"].isin(gz["zip_code_prefix"])
    log("geolocation_zip", "Clients dont le code postal n'a pas de coordonnées",
        no_geo.sum(), "signalé")
    out["geolocation_zip"] = gz

    return out


# =====================================================================
# LOAD
# =====================================================================
def copy_dataframe(cur, df: pd.DataFrame, table: str) -> None:
    """Chargement ultra-rapide avec COPY (bien plus rapide que des INSERT ligne à ligne)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, date_format="%Y-%m-%d %H:%M:%S")
    buf.seek(0)
    cols = ", ".join(df.columns)
    cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)


def load(data: dict[str, pd.DataFrame]) -> None:
    import psycopg2

    print(f"\n[3/3] LOAD – chargement dans PostgreSQL (base '{PG['db']}')")
    conn = psycopg2.connect(host=PG["host"], port=PG["port"], user=PG["user"],
                            password=PG["password"], dbname=PG["db"])
    conn.set_client_encoding("UTF8")   # accents portugais (ã, ç, é…) sous Windows
    try:
        with conn, conn.cursor() as cur:   # une seule transaction : tout ou rien
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
            print("   [OK] Schéma créé (sql/01_schema.sql)")
            for table in LOAD_ORDER:
                t0 = time.time()
                copy_dataframe(cur, data[table], table)
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                n_db = cur.fetchone()[0]
                status = "[OK]" if n_db == len(data[table]) else "[!!]"
                print(f"   {status} {table:<22} {fmt(n_db):>10} lignes  ({time.time() - t0:.1f}s)")
            cur.execute("ANALYZE")
    finally:
        conn.close()


# =====================================================================
# RAPPORT QUALITÉ
# =====================================================================
def write_report(raw: dict[str, pd.DataFrame], data: dict[str, pd.DataFrame]) -> None:
    lines = ["# Rapport qualité des données – ETL Olist", "",
             f"Généré le {pd.Timestamp.now():%d/%m/%Y à %H:%M} par `src/etl.py`.", "",
             "## Volumes", "", "| Table | Lignes brutes | Lignes chargées | Écart |",
             "|---|---:|---:|---:|"]
    for t in LOAD_ORDER:
        before = len(raw[t]) if t in raw else None
        after = len(data[t])
        diff = "" if before is None else ("+" if after >= before else "-") + fmt(abs(after - before))
        before_s = "—" if before is None else fmt(before)
        lines.append(f"| {t} | {before_s} | {fmt(after)} | {diff} |")
    lines += ["", "## Contrôles effectués", "", "| Table | Contrôle | Lignes | Action |",
              "|---|---|---:|---|"]
    for table, check, n, action in QUALITY_LOG:
        lines.append(f"| {table} | {check} | {fmt(n)} | {action if n else 'OK'} |")
    REPORT_FILE.parent.mkdir(exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n   Rapport qualité écrit : {REPORT_FILE.relative_to(ROOT)}")


def save_processed(data: dict[str, pd.DataFrame]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"   CSV nettoyés écrits dans {PROCESSED_DIR.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Olist -> PostgreSQL")
    parser.add_argument("--no-db", action="store_true",
                        help="ne pas charger dans PostgreSQL, écrire les CSV nettoyés")
    args = parser.parse_args()

    t0 = time.time()
    raw = extract()
    data = transform(raw)
    if args.no_db:
        save_processed(data)
    else:
        load(data)
    write_report(raw, data)
    print(f"\nTerminé en {time.time() - t0:.0f} s.")


if __name__ == "__main__":
    main()
