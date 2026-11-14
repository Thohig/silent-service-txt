"""Starta ubåtssimulatorn:  uv run main.py [--seed N]"""
import argparse

from ui.app import SubApp


def main() -> None:
    p = argparse.ArgumentParser(description="K-114 – textbaserad ubåtssimulator, 1962")
    p.add_argument("--seed", type=int, default=None, help="slumpfrö för reproducerbart scenario")
    args = p.parse_args()
    SubApp(seed=args.seed).run()


if __name__ == "__main__":
    main()
