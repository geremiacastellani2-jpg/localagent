"""Etichette COCO → italiano, per parlare all'utente (e al modello) nella sua lingua."""

from __future__ import annotations

COCO_IT: dict[str, str] = {
    "person": "persona", "bicycle": "bicicletta", "car": "auto", "motorcycle": "moto",
    "airplane": "aereo", "bus": "autobus", "train": "treno", "truck": "camion", "boat": "barca",
    "traffic light": "semaforo", "fire hydrant": "idrante", "stop sign": "segnale di stop",
    "parking meter": "parchimetro", "bench": "panchina", "bird": "uccello", "cat": "gatto",
    "dog": "cane", "horse": "cavallo", "sheep": "pecora", "cow": "mucca", "elephant": "elefante",
    "bear": "orso", "zebra": "zebra", "giraffe": "giraffa", "backpack": "zaino",
    "umbrella": "ombrello", "handbag": "borsa", "tie": "cravatta", "suitcase": "valigia",
    "frisbee": "frisbee", "skis": "sci", "snowboard": "snowboard", "sports ball": "palla",
    "kite": "aquilone", "baseball bat": "mazza da baseball", "baseball glove": "guanto da baseball",
    "skateboard": "skateboard", "surfboard": "tavola da surf", "tennis racket": "racchetta",
    "bottle": "bottiglia", "wine glass": "calice", "cup": "tazza", "fork": "forchetta",
    "knife": "coltello", "spoon": "cucchiaio", "bowl": "ciotola", "banana": "banana",
    "apple": "mela", "sandwich": "panino", "orange": "arancia", "broccoli": "broccolo",
    "carrot": "carota", "hot dog": "hot dog", "pizza": "pizza", "donut": "ciambella",
    "cake": "torta", "chair": "sedia", "couch": "divano", "potted plant": "pianta in vaso",
    "bed": "letto", "dining table": "tavolo", "toilet": "wc", "tv": "televisore",
    "laptop": "portatile", "mouse": "mouse", "remote": "telecomando", "keyboard": "tastiera",
    "cell phone": "telefono", "microwave": "microonde", "oven": "forno", "toaster": "tostapane",
    "sink": "lavandino", "refrigerator": "frigorifero", "book": "libro", "clock": "orologio",
    "vase": "vaso", "scissors": "forbici", "teddy bear": "orsacchiotto",
    "hair drier": "asciugacapelli", "toothbrush": "spazzolino",
}


def label_it(label: str) -> str:
    return COCO_IT.get((label or "").strip().lower(), label)
