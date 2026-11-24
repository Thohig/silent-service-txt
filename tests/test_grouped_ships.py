"""Fartyg som går i grupp räknas som sicksackande innan plottet vet att det är en konvoj (2026-11-24: konvoj,
24 frön, goda lösningar grovt fel 28 % ⇒ 21 %)."""
from sim.knowledge import ContactTrack, Knowledge
from sim.tma import BearingObs


def _track(k, des, bearing, t=100, classification="Okänd kontakt"):
    tr = ContactTrack(des, 0, classification=classification)
    tr.observations.append(BearingObs(t, bearing, 1.0, 0.0, 0.0, 0.0))
    k.tracks[des] = tr
    return tr


def _k():
    return Knowledge()


def test_three_ships_in_one_sector_are_a_group():
    k = _k()
    a = _track(k, "S-1", 100.0)
    _track(k, "S-2", 110.0)
    assert not k.grouped(a, 120)
    _track(k, "S-3", 118.0)
    assert k.grouped(a, 120)


def test_spread_old_or_known_convoy_is_no_group():
    k = _k()
    a = _track(k, "S-1", 100.0)
    _track(k, "S-2", 160.0)
    _track(k, "S-3", 110.0, t=-1000)                 # hörd för länge sedan
    assert not k.grouped(a, 120)
    k = _k()
    a = _track(k, "S-1", 100.0)
    _track(k, "S-2", 105.0)
    _track(k, "S-3", 110.0)
    k.convoy = object()                               # känd konvoj: medlemskapet avgör
    assert not k.grouped(a, 120)
