# Démarrage de l'interface SmartExpenseAgent

## Prérequis
- Python 3.11+
- PostgreSQL installé et démarré
- Les dépendances de l'agent existant déjà installées

---

## 1. Créer la base de données PostgreSQL

```sql
CREATE DATABASE smartexpense_db;
```

---

## 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditez .env avec vos vraies valeurs (DB_PASSWORD, Azure keys, etc.)
```

---

## 3. Installer et démarrer le backend Django

```bash
cd backend
pip install -r requirements.txt

# Créer les tables
python manage.py migrate

# (Optionnel) Créer un superadmin
python manage.py createsuperuser

# Démarrer le serveur Django (port 8000)
python manage.py runserver
```

---

## 4. Installer et démarrer le frontend Streamlit

Dans un **second terminal**, depuis la racine du projet :

```bash
pip install -r frontend/requirements.txt

streamlit run frontend/app.py
```

Streamlit s'ouvre automatiquement sur **http://localhost:8501**

---

## Structure des URLs

| URL | Description |
|-----|-------------|
| http://localhost:8501 | Interface Streamlit (utilisateurs) |
| http://localhost:8000/admin | Admin Django (superadmin) |
| http://localhost:8000/api/auth/register/ | API inscription |
| http://localhost:8000/api/auth/login/ | API connexion |
| http://localhost:8000/api/invoices/ | API factures |
| http://localhost:8000/api/invoices/stats/ | API statistiques |

---

## Pages Streamlit

| Page | Description |
|------|-------------|
| `/` (app.py) | Accueil — Connexion / Inscription entreprise |
| `1_Dashboard` | Statistiques, graphiques, dernières factures |
| `2_Upload` | Importer une facture directement |
| `3_Pipeline` | Lancer le pipeline email |
| `4_Telechargements` | Télécharger les rapports Excel |
