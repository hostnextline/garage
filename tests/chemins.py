"""Où se trouvent l'app et les outils de test. Le même fichier marche dans le dépôt (le dossier tests/ à côté de
carnet.html) et ailleurs : GARAGE_DIR peut aussi le dire."""
import os
ICI = os.path.dirname(os.path.abspath(__file__))
_haut = os.path.dirname(ICI)
GARAGE = os.environ.get('GARAGE_DIR') or (_haut if os.path.exists(os.path.join(_haut, 'carnet.html')) else '/home/claude/garage')
SAUVEGARDES = next((p for p in (os.path.join(GARAGE, 'sauvegardes-repo'), os.path.join(GARAGE, 'sauvegardes')) if os.path.isdir(p)), os.path.join(GARAGE, 'sauvegardes'))
