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


PHRASES = {
    "nav.course.ack": lambda d: f"{ru('Jest')}, kurs {fmt_course(d['course'])}."
    + (" Vi ligger på den." if d.get("already") else ""),
    "nav.speed.ack": lambda d: f"{ru('Jest')}, stopp i maskin." if d["speed"] == 0
    else f"{ru('Jest')}, fart {kn(d['speed'])} knop.",
    "nav.depth.ack": lambda d: (f"{ru('Jest')}, upp till ytan." if d["depth"] == 0 else
                                f"{ru('Jest')}, djup {d['depth']:.0f} meter.")
    + (" Det är under provdjup, kapten." if d.get("below_test") else "")
    + (f" Det är is ovanför, kapten, vi kommer inte högre än cirka {d['ice_ceiling']:.0f} meter."
       if d.get("ice_ceiling") else
       " Det är is ovanför, kapten, masterna kommer inte upp här." if d.get("ice_masts") else "")
    + (f" Kortet visar botten på cirka {d['shoal']:.0f} meter här, kapten." if d.get("shoal") else ""),
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
       + ("här" if d["dist"] < 0.15 else f"inom {nm(d['dist'])} sjömil framåt"))
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
    "nav.attack.lost": lambda d: f"Kapten, lösningen på {d['designation']} är för gammal. "
    "Slutar styra mot skjutläget.",
    "nav.attack.arrived": lambda d: f"Kapten, vi är i skjutläge. {_att_what(d).capitalize()} "
    f"är tvärs om ungefär {_minutes(d['passage_min'])}, vi ligger {nm(d['dist'])} "
    f"sjömil om {'styrbord' if d['side'] > 0 else 'babord'} om {_att_path(d)}.",
    "nav.attack.passed": lambda d: f"Kapten, {_att_what(d)} har redan passerat oss. "
    "Slutar styra mot skjutläget.",
    "nav.suggest.attack_slow": lambda d: "Kapten, navigatören. Föreslår fart 3, tyst medan de kommer.",
    "nav.suggest.attack": lambda d: f"Kapten, navigatören. Plottet har "
    f"{'konvojen' if d.get('convoy') else d['designation']} på kurs "
    f"{fmt_course(d['course'])}, och vi ligger framför. Föreslår att vi går till skjutläge "
    f"vid sidan av dess väg, mot {d['designation']}"
    + (f", {d['classification']}" if d.get("classification") else "") + ".",
    "nav.steer": lambda d: f"Kurs {fmt_course(d['course'])} mot {d['name']}, "
    f"{nm(d['range'])} sjömil, ± {nm(d['sigma'])}.",
    "nav.steer.none": lambda d: f"Kapten, vi har ingen position för {d['name']}. "
    + (f"Vi känner till: {', '.join(d['known'])}." if d["known"] else ""),
    "nav.suggest.land": lambda d: "Kapten, navigatören! "
    + ("Land" if d["shoal"] <= 0 else f"Bara {d['shoal']:.0f} meter vatten")
    + (" här enligt kortet" if d["dist"] < 0.15 else f" inom {nm(d['dist'])} sjömil framåt")
    + f". Föreslår kurs {fmt_course(d['course'])}.",
    "nav.course.done": lambda d: f"Kapten, kurs {fmt_course(d['course'])} påkommen.",
    "nav.speed.done": lambda d: f"Fart {kn(d['speed'])} knop uppnådd.",
    "nav.depth.done": lambda d: "Vi är i ytläge, kapten." if d["depth"] < 1
    else f"Djup {d['depth']:.0f} meter, kapten.",
    "nav.limit": lambda d: f"Kapten, högsta fart just nu är {kn(d['limit'])} knop."
    if d["what"] == "speed" else f"Kapten, största djup är {d['limit']:.0f} meter.",
    "nav.fairway": lambda d: f"{ru('Jest')}, följer farleden ut, kurs {fmt_course(d['course'])}. "
    f"{d['legs']} ben, {nm(d['dist'])} sjömil. Vi håller styrbords sida.",
    "nav.fairway.leg": lambda d: f"Girpunkt i farleden, ny kurs {fmt_course(d['course'])}."
    + (" Sista benet ut." if d["legs"] == 1 else ""),
    "nav.fairway.done": lambda d: "Kapten, vi är ute ur farleden"
    + (f", {d['depth']:.0f} meter vatten enligt kortet" if d.get("depth") else "")
    + (". Fritt att dyka här." if d.get("surfaced") else ".")
    + (f" {d['to']} ligger framför oss." if d.get("to") else ""),
    "nav.fjord_dive": lambda d: "Kapten, navigatören! Vi är inne i fjorden. Ordern förbjuder "
    "dykning innanför mynningen!",
    "nav.fairway.none": lambda d: "Kapten, vi har redan gått farleden ut." if d["done"]
    else "Kapten, det finns ingen farled framför oss på kortet.",
    "nav.suggest.fairway": lambda d: "Kapten, navigatören. Jag föreslår att vi följer farleden ut"
    + (f" mot {d['to'].lower()}" if d.get("to") else "")
    + ", på styrbords sida. Jag tar fixar från bryggan under tiden.",
    "nav.suggest.fairway_to": lambda d: f"Kapten, {d['name'].lower()} ligger i "
    f"{fmt_course(d['course'])}, {nm(d['range'])} sjömil. Föreslår kurs mot {d['name'].lower()}.",
    "nav.fix.start": lambda d: "Pejlar landmärken från bryggan, en halv minut." if d.get("bridge")
    and d.get("day") else "Pejlar fyrarna från bryggan, under en minut." if d.get("bridge") else
    ("Tar fix på landmärken, en halv minut." if d.get("coast") and
                                d.get("day") else "Tar fix på fyrarna, under en minut."
                                if d.get("coast") else "Tar fix i periskopet, cirka två minuter."),
    "nav.fix.refused": lambda d: f"Kapten, {d['reason']}.",
    "nav.fix.aborted": lambda d: "Fixen avbröts, vi lämnade periskopdjup.",
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
    + f" Föreslår kurs {fmt_course(d['course'])}.",
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
    "nav.suggest.up": lambda d: f"Kapten, vi står stilla under öppningen, {d['kind']} ovanför. "
    + ("Vi är vid Nord-7. Föreslår ytläge." if d.get("station") else
       "Föreslår periskopdjup." if d["open"] else "Föreslår ytläge, vi bryter igenom nyisen."),
    "nav.vak.missed": lambda d: "Kapten, isekolodet visar tjock is här. Öppningen har drivit "
    "iväg eller så missade vi den.",
    "nav.vak.next": lambda d: "Kapten, navigatören. " + _opening_words(d) + " Föreslår att vi går dit.",
    "nav.vak.too_narrow": lambda d: f"Kapten, vi står under nyisen, men råken är bara cirka "
    f"{d['length']} meter. För smal för att bryta igenom med hela skrovet. Föreslår att vi söker "
    f"vidare, fart 5 på {d['depth']} meter.",
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
    if d.get("below_test"):
        txt += " Это ниже рабочей глубины, товарищ командир."
    if d.get("ice_ceiling"):
        txt += f" Над нами лёд, выше {R.count(d['ice_ceiling'], R.METER)} не поднимемся."
    elif d.get("ice_masts"):
        txt += " Над нами лёд, мачты здесь не поднять."
    if d.get("shoal"):
        txt += f" По карте глубина здесь около {R.count(d['shoal'], R.METER)}."
    return txt


def _ru_ahead(d: dict) -> str:
    return "здесь" if d["dist"] < 0.15 else f"в {R.dec(d['dist'], R.MILE)} впереди"


RU_PHRASES = {
    "nav.course.ack": lambda d: f"Есть, курс {R.course(d['course'])}."
    + (" Уже на курсе." if d.get("already") else ""),
    "nav.speed.ack": lambda d: "Есть, стоп машина." if d["speed"] == 0
    else f"Есть, ход {R.count(d['speed'], R.KNOT)}.",
    "nav.depth.ack": _ru_depth_ack,
    "nav.course.done": lambda d: f"{R.CAPTAIN}, легли на курс {R.course(d['course'])}.",
    "nav.speed.done": lambda d: f"Ход {R.count(d['speed'], R.KNOT)}.",
    "nav.depth.done": lambda d: "Мы в надводном положении, товарищ командир." if d["depth"] < 1
    else f"Глубина {R.count(d['depth'], R.METER)}, товарищ командир.",
    "nav.limit": lambda d: f"{R.CAPTAIN}, предельный ход сейчас {R.count(d['limit'], R.KNOT)}."
    if d["what"] == "speed" else f"{R.CAPTAIN}, предельная глубина {R.count(d['limit'], R.METER)}.",
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
    "nav.fjord_dive": lambda d: f"{R.CAPTAIN}, штурман! Мы в заливе. Погружение здесь запрещено!",
    "nav.suggest.fairway": lambda d: f"{R.CAPTAIN}, штурман. Предлагаю идти по фарватеру, "
    "правой стороной.",
    "nav.suggest.fairway_to": lambda d: f"{R.CAPTAIN}, предлагаю курс {R.course(d['course'])} "
    "в район учений.",
    "nav.fix.start": lambda d: "Есть, определяемся по береговым ориентирам." if d.get("bridge")
    else "Есть, определяемся по перископу.",
    "nav.fix.aborted": lambda d: "Определение прервано, мы ушли с перископной глубины.",
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
    "nav.suggest.attack_slow": lambda d: f"{R.CAPTAIN}, штурман. Предлагаю ход три узла.",
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
    + f" Предлагаю курс {R.course(d['course'])}.",
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
    "nav.suggest.up": lambda d: f"{R.CAPTAIN}, мы стоим под полыньёй. "
    + ("Мы у станции Северный полюс семь. Предлагаю всплыть." if d.get("station") else
       "Предлагаю перископную глубину." if d["open"] else
       "Предлагаю всплыть, проломим молодой лёд."),
}
phrases.register_ru(RU_PHRASES)
