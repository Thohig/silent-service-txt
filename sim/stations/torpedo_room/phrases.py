"""Torpedrummets fraser, svenska och ryska."""
from __future__ import annotations


from ... import phrases
from ...fmt import fmt_course, nm
from ... import russian as R
from ...russian import ru
from ...reports import Quality
from ...weapons import WIRE_MAX_SPEED, WIRE_MAX_TURN

_WIRE_SPEED, _WIRE_TURN = round(WIRE_MAX_SPEED), round(WIRE_MAX_TURN)


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60} min {s % 60:02d} s"


def _tubes(d: dict) -> str:
    parts = []
    for t in d["tubes"]:
        if t["loading"]:
            parts.append(f"{t['n']}: laddas {t['loading']}")
        else:
            parts.append(f"{t['n']}: {t['load'] or 'tom'}")
    inv = ", ".join(f"{k} {v}" for k, v in d["inventory"].items())
    return "Tuber – " + ", ".join(parts) + f". I förråd: {inv}. Skenmål: {d['decoys']}."


def _in_water(d: dict) -> str:
    if not d["running"]:
        return "Inga torpeder i vattnet."
    rows = []
    for r in d["running"]:
        aim = f" mot {r['designation']}" if r["designation"] else f", kurs {fmt_course(r['course'])}"
        s = f"tub {r['tube']} ({r['type']}{aim}): gått {_mmss(r['elapsed'])}"
        if r.get("to_hit") is not None:
            s += (f", beräknad träff om {_mmss(r['to_hit'])}" if r["to_hit"] > 0
                  else ", beräknad träfftid passerad")
        s += f", räckvidden slut om {_mmss(r['to_end'])}"
        if r["bearing"] is None:
            s += ", sonar hör den inte"
        elif r["lost"]:
            s += f", sonar har tappat den (sista bäring {fmt_course(r['bearing'])})"
        else:
            s += f", hörs i bäring {fmt_course(r['bearing'])}"
        if r.get("wired"):
            s += ", går på tråd"
        elif r.get("guided"):
            s += ", tråden av, målsökaren söker"
        if r["turned"] and not r.get("wired"):
            s += ", har svängt, troligen målsökt"
        rows.append(s)
    return "Torpeder i vattnet – " + "; ".join(rows) + "."


def _solution(d: dict) -> str:
    rows = []
    for r in d["rows"]:
        if r.get("blocked"):
            rows.append(f"{r['type']}: {r['blocked']}")
        elif r.get("course") is None:
            rows.append(f"{r['type']}: utom räckhåll")
        else:
            rows.append(f"{r['type']}: kurs {fmt_course(r['course'])}, gångtid {_mmss(r['run_s'])}")
    return (f"Skjutlösning {d['designation']} (lösning {Quality(d['quality']).label}): "
            + "; ".join(rows) + ".")


DECOY_RU = ("имитатор", "имитатора", "имитаторов")

PHRASES = {
    "torp.refused": lambda d: f"Kapten, {d['reason']}.",
    "torp.nuclear_confirm": lambda d: f"Kapten, torped. Tub {d['tube']} har kärnladdning, nycklarna "
    f"är vridna. Upprepa ordern om vi ska skjuta mot {d['designation']}.",
    "torp.confirm": lambda d: (
        f"Kapten, {d['designation']} är klassad som {d['classification']}. "
        if d["civil"] else
        f"Kapten, {d['designation']} är inte säkert klassad som örlogsfartyg, "
        f"bara {d['classification']}. ") + "Upprepa ordern om vi ska skjuta.",
    "torp.neutral": lambda d: "Kapten, torpedrummet. Varning: "
    + ", ".join(f"{n['designation']} ({n['classification']}, bäring {fmt_course(n['bearing'])}"
                + (f", {nm(n['range'])} sjömil" if n.get("range") is not None else ", avståndet okänt")
                + ")" for n in d["ships"])
    + " ligger nära torpedernas bana. En rak torped som missar går vidare och kan träffa."
    + ("" if d.get("preview") else " Upprepa ordern om vi ska skjuta."),
    "torp.fired": lambda d: f"{ru('Torpeda vysjla')}! Tub {d['tube']} avfyrad, {d['type']}, kurs {fmt_course(d['course'])}"
    + (f", beräknad gångtid {_mmss(d['run_s'])}" if d.get("run_s") else "")
    + (". Lösningen var dålig, risk för miss." if d.get("quality") == Quality.DALIG else ".")
    + (f" Den går på tråd: vi styr den mot plottets lösning. Håll farten under "
       f"{_WIRE_SPEED} knop och gira inte mer än {_WIRE_TURN} grader." if d.get("wired") else ""),
    "torp.wire.guide": lambda d: f"Tub {d['tube']}: plottet har flyttat {d['designation']}, "
    f"vi styr torpeden till kurs {fmt_course(d['course'])}.",
    "torp.wire.seeker": lambda d: f"Tub {d['tube']}: torpeden är nära {d['designation']} enligt "
    "plottet. Tråden kapad, målsökaren söker.",
    "torp.wire.no_solution": lambda d: f"Tub {d['tube']}: plottet har ingen lösning på "
    f"{d['designation']} längre. Torpeden går vidare på sin kurs tills vi har en.",
    "torp.wire.strain": lambda d: f"Kapten, torpedrummet! Tråden till tub {d['tube']}: "
    + (f"vi går över {round(d['limit'])} knop, den slits av om vi inte saktar."
       if d["why"] == "fart" else
       f"vi har girat för långt, över {round(d['limit'])} grader går den i propellern."),
    "torp.wire.broken": lambda d: f"Tub {d['tube']}: tråden har gått av"
    + {"fart": " – farten slet av den", "gir": " – giren tog den", "längd": ", den är utspelad",
       "": ""}[d["why"]]
    + f". Torpeden går vidare på kurs {fmt_course(d['course'])}, målsökaren är till.",
    "torp.wire.cut": lambda d: "Tråden kapad"
    + (f" till tub {d['tubes'][0]}" if len(d["tubes"]) == 1
       else " till tuberna " + ", ".join(str(t) for t in d["tubes"]))
    + ". Målsökaren tar över, vi är fria att manövrera.",
    "torp.suggest.cut_wire": lambda d: "Kapten, torped. Vi har en torped på tråd. Föreslår att vi "
    "kapar tråden, så att vi kan gå undan fritt.",
    "torp.salvo": lambda d: f"Salva mot {d['designation']}: {d['n']} torpeder i solfjäder, "
    f"{nm(d['step'])} grader isär.",
    "torp.leg_warning": lambda d: f"Kapten, torpedrummet. Varning: "
    + (f"{d['designation']} jagar och girar hela tiden, och en {d['type']} är framme om "
       f"{_mmss(d['run_s'])}. Den hinner gira." if d.get("kind") == "hunting" else
       f"{d['designation']} sicksackar. Benet har gått {round(d['elapsed_s'] / 60)} minuter av ungefär "
       f"{round(d['leg_s'] / 60)}, och en {d['type']} är framme om {_mmss(d['run_s'])}. "
       + ("Konvojen" if d.get("kind", "convoy") == "convoy" else "Den") + " kan ha girat innan dess.")
    + (" Den målsökande torpeden söker själv efter giren." if d.get("homing")
       else " En målsökande torped har större chans."),
    "torp.time": lambda d: f"Tid för torpeden från tub {d['tube']}"
    + (f" mot {d['designation']}" if d.get("designation") else "") + "!",
    "torp.too_close": lambda d: f"Kapten, torped! {d['designation']} är för nära, cirka "
    f"{nm(d['range'])} sjömil till träffpunkten. Torpeden armeras först efter en kvarts sjömil och "
    "exploderar inte. Upprepa ordern om vi ändå skjuter.",
    "torp.time.sunk": lambda d: f"Tid för torpeden från tub {d['tube']}, men {d['designation']} har "
    "redan sjunkit. Den går vidare tills räckvidden är slut.",
    "torp.loading": lambda d: f"Laddar tub {d['tube']} med {d['type']}. "
    + ("Vi tar det försiktigt, åtta minuter. Det slamrar ändå när torpeden går in." if d.get("quiet")
       else "Fem minuter."),
    "torp.loaded": lambda d: f"Tub {d['tube']} laddad med {d['type']}.",
    "torp.status": _tubes,
    "torp.solution": _solution,
    "torp.decoy": lambda d: f"Skenmål ute. {d['left']} kvar.",
    "torp.ready": lambda d: f"Kapten, torped. Vi har skjutlösning på {d['designation']}: "
    f"tub {d['tube']} med {d['type']}, gångtid {_mmss(d['run_s'])}. Inväntar order.",
    "torp.suggest.reload": lambda d: f"Kapten, torped. Tub {d['tube']} är tom. "
    f"Föreslår att vi laddar {d['type']}.",
    "torp.suggest.decoy": lambda d: "Kapten, torped. Föreslår skenmål för att dra deras sonar."
    + (f" Vi har {d['left']} kvar." if d.get("left", 99) <= 2 else ""),
    "torp.in_water": _in_water,
    "torp.run.running": lambda d: f"Tub {d['tube']}: sonar hör torpeden i bäring "
    f"{fmt_course(d['bearing'])}, normal gång.",
    "torp.run.turned": lambda d: f"Tub {d['tube']}: torpeden svänger, nu i bäring "
    f"{fmt_course(d['bearing'])}. Målsökaren har troligen fått något.",
    "torp.run.lost": lambda d: f"Tub {d['tube']}: sonar har tappat torpeden"
    + (f", sista bäring {fmt_course(d['bearing'])}" if d.get("bearing") is not None else "") + ".",
    "torp.run.hit": lambda d: (
        f"Tub {d['tube']}: kärnladdningen har detonerat i bäring {fmt_course(d['bearing'])}."
        if d.get("nuclear") else
        f"Tub {d['tube']}: detonation i bäring {fmt_course(d['bearing'])}. Det var vår torped!"),
    "torp.run.early": lambda d: f"Tub {d['tube']}: detonation i bäring {fmt_course(d['bearing'])}, "
    f"{_mmss(d['early_s'])} före beräknad tid. Den har inte nått {d['designation']}: "
    "den gick av i förtid eller tog något annat.",
    "torp.run.dud": lambda d: f"Tub {d['tube']}: en smäll mot ett skrov i bäring "
    f"{fmt_course(d['bearing'])}, ingen detonation. Blindgångare, kapten. Målet är kvar.",
    "torp.run.silent": lambda d: f"Tub {d['tube']}: torpeden har tystnat"
    + (f" i bäring {fmt_course(d['bearing'])}" if d.get("bearing") is not None else "")
    + " utan detonation. Miss, kapten.",
    "torp.run.exercise_end": lambda d: f"Tub {d['tube']}: övningstorpeden har gått färdigt "
    "och flyter upp för bärgning.",
    "torp.run.timeout": lambda d: f"Tub {d['tube']}: torpedens räckvidd är slut och vi har inte "
    "hört någon detonation. Trolig miss.",
}
phrases.register(PHRASES)


def _ru_tube(d: dict) -> str:
    return f"Аппарат {d['tube']}"


def _ru_in_water(d: dict) -> str:
    if not d["running"]:
        return "Торпед в воде нет."
    rows = []
    for r in d["running"]:
        s = f"аппарат {r['tube']}, " + (f"по {R.contact(r['designation'], True)}" if r["designation"]
                                        else f"курс {R.course(r['course'])}")
        s += f", в воде {R.mmss(r['elapsed'])}"
        if r.get("to_hit") is not None:
            s += (f", до попадания {R.mmss(r['to_hit'])}" if r["to_hit"] > 0
                  else ", расчётное время попадания прошло")
        if r["bearing"] is None:
            s += ", акустик её не слышит"
        elif r["lost"]:
            s += ", акустик её потерял"
        else:
            s += f", пеленг {R.course(r['bearing'])}"
        if r.get("wired"):
            s += ", идёт по проводу"
        elif r.get("guided"):
            s += ", провод оборван, самонаводится"
        if r["turned"] and not r.get("wired"):
            s += ", повернула, видимо наводится"
        rows.append(s)
    return "Торпеды в воде: " + "; ".join(rows) + "."


def _ru_solution(d: dict) -> str:
    rows = []
    for r in d["rows"]:
        if r.get("blocked"):
            rows.append(f"{R.weapon(r['type'])}: нельзя")
        elif r.get("course") is None:
            rows.append(f"{R.weapon(r['type'])}: не достаёт")
        else:
            rows.append(f"{R.weapon(r['type'])}: курс {R.course(r['course'])}, время хода "
                        f"{R.mmss(r['run_s'])}")
    return (f"Решение по {R.contact(d['designation'], True)}, "
            f"{R.QUALITY_RU[int(d['quality'])]}: " + "; ".join(rows) + ".")


def _ru_tubes(d: dict) -> str:
    parts = [f"{t['n']} — заряжается" if t["loading"] else
             f"{t['n']} — {R.weapon(t['load'])}" if t["load"] else f"{t['n']} — пуст"
             for t in d["tubes"]]
    inv = ", ".join(f"{R.weapon(k)} — {v}" for k, v in d["inventory"].items())
    return f"Аппараты: {', '.join(parts)}. В запасе: {inv}. Имитаторов: {d['decoys']}."


RU_PHRASES = {
    "torp.refused": lambda d: f"{R.CAPTAIN}, минёр. Выполнить не могу.",
    "torp.nuclear_confirm": lambda d: f"{R.CAPTAIN}, минёр. В аппарате {d['tube']} ядерная "
    "торпеда, ключи повёрнуты. Повторите приказ, если стреляем.",
    "torp.confirm": lambda d: f"{R.CAPTAIN}, минёр. "
    + (f"{R.contact(d['designation']).capitalize()}: {R.classification(d['classification'])}. "
       if d["civil"] else
       f"{R.contact(d['designation']).capitalize()} не опознана как военный корабль. ")
    + "Повторите приказ, если стреляем.",
    "torp.in_water": _ru_in_water,
    "torp.solution": _ru_solution,
    "torp.status": _ru_tubes,
    "torp.fired":lambda d: f"Торпеда вышла! {_ru_tube(d)}, {R.weapon(d['type'])}, курс "
    f"{R.course(d['course'])}"
    + (f", расчётное время хода {R.mmss(d['run_s'])}" if d.get("run_s") else "")
    + (". Решение было плохое, возможен промах." if d.get("quality") == Quality.DALIG else ".")
    + (" Идёт по проводу, наводим по решению." if d.get("wired") else ""),
    "torp.wire.guide": lambda d: f"{_ru_tube(d)}: цель сместилась, доворачиваем торпеду на курс "
    f"{R.course(d['course'])}.",
    "torp.wire.seeker": lambda d: f"{_ru_tube(d)}: торпеда рядом с целью. Провод обрезан, "
    "головка самонаведения ищет.",
    "torp.wire.no_solution": lambda d: f"{_ru_tube(d)}: решения по цели больше нет. Торпеда идёт "
    "прежним курсом.",
    "torp.wire.strain": lambda d: f"{R.CAPTAIN}, торпедный отсек! Провод аппарата {d['tube']}: "
    + ("ход слишком большой, оборвём." if d["why"] == "fart" else "слишком большой поворот, "
       "намотаем на винт."),
    "torp.wire.broken": lambda d: f"{_ru_tube(d)}: провод оборван. Торпеда идёт курсом "
    f"{R.course(d['course'])}, самонаведение включено.",
    "torp.wire.cut": lambda d: "Есть, провод обрезан. Головка самонаведения ищет сама.",
    "torp.suggest.cut_wire": lambda d: f"{R.CAPTAIN}, минёр. Торпеда на проводе. Предлагаю "
    "обрезать провод, чтобы маневрировать свободно.",
    "torp.salvo": lambda d: f"Залп по {R.contact(d['designation'], True)}: "
    f"{R.count(d['n'], ('торпеда', 'торпеды', 'торпед'))} веером.",
    "torp.neutral": lambda d: f"{R.CAPTAIN}, торпедный отсек. Внимание: "
    + ("торговое судно" if len(d["ships"]) == 1 else "торговые суда")
    + " рядом с курсом торпед."
    + ("" if d.get("preview") else " Повторите приказ, если стреляем."),
    "torp.leg_warning": lambda d: f"{R.CAPTAIN}, торпедный отсек. Внимание: "
    + ("цель нас ищет и всё время маневрирует, успеет отвернуть." if d.get("kind") == "hunting" else
       "цель идёт зигзагом, "
       + ("конвой" if d.get("kind", "convoy") == "convoy" else "она")
       + " может повернуть раньше, чем дойдёт торпеда."),
    "torp.too_close": lambda d: f"{R.CAPTAIN}, минёр! {R.contact(d['designation']).capitalize()} "
    "слишком близко, торпеда не успеет взвестись. Повторите приказ, если стреляем.",
    "torp.time.sunk": lambda d: f"Время торпеды из аппарата {d['tube']}, но цель уже тонет.",
    "torp.time": lambda d: f"Время торпеды из аппарата {d['tube']}"
    + (f" по {R.contact(d['designation'], True)}" if d.get("designation") else "") + "!",
    "torp.loading": lambda d: f"Есть, заряжаем аппарат {d['tube']}, {R.weapon(d['type'])}. "
    + ("Тихо, восемь минут." if d.get("quiet") else "Пять минут."),
    "torp.loaded": lambda d: f"{_ru_tube(d)} заряжен, {R.weapon(d['type'])}.",
    "torp.decoy": lambda d: f"Есть, имитатор выпущен. Осталось {d['left']}.",
    "torp.ready": lambda d: f"{R.CAPTAIN}, минёр. Есть решение по {R.contact(d['designation'], True)}: "
    f"аппарат {d['tube']}, {R.weapon(d['type'])}, время хода {R.mmss(d['run_s'])}. Ждём команды.",
    "torp.suggest.reload": lambda d: f"{R.CAPTAIN}, минёр. Аппарат {d['tube']} пуст. "
    f"Предлагаю зарядить {R.weapon(d['type'])}.",
    "torp.suggest.decoy": lambda d: f"{R.CAPTAIN}, минёр. Предлагаю выпустить имитатор, "
    "чтобы отвлечь их гидролокатор."
    + (f" Осталось {R.count(d['left'], DECOY_RU)}." if d.get("left", 99) <= 2 else ""),
    "torp.run.running": lambda d: f"{_ru_tube(d)}: акустик слышит торпеду, пеленг "
    f"{R.course(d['bearing'])}, идёт нормально.",
    "torp.run.turned": lambda d: f"{_ru_tube(d)}: торпеда поворачивает, пеленг "
    f"{R.course(d['bearing'])}. Головка самонаведения, видимо, что-то захватила.",
    "torp.run.lost": lambda d: f"{_ru_tube(d)}: торпеда потеряна"
    + (f", последний пеленг {R.course(d['bearing'])}" if d.get("bearing") is not None else "") + ".",
    "torp.run.hit": lambda d: (
        f"{_ru_tube(d)}: ядерный заряд взорвался, пеленг {R.course(d['bearing'])}."
        if d.get("nuclear") else
        f"{_ru_tube(d)}: взрыв, пеленг {R.course(d['bearing'])}. Это наша торпеда!"),
    "torp.run.early": lambda d: f"{_ru_tube(d)}: взрыв, пеленг {R.course(d['bearing'])}, на "
    f"{R.mmss(d['early_s'])} раньше расчётного. До цели не дошла.",
    "torp.run.dud": lambda d: f"{_ru_tube(d)}: удар о корпус, пеленг {R.course(d['bearing'])}, "
    "взрыва нет. Отказ взрывателя, товарищ командир.",
    "torp.run.silent": lambda d: f"{_ru_tube(d)}: торпеда затихла"
    + (f", пеленг {R.course(d['bearing'])}" if d.get("bearing") is not None else "")
    + ", взрыва не было. Промах, товарищ командир.",
    "torp.run.exercise_end": lambda d: f"{_ru_tube(d)}: практическая торпеда прошла дистанцию "
    "и всплыла.",
    "torp.run.timeout": lambda d: f"{_ru_tube(d)}: запас хода торпеды кончился, взрыва не "
    "слышали. Вероятно, промах.",
}
phrases.register_ru(RU_PHRASES)
