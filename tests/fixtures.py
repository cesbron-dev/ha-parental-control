"""Données de test partagées : config d'exemple de la tâche 1."""

NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "disneyplus": "Disney+"}

EX = {
    "version": 2,
    "services": [
        {"id": s, "name": NAMES.get(s, s.capitalize()), "adguard": [s], "labels": []}
        for s in ("youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch", "minecraft")
    ],
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
            "owners": ["hugo"],
            "quota_minutes": {"fin_de_semaine": 180},
            "devices": [{"name": "Télé salon", "integrations": [
                {"kind": "media_player", "entity_id": "media_player.tv_salon", "notify_service": None},
            ]}],
        },
        {
            "id": "iphone_hugo",
            "name": "iPhone Hugo",
            "owners": ["hugo"],
            "devices": [{"name": "iPhone Hugo", "integrations": [
                {"kind": "adguard_services", "device_id": "adguard_iphone_hugo"},
            ]}],
        },
        {
            "id": "switch",
            "name": "Switch",
            "owners": ["hugo"],
            "devices": [{"name": "Switch", "integrations": [
                {
                    "kind": "nintendo",
                    "device_id": "c52a9e7f10b84d3698e1f4a7d3b60c28",
                    "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
                    "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
                    "used_entity": "sensor.switch_papa_temps_d_ecran_utilise",
                },
            ]}],
        },
    ],
}


def integration_of(resource: dict) -> dict:
    """Seule intégration d'une ressource de l'exemple (un appareil, une intégration)."""
    (device,) = resource["devices"]
    (integration,) = device["integrations"]
    return integration
