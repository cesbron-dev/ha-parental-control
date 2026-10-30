"""Données de test partagées : config d'exemple de la tâche 1."""

EX = {
    "version": 1,
    "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
    "calendar_map": {"pédagogique": "conge_peda", "vacances": "vacances", "relâche": "vacances"},
    "notify": ["notify.mobile_app_iphone_de_olivier"],
    "kids": [
        {
            "id": "gabin",
            "name": "Gabin",
            "emoji": "🎮",
            "color": "#FF6B6B",
            "calendar": "calendar.ecole_primaire",
            "leisure_add": [],
            "leisure_remove": [],
            "resource_modes": {"switch": "sur_demande"},
            "profiles": {
                "ecole": {
                    "segments": [
                        {"start": "00:00", "type": "bloque"},
                        {"start": "15:25", "type": "libre"},
                        {"start": "16:00", "type": "apres_devoirs"},
                        {"start": "19:00", "type": "bloque"},
                    ]
                },
                "fin_de_semaine": {
                    "quota_minutes": 120,
                    "segments": [
                        {"start": "00:00", "type": "bloque"},
                        {"start": "08:00", "type": "quota"},
                        {"start": "20:00", "type": "bloque"},
                    ],
                },
            },
        }
    ],
    "resources": [
        {
            "id": "tv",
            "name": "Télé salon",
            "kind": "media_player",
            "owners": ["gabin"],
            "entity_id": "media_player.tv_salon",
            "notify_service": None,
            "quota_minutes": {"fin_de_semaine": 180},
        },
        {
            "id": "iphone_gabin",
            "name": "iPhone Gabin",
            "kind": "adguard_services",
            "owners": ["gabin"],
            "device_id": "adguard_iphone_gabin",
        },
        {
            "id": "switch",
            "name": "Switch",
            "kind": "nintendo",
            "owners": ["gabin"],
            "device_id": "b64d274dc045916f9a6de862a104fbb5",
            "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
            "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
            "used_entity": "sensor.switch_papa_temps_d_ecran_utilise",
        },
    ],
}
