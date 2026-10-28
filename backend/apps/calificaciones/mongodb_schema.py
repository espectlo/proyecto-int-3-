from pymongo.errors import CollectionInvalid


DETALLE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "id_carga",
            "nro_fila",
            "tipo_carga",
            "sha256_payload",
            "datos",
        ],
        "properties": {
            "_id": {"bsonType": "string"},
            "id_carga": {"bsonType": "number"},
            "nro_fila": {"bsonType": "number", "minimum": 1},
            "tipo_carga": {"enum": ["MONTOS", "FACTORES"]},
            "sha256_payload": {"bsonType": "string"},
            "datos": {"bsonType": "object"},
        },
    }
}

CARGA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "id_carga",
            "archivo",
            "formato",
            "encabezados_detectados",
            "creado_en",
        ],
        "properties": {
            "id_carga": {"bsonType": "number"},
            "id_corredor": {"bsonType": ["number", "null"]},
            "archivo": {"bsonType": "string", "maxLength": 200},
            "formato": {"enum": ["CSV", "XML", "XLSX"]},
            "hoja": {"bsonType": ["string", "null"]},
            "encabezados_detectados": {
                "bsonType": "array",
                "items": {"bsonType": "string"},
            },
            "total_filas": {"bsonType": "number", "minimum": 0},
            "total_rechazadas": {"bsonType": "number", "minimum": 0},
            "sha256_payload": {"bsonType": "string"},
            "creado_en": {"bsonType": "date"},
        },
    }
}

RECHAZADA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "id_carga",
            "fila",
            "contenido_original",
            "errores",
            "creado_en",
        ],
        "properties": {
            "id_carga": {"bsonType": "number"},
            "id_corredor": {"bsonType": ["number", "null"]},
            "fila": {"bsonType": "number", "minimum": 1},
            "contenido_original": {"bsonType": "object"},
            "errores": {
                "bsonType": "array",
                "items": {"bsonType": "string"},
            },
            "creado_en": {"bsonType": "date"},
        },
    }
}

COLECCIONES_CARGA = {
    "calificaciones_detalle": DETALLE_VALIDATOR,
    "cargas_detalle": CARGA_VALIDATOR,
    "cargas_filas_rechazadas": RECHAZADA_VALIDATOR,
}


def preparar_esquema_cargas(database):
    colecciones = set(database.list_collection_names())
    for nombre, validator in COLECCIONES_CARGA.items():
        if nombre not in colecciones:
            try:
                database.create_collection(
                    nombre,
                    validator=validator,
                    validationLevel="strict",
                    validationAction="error",
                )
            except CollectionInvalid:
                database.command(
                    "collMod",
                    nombre,
                    validator=validator,
                    validationLevel="strict",
                    validationAction="error",
                )
        else:
            database.command(
                "collMod",
                nombre,
                validator=validator,
                validationLevel="strict",
                validationAction="error",
            )

    database["calificaciones_detalle"].create_index(
        [("id_carga", 1), ("nro_fila", 1)],
        unique=True,
    )
    database["cargas_detalle"].create_index(
        [("id_carga", 1)],
        unique=True,
    )
    database["cargas_detalle"].create_index(
        [("id_corredor", 1), ("creado_en", -1)],
    )
    database["cargas_filas_rechazadas"].create_index(
        [("id_carga", 1), ("fila", 1)],
        unique=True,
    )
    database["cargas_filas_rechazadas"].create_index(
        [("id_corredor", 1)],
    )
