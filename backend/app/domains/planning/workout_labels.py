"""Spanish labels snapshotted in provider-neutral structured workouts."""

WORKOUT_ROLE_LABELS = {
    "warmup": "Calentamiento",
    "work": "Trabajo principal",
    "recovery": "Recuperación activa",
    "cooldown": "Vuelta a la calma",
    "drill": "Técnica",
    "strength": "Fuerza",
}

SWIM_DRILLS = (
    ("Técnica catch-up", "Nado suave centrado en alargar la brazada."),
    ("Sculling frontal", "Remadas suaves para mejorar el apoyo y la sensibilidad al agua."),
    ("Arrastre de dedos", "Recobro relajado con el codo alto y los dedos cerca del agua."),
)

MOVEMENT_PATTERN_LABELS = {
    "KNEE_DOMINANT": "Dominante de rodilla", "HIP_HINGE": "Bisagra de cadera",
    "UNILATERAL_LOWER": "Pierna unilateral", "CALF": "Gemelo", "SOLEUS": "Sóleo",
    "HORIZONTAL_PULL": "Tracción horizontal", "HORIZONTAL_PUSH": "Empuje horizontal",
    "CORE_ANTI_EXTENSION": "Core antiextensión", "CORE_ANTI_ROTATION": "Core antirrotación",
    "CORE_LATERAL": "Core lateral",
}

STRENGTH_VARIANTS = (
    (("Sentadilla goblet", "KNEE_DOMINANT", False), ("Peso muerto rumano", "HIP_HINGE", False), ("Zancada inversa", "UNILATERAL_LOWER", True), ("Elevación de gemelo", "CALF", False), ("Remo con banda o mancuerna", "HORIZONTAL_PULL", False), ("Dead bug", "CORE_ANTI_EXTENSION", False)),
    (("Sentadilla búlgara", "UNILATERAL_LOWER", True), ("Bisagra de cadera a una pierna", "HIP_HINGE", True), ("Flexión o press con mancuerna", "HORIZONTAL_PUSH", False), ("Elevación de sóleo con rodilla flexionada", "SOLEUS", False), ("Remo con banda", "HORIZONTAL_PULL", False), ("Press Pallof con banda", "CORE_ANTI_ROTATION", False)),
)
