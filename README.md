# Parental Control

Intégration Home Assistant (HACS) de contrôle parental : une frise horaire par enfant
et par type de journée (école, fin de semaine, congé pédagogique, vacances), appliquée
aux téléviseurs, aux services AdGuard Home et aux consoles Nintendo.

Le projet est en cours de développement (moteur de règles).

## Développement

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```
