# CrowdCare — Professional UI/UX Remake

This version keeps the existing CrowdCare Flask/MySQL backend and workflows and completely refreshes the front-end presentation.

## What changed

- New light, professional visual system
- Animated homepage with reveal effects, counters, progress animations and floating visual elements
- Responsive navigation and mobile menu
- Campaign cards with local category artwork
- Campaign search, category filtering and sorting
- New campaign detail experience
- New donor, creator and admin dashboard layouts
- New forms, verification screens and transaction screens
- Responsive admin tables and review interfaces
- Creator verification document-review workflow retained
- Campaign approval/rejection/closure/refund controls retained
- Donation and withdrawal workflows retained
- No dark-mode UI was added

## Backend

`app.py` and `db.py` are kept from the supplied project. No new application feature or database architecture is required for the UI remake.

## Demo data

Run:

```powershell
python seed_demo.py
```

Demo accounts:

| Role | Email | Password |
|---|---|---|
| Admin | admin@crowdcare.demo | Admin@123 |
| Donor | donor@crowdcare.demo | Donor@123 |
| Donor | donor2@crowdcare.demo | Donor@123 |
| Creator | creator@crowdcare.demo | Creator@123 |
| Creator | creator2@crowdcare.demo | Creator@123 |
| Creator | creator3@crowdcare.demo | Creator@123 |

Login OTP for the current development version is `6969`.

## Run

Use the existing virtual environment or create a fresh one:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install flask mysql-connector-python werkzeug python-dotenv
python app.py
```

Make sure your existing database and `.env` configuration are present. The remake package intentionally does **not** include `.env` or `venv`.

Open:

`http://127.0.0.1:5000`
