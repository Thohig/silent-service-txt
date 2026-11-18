"""Navigatörens konstanter och order."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...orders import Order

FIX_TIME_S = 120
IDLE_FIX_SIGMA_NM = 0.5     # vid tystnad: föreslå fix redan vid denna osäkerhet
SEARCH_LEG_S = 1800         # utan kontakt: nytt sökben efter så här lång rak kurs
DR_GROWTH_NM_PER_H = 0.5
DR_TICK_S = 600             # tidsstreck på besticket var 10:e minut på klockan
DR_LABEL_S = 1800           # klockslag vid strecket varje halvtimme
SOUNDER_INTERVAL_S = 5      # isekolodet lodar så här ofta
SAFE_ICE_DEPTH = 60         # under isen: djupare än de djupaste kölarna (≤ 45 m)
VAK_SPEED = 3.0             # fart mot en öppning
VAK_TIMEOUT_S = 1800
VAK_RUN_OUT_M = 250         # vaken bakom och närmare: gå ut så här långt innan vi vänder
DECEL_M_PER_S2 = 0.05 * 1852 / 3600
ICE_FIX_SIGMA_NM = 1.0      # under isen: stoppa för fix först vid denna osäkerhet
FIX_VAK_MAX_M = 1500        # gå inte längre än så för en fix
VAK_FAST_SPEED = 5.0        # långt till öppningen: gå fortare, sakta in sista biten
VAK_SLOW_M = 500
REPORT_OPENING_M = 60       # kortare öppningar nämns inte när vi passerar dem
STATION_NAME = "Nord-7"
STATION_ARRIVE_NM = 0.3     # framme vid huvudstabens position (plus dess osäkerhet)
STATION_NEAR_NM = 1.2       # så nära: ett stopp i öppet vatten är värt det
STATION_OVERHEAD_SE = 15.0  # generatorn så stark: vi är inom några kabellängder
STATION_SEARCH_R_NM = 0.3   # sökspiral runt stationen efter öppet vatten: startradie
STATION_SEARCH_GROW_NM_PER_H = 0.3
STATION_SEARCH_MAX_NM = 1.2
STATION_SEARCH_SPEED = 4.0
DR_TRACK_INTERVAL_S = 60    # navigatören prickar in besticket på kortet så här ofta
OWN_VECTOR_S = 360          # egen fartvektor på kortet: sex minuters gång
DEPTH_LOG_INTERVAL_S = 10   # djupprofilen: djupmätaren noteras så här ofta
PROFILE_KEEP_S = 3 * 3600   # så långt bakåt minns profilen
SHOAL_MARGIN_M = 30         # håll så här långt över botten enligt kortet
SHOAL_LOOK_MIN = 6          # navigatören tittar så många minuters gång framåt
SHOAL_LOOK_MIN_NM = 0.6     # men minst så långt (stigning 100 m tar ~7 min)
SHOAL_CHECK_S = 20
SOUNDING_TRUST_S = 600      # en lodning räknas så här länge
BFIX_N = 9                  # fix mot botten: så många lodningar
BFIX_INTERVAL_S = 20        # med så här långt mellan
BFIX_MIN_SPEED = 2.0        # vi måste röra oss över botten
BFIX_FLAT = 0.8             # matchningen smalnar inte av mer än så: botten för flat
BFIX_GAIN = 2.0             # föreslå bara om besticket är så här mycket sämre än kortet
BFIX_RELIEF_M_PER_NM = 150  # föreslå bottenfix bara där kortet visar så här brant botten
PERISCOPE_FIX_SIGMA = 0.1
COAST_FIX_SIGMA = 0.05      # bäringar på landmärken: snabbare och bättre
STAR_FIX_S = 240            # stjärnfix: flera stjärnor med sextanten och räkning
STAR_FIX_SIGMA = 0.05       # stjärnor mot horisonten i skymning eller gryning
MOON_FIX_SIGMA = 0.15       # månen och några stjärnor mot månhorisonten en ljus natt
PERISCOPE_SEXTANT_F = 1.5   # genom periskopet (periskopsextant) sämre än på bryggan
STAR_SUN_HIGH = -3.0        # för ljust för stjärnorna över denna solhöjd
STAR_SUN_LOW = -11.0        # för mörkt för horisonten under denna (utan månen)
MOON_FIX_LIGHT = 0.4        # månljus som ger en horisont att mäta mot
STAR_SUGGEST_SIGMA = 0.25   # navigatören föreslår stjärnfix när besticket är sämre än så
COAST_FIX_S = 30
COAST_FIX_NIGHT_S = 45      # fyrar
LANDMARK_DAY_NM = 8.0
LANDMARK_NIGHT_NM = 5.0
LAND_MARK_STEP_NM = 0.25   # land på sjökortet: en prick per ruta
LAND_CLEAR_M = 21          # grundare än så framåt: inte ens periskopdjup går, gir i stället
LAND_TURNS = (30, 60, 90, 120, 150, 180)
FOLLOW_STEP_S = 15         # följ: ny kurs på kontaktens bäring så här ofta
WAIT_NAME = "Väntläget"    # punkten utanför grinden där vi väntar på ett fartyg in
WAIT_OUT_NM = 1.4          # så långt ut från nätet längs farleden (innanför patrullbåtens skärm)
WAIT_SIDE_NM = 0.35        # så långt vid sidan av leden (fartyget passerar nära, inte över oss)
WAIT_MIN_DEPTH_M = 40      # kortets djup vid väntläget minst så här
WAIT_STEP_S = 15
WAIT_ARRIVED_NM = 0.1
WAIT_TRANSIT_KN = 5.0      # dit i smygmotorns högsta fart ...
WAIT_QUIET_NM = 5.0        # ... tills vi är så här nära nätet,
WAIT_QUIET_KN = 3.0        # sedan så här tyst
WAIT_SUGGEST_S = 900
DIVE_ORDER = re.compile(r"(?:^|,\s*)(?:(?:djup|d)\s+[1-9]|periskopdjup|pd\b|antenndjup|botten)")
FAIRWAY_STEP_S = 15        # farleden: ny kurs mot nästa punkt så här ofta
FAIRWAY_RIGHT_NM = 0.15    # håll så här långt till styrbord om farledens mitt
FAIRWAY_TURN_NM = 0.25     # gir mot nästa ben så här långt före brytpunkten
FAIRWAY_SUGGEST_S = 600
BRIDGE_FIX_EVERY_S = 180   # i ytläge med land i sikte pejlar navigatören landmärken så här ofta
BRIDGE_FIX_QUIET_NM = 0.15 # mindre rättelse än så sägs inte
ATTACK_STEP_S = 30         # anfall: ny kurs mot skjutläget så här ofta
ATTACK_OFFSET_NM = 1.2     # skjutläget ligger så här långt från målets väg
ATTACK_LEAD_H = 4 / 60     # framme så här länge innan målet är tvärs
ATTACK_IN_POSITION_H = 8 / 60   # målet tvärs inom så här lång tid ...
ATTACK_IN_POSITION_NM = 2.5     # ... och vi så här nära dess väg: i skjutläge
ATTACK_PASSED_NM = 0.3          # vi ligger så här långt bakom målet: det har passerat
ATTACK_MAX_H = 1.5         # längre bort än så: vi hinner inte i praktiken
ATTACK_SUGGEST_S = 300     # mål känt: föreslå anfall så här ofta (obesvarat glesas ut)
ATTACK_REST_S = 1200       # efter skjutläge: föreslå inte nytt anfall förrän efter så här länge
PATH_STEP_NM = 0.1         # vägsökningens rutnät
EXIT_RECALC_S = 20         # vägen ut räknas om så här ofta
TIDE_TABLE_ERR = 0.3        # tidvattentabellen kan ha så här stort fel (andel av farten)
EXIT_FIRST_SUGGEST_S = 150  # ut ur området: låt sonar och djup komma först
EXIT_THREAT_SECTOR = 40     # en väg ut inom så många grader från en hotkontakt är inte fri
EXIT_THREAT_PENALTY_NM = 4.0
EXIT_DEEP_M = 300           # grundare än så enligt kortet kan vi inte springa djupt (220 m) ...
EXIT_SHALLOW_FACTOR = 1.0   # ... så den biten av vägen ut räknas så mycket längre
EXIT_SAMPLE_NM = 0.2
SETTLE_SPEED = 1.0          # fart när vi går ned mot botten
SETTLE_DESCEND_KN = 1.5     # gå ned först när farten är nere i detta
SETTLE_EXTRA_M = 60         # sikta så här långt under kortets botten
SETTLE_SUGGEST_MAX_M = 280  # föreslå att lägga oss på botten bara grundare än så
BOTTOM_WORDS = {"lera": "lerbotten", "sand": "sandbotten", "klippa": "klippbotten"}
CONTOUR_MARGIN_NM = 4.0     # djupkurvor så här långt utanför kvadraten
CONTOUR_LABEL_SPOTS = ((5, 5), (15, 5), (5, 15), (15, 15), (10, 10))   # andelar av kvadraten ×20


@dataclass(frozen=True)
class SteerTo(Order):
    name: str


@dataclass(frozen=True)
class GoToWait(Order):
    pass


@dataclass(frozen=True)
class FollowFairway(Order):
    pass


@dataclass(frozen=True)
class FollowContact(Order):
    designation: str


@dataclass(frozen=True)
class AttackApproach(Order):
    designation: str


@dataclass(frozen=True)
class SetCourse(Order):
    course: int
    STANDING = True


@dataclass(frozen=True)
class SetSpeed(Order):
    speed: float
    STANDING = True


@dataclass(frozen=True)
class SetDepth(Order):
    depth: int
    STANDING = True


@dataclass(frozen=True)
class TakeFix(Order):
    pass


@dataclass(frozen=True)
class StarFix(Order):
    """Astronomisk fix med sextanten: stjärnor i skymningen, månen en ljus natt."""


@dataclass(frozen=True)
class ReportPosition(Order):
    pass


@dataclass(frozen=True)
class EchoSounder(Order):
    pass


@dataclass(frozen=True)
class IceReport(Order):
    pass


@dataclass(frozen=True)
class GoToOpening(Order):
    pass


@dataclass(frozen=True)
class GoToStation(Order):
    pass


@dataclass(frozen=True)
class SettleOnBottom(Order):
    pass


@dataclass(frozen=True)
class BottomFix(Order):
    pass
