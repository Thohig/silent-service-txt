"""Bakgrundsljud: styrs av statusraden och kunskapen, mixas mjukt och sömlöst."""
import random
from dataclasses import replace

import numpy as np

from sim.game import Game, StatusSnapshot
from sim.knowledge import ContactTrack
from sim.scenario import build_scenario
from sim.tma import BearingObs
from ui.ambience import (BLOCK, MAX_CONTACTS, RATE, Ambience, Target, ambient_targets,
                         contact_sample, synth_ambience)
from ui.audio import NullPlayer, SoundBoard
from sim.events import EventBus


def _st(**kw):
    base = StatusSnapshot(clock=0, sim_time=0, course=0.0, ordered_course=0.0, speed=5.0,
                          ordered_speed=5.0, depth=100.0, ordered_depth=100.0,
                          changing=frozenset(), time_scale=1, contacts_held=())
    return replace(base, **kw)


def _track(desig, classification, bearing, se, held=True):
    tr = ContactTrack(desig, 0, classification=classification, held=held)
    tr.observations.append(BearingObs(0, bearing, 1.0, 0.0, 0.0, 0.0, se=se))
    return tr


# --- steg 3: egen båt --------------------------------------------------------------
def test_reactor_hums_whenever_it_runs():
    assert "reactor" in ambient_targets(_st())
    assert "reactor" not in ambient_targets(_st(reactor="scram"))


def test_turbine_grows_with_speed_and_creeping_motor_is_quieter():
    slow = ambient_targets(_st(speed=5))["turbine"]
    fast = ambient_targets(_st(speed=20))["turbine"]
    assert fast.gain > slow.gain and fast.rate > slow.rate
    quiet = ambient_targets(_st(speed=5, propulsion="electric"))
    assert "turbine" not in quiet and quiet["electric"].gain < slow.gain
    assert sum(t.gain for t in quiet.values()) < sum(t.gain for t in ambient_targets(_st(speed=5)).values())


def test_hull_creaks_on_depth_change_and_groans_near_test_depth():
    assert "creak" not in ambient_targets(_st(depth=100))
    assert "creak" in ambient_targets(_st(depth=100, changing=frozenset({"depth"})))
    deep = ambient_targets(_st(depth=300, changing=frozenset({"depth"})))
    assert deep["creak"].gain > ambient_targets(_st(depth=100, changing=frozenset({"depth"})))["creak"].gain
    assert "groan" in deep and "groan" not in ambient_targets(_st(depth=200))


def test_cavitation_flooding_and_surface():
    assert "cavitation" in ambient_targets(_st(speed=20, cavitating=True))
    assert "flooding" in ambient_targets(_st(flooding=0.1, leak_rate=0.5))     # läckan sprutar
    assert "drip" in ambient_targets(_st(flooding=0.5))                       # vatten utan läcka droppar
    surf = ambient_targets(_st(depth=0.0))
    assert "waves" in surf and "ice" not in ambient_targets(_st(depth=0.0, under_ice=True))


# --- steg 4: is, brand, kontakter --------------------------------------------------
def test_ice_noise_follows_what_sonar_hears():
    calm = ambient_targets(_st(under_ice=True, sea_noise=50))["ice"]
    loud = ambient_targets(_st(under_ice=True, sea_noise=72))["ice"]
    assert loud.gain > calm.gain
    assert "ice" not in ambient_targets(_st(sea_noise=72))


def test_fire_and_ventilation():
    fire = ambient_targets(_st(fire=True, smoke=0.2))
    assert "fire" in fire and "fans" in fire
    smoke = ambient_targets(_st(smoke=0.5))
    assert "fire" not in smoke and "fans" in smoke
    assert "vent" in ambient_targets(_st(ventilating=True))


def test_contact_sound_follows_classification():
    assert contact_sample("okänd kontakt") == "screws_unknown"
    assert contact_sample("ytfartyg, tvåskruv, trolig jagare") == "screws_warship"
    assert contact_sample("handelsfartyg, diesel, en axel") == "screws_merchant"
    assert contact_sample("dieselgenerator, drivstation på isen") == "generator"
    assert contact_sample("trolig isskruvning") is None


def test_held_contacts_are_panned_and_only_the_loudest_heard():
    tracks = [_track(f"S-{i}", "handelsfartyg, diesel, en axel", 270.0, se=float(i))
              for i in range(1, 6)]
    tracks.append(_track("S-9", "jagare, ångturbiner, två axlar", 90.0, se=50.0))
    tracks.append(_track("S-8", "jagare", 90.0, se=80.0, held=False))
    t = ambient_targets(_st(course=0.0), tracks)
    heard = {k: v for k, v in t.items() if k.startswith("contact:")}
    assert len(heard) == MAX_CONTACTS
    assert "contact:S-9" in heard and "contact:S-8" not in heard
    assert heard["contact:S-9"].pan > 0.99 and heard["contact:S-5"].pan < -0.99
    assert heard["contact:S-9"].gain > heard["contact:S-4"].gain


# --- mixern -----------------------------------------------------------------------
def test_loops_are_seamless_and_finite():
    for name, s in synth_ambience().items():
        assert np.isfinite(s).all(), name
        jump = abs(s[0] - s[-1])
        typical = np.mean(np.abs(np.diff(s)))
        assert jump < 12 * typical + 0.05, name


def test_mixer_fades_layers_in_and_out_and_pans():
    a = Ambience({"x": np.ones(RATE)}, volume=1.0)
    a.set_targets({"x": Target("x", 0.5, pan=-1.0)})
    for _ in range(40):
        out = a.render(BLOCK)
    assert out[-1, 0] > 0.3 and abs(out[-1, 1]) < 1e-6
    a.set_targets({})
    for _ in range(150):                            # ~7 s: tonar ut, sedan bort
        out = a.render(BLOCK)
    assert np.max(np.abs(out)) < 0.01 and "x" not in a.layers


def test_muted_mixer_goes_silent():
    a = Ambience({"x": np.ones(RATE)}, volume=1.0)
    a.set_targets({"x": Target("x", 0.5)})
    for _ in range(20):
        a.render(BLOCK)
    a.enabled = False
    for _ in range(40):
        out = a.render(BLOCK)
    assert np.max(np.abs(out)) < 0.01


def test_soundboard_feeds_ambience_from_a_real_game():
    g = Game(build_scenario("arktis", random.Random(3)), seed=3)
    amb = Ambience({}, volume=1.0)
    board = SoundBoard(EventBus(), NullPlayer(), ambience=amb)
    for _ in range(30):
        g.tick()
    st = g.status()
    assert st.under_ice and st.sea_noise > 40
    board.ambient(st, g.knowledge.tracks.values())
    assert {"reactor", "ice"} <= set(amb._targets)
    board.toggle()
    assert not amb.enabled
    board.ambient(replace(st, over=True))
    assert amb._targets == {}


# --- centralen: luften, besättningen, hotet --------------------------------------------
def test_crew_murmurs_until_we_go_quiet_and_the_air_always_runs():
    normal = ambient_targets(_st())
    assert "crew" in normal and "aircon" in normal and "dread" not in normal
    creeping = ambient_targets(_st(propulsion="electric"))
    assert "crew" not in creeping and creeping["aircon"].gain < normal["aircon"].gain
    assert "crew" not in ambient_targets(_st(hunted=True))
    assert "aircon" not in ambient_targets(_st(reactor="scram"))


def test_menace_when_hunted_or_a_warship_is_loud_in_the_sonar():
    hunted = ambient_targets(_st(hunted=True))["dread"]
    dd = _track("S-1", "jagare, ångturbiner, två axlar", 90, se=20)
    from sim.reports import Quality
    dd.class_quality = Quality.GOD
    near = ambient_targets(_st(), [dd])["dread"]
    assert hunted.gain > near.gain > 0
    dd.observations[-1] = BearingObs(0, 90, 1.0, 0.0, 0.0, 0.0, se=3)
    assert "dread" not in ambient_targets(_st(), [dd])                # svag: inget hot än


def test_contact_sound_follows_a_new_classification():
    """Kontakten klassas om (okänd ⇒ jagare): ljudet byts, det gamla tonar ut."""
    amb = Ambience(samples={"screws_unknown": np.full(100, 0.1),
                            "screws_warship": np.full(100, -0.1)})
    amb.set_targets({"contact:S-1": Target("screws_unknown", 0.5)})
    for _ in range(20):
        amb.render(1024)
    amb.set_targets({"contact:S-1": Target("screws_warship", 0.5)})
    amb.render(1024)
    assert amb.layers["contact:S-1"].sample == "screws_warship"
    assert any(lay.sample == "screws_unknown" for lay in amb.layers.values())   # tonar ut
    for _ in range(100):
        amb.render(1024)
    assert [lay.sample for lay in amb.layers.values()] == ["screws_warship"]


def test_the_boat_sounds_like_its_damage_control():
    """Läckan sprutar, vattnet i kölsvinet droppar, pumparna dunkar, reparationen slår eller filar tyst,
    och i tystnad står fläktarna."""
    t = ambient_targets(_st(leak_rate=1.0, flooding=4.0))
    assert "flooding" in t and "drip" not in t
    t = ambient_targets(_st(leak_rate=0.0, flooding=4.0, pumps="bilge", repairing="loud"))
    assert {"drip", "pumps", "repair"} <= set(t)
    t = ambient_targets(_st(repairing="quiet", hushed=True))
    assert t["repair"].sample == "repair_quiet" and "aircon" not in t
    assert "aircon" in ambient_targets(_st())
