"""Navigatörens fraser, svenska och ryska."""
from __future__ import annotations

from ... import phrases
from ... import russian as R
from ...fmt import fmt_course, kn, nm
from ...icemap import OPEN_M, thickness_words
from ...russian import ru
from .common import BOTTOM_WORDS, WAIT_SIDE_NM


def _minutes(m: float) -> str:
    n = max(1, round(m))
    return f"{n} minut" if n == 1 else f"{n} minuter"


def _att_what(d: dict) -> str:
    return "konvojen" if d["what"] == "konvojen" else d["designation"]


def _att_side(d: dict) -> str:
    return "styrbord" if d["side"] > 0 else "babord"


def _att_path(d: dict) -> str:
    what = "konvojens" if d["what"] == "konvojen" else "dess"
    if d["basis"] == "base":
        return f"{what} baskurs {fmt_course(d['target_course'])}"
    if d["basis"] == "leg":
        return f"{what} nuvarande ben {fmt_course(d['target_course'])} (baskursen är inte känd)"
    return f"{what} kurs {fmt_course(d['target_course'])}"


_LEVEL = {"sakta": ("Malyj nazad", "sakta back"), "halv": ("Srednij nazad", "halv back"),
          "full": ("Polnyj nazad", "full back")}
_LEVEL_RU = {"sakta": "Малый назад", "halv": "Средний назад", "full": "Полный назад"}


def _speed_ack(d: dict) -> str:
    if d.get("astern"):
        if d.get("level"):
            word, sv = _LEVEL[d["level"]]
            txt = f"{ru('Jest')}, {ru(word)}, {sv}, {kn(d['speed'])} knop."
        else:
            txt = f"{ru('Jest')}, back i maskin, {kn(d['speed'])} knop."
        if d.get("from_ahead"):
            txt += f" Maskinen slår om, vi bromsar från {kn(d['from_ahead'])} knop framåt."
        return txt + (" Omkastningen hörs långt." if d.get("loud") else "")
    if d["speed"] == 0:
        return f"{ru('Jest')}, stopp i maskin."
    txt = f"{ru('Jest')}, fart {kn(d['speed'])} knop."
    if d.get("from_astern"):
        txt += " Maskinen slår om till framåt."
    return txt + (" Omkastningen hörs långt." if d.get("loud") else "")


def _limit(d: dict) -> str:
    match d["what"]:
        case "speed":
            return f"Kapten, högsta fart just nu är {kn(d['limit'])} knop."
        case "astern" if d["limit"] <= 0:
            return "Kapten, maskinen kan inte gå back nu, vi har ingen kraft."
        case "astern":
            return f"Kapten, största backfart just nu är {kn(d['limit'])} knop."
        case "astern_zero":
            return "Kapten, back i noll knop är stopp. Säg back och farten, eller stopp."
    return f"Kapten, största djup är {d['limit']:.0f} meter."


def _ru_speed_ack(d: dict) -> str:
    if d.get("astern"):
        txt = (f"Есть, {_LEVEL_RU[d['level']].lower()}." if d.get("level")
               else f"Есть, задний ход, {R.dec(d['speed'], R.KNOT)}.")
        if d.get("from_ahead"):
            txt += " Реверс, гасим ход."
        return txt + (" Реверс слышно далеко." if d.get("loud") else "")
    if d["speed"] == 0:
        return "Есть, стоп машина."
    txt = f"Есть, ход {R.dec(d['speed'], R.KNOT)}."
    if d.get("from_astern"):
        txt += " Реверс, вперёд."
    return txt + (" Реверс слышно далеко." if d.get("loud") else "")


def _ru_limit(d: dict) -> str:
    match d["what"]:
        case "speed":
            return f"{R.CAPTAIN}, предельный ход сейчас {R.dec(d['limit'], R.KNOT)}."
        case "astern" if d["limit"] <= 0:
            return f"{R.CAPTAIN}, задний ход дать не можем, нет мощности."
        case "astern":
            return f"{R.CAPTAIN}, предельный задний ход сейчас {R.dec(d['limit'], R.KNOT)}."
        case "astern_zero":
            return f"{R.CAPTAIN}, задний ход ноль — это стоп."
    return f"{R.CAPTAIN}, предельная глубина {R.count(d['limit'], R.METER)}."


def _lights_fix(names: list[str]) -> str:
    if len(names) == 1:
        return (f"Bara {names[0]} syns. Bäring och avstånd ur kimningen, sämre än korsbäring, "
                "under en minut.")
    return f"Tar fix på fyrarna {' och '.join([', '.join(names[:-1]), names[-1]])}, under en minut."


PHRASES = {
    "nav.course.ack": lambda d: f"{ru('Jest')}, kurs {fmt_course(d['course'])}."
    + (" Vi ligger på den." if d.get("already") else ""),
    "nav.speed.ack": _speed_ack,
    "nav.depth.ack": lambda d: (f"{ru('Jest')}, upp till ytan." if d["depth"] == 0 else
                                f"{ru('Jest')}, djup {d['depth']:.0f} meter.")
    + (" Brant vinkel." if d.get("steep") else "")
    + (" Det är under provdjup, kapten." if d.get("below_test") else "")
    + (f" Det är is ovanför, kapten, vi kommer inte högre än cirka {d['ice_ceiling']:.0f} meter."
       if d.get("ice_ceiling") else
       " Det är is ovanför, kapten, masterna kommer inte upp här." if d.get("ice_masts") else "")
    + ("" if "shoal" not in d else " Kortet visar land här, kapten." if d["shoal"] <= 0
       else f" Kortet visar botten på cirka {d['shoal']:.0f} meter här, kapten."),
    "nav.settle.ack": lambda d: f"{ru('Jest')}, lägger oss på botten. "
    + (f"Ekolodet gav {d['depth']:.0f} meter" if d.get("sounded") else
       f"Kortet visar cirka {d['depth']:.0f} meter")
    + (f", {BOTTOM_WORDS[d['kind']]} enligt kortet" if d.get("kind") else "")
    + ". Sakta i en knop och går ned.",
    "nav.settle.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.settle.already": lambda d: "Vi ligger redan på botten, kapten.",
    "nav.settle.lift": lambda d: "Vi lättar från botten.",
    "nav.settle.not_reached": lambda d: f"Kapten, vi är på {d['depth']:.0f} meter och har inte "
    "nått botten. Kortet stämmer inte här. Föreslår ekolod.",
    "nav.suggest.settle": lambda d: "Kapten, navigatören. Vi är över grunt vatten, kortet visar "
    f"{BOTTOM_WORDS[d['kind']]} på cirka {d['depth']:.0f} meter. Ligger vi stilla på botten "
    "drunknar vårt eko i bottenekot. Föreslår att vi lägger oss på botten.",
    "nav.bfix.start": lambda d: f"{ru('Jest')}, fix mot botten. Lodar {d['n']} gånger under "
    f"{d['minutes']} minuter. Håll kurs och fart, ekolodet hörs.",
    "nav.bfix.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.bfix.aborted": lambda d: "Fixen mot botten avbröts, vi har nästan stannat.",
    "nav.bfix.done": lambda d: f"Fix mot botten klar. Lodningarna passar kortet bäst "
    f"{nm(d['error'])} sjömil åt {fmt_course(d['bearing'])}. Bestick korrigerat, osäkerhet "
    f"{nm(d['sigma'])} sjömil.",
    "nav.bfix.line": lambda d: f"Fix mot botten ger en lägeslinje: läget är bestämt i led "
    f"{fmt_course(d['bearing'])}–{fmt_course((d['bearing'] + 180) % 360)} på {nm(d['minor'])} sjömil, "
    f"men inte längs djupkurvorna. Bestick korrigerat {nm(d['error'])} sjömil åt "
    f"{fmt_course(d['bearing_corr'])}, osäkerhet {nm(d['sigma'])} sjömil. En fix där botten "
    "varierar åt flera håll, vid ett berg eller en ränna, ger läget i båda led.",
    "nav.bfix.mismatch": lambda d: "Fix mot botten: lodningarna stämmer inte med kortet här, "
    f"botten är {d['how']} än kortet visar. Kortet saknar något. Besticket oförändrat.",
    "nav.bfix.flat": lambda d: "Fix mot botten: botten är för flat här, lodningarna säger "
    "inget om var vi är. Besticket oförändrat.",
    "nav.bfix.chart": lambda d: f"Fix mot botten: lodningarna passar kortet, men kortet är inte "
    f"bättre än {nm(d['accuracy'])} sjömil. Besticket är lika bra. Oförändrat.",
    "nav.suggest.bfix": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är {nm(d['sigma'])} "
    "sjömil och vi kan inte ta fix i periskopet. Kortet visar brant botten här. Föreslår fix "
    "mot botten, nio lodningar.",
    "nav.suggest.shoal": lambda d: "Kapten, navigatören. "
    + (f"Ekolodet visade {d['shoal']:.0f} meter till botten här" if d.get("sounded") else
       f"Sjökortet visar {d['shoal']:.0f} meter "
       + ("här" if d["dist"] < 0.15 else f"inom {nm(d['dist'])} sjömil "
          + ("akterut" if d.get("astern") else "framåt")))
    + f". Föreslår djup {d['depth']:.0f}.",
    "nav.follow": lambda d: f"Följer {d['designation']} i kölvattnet, kurs "
    f"{fmt_course(d['course'])}" + (f", fart {d['speed']} knop" if d.get("speed") else
                                      ", farten håller vi tills plottet har en lösning") + ".",
    "nav.follow.none": lambda d: f"Kapten, vi har ingen bäring på {d['designation']}.",
    "nav.follow.lost": lambda d: f"Kapten, vi har tappat {d['designation']}. Slutar följa.",
    "nav.suggest.wait": lambda d: f"Kapten, navigatören. Grinden i nätet öppnas bara för fartyg. "
    f"Föreslår att vi väntar {nm(d['out'])} sjömil ut från nätet, vid sidan av farleden och "
    f"innanför patrullbåtens skärm, och lyssnar efter ett fartyg på väg in. "
    f"{nm(d['range'])} sjömil dit, i smygmotor.",
    "nav.wait": lambda d: f"{ru('Jest')}, till väntläget, kurs {fmt_course(d['course'])}, "
    f"{nm(d['range'])} sjömil.",
    "nav.wait.arrived": lambda d: "Kapten, vi ligger vid väntläget och håller läget i låg fart. "
    f"Bestickets osäkerhet är {nm(d['sigma'])} sjömil"
    + (", så leden kan ligga närmare eller längre bort än vi tror" if d["sigma"] > WAIT_SIDE_NM
       else "") + ". Sonar lyssnar efter fartyg på väg in.",
    "nav.wait.none": lambda d: "Kapten, vi känner inte nätets och ankarplatsens läge, "
    "så jag kan inte lägga ut något väntläge.",
    "nav.attack": lambda d: f"Anfall mot {_att_what(d)}. Skjutläge {nm(d['offset'])} sjömil om "
    f"{_att_side(d)} om {_att_path(d)}. Kurs {fmt_course(d['course'])}, framme om "
    f"{_minutes(d['minutes'])} i {kn(d['speed'])} knop.",
    "nav.attack.speed": lambda d: f"Anfall mot {_att_what(d)}. I {kn(d['speed'])} knop hinner vi "
    f"inte. I {d['need']} knop är vi i skjutläge om {_minutes(d['minutes'])}, kurs "
    f"{fmt_course(d['course'])}." + (" Det kräver turbinen." if d.get("turbine") else ""),
    "nav.suggest.attack_speed": lambda d: f"Kapten, navigatören. Föreslår fart {d['need']} "
    f"för att hinna till skjutläget.",
    "nav.attack.cannot": lambda d: f"Kapten, vi hinner inte till skjutläge framför {_att_what(d)}, "
    f"den går {d['target_speed']:.0f} knop bort från oss.",
    "nav.attack.none": lambda d: f"Kapten, plottet har ingen lösning på {d['designation']} "
    "att anfalla efter.",
    "nav.attack.lost": lambda d: {
        "lost": f"Kapten, vi har tappat {d['designation']} och lösningen är för gammal att styra efter. ",
        "poor": f"Kapten, lösningen på {d['designation']} har blivit för osäker att styra efter. ",
    }.get(d.get("why"), f"Kapten, lösningen på {d['designation']} är för gammal. ")
    + "Slutar styra mot skjutläget.",
    "nav.attack.arrived": lambda d: f"Kapten, vi är i skjutläge. {_att_what(d).capitalize()} "
    f"är tvärs om ungefär {_minutes(d['passage_min'])}, vi ligger {nm(d['dist'])} "
    f"sjömil om {'styrbord' if d['side'] > 0 else 'babord'} om {_att_path(d)}.",
    "nav.attack.passed": lambda d: f"Kapten, {_att_what(d)} har redan passerat oss. "
    "Slutar styra mot skjutläget.",
    "nav.suggest.attack_slow": lambda d: "Kapten, navigatören. Föreslår "
    + ("fart 3, tyst medan de kommer" if d.get("slow", True) else "")
    + (("" if not d.get("slow", True) else ", och ")
       + f"djup {d['fire_depth']}: torpederna går inte ut djupare än {d['max_depth']} meter"
       if d.get("fire_depth") else "") + "."
    + (" De har oss, så uppe på skjutdjupet är vi lättare att höra och närmare deras laddningar."
       if d.get("hunted") and d.get("fire_depth") else ""),
    "nav.suggest.attack_depth": lambda d: f"Kapten, navigatören. Vi ligger i skjutläget, och "
    f"{_att_what(d)} är tvärs om ungefär {_minutes(d['minutes'])}. Föreslår djup {d['fire_depth']}: "
    f"torpederna går inte ut djupare än {d['max_depth']} meter.",
    "nav.suggest.attack": lambda d: f"Kapten, navigatören. Plottet har "
    f"{'konvojen' if d.get('convoy') else d['designation']} på kurs "
    f"{fmt_course(d['course'])}, och vi ligger framför. Föreslår att vi går till skjutläge "
    f"vid sidan av dess väg, mot {d['designation']}"
    + (f", {d['classification']}" if d.get("classification") else "") + ".",
    "nav.steer": lambda d: f"Kurs {fmt_course(d['course'])} mot {d['name']}, "
    f"{nm(d['range'])} sjömil, ± {nm(d['sigma'])}.",
    "nav.suggest.task": lambda d: f"Kapten, navigatören. Enligt staben ligger {d['name']} "
    f"{nm(d['range'])} sjömil i kurs {fmt_course(d['course'])}, ± {nm(d['sigma'])}. "
    f"Föreslår kurs mot {d['name']}"
    + (f", på turbinen i {d['speed']} knop, så är vi där om "
       f"{round(d['range'] / d['speed'] * 60 / 10) * 10} minuter." if d.get("speed") else "."),
    "nav.steer.none": lambda d: f"Kapten, vi har ingen position för {d['name']}."
    + (f" Vi känner till: {', '.join(d['known'])}." if d["known"] else ""),
    "nav.steer.bank": lambda d: f"Kurs {fmt_course(d['course'])} mot banken, {nm(d['range'])} sjömil "
    f"till {d['depth']:.0f} meter enligt kortet, ± {nm(d['sigma'])}.",
    "nav.steer.bank_here": lambda d: f"Kapten, vi är redan över banken. Kortet visar cirka "
    f"{d['depth']:.0f} meter här.",
    "nav.suggest.land": lambda d: "Kapten, navigatören! "
    + ("Land" if d["shoal"] <= 0 else f"Bara {d['shoal']:.0f} meter vatten")
    + (" här enligt kortet" if d["dist"] < 0.15 else f" inom {nm(d['dist'])} sjömil framåt")
    + f". Föreslår kurs {fmt_course(d['course'])}.",
    "nav.suggest.land_astern": lambda d: "Kapten, navigatören! "
    + ("Land" if d["shoal"] <= 0 else f"Bara {d['shoal']:.0f} meter vatten")
    + (" här enligt kortet" if d["dist"] < 0.15 else f" inom {nm(d['dist'])} sjömil akter om oss")
    + ", och vi backar. Föreslår stopp i maskin.",
    "nav.suggest.unstick": lambda d: "Kapten, navigatören. "
    + ("Aktern" if d["stern"] else "Fören") + (" ligger an mot isen" if d["ice"] else " ligger an")
    + ". Föreslår " + (f"fart {kn(d['speed'])} knop framåt" if d["stern"]
                       else f"sakta back, {kn(d['speed'])} knop") + ", så kommer vi loss.",
    "nav.suggest.unstuck": lambda d: "Kapten, navigatören. Vi har backat loss, fören är fri. "
    f"Föreslår kurs {fmt_course(d['course'])}, fart {kn(d['speed'])} knop, bort från grundet.",
    "nav.suggest.chart_land": lambda d: "Kapten, navigatören! Kortet visar land där besticket står, "
    "men vi flyter: kortet ligger fel här, och stranden är nära. Närmaste vatten på kortet i kurs "
    f"{fmt_course(d['course'])}, {nm(d['dist'])} sjömil. Föreslår kurs {fmt_course(d['course'])}.",
    "nav.course.done": lambda d: f"Kapten, kurs {fmt_course(d['course'])} påkommen.",
    "nav.speed.done": lambda d: f"Back {kn(d['speed'])} knop, kapten, vi går akterut."
    if d.get("astern") else f"Fart {kn(d['speed'])} knop uppnådd.",
    "nav.speed.stopped": lambda d: "Båten står stilla, kapten. Nu går vi akterut." if d["astern"]
    else "Båten står stilla, kapten. Nu går vi framåt.",
    "nav.depth.done": lambda d: "Vi är i ytläge, kapten." if d["depth"] < 1
    else f"Djup {d['depth']:.0f} meter, kapten.",
    "nav.limit": _limit,
    "nav.fairway": lambda d: f"{ru('Jest')}, följer farleden ut, kurs {fmt_course(d['course'])}. "
    f"{d['legs']} ben, {nm(d['dist'])} sjömil. Vi håller styrbords sida.",
    "nav.fairway.leg": lambda d: f"Girpunkt i farleden, ny kurs {fmt_course(d['course'])}."
    + (" Sista benet ut." if d["legs"] == 1 else ""),
    "nav.fairway.done": lambda d: "Kapten, vi är ute ur farleden"
    + (f", {d['depth']:.0f} meter vatten enligt kortet" if d.get("depth") else "")
    + (". Fritt att dyka här." if d.get("surfaced") else ".")
    + (f" {d['to']} ligger framför oss." if d.get("to") else ""),
    "nav.fjord_dive": lambda d: "Kapten, navigatören! Vi är inne i fjorden. Ordern förbjuder "
    "dykning innanför mynningen! Svara ja om vi ändå ska dyka.",
    "nav.surface_confirm": lambda d: f"Kapten, navigatören! Plottet har {d['designation']}, "
    f"{d['classification']}" + (f", cirka {nm(d['range'])} sjömil bort" if d.get("range") is not None
                                else ", avståndet okänt")
    + ". I ytläge ser de oss. Svara ja om vi ska upp.",
    "nav.fairway.none": lambda d: "Kapten, vi har redan gått farleden ut." if d["done"]
    else "Kapten, det finns ingen farled framför oss på kortet.",
    "nav.suggest.fairway": lambda d: "Kapten, navigatören. Jag föreslår att vi följer farleden ut"
    + (f" mot {d['to'].lower()}" if d.get("to") else "")
    + ", på styrbords sida. Jag tar fixar från bryggan under tiden.",
    "nav.suggest.fairway_to": lambda d: f"Kapten, {d['name'].lower()} ligger i "
    f"{fmt_course(d['course'])}, {nm(d['range'])} sjömil. Föreslår kurs mot {d['name'].lower()}.",
    "nav.fix.start": lambda d: _lights_fix(d["lights"]) if d.get("lights") else
    "Pejlar landmärken från bryggan, en halv minut." if d.get("bridge")
    and d.get("day") else "Pejlar fyrarna från bryggan, under en minut." if d.get("bridge") else
    ("Tar fix på landmärken, en halv minut." if d.get("coast") and
                                d.get("day") else "Tar fix på fyrarna, under en minut."
                                if d.get("coast") else "Tar fix i periskopet, cirka två minuter."),
    "nav.fix.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.fix.aborted": lambda d: "Fixen avbröts, " + (
        "bryggan utryms." if d.get("bridge") else "vi lämnade periskopdjup."),
    "nav.starfix.start": lambda d: (
        "Sextanten upp på bryggan" if d.get("bridge") else "Periskopsextanten") + (
        ", tar höjder på stjärnorna mot horisonten, cirka fyra minuter."
        if d["method"] == "stjärnor" else
        ", tar höjder på månen och några stjärnor mot månhorisonten, cirka fyra minuter."),
    "nav.starfix.refused": lambda d: f"Ingen stjärnfix nu: {d['reason']}.",
    "nav.starfix.aborted": lambda d: "Stjärnfixen avbröts, " + (
        "bryggan utryms." if d.get("bridge") else "vi gick under periskopdjup."),
    "nav.starfix.done": lambda d: f"Stjärnfix klar, osäkerhet {nm(d['sigma'])} sjömil. Bestick "
    f"korrigerat {nm(d['error'])} sjömil åt {fmt_course(d['bearing'])}.",
    "nav.suggest.starfix": lambda d: f"Kapten, navigatören. {d['when'].capitalize()}: horisonten och "
    f"stjärnorna syns samtidigt. Bestickets osäkerhet är {nm(d['sigma'])} sjömil. Föreslår "
    "stjärnfix.",
    "nav.fix.done": lambda d: f"Fix tagen. Bestick korrigerat {nm(d['error'])} sjömil "
    f"åt {fmt_course(d['bearing'])}.",
    "nav.position": lambda d: f"Beräknad position {nm(d['x'])} sjömil öst och "
    f"{nm(d['y'])} norr i kvadraten, osäkerhet {nm(d['sigma'])} sjömil. "
    f"Senaste fix {d['last_fix']}.",
    "nav.echo": lambda d: f"Ekolod: {d['under_keel']:,.0f} meter under kölen.".replace(",", " "),
    "nav.suggest.fix": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är "
    f"{nm(d['sigma'])} sjömil. Föreslår fix på periskopdjup.",
    "nav.suggest.fix_now": lambda d: f"Kapten, vi är på periskopdjup. Bestickets osäkerhet är "
    f"{nm(d['sigma'])} sjömil. Föreslår att vi tar en fix nu.",
    "nav.suggest.search": lambda d: "Kapten, navigatören. Inga kontakter på länge. "
    f"Föreslår nytt sökben, kurs {fmt_course(d['course'])}.",
    "nav.suggest.area": lambda d: f"Kapten, vi är på väg ut ur {d.get('area', 'kvadrat 7')}. "
    f"Föreslår kurs {fmt_course(d['course'])}.",
    "nav.suggest.exit": lambda d: f"Kapten, navigatören. Närmaste väg ut ur {d['area']} "
    + (f"går runt land, {nm(d['dist'])} sjömil. Första biten kurs {fmt_course(d['course'])}"
       if d.get("via") else
       f"är kurs {fmt_course(d['course'])}, {nm(d['dist'])} sjömil")
    + (", bort från kontakterna." if d.get('clear') else ".")
    + f" Föreslår kurs {fmt_course(d['course'])}"
    + ((f", på turbinen i {d['speed']} knop." if d["speed"] > 4 else f", i {d['speed']} knop.")
       if d.get("speed") else "."),
    "nav.exit.out": lambda d: f"Kapten, enligt besticket är vi ute ur {d['area']}.",
    "nav.suggest.test_depth": lambda d: f"Kapten, vi är på {d['depth']:.0f} meter, under "
    f"provdjup. Föreslår djup 280.",
    "nav.ice.report": lambda d: _ice_report(d),
    "nav.ice.passed": lambda d: f"Isekolod: vi passerade {d['kind']}, cirka {d['length']} meter. "
    f"Loggat som öppning {d['no']}.",
    "nav.suggest.keel": lambda d: f"Kapten, navigatören. Vi går grunt under isen i {kn(d['speed'])} "
    f"knop. Kölarna kan nå 40–45 meter. Föreslår djup {d['depth']}.",
    "nav.suggest.ice_closing": lambda d: "Kapten! Isekolodet visar tjock is ovanför, isen driver "
    f"in över oss. Föreslår djup {d['depth']}.",
    "nav.suggest.fix_vak": lambda d: f"Kapten, navigatören. Bestickets osäkerhet är {nm(d['sigma'])} "
    f"sjömil och det är is ovanför. " + _opening_words(d) + " Föreslår att vi går dit för en fix.",
    "nav.vak.none": lambda d: "Kapten, vi har ingen öppning i isen loggad som vi kan hitta igen. "
    "Vi får leta: isekolodet säger till när vi passerar en.",
    "nav.vak.ack": lambda d: f"Går till öppning {d['no']}, bäring {fmt_course(d['bearing'])}, cirka "
    f"{d['range']} meter. Fart {kn(d['speed'])} knop" + (f", djup {d['depth']}" if d.get("depth") else "")
    + ".",
    "nav.vak.here": lambda d: f"Vi ligger under öppningen nu, {d['kind']}. Stoppar.",
    "nav.vak.measure": lambda d: f"Vi ligger under öppningen nu, {d['kind']}. Saktar till {kn(d['speed'])} "
    "knop och mäter upp den, sedan back till mitten. Back i maskin nu stoppar oss fortare, men "
    "omkastningen hörs.",
    "nav.vak.too_short": lambda d: f"Isekolodet: öppningen slutar här, bara cirka {d['length']} meter nyis, för kort "
    "att bryta igenom." + (f" Går till öppning {d['next']} i stället." if d["next"] else
                           " Ingen annan öppning loggad, vi söker vidare i 3 knop."),
    "nav.vak.back_ordered": lambda d: (f"Navigatören. Jag säger stopp mitt i öppningen, cirka {d['range']} "
                                       "meter akterut." if d["end"] else
                                       "Navigatören. Öppningen fortsätter förut, jag säger stopp när vi står."),
    "nav.vak.measured": lambda d: f"Isekolodet: öppningen slutar här, cirka {d['length']} meter lång. "
    f"Back {kn(d['speed'])} knop till mitten, cirka {d['range']} meter.",
    "nav.suggest.up": lambda d: f"Kapten, vi står stilla under öppningen, {d['kind']} ovanför. "
    + ("Vi är vid Nord-7. Föreslår ytläge." if d.get("station") else
       "Föreslår periskopdjup." if d["open"] else "Föreslår ytläge, vi bryter igenom nyisen."),
    "nav.vak.missed": lambda d: "Kapten, isekolodet visar tjock is här. Öppningen har drivit "
    "iväg eller så missade vi den.",
    "nav.vak.next": lambda d: "Kapten, navigatören. " + _opening_words(d) + " Föreslår att vi går dit.",
    "nav.vak.too_narrow": lambda d: (
        f"Kapten, vi står under nyisen, men för- och akterskeppet har tjock is över sig, råken är "
        f"cirka {d['length']} meter och vi kommer inte rätt i den." if d.get("cramped")
        else f"Kapten, vi står under nyisen, men råken är bara cirka {d['length']} meter. För smal "
        "för att bryta igenom med hela skrovet.")
    + f" Föreslår att vi söker vidare, fart 5 på {d['depth']} meter.",
    "nav.suggest.resume": lambda d: "Kapten, navigatören. Vi ligger stilla under tjock is. Föreslår "
    f"att vi söker vidare efter öppet vatten, fart 5 på {d['depth']} meter.",
    "nav.station.wp": lambda d: f"Kurs {fmt_course(d['course'])} mot {d['name']}, cirka "
    f"{nm(d['range'])} sjömil enligt huvudstabens position, osäkerhet {nm(d['sigma'])} sjömil.",
    "nav.station.sonar": lambda d: f"Styr på sonarbäringen mot {d['name']} ({d['designation']}), "
    f"kurs {fmt_course(d['course'])}.",
    "nav.station.none": lambda d: "Kapten, vi har ingen position på drivstationen ännu. Huvudstaben "
    "kan ge oss en vid sambandstillfället.",
    "nav.station.arrived": lambda d: f"Kapten, vi är vid huvudstabens position för {d['name']}. "
    f"Den kan ha drivit, osäkerheten är {nm(d['sigma'])} sjömil. Föreslår fart 3 och smygmotor, "
    "så att sonaren kan lyssna efter generatorn.",
    "nav.suggest.station_stop": lambda d: f"Kapten, navigatören. {d['kind'].capitalize()} ovanför oss "
    f"och vi bör vara nära {d['name']}. Föreslår att vi stoppar här.",
    "nav.suggest.station_go": lambda d: f"Kapten, navigatören. Vi har en position på {d['name']}, "
    f"kurs {fmt_course(d['course'])}, cirka {nm(d['range'])} sjömil. Föreslår att vi går dit.",
    "nav.suggest.station_continue": lambda d: f"Kapten, navigatören. Besticket är rättat. Föreslår "
    f"att vi fortsätter mot {d['name']}, fart 5 på {d['depth']} meter.",
    "nav.station.circle": lambda d: f"Kapten, generatorn på {d['name']} hörs mycket starkt, vi är "
    f"nästan under stationen. Går i en vidgande spiral runt den, från cirka {d['radius']} meter, "
    "och letar öppet vatten med isekolodet.",
    "nav.suggest.bumped": lambda d: "Kapten, vi skrapar mot isen i fart! Föreslår djup "
    f"{d['depth']} genast.",
    "nav.vak.narrow_station": lambda d: f"Kapten, öppet vatten ovanför, men råken är bara cirka "
    f"{d['length']} meter, för smal för ytläge. Föreslår att vi letar vidare runt {d['name']}, "
    f"fart 4 på {d['depth']} meter.",
    "nav.vak.overshot": lambda d: "Vi gled förbi öppningen när vi stoppade. Vänder tillbaka.",
    "nav.vak.reposition": lambda d: "Tornet står i kanten av öppningen, för- eller akterskeppet "
    "har is ovanför. Lägger oss mitt i den först.",
    "nav.vak.search": lambda d: "Kapten, navigatören. Ingen annan öppning loggad. Föreslår att vi "
    f"fortsätter söka, fart 5 på {d['depth']} meter.",
    "nav.suggest.stop_here": lambda d: f"Kapten, navigatören. {d['kind'].capitalize()} ovanför oss nu. "
    f"Bestickets osäkerhet är {nm(d['sigma'])} sjömil. Föreslår att vi stoppar här för en fix.",
    "nav.vak.timeout": lambda d: "Kapten, vi hittar inte tillbaka till öppningen. Avbryter.",
}


def _opening_words(d: dict) -> str:
    return (f"Öppning {d['no']} ligger i bäring {fmt_course(d['bearing'])}, cirka {d['range']} "
            f"meter, {d['length']} meter lång, {d['kind']}.")


def _ice_report(d: dict) -> str:
    if not d.get("sounded"):
        return "Isekolod: ingen is ovanför."
    if d["thickness"] < OPEN_M:
        txt = "Isekolod: öppet vatten ovanför."
    else:
        txt = (f"Isekolod: {thickness_words(d['thickness']) if d['thickness'] <= 1.0 else 'tjock is, cirka ' + nm(d['thickness']) + ' meter'}"
               f" ovanför, undersidan på cirka {nm(d['draft'])} meter.")
    if d.get("keel"):
        txt += f" Djupaste köl senaste tio minuterna cirka {d['keel']:.0f} meter."
    if d.get("opening"):
        txt += " " + _opening_words(d["opening"])
    else:
        txt += " Ingen användbar öppning loggad."
    return txt
phrases.register(PHRASES)


def _ru_depth_ack(d: dict) -> str:
    txt = ("Есть, всплывать в надводное положение." if d["depth"] == 0 else
           f"Есть, глубина {R.count(d['depth'], R.METER)}.")
    if d.get("steep"):
        txt += " С большим дифферентом."
    if d.get("below_test"):
        txt += " Это ниже рабочей глубины, товарищ командир."
    if d.get("ice_ceiling"):
        txt += f" Над нами лёд, выше {R.count(d['ice_ceiling'], R.METER)} не поднимемся."
    elif d.get("ice_masts"):
        txt += " Над нами лёд, мачты здесь не поднять."
    if "shoal" in d:
        txt += " По карте здесь земля." if d["shoal"] <= 0 else \
            f" По карте глубина здесь около {R.count(d['shoal'], R.METER)}."
    return txt


def _ru_ahead(d: dict) -> str:
    return "здесь" if d["dist"] < 0.15 else f"в {R.dec(d['dist'], R.MILE)} " \
        + ("за кормой" if d.get("astern") else "впереди")


_NAV = f"{R.CAPTAIN}, штурман."


def _ru_opening(d: dict) -> str:
    return (f"Полынья {d['no']}, пеленг {R.course(d['bearing'])}, около "
            f"{R.count(d['range'], R.METER)}, длина {R.count(d['length'], R.METER)}, "
            f"{R.ice_kind(d['kind'])}.")


def _ru_ice_report(d: dict) -> str:
    if not d.get("sounded"):
        return "Эхоледомер: льда над нами нет."
    if d["thickness"] < OPEN_M:
        txt = "Эхоледомер: над нами чистая вода."
    elif d["thickness"] <= 1.0:
        txt = f"Эхоледомер: над нами молодой лёд, около {R.dec(d['thickness'], R.METER)}."
    else:
        txt = (f"Эхоледомер: над нами толстый лёд, около {R.dec(d['thickness'], R.METER)}, "
               f"нижняя кромка около {R.dec(d['draft'], R.METER)}.")
    if d.get("keel"):
        txt += f" Самый глубокий киль за десять минут около {R.count(d['keel'], R.METER)}."
    txt += " " + _ru_opening(d["opening"]) if d.get("opening") else " Годных полыней не отмечено."
    return txt


def _ru_ns(v: float, pos: str, neg: str) -> str:
    return f"{R.dec(abs(v), R.MILE)} {pos if v >= 0 else neg}"


RU_PHRASES = {
    "nav.settle.refused": lambda d: f"{_NAV} Выполнить не могу.",
    "nav.bfix.refused": lambda d: f"{_NAV} Определиться по глубинам сейчас не могу.",
    "nav.fix.refused": lambda d: f"{_NAV} Определиться сейчас не могу.",
    "nav.settle.not_reached": lambda d: f"{R.CAPTAIN}, мы на {R.count(d['depth'], R.METER)}, а грунта "
    "нет. Карта здесь врёт. Предлагаю эхолот.",
    "nav.bfix.aborted": lambda d: "Определение по глубинам прервано, мы почти остановились.",
    "nav.bfix.done": lambda d: f"Место по глубинам определено. Поправка {R.dec(d['error'], R.MILE)} "
    f"по пеленгу {R.course(d['bearing'])}, ошибка {R.dec(d['sigma'], R.MILE)}.",
    "nav.bfix.line": lambda d: f"По глубинам получили линию положения, пеленг "
    f"{R.course(d['bearing'])}. Поправка {R.dec(d['error'], R.MILE)} по пеленгу "
    f"{R.course(d['bearing_corr'])}, ошибка {R.dec(d['sigma'], R.MILE)}. Вдоль изобат место "
    "не определено.",
    "nav.bfix.mismatch": lambda d: "Промеры не сходятся с картой, здесь "
    + ("мельче" if d["how"] == "grundare" else "глубже") + ", чем на карте. Счисление не меняем.",
    "nav.bfix.flat": lambda d: "Грунт здесь слишком ровный, промеры ничего не дают. "
    "Счисление не меняем.",
    "nav.bfix.chart": lambda d: f"Промеры сходятся с картой, но карта точна только до "
    f"{R.dec(d['accuracy'], R.MILE)}. Счисление не меняем.",
    "nav.suggest.bfix": lambda d: f"{_NAV} Ошибка счисления {R.dec(d['sigma'], R.MILE)}, а в перископ "
    "определиться нельзя. Здесь крутой рельеф дна. Предлагаю определиться по глубинам, "
    "девять промеров.",
    "nav.position": lambda d: f"Счислимое место: {_ru_ns(d['x'], 'к востоку', 'к западу')} и "
    f"{_ru_ns(d['y'], 'к северу', 'к югу')} в квадрате, ошибка {R.dec(d['sigma'], R.MILE)}. "
    f"Последнее определение в {d['last_fix']}.",
    "nav.echo": lambda d: f"Эхолот: под килём {R.count(d['under_keel'], R.METER)}.",
    "nav.follow.none": lambda d: f"{R.CAPTAIN}, пеленга на {R.contact(d['designation'])} нет.",
    "nav.steer.bank": lambda d: f"Курс {R.course(d['course'])} на банку, дистанция "
    f"{R.dec(d['range'], R.MILE)}, глубина по карте {R.count(d['depth'], R.METER)}.",
    "nav.steer.bank_here": lambda d: f"{R.CAPTAIN}, мы уже над банкой. По карте здесь "
    f"{R.count(d['depth'], R.METER)}.",
    "nav.steer": lambda d: f"Курс {R.course(d['course'])}, дистанция {R.dec(d['range'], R.MILE)}, "
    f"ошибка {R.dec(d['sigma'], R.MILE)}.",
    "nav.suggest.task": lambda d: f"{R.CAPTAIN}, штурман. По данным штаба цель в "
    f"{R.dec(d['range'], R.MILE)}, курс {R.course(d['course'])}. Предлагаю идти туда"
    + (f", турбина, {R.count(d['speed'], R.KNOT)}." if d.get("speed") else "."),
    "nav.steer.none": lambda d: f"{R.CAPTAIN}, места этой точки у нас нет.",
    "nav.ice.report": _ru_ice_report,
    "nav.suggest.keel": lambda d: f"{_NAV} Идём мелко подо льдом, ход {R.dec(d['speed'], R.KNOT)}. "
    f"Кили бывают до сорока пяти метров. Предлагаю глубину {R.count(d['depth'], R.METER)}.",
    "nav.suggest.fix_vak": lambda d: f"{_NAV} Ошибка счисления {R.dec(d['sigma'], R.MILE)}, над нами "
    f"лёд. {_ru_opening(d)} Предлагаю идти туда и определиться.",
    "nav.vak.none": lambda d: f"{R.CAPTAIN}, полыней, которые можно найти снова, не отмечено. "
    "Будем искать, эхоледомер доложит.",
    "nav.vak.missed": lambda d: f"{R.CAPTAIN}, эхоледомер показывает толстый лёд. Полынью "
    "отнесло, или мы её проскочили.",
    "nav.vak.next": lambda d: f"{_NAV} {_ru_opening(d)} Предлагаю идти туда.",
    "nav.vak.too_narrow": lambda d: (
        f"{R.CAPTAIN}, мы под молодым льдом, но над носом и кормой толстый лёд. "
        if d.get("cramped") else
        f"{R.CAPTAIN}, мы под молодым льдом, но разводье всего около {R.count(d['length'], R.METER)}. ")
    + f"Корпусом не проломить. Предлагаю искать дальше, ход пять узлов на {R.count(d['depth'], R.METER)}.",
    "nav.suggest.resume": lambda d: f"{_NAV} Стоим под толстым льдом. Предлагаю искать чистую "
    f"воду дальше, ход пять узлов на {R.count(d['depth'], R.METER)}.",
    "nav.vak.narrow_station": lambda d: f"{R.CAPTAIN}, над нами чистая вода, но разводье всего около "
    f"{R.count(d['length'], R.METER)}, для всплытия узко. Предлагаю искать дальше вокруг станции, "
    f"ход четыре узла на {R.count(d['depth'], R.METER)}.",
    "nav.vak.overshot": lambda d: "При остановке проскочили полынью. Возвращаемся.",
    "nav.vak.reposition": lambda d: "Рубка у края полыньи, над носом или кормой лёд. "
    "Сначала встанем посередине.",
    "nav.vak.search": lambda d: f"{_NAV} Других полыней не отмечено. Предлагаю продолжать поиск, "
    f"ход пять узлов на {R.count(d['depth'], R.METER)}.",
    "nav.vak.timeout": lambda d: f"{R.CAPTAIN}, полынью найти не можем. Прекращаем.",
    "nav.suggest.stop_here": lambda d: f"{_NAV} Над нами {R.ice_kind(d['kind'])}. Ошибка "
    f"счисления {R.dec(d['sigma'], R.MILE)}. Предлагаю остановиться здесь и определиться.",
    "nav.suggest.bumped": lambda d: f"{R.CAPTAIN}, на ходу задеваем лёд! Предлагаю глубину "
    f"{R.count(d['depth'], R.METER)}, немедленно.",
    "nav.station.wp": lambda d: f"Курс {R.course(d['course'])} на станцию, около "
    f"{R.dec(d['range'], R.MILE)} по данным штаба, ошибка {R.dec(d['sigma'], R.MILE)}.",
    "nav.station.sonar": lambda d: f"Идём на станцию по пеленгу акустика, курс "
    f"{R.course(d['course'])}.",
    "nav.station.none": lambda d: f"{R.CAPTAIN}, места дрейфующей станции у нас нет. Штаб может "
    "дать его в сеанс связи.",
    "nav.station.arrived": lambda d: f"{R.CAPTAIN}, мы в точке станции по данным штаба. Её могло "
    f"отнести, ошибка {R.dec(d['sigma'], R.MILE)}. Предлагаю ход три узла на электромоторе, "
    "чтобы акустик послушал генератор.",
    "nav.station.circle": lambda d: f"{R.CAPTAIN}, генератор станции слышно очень громко, мы почти "
    f"под ней. Идём расходящейся спиралью, от {R.count(d['radius'], R.METER)}, ищем чистую воду.",
    "nav.suggest.station_stop": lambda d: f"{_NAV} Над нами {R.ice_kind(d['kind'])}, станция должна "
    "быть рядом. Предлагаю остановиться здесь.",
    "nav.suggest.station_go": lambda d: f"{_NAV} Место станции известно, курс "
    f"{R.course(d['course'])}, около {R.dec(d['range'], R.MILE)}. Предлагаю идти туда.",
    "nav.suggest.station_continue": lambda d: f"{_NAV} Счисление исправлено. Предлагаю продолжать к "
    f"станции, ход пять узлов на {R.count(d['depth'], R.METER)}.",
    "nav.course.ack": lambda d: f"Есть, курс {R.course(d['course'])}."
    + (" Уже на курсе." if d.get("already") else ""),
    "nav.speed.ack": _ru_speed_ack,
    "nav.depth.ack": _ru_depth_ack,
    "nav.suggest.chart_land": lambda d: f"{R.CAPTAIN}, штурман! По карте мы на берегу, но мы на плаву: "
    "карта здесь врёт, берег рядом. Ближайшая вода по карте курсом "
    f"{R.course(d['course'])}, {R.dec(d['dist'], R.MILE)}. Предлагаю курс {R.course(d['course'])}.",
    "nav.course.done": lambda d: f"{R.CAPTAIN}, легли на курс {R.course(d['course'])}.",
    "nav.speed.done": lambda d: f"Задний ход {R.dec(d['speed'], R.KNOT)}." if d.get("astern")
    else f"Ход {R.dec(d['speed'], R.KNOT)}.",
    "nav.speed.stopped": lambda d: "Лодка остановилась. Идём назад." if d["astern"]
    else "Лодка остановилась. Идём вперёд.",
    "nav.depth.done": lambda d: "Мы в надводном положении, товарищ командир." if d["depth"] < 1
    else f"Глубина {R.count(d['depth'], R.METER)}, товарищ командир.",
    "nav.limit": _ru_limit,
    "nav.settle.ack": lambda d: f"Есть, ложимся на грунт. Глубина около {R.count(d['depth'], R.METER)}. "
    "Ход один узел, погружаемся.",
    "nav.settle.already": lambda d: "Мы уже лежим на грунте, товарищ командир.",
    "nav.settle.lift": lambda d: "Отрываемся от грунта.",
    "nav.bfix.start": lambda d: f"Есть, определяемся по глубинам. {d['n']} промеров за "
    f"{R.count(d['minutes'], R.MINUTE)}. Держите курс и ход, эхолот слышно.",
    "nav.fairway": lambda d: f"Есть, идём по фарватеру, курс {R.course(d['course'])}. "
    "Держимся правой стороны.",
    "nav.fairway.leg": lambda d: f"Поворотная точка. Новый курс {R.course(d['course'])}.",
    "nav.fairway.done": lambda d: f"{R.CAPTAIN}, фарватер пройден. Можно погружаться.",
    "nav.fairway.none": lambda d: f"{R.CAPTAIN}, фарватера впереди нет.",
    "nav.fjord_dive": lambda d: f"{R.CAPTAIN}, штурман! Мы в заливе. Погружение здесь запрещено! "
    "Повторите приказ, если погружаемся.",
    "nav.surface_confirm": lambda d: f"{R.CAPTAIN}, штурман! Рядом {R.contact(d['designation'])}. "
    "В надводном положении нас увидят. Повторите приказ, если всплываем.",
    "nav.suggest.fairway": lambda d: f"{R.CAPTAIN}, штурман. Предлагаю идти по фарватеру, "
    "правой стороной.",
    "nav.suggest.fairway_to": lambda d: f"{R.CAPTAIN}, предлагаю курс {R.course(d['course'])} "
    "в район учений.",
    "nav.fix.start": lambda d: "Есть, определяемся по береговым ориентирам." if d.get("bridge")
    else "Есть, определяемся по перископу.",
    "nav.fix.aborted": lambda d: "Определение прервано, " + (
        "мостик покинут." if d.get("bridge") else "мы ушли с перископной глубины."),
    "nav.starfix.start": lambda d: "Есть, определяемся по звёздам." if d["method"] == "stjärnor"
    else "Есть, определяемся по луне.",
    "nav.starfix.refused": lambda d: "Определиться по звёздам сейчас нельзя.",
    "nav.starfix.aborted": lambda d: "Определение по звёздам прервано.",
    "nav.starfix.done": lambda d: f"Место по звёздам определено. Поправка "
    f"{R.dec(d['error'], R.MILE)} по пеленгу {R.course(d['bearing'])}.",
    "nav.suggest.starfix": lambda d: f"{R.CAPTAIN}, штурман. Сумерки, видны и горизонт, и звёзды. "
    "Предлагаю определиться по звёздам.",
    "nav.fix.done": lambda d: f"Место определено. Поправка {R.dec(d['error'], R.MILE)} "
    f"по пеленгу {R.course(d['bearing'])}.",
    "nav.suggest.shoal": lambda d: f"{R.CAPTAIN}, штурман. "
    + (f"Эхолот показал {R.count(d['shoal'], R.METER)} до грунта" if d.get("sounded") else
       f"По карте {R.count(d['shoal'], R.METER)} {_ru_ahead(d)}")
    + f". Предлагаю глубину {R.count(d['depth'], R.METER)}.",
    "nav.suggest.land_astern": lambda d: f"{R.CAPTAIN}, штурман! "
    + ("Земля" if d["shoal"] <= 0 else f"Всего {R.count(d['shoal'], R.METER)} воды")
    + " за кормой по карте, а мы идём назад. Предлагаю стоп машина.",
    "nav.suggest.unstick": lambda d: f"{R.CAPTAIN}, штурман. "
    + ("Упёрлись кормой" if d["stern"] else "Упёрлись носом")
    + (" в лёд" if d["ice"] else "") + ". Предлагаю "
    + (f"ход {R.dec(d['speed'], R.KNOT)} вперёд" if d["stern"]
       else f"малый назад, {R.dec(d['speed'], R.KNOT)}") + ", отойдём.",
    "nav.suggest.unstuck": lambda d: f"{R.CAPTAIN}, штурман. Отошли, нос свободен. "
    f"Предлагаю курс {R.course(d['course'])}, ход {R.dec(d['speed'], R.KNOT)}, уходим от мели.",
    "nav.suggest.land": lambda d: f"{R.CAPTAIN}, штурман! "
    + ("Земля" if d["shoal"] <= 0 else f"Всего {R.count(d['shoal'], R.METER)} воды")
    + f" {_ru_ahead(d)} по карте. Предлагаю курс {R.course(d['course'])}.",
    "nav.follow": lambda d: f"Есть, идём в кильватер {R.contact(d['designation'], True)}, "
    f"курс {R.course(d['course'])}.",
    "nav.attack": lambda d: f"Есть, выходим в атаку. Курс {R.course(d['course'])}, в точке залпа "
    f"через {R.count(d['minutes'], R.MINUTE)}.",
    "nav.attack.speed": lambda d: f"{R.CAPTAIN}, на этой скорости не успеем. Нужно "
    f"{R.count(d['need'], R.KNOT)}, тогда в точке залпа через {R.count(d['minutes'], R.MINUTE)}.",
    "nav.suggest.attack_speed": lambda d: f"{R.CAPTAIN}, штурман. Предлагаю ход "
    f"{R.count(d['need'], R.KNOT)}.",
    "nav.attack.cannot": lambda d: f"{R.CAPTAIN}, в точку залпа не успеваем, цель уходит.",
    "nav.attack.none": lambda d: f"{R.CAPTAIN}, по {R.contact(d['designation'], True)} решения нет.",
    "nav.attack.lost": lambda d: f"{R.CAPTAIN}, решение по {R.contact(d['designation'], True)} "
    "устарело. Прекращаем выход в атаку.",
    "nav.attack.arrived": lambda d: f"{R.CAPTAIN}, мы в точке залпа. Цель пройдёт траверз примерно "
    f"через {R.count(max(1, round(d['passage_min'])), R.MINUTE)}.",
    "nav.attack.passed": lambda d: f"{R.CAPTAIN}, цель уже прошла. Прекращаем выход в атаку.",
    "nav.suggest.attack_slow": lambda d: f"{R.CAPTAIN}, штурман. Предлагаю "
    + ("ход три узла" if d.get("slow", True) else "")
    + ((" и " if d.get("slow", True) else "") + f"глубину {d['fire_depth']} метров"
       if d.get("fire_depth") else "") + "."
    + (" Нас держат, наверху нас легче услышать." if d.get("hunted") and d.get("fire_depth") else ""),
    "nav.suggest.attack_depth": lambda d: f"{R.CAPTAIN}, штурман. Мы в точке залпа, цель пройдёт траверз "
    f"через {R.count(max(1, round(d['minutes'])), R.MINUTE)}. Предлагаю глубину {d['fire_depth']} метров.",
    "nav.suggest.attack": lambda d: f"{R.CAPTAIN}, штурман. "
    f"{'Конвой' if d.get('convoy') else R.contact(d['designation']).capitalize()} идёт курсом "
    f"{R.course(d['course'])}, мы впереди. Предлагаю выйти в атаку по "
    f"{R.contact(d['designation'], True)}.",
    "nav.suggest.wait": lambda d: f"{R.CAPTAIN}, штурман. Ворота в сети открывают только для "
    "судов. Предлагаю ждать у фарватера и слушать, не идёт ли судно в гавань.",
    "nav.wait": lambda d: f"Есть, идём в точку ожидания, курс {R.course(d['course'])}.",
    "nav.wait.arrived": lambda d: f"{R.CAPTAIN}, мы в точке ожидания. Держим место малым ходом.",
    "nav.wait.none": lambda d: f"{R.CAPTAIN}, место сети неизвестно. Точку ожидания "
    "назначить не могу.",
    "nav.follow.lost": lambda d: f"{R.CAPTAIN}, мы потеряли {R.contact(d['designation'])}. "
    "Прекращаем следование.",
    "nav.suggest.fix": lambda d: f"{R.CAPTAIN}, штурман. Ошибка счисления {R.dec(d['sigma'], R.MILE)}. "
    "Предлагаю определиться на перископной глубине.",
    "nav.suggest.fix_now": lambda d: f"{R.CAPTAIN}, мы на перископной глубине. Ошибка счисления "
    f"{R.dec(d['sigma'], R.MILE)}. Предлагаю определиться сейчас.",
    "nav.suggest.search": lambda d: f"{R.CAPTAIN}, штурман. Контактов давно нет. "
    f"Предлагаю новый галс поиска, курс {R.course(d['course'])}.",
    "nav.suggest.area": lambda d: f"{R.CAPTAIN}, мы выходим из района. "
    f"Предлагаю курс {R.course(d['course'])}.",
    "nav.suggest.exit": lambda d: f"{R.CAPTAIN}, штурман. Ближайший выход из района "
    + (f"в обход земли, {R.dec(d['dist'], R.MILE)}" if d.get("via") else
       f"курсом {R.course(d['course'])}, {R.dec(d['dist'], R.MILE)}")
    + (", в сторону от контактов." if d.get("clear") else ".")
    + f" Предлагаю курс {R.course(d['course'])}"
    + ((f", турбина, {R.count(d['speed'], R.KNOT)}." if d["speed"] > 4 else
        f", {R.count(d['speed'], R.KNOT)}.") if d.get("speed") else "."),
    "nav.exit.out": lambda d: f"{R.CAPTAIN}, по счислению мы вышли из района.",
    "nav.suggest.settle": lambda d: f"{R.CAPTAIN}, штурман. Мы над мелководьем, по карте около "
    f"{R.count(d['depth'], R.METER)}. Если ляжем на грунт, наше эхо утонет в донном. "
    "Предлагаю лечь на грунт.",
    "nav.suggest.test_depth": lambda d: f"{R.CAPTAIN}, мы на глубине {R.count(d['depth'], R.METER)}, "
    "ниже рабочей глубины. Предлагаю глубину 280 метров.",
    "nav.ice.passed": lambda d: f"Эхоледомер: прошли полынью, около {R.count(d['length'], R.METER)}. "
    f"Записана под номером {d['no']}.",
    "nav.suggest.ice_closing": lambda d: f"{R.CAPTAIN}! Эхоледомер показывает толстый лёд, лёд "
    f"надвигается на нас. Предлагаю глубину {R.count(d['depth'], R.METER)}.",
    "nav.vak.ack": lambda d: f"Есть, идём к полынье {d['no']}, пеленг {R.course(d['bearing'])}, "
    f"около {R.count(d['range'], R.METER)}. Ход {R.count(d['speed'], R.KNOT)}.",
    "nav.vak.here": lambda d: "Мы под полыньёй. Стоп.",
    "nav.vak.measure": lambda d: "Мы под полыньёй. Малый ход, промеряем её, потом назад на середину. "
    "Задний ход сейчас остановит быстрее, но будет слышно.",
    "nav.vak.too_short": lambda d: f"Эхоледомер: полынья кончается, всего около {R.count(d['length'], R.METER)} "
    "молодого льда, пробить не можем." + (f" Идём к полынье {d['next']}." if d["next"] else
                                         " Других полыней не отмечено, ищем дальше."),
    "nav.vak.back_ordered": lambda d: (f"Штурман. Скажу стоп посередине полыньи, около "
                                       f"{R.count(d['range'], R.METER)} за кормой." if d["end"] else
                                       "Штурман. Полынья продолжается впереди, скажу стоп, когда встанем."),
    "nav.vak.measured": lambda d: f"Эхоледомер: полынья кончается, длина около {R.count(d['length'], R.METER)}. "
    f"Задний ход {R.count(d['speed'], R.KNOT)}, до середины около {R.count(d['range'], R.METER)}.",
    "nav.suggest.up": lambda d: f"{R.CAPTAIN}, мы стоим под полыньёй. "
    + ("Мы у станции Северный полюс семь. Предлагаю всплыть." if d.get("station") else
       "Предлагаю перископную глубину." if d["open"] else
       "Предлагаю всплыть, проломим молодой лёд."),
}
phrases.register_ru(RU_PHRASES)
