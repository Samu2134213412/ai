# Eigene 3D-Modelle

Hier abgelegte `.glb`-Dateien ersetzen die eingebauten Modelle. Die Zuordnung steht in `manifest.json`:

```json
[
  { "cat": "gpu", "match": "RTX 5090", "file": "rtx5090.glb" },
  { "cat": "cooler", "match": "Peerless Assassin", "file": "pa120.glb" },
  { "cat": "psu", "file": "netzteil.glb" }
]
```

- `cat`: cpu, mobo, ram, gpu, storage, cooler, psu, case
- `match`: Textstück aus Hersteller + Name (Groß-/Kleinschreibung egal). Ohne `match` gilt das Modell für die ganze Kategorie.
- Größe und Ausrichtung werden automatisch an das Teil angepasst.

Einzelne Modelle lassen sich auch direkt in der App laden: in „Dein PC“ beim Teil auf „3D-Modell laden“ klicken.
