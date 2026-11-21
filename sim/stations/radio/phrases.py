"""Radions fraser, svenska och ryska."""
from __future__ import annotations


from ... import phrases
from ... import russian as R
from ...fmt import fmt_course, nm
from ...ownship import ANTENNA_DEPTH
from .common import VLF_DEPTH, VLF_RECEIVE_S, VLF_SLOW_KN, VLF_SPEED, VLF_UP_DEPTH


KIND_SV = {"full": "rapporten", "short": "kort rapport", "contact": "rapport om kontakten"}
KIND_RU = {"full": "донесение", "short": "короткое донесение", "contact": "донесение о цели"}
RISK_RU = {"liten": "малый", "måttlig": "умеренный", "stor": "большой"}


def _groups(n: int) -> str:
    return f"{n} grupp" if n == 1 else f"{n} grupper"


def _contacts_sv(n: int) -> str:
    return "en kontakt" if n == 1 else f"{n} kontakter"


def _intercept_sv(d: dict) -> str:
    parts = []
    if d["air"]:
        parts.append("amerikansk flygradio, " + ("ett plan" if d["air"] == 1 else
                                                 f"{d['air']} plan") + " i luften i området")
    if d["ships"]:
        parts.append("radiotelefoni från " + ("ett örlogsfartyg" if d["ships"] == 1 else
                                              f"{d['ships']} örlogsfartyg"))
    if d["hunting"]:
        parts.append("jagarna rapporterar kontakt till varandra, de söker något")
    if not parts:
        return "Kapten, radio. Avlyssning: bara avlägsen rutintrafik, inget som rör oss."
    return "Kapten, radio. Avlyssning: " + "; ".join(parts) + "."


def _intercept_ru(d: dict) -> str:
    parts = []
    if d["air"]:
        parts.append(f"американская авиационная связь, самолётов в районе: {d['air']}")
    if d["ships"]:
        parts.append(f"радиотелефон военных кораблей: {d['ships']}")
    if d["hunting"]:
        parts.append("эсминцы докладывают друг другу о контакте, они кого-то ищут")
    if not parts:
        return f"{R.CAPTAIN}, радист. Радиоперехват: только дальний обычный трафик."
    return f"{R.CAPTAIN}, радист. Радиоперехват: " + "; ".join(parts) + "."


WHY_GARBLED = {"day": "dagsljus", "speed": f"farten över {VLF_SLOW_KN} knop",
               "depth": f"djupare än {VLF_UP_DEPTH} meter"}


def _why_garbled(why: list[str]) -> str:
    words = [WHY_GARBLED[w] for w in why]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " och " + words[-1]



PHRASES = {
    "radio.prewarn": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. "
    f"Vi behöver antenndjup, {ANTENNA_DEPTH:.0f} meter eller grundare.",
    "radio.prewarn_vlf": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. Vi kan ta emot "
    f"på långvåg med flytkabeln, högst {VLF_DEPTH:.0f} meter och högst {VLF_SPEED:.0f} knop; det tar "
    f"cirka {VLF_RECEIVE_S // 60} minuter." + (
        " I den här farten dras kabeln under, så föreslår antenndjup: masten tar emot på en minut."
        if d.get("mast") else f" Föreslår {d['what']}." if d.get("what") else ""),
    "radio.window_open": lambda d: "Sambandstillfället har börjat. Vi lyssnar.",
    "radio.cable.out": lambda d: f"Flytkabeln ute, vi tar emot på långvåg, cirka {d['minutes']} minuter.",
    "radio.cable.fast": lambda d: "Kapten, radio. Flytkabeln dras under i den här farten, vi tappar "
    f"långvågen. Föreslår fart {VLF_SLOW_KN}.",
    "radio.garbled": lambda d: "Kapten, radio. Långvågen kom in stympad, " + _why_garbled(d["why"])
    + ". Vi lyssnar vidare på omsändningen." + (f" Föreslår {d['what']}." if d.get("what") else ""),
    "radio.message": lambda d: f"Kapten, radio. Radiogram nummer {d['telegram']} från huvudstaben"
    + (", på långvåg." if d.get("via") == "vlf" else "."),
    "radio.nothing": lambda d: "Sambandstillfälle: inga nya meddelanden till oss.",
    "radio.missed": lambda d: "Kapten, vi missade sambandstillfället. " + (
        f"Staben sänder om radiogrammen vid nästa, kl {d['next']}." if d.get("next") else
        "Det finns inget fler inplanerat, så det staben sänt når oss inte."),
    "radio.refused": lambda d: f"Kapten, {d['reason']}.",
    "radio.sending": lambda d: f"Sänder {KIND_SV[d['kind']]} på kortvåg, {_groups(d['groups'])}, "
    f"cirka {d['seconds']} sekunder. Risken att de pejlar oss är {d['risk']}.",
    "radio.sent": lambda d: "Rapport sänd och kvitterad"
    + (f", {_contacts_sv(d['contacts'])} rapporterade." if d["contacts"] else "."),
    "radio.aborted": lambda d: "Sändningen avbröts, antennen kom under ytan.",
    "radio.prewarn_ice": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}. Det är is "
    "ovanför oss. " + (f"Navigatören har öppning {d['no']} i bäring {fmt_course(d['bearing'])}, cirka "
                       f"{d['range']} meter. Föreslår att vi går dit." if d.get("no")
                       else "Vi har ingen öppning loggad, vi behöver hitta öppet vatten."),
    "radio.opening_now": lambda d: f"Kapten, radio. Navigatören har {d['kind']} ovanför oss nu, och "
    f"sambandstillfället kl {d['clock']} är inte avklarat. Föreslår att vi stoppar här.",
    "radio.suggest.air_clear": lambda d: f"Kapten, radio. Flygradarn hördes nära för "
    f"{d['minutes']} minuter sedan, och sambandstillfället stänger kl {d['close']}. Föreslår "
    "periskopdjup: radarvarnaren säger om flyget gått, och då sänder vi.",
    "radio.intercept.start": lambda d: "Avlyssnar amerikansk trafik, en minut.",
    "radio.intercept.lost": lambda d: "Avlyssningen avbröts, antennen kom under ytan.",
    "radio.intercept": _intercept_sv,
    "radio.suggest.intercept": lambda d: "Kapten, radio. Vi har antennen uppe. Föreslår att vi "
    "avlyssnar den amerikanska trafiken en minut, så vet vi om flyget och jagarna är i närheten.",
    "radio.ice": lambda d: "Kapten, radio. Antennen och flytkabeln kommer inte upp genom isen, vi får "
    "ingen mottagning. "
    "Vi behöver öppet vatten ovanför.",
    "radio.suggest.report": lambda d: "Kapten, radio. Sambandstillfället är öppet och huvudstaben "
    "väntar på vår rapport. " + (
        (f"Hela rapporten tar cirka {d['seconds']} sekunder och risken att de pejlar oss är "
         f"{d['risk']}. Föreslår en kort rapport, cirka {d['short_s']} sekunder."
         if d.get("short") else
         f"Föreslår att vi sänder nu. Det tar cirka {d['seconds']} sekunder, och risken att de "
         f"pejlar oss är {d['risk']}.") if d["now"] else
        "Vi måste upp på periskopdjup för att sända. Föreslår periskopdjup."),
    "radio.suggest.task_report": lambda d: f"Kapten, radio. Staben vill ha kurs och fart på "
    f"styrkan, och plottet har en lösning på {d['designation']}. " + (
        f"Föreslår att vi sänder rapporten nu. Det tar cirka {d['seconds']} sekunder, och risken "
        f"att de pejlar oss är {d['risk']}." if d["now"] else
        "Vi måste upp på periskopdjup för att sända. Föreslår periskopdjup."),
    "radio.wait": lambda d: f"Kapten, radio. Sambandstillfälle kl {d['clock']}, men plottet har "
    f"{d['designation']} på {nm(d['range'])} sjömil. Där uppe ligger vi över skiktet och hörs. "
    "Föreslår att vi väntar på djupet tills den gått längre bort.",
    "radio.clear": lambda d: f"Kapten, radio. Plottet har nu {d['designation']} på {nm(d['range'])} "
    "sjömil" + (f", och sambandstillfället stänger kl {d['close']}" if d.get("close") else "")
    + f". Föreslår {d.get('what', 'antenndjup')}.",
    "radio.listen": lambda d: "Lyssnar på kortvåg efter Moskva.",
    "radio.listen.lost": lambda d: "Tappade Moskva, antennen kom under ytan.",
    "radio.moscow": lambda d: f"Kapten, radio. Radio Moskva hörs, remsa nummer {d['telegram']}.",
    "radio.moscow.silent": lambda d: "Kapten, radio. Moskva tiger, bara bärvågen.",
    "radio.status": lambda d: (
        f"Sambandstillfället pågår, från {d['open']} till {d['until']}. " if d.get("open")
        else f"Nästa sambandstillfälle kl {d['next']}. " if d.get("next")
        else "Inga fler sambandstillfällen inplanerade. ")
    + ("Inga meddelanden mottagna." if d["received"] == 0
       else "1 meddelande mottaget." if d["received"] == 1
       else f"{d['received']} meddelanden mottagna.")
    + (f" Senaste: {d['last']}" if d.get("last") else ""),
}
phrases.register(PHRASES)

RU_PHRASES = {
    "radio.refused": lambda d: f"{R.CAPTAIN}, радист. Выполнить не могу.",
    "radio.intercept.start": lambda d: "Есть, слушаем американский трафик, одну минуту.",
    "radio.intercept.lost": lambda d: "Перехват прерван, антенна ушла под воду.",
    "radio.intercept": _intercept_ru,
    "radio.suggest.intercept": lambda d: f"{R.CAPTAIN}, радист. Антенна поднята. Предлагаю минуту "
    "послушать американский трафик, узнаем, нет ли рядом самолётов и эсминцев.",
    "radio.suggest.air_clear": lambda d: f"{R.CAPTAIN}, радист. Самолёт слышали рядом "
    f"{R.count(d['minutes'], R.MINUTE)} назад, сеанс связи кончается в {d['close']}. Предлагаю "
    "перископную глубину: станция предупреждения покажет, ушёл ли самолёт, и тогда передадим.",
    "radio.prewarn_ice": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Над нами лёд. "
    + (f"У штурмана полынья {d['no']}, пеленг {R.course(d['bearing'])}, около "
       f"{R.count(d['range'], R.METER)}. Предлагаю идти туда." if d.get("no")
       else "Полыней не отмечено, нужно искать чистую воду."),
    "radio.opening_now": lambda d: f"{R.CAPTAIN}, радист. Над нами {R.ice_kind(d['kind'])}, а сеанс связи в "
    f"{d['clock']} ещё не прошёл. Предлагаю остановиться здесь.",
    "radio.ice": lambda d: f"{R.CAPTAIN}, радист. Антенны подо льдом, приёма нет. "
    "Нужна чистая вода над нами.",
    "radio.status": lambda d: (
        f"Идёт сеанс связи, с {d['open']} до {d['until']}. " if d.get("open")
        else f"Следующий сеанс связи в {d['next']}. " if d.get("next")
        else "Сеансов связи больше не запланировано. ")
    + f"Принято радиограмм: {d['received']}.",
    "radio.prewarn": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Нужна глубина "
    f"под антенну, {R.count(ANTENNA_DEPTH, R.METER)} или меньше.",
    "radio.prewarn_vlf": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}. Примем на "
    "сверхдлинных волнах на плавающую антенну." + (
        " Предлагаю " + " и ".join(w for w, on in (("подвсплыть", d.get("up")), ("сбавить ход", d.get("slow")))
                                   if on) + "." if d.get("what") else ""),
    "radio.window_open": lambda d: "Сеанс связи начался. Слушаем.",
    "radio.cable.out": lambda d: "Плавающая антенна выпущена, принимаем на сверхдлинных волнах.",
    "radio.cable.fast": lambda d: f"{R.CAPTAIN}, радист. На этом ходу антенну притапливает. "
    "Предлагаю сбавить ход.",
    "radio.garbled": lambda d: f"{R.CAPTAIN}, радист. Приём на сверхдлинных волнах искажён, "
    "ждём повтора." + (" Предлагаю " + " и ".join(
        w for w, on in (("подвсплыть", "depth" in d["why"]), ("сбавить ход", "speed" in d["why"])) if on)
        + "." if d.get("what") else ""),
    "radio.message": lambda d: f"{R.CAPTAIN}, радист. Радиограмма из Главного штаба"
    + (" на сверхдлинных волнах." if d.get("via") == "vlf" else "."),
    "radio.nothing": lambda d: "Сеанс связи: новых радиограмм для нас нет.",
    "radio.missed": lambda d: f"{R.CAPTAIN}, мы пропустили сеанс связи. " + (
        f"Штаб повторит радиограммы в {d['next']}." if d.get("next") else
        "Сеансов больше нет, радиограммы до нас не дойдут."),
    "radio.listen": lambda d: "Есть, слушаем Москву на коротких волнах.",
    "radio.listen.lost": lambda d: "Москву потеряли, антенна ушла под воду.",
    "radio.moscow": lambda d: d["ru"],
    "radio.moscow.silent": lambda d: f"{R.CAPTAIN}, радист. Только несущая. Москва молчит.",
    "radio.sending": lambda d: f"Есть, передаём {KIND_RU[d['kind']]} на коротких волнах, "
    f"{R.count(d['groups'], ('группа', 'группы', 'групп'))}, около {R.count(d['seconds'], R.SECOND)}. "
    f"Риск пеленгации {RISK_RU[d['risk']]}.",
    "radio.sent": lambda d: "Донесение передано, квитанция получена.",
    "radio.aborted": lambda d: "Передача прервана, антенна ушла под воду.",
    "radio.wait": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи в {d['clock']}, но "
    f"{R.contact(d['designation'])} в {R.dec(d['range'], R.MILE)}. Предлагаю ждать на глубине.",
    "radio.clear": lambda d: f"{R.CAPTAIN}, радист. {R.contact(d['designation']).capitalize()} теперь в "
    f"{R.dec(d['range'], R.MILE)}. Предлагаю подвсплыть.",
    "radio.suggest.task_report": lambda d: f"{R.CAPTAIN}, радист. Штаб ждёт курс и скорость "
    f"отряда. Есть решение: {R.contact(d['designation'])}. " + (
        f"Предлагаю передать сейчас, около {R.count(d['seconds'], R.SECOND)}. Риск пеленгации "
        f"{RISK_RU[d['risk']]}." if d["now"] else
        "Для передачи нужна перископная глубина. Предлагаю всплыть под перископ."),
    "radio.suggest.report": lambda d: f"{R.CAPTAIN}, радист. Сеанс связи идёт, штаб ждёт донесения. "
    + ((f"Полное донесение около {R.count(d['seconds'], R.SECOND)}, риск пеленгации "
        f"{RISK_RU[d['risk']]}. Предлагаю короткое донесение, около "
        f"{R.count(d['short_s'], R.SECOND)}." if d.get("short") else
        f"Предлагаю передать сейчас, около {R.count(d['seconds'], R.SECOND)}. Риск пеленгации "
        f"{RISK_RU[d['risk']]}.") if d["now"] else
       "Для передачи нужна перископная глубина. Предлагаю всплыть под перископ."),
}
phrases.register_ru(RU_PHRASES)
