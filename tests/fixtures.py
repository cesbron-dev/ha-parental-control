"""Données de test partagées : config d'exemple de la tâche 1."""

EX = {
    "version": 1,
    "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
    "calendar_map": {"pédagogique": "conge_peda", "vacances": "vacances", "relâche": "vacances"},
    "notify": ["notify.mobile_app_iphone_de_marc"],
    "kids": [
        {
            "id": "hugo",
            "name": "Hugo",
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
            "owners": ["hugo"],
            "entity_id": "media_player.tv_salon",
            "notify_service": None,
            "quota_minutes": {"fin_de_semaine": 180},
        },
        {
            "id": "iphone_hugo",
            "name": "iPhone Hugo",
            "kind": "adguard_services",
            "owners": ["hugo"],
            "client": "iphone_hugo",
        },
        {
            "id": "switch",
            "name": "Switch",
            "kind": "nintendo",
            "owners": ["hugo"],
            "device_id": "c52a9e7f10b84d3698e1f4a7d3b60c28",
            "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
            "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
            "used_entity": "sensor.switch_papa_temps_d_ecran_utilise",
        },
    ],
}
