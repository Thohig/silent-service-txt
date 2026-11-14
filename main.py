"""Starta ubåtssimulatorn:  uv run main.py [--seed N] [--scenario NAMN] [--tyst]"""
import argparse

from sim.scenario import SCENARIOS
from ui.app import SubApp


def main() -> None:
    p = argparse.ArgumentParser(description="K-114 – textbaserad ubåtssimulator, 1962")
    p.add_argument("--seed", type=int, default=None, help="slumpfrö för reproducerbart scenario")
    p.add_argument("--scenario", choices=list(SCENARIOS), default=None,
                   help="hoppa över scenarioväljaren: " + ", ".join(SCENARIOS))
    p.add_argument("--tyst", action="store_true", help="inget ljud (tal och larm)")
    args = p.parse_args()
    SubApp(seed=args.seed, scenario=args.scenario, sound=not args.tyst).run()


if __name__ == "__main__":
    main()
