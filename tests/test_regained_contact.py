"""En kontakt som tappats och återfunnits har ingen gammal lösning kvar."""
from sim.events import ContactDetected, ContactLost, EventBus
from sim.knowledge import Knowledge
from sim.reports import Quality


def test_a_regained_contact_drops_the_old_solution():
    bus = EventBus()
    k = Knowledge()
    k.attach(bus)
    bus.publish(ContactDetected(0, "S-1", 10.0, "jagare", Quality.GOD))
    tr = k.track("S-1")
    tr.solution = object()                      # vad som helst: plottets lösning från förr
    bus.publish(ContactDetected(30, "S-1", 10.0, "jagare", Quality.GOD))
    assert tr.solution is not None              # fortfarande hållen: lösningen står kvar
    bus.publish(ContactLost(60, "S-1"))
    assert tr.solution is not None              # tappad: plottet visar den inte, men den finns
    bus.publish(ContactDetected(3600, "S-1", 40.0, "jagare", Quality.GOD))
    assert tr.held and tr.solution is None
