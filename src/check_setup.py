"""Étape 0 – Vérifie que l'environnement est prêt.

1. Les librairies Python sont installées
2. Les 9 CSV Olist sont dans data/raw/ (avec un aperçu des volumes)
3. PostgreSQL répond et la base 'olist' existe (créée si besoin)

Usage :  python src/check_setup.py
"""
import importlib
import sys

OK, KO = "[OK]", "[!!]"


def check_libs() -> bool:
    print("\n1) Librairies Python")
    libs = ["pandas", "numpy", "sqlalchemy", "psycopg2", "dotenv", "scipy", "sklearn"]
    all_ok = True
    for lib in libs:
        try:
            mod = importlib.import_module(lib)
            print(f"   {OK} {lib} {getattr(mod, '__version__', '')}")
        except ImportError:
            print(f"   {KO} {lib} manquant -> pip install -r requirements.txt")
            all_ok = False
    return all_ok


def check_files() -> bool:
    import pandas as pd
    from config import EXPECTED_FILES, RAW_DIR

    print(f"\n2) Fichiers CSV dans {RAW_DIR}")
    all_ok = True
    for name in EXPECTED_FILES:
        path = RAW_DIR / name
        if not path.exists():
            print(f"   {KO} {name} introuvable")
            all_ok = False
            continue
        df = pd.read_csv(path, nrows=None if "geolocation" not in name else 5)
        rows = f"{len(df):,}".replace(",", " ") if "geolocation" not in name else "~1M"
        print(f"   {OK} {name:<42} {rows:>8} lignes | {df.shape[1]} colonnes")
    return all_ok


def check_postgres() -> bool:
    from sqlalchemy import create_engine, text
    from config import PG, pg_url

    print(f"\n3) PostgreSQL ({PG['host']}:{PG['port']})")
    try:
        # Connexion à la base système pour créer 'olist' si elle n'existe pas
        engine = create_engine(pg_url("postgres"), isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            print(f"   {OK} Connecté : {version.split(',')[0]}")
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db"), {"db": PG["db"]}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{PG["db"]}"'))
                print(f"   {OK} Base '{PG['db']}' créée")
            else:
                print(f"   {OK} Base '{PG['db']}' déjà présente")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"   {KO} Connexion impossible : {exc.__class__.__name__}: {exc}")
        print("       -> vérifie que PostgreSQL tourne et le mot de passe dans .env")
        return False


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    results = [check_libs()]
    if results[0]:
        results += [check_files(), check_postgres()]
    print("\n" + ("Tout est prêt pour l'étape 1 !" if all(results) else "Corrige les points [!!] ci-dessus."))
