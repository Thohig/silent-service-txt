"""Startläge, den hemliga ordern och radiomeddelanden från huvudstaben.

Ett modul per scenario (med sin korta variant); `common` har det de delar. Scenarierna
registreras här, i menyns ordning."""
from __future__ import annotations

from .common import (  # noqa: F401
    RadioMessage,
    Warmup,
    Scenario,
    KUBA_PLACE,
    GUANTANAMO_PLACE,
    CONVOY_PLACE,
    ARCTIC_PLACE,
    KOLA_PLACE,
    _place,
    _compass,
    _crew,
    ScenarioDef,
    SCENARIOS,
    register,
    build_scenario,
)
from .kuba import (  # noqa: F401
    SECRET_ORDER,
    RADIO_MESSAGES,
    KUBA_TRAFFIC,
    KUBA_AIR,
    default_scenario,
    KUBA_SHORT_WARM_S,
    KUBA_SHORT_WINDOW_IN_S,
    KUBA_SHORT_WINDOW_S,
    KUBA_SHORT_AFTER_S,
    KUBA_SHORT_DD_NM,
    KUBA_SHORT_CONTACT_SIGMA_NM,
    KUBA_SHORT_TURN_S,
    _kuba_watch_pilot,
    kuba_short_scenario,
)
from .arktis import (  # noqa: F401
    ARCTIC_ORDER,
    STATION_NAME,
    arctic_scenario,
    ARCTIC_SHORT_STATION_NM,
    ARCTIC_SHORT_SUB_NM,
    ARCTIC_SHORT_WARM_S,
    ARCTIC_SHORT_LIMIT_S,
    ARCTIC_SHORT_FIRE_MIN,
    _arctic_watch_pilot,
    arctic_short_scenario,
)
from .jagad import (  # noqa: F401
    HUNTED_ORDER,
    HUNTED_RADIO,
    HUNTED_AIR,
    _bank_edge_x,
    hunted_scenario,
    HUNTED_SHORT_SIZE,
    HUNTED_SHORT_EDGE_NM,
    HUNTED_SHORT_DD1_NM,
    HUNTED_SHORT_DD2_NM,
    HUNTED_SHORT_LIMIT_S,
    hunted_short_scenario,
)
from .sundet import (  # noqa: F401
    STRAIT_ORDER,
    STRAIT_RADIO,
    HARBOR_PATROL_SPEED,
    strait_scenario,
    STRAIT_IN_CLOCK,
    STRAIT_IN_WARM_S,
    STRAIT_IN_LIMIT_S,
    STRAIT_IN_SHIP_NM,
    _strait_watch_pilot,
    strait_in_scenario,
    STRAIT_OUT_CLOCK,
    STRAIT_OUT_WARM_S,
    STRAIT_OUT_LIMIT_S,
    STRAIT_OUT_INSIDE_NM,
    STRAIT_OUT_LINE_NM,
    STRAIT_OUT_SIDE_NM,
    STRAIT_OUT_SHIP_BEHIND_NM,
    _strait_out_pilot,
    strait_out_scenario,
)
from .konvoj import (  # noqa: F401
    CONVOY_ORDER,
    CONVOY_RADIO,
    convoy_scenario,
    CONVOY_SHORT_WARM_S,
    CONVOY_SHORT_LIMIT_S,
    CONVOY_SHORT_LOOK_S,
    _convoy_watch_pilot,
    convoy_short_scenario,
    COUNTER_MAX_WARM_S,
    COUNTER_LIMIT_S,
    COUNTER_LOOK_S,
    COUNTER_RUN_IN_NM,
    COUNTER_SIDE_NM,
    COUNTER_LEASH_NM,
    COUNTER_WAKE_SIGMA_NM,
    COUNTER_FIRE_NM,
    COUNTER_MIN_SPAN_S,
    COUNTER_LOOK_FRESH_S,
    COUNTER_MAX_KN,
    COUNTER_HANDOVER_S,
    _CounterattackWatch,
    convoy_counter_scenario,
)
from .ovning import (  # noqa: F401
    TRAINING_ORDER,
    TRAINING_CLOCK,
    TRAINING_SIZE,
    TRAINING_AREA,
    TRAINING_AREA_OUT_NM,
    TRAINING_STEPS,
    TRAINING_ARMAMENT,
    TRAINING_SHIP_R_NM,
    TRAINING_AREA_SIDE_NM,
    TRAINING_KEEP_RIGHT_NM,
    TRAINING_KN,
    TRAINING_START_Y,
    training_scenario,
    TRAINING_SHORT_WARM_S,
    TRAINING_SHORT_LIMIT_S,
    TRAINING_SHORT_STEPS,
    _training_watch_pilot,
    training_short_scenario,
)

register(ScenarioDef(
    "kuba", "Kvadrat 7, oktober 1962",
    "Kubakrisen. Förbli oupptäckt för en amerikansk jagare i karantänlinjen.",
    default_scenario))
register(ScenarioDef(
    "kuba-kort", "Kvadrat 7 – sambandsfönstret, oktober 1962",
    "Kort variant. En amerikansk jagare patrullerar några sjömil bort. Sambandstillfället "
    "öppnar om fem minuter: sänd rapporten och se till att ingen har er när det stänger.",
    kuba_short_scenario, minutes=25))
register(ScenarioDef(
    "arktis", "Under packisen, oktober 1962",
    "Polarnatt vid 85° nord. Drivstationen Nord-7 har tystnat. Ta er dit under isen, "
    "hitta öppet vatten och gå upp. En amerikansk ubåt är på väg mot samma plats.",
    arctic_scenario))
register(ScenarioDef(
    "arktis-kort", "Under packisen – sista milen, oktober 1962",
    "Kort variant. Vakten har gått mot Nord-7 under isen i tjugo minuter. Stationen ligger "
    "några sjömil fram, en amerikansk ubåt är på väg dit och isen ovanför är tjock.",
    arctic_short_scenario, minutes=25))
register(ScenarioDef(
    "jagad", "Jagade, natten till 27 oktober 1962",
    "En amerikansk jagare har just fått kontakt och en till är på väg. Bryt kontakten "
    "och ta er ut ur kvadrat 7 innan sjunkbomberna blir skarpa.",
    hunted_scenario))
register(ScenarioDef(
    "jagad-kort", "Jagade – skarpt, natten till 27 oktober 1962",
    "Kort variant. Jagaren fäller redan skarpa sjunkbomber och går in igen på en och en halv "
    "sjömil. Kvadraten är liten, men den andra jagaren spärrar den kortaste vägen ut.",
    hunted_short_scenario, minutes=25))
register(ScenarioDef(
    "sundet", "Guantánamo, 25 oktober 1962",
    "Smyg in mot den amerikanska flottbasen genom ett grunt inlopp med nät, hydrofoner och "
    "patrullbåt. Fotografera ankarplatsen i dagsljus och ta er ut igen.",
    strait_scenario))
register(ScenarioDef(
    "sundet-in", "Guantánamo – grinden, 25 oktober 1962",
    "Kort variant. Ni ligger i väntläget utanför nätet och ett fartyg är på väg in mot "
    "grinden. Ta er in bakom det och fotografera ankarplatsen.",
    strait_in_scenario, minutes=25))
register(ScenarioDef(
    "sundet-ut", "Guantánamo – ut med filmen, 25 oktober 1962",
    "Kort variant. Bilderna av ankarplatsen är tagna och ni ligger innanför nätet. Ett "
    "fartyg är på väg ut mot grinden. Ta er ut förbi patrullbåten med filmen.",
    strait_out_scenario, minutes=20))
register(ScenarioDef(
    "konvoj", "Konvojen, 28 oktober 1962",
    "Kriget har börjat. En eskorterad konvoj med trupper till Kuba sicksackar genom "
    "kvadrat 12. Kom i skjutläge, sänk minst ett fartyg och bryt kontakten.",
    convoy_scenario))
register(ScenarioDef(
    "konvoj-kort", "Konvojen – skjutläge, 28 oktober 1962",
    "Kort variant. Vakten har följt konvojen i en halvtimme och plottet har den. Ni tar "
    "befälet med målen några sjömil bort: kom i skjutläge, sänk och bryt kontakten.",
    convoy_short_scenario, minutes=30))
register(ScenarioDef(
    "konvoj-mot", "Konvojen – motanfallet, 28 oktober 1962",
    "Kort variant. Vakten har skjutit en salva mot konvojen och torpederna är framme om "
    "en knapp minut. Eskorten vänder redan mot er: bryt kontakten.",
    convoy_counter_scenario, minutes=20))
register(ScenarioDef(
    "ovning", "Övning – ut från Poljarnyj, oktober 1962",
    "Övning för att lära känna båten. Gå ut genom Kolafjorden i ytläge, möt trafiken, "
    "dyk utanför mynningen och gå igenom övningsprogrammet: periskop, fix, provdjup, "
    "smygmotor och lyssning mot ett eget bevakningsfartyg.",
    training_scenario))
register(ScenarioDef(
    "ovning-kort", "Övning – i övningsområdet, oktober 1962",
    "Kort variant. K-114 ligger redan på periskopdjup i övningsområdet. Gå igenom resten av "
    "programmet: djup 100, provdjup, smygmotor, lyssning, övningstorped och uppstigning.",
    training_short_scenario, minutes=40))
