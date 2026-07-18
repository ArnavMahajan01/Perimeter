#!/usr/bin/env python3
"""Perimeter CLI.

  python cli.py app                        # THE desktop app (setup + config + run)

Power-user / headless commands:
  python cli.py devices                    # list input devices
  python cli.py listen                     # raw RMS/crest meter, no classification
  python cli.py calibrate --zone lr -n 10  # collect samples for a zone
  python cli.py calibrate --negative -n 20 # collect the negative class
  python cli.py train                      # train with quality gates, save model
  python cli.py run                        # headless daemon (no window)
  python cli.py test                       # daemon with dispatch disabled
"""

import argparse
import sys


def cmd_devices(_args):
    from perimeter.capture import list_devices
    for idx, name, ch, sr in list_devices():
        print(f"[{idx}] {name}  ({ch} ch, {sr:.0f} Hz)")


def cmd_listen(_args):
    import queue

    from perimeter import config as config_mod
    from perimeter.capture import Capture
    from perimeter.onset import OnsetDetector

    cfg = config_mod.load()
    cap = Capture(device=cfg.get("device"))
    det = OnsetDetector(
        trigger_mult=cfg["onset"]["trigger_mult"],
        abs_floor=cfg["onset"]["abs_floor"],
        crest_min=cfg["onset"]["crest_min"],
        refractory_s=cfg["onset"]["refractory_s"],
    )
    cap.start()
    print("Live meter — tap the desk. Ctrl-C to stop.")
    try:
        while True:
            try:
                start_frame, block = cap.blocks.get(timeout=2.0)
            except queue.Empty:
                continue
            onset = det.process(block, start_frame)
            bar = "#" * min(60, int(det.last_rms * 2000))
            flag = "  <-- ONSET" if onset is not None else ""
            print(f"rms={det.last_rms:.5f} crest={det.last_crest:5.1f} "
                  f"floor={det.noise_floor:.5f} |{bar:<60}|{flag}")
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()


def cmd_calibrate(args):
    from perimeter import calibrate
    from perimeter import config as config_mod

    cfg = config_mod.load()
    profile = cfg.get("profile", "default")
    if args.negative:
        calibrate.collect(calibrate.NEGATIVE_ZONE, args.n or 20,
                          device=cfg.get("device"), profile=profile)
        return
    if not args.zone:
        sys.exit("Specify --zone <id> (lr, rr, lf, rf) or --negative")
    valid = {z["id"] for z in cfg["zones"]}
    if args.zone not in valid:
        sys.exit(f"Unknown zone '{args.zone}'. Valid: {', '.join(sorted(valid))}")
    calibrate.collect(args.zone, args.n or 30, device=cfg.get("device"), profile=profile)


def cmd_train(_args):
    from perimeter import config as config_mod
    from perimeter import model
    result = model.train(config_mod.load().get("profile", "default"))
    sys.exit(0 if result["ok"] else 1)


def cmd_app(_args):
    try:
        from perimeter.webui import main as app_main
    except ImportError:
        print("pywebview not installed — falling back to the basic Tk interface")
        from perimeter.app_tk import main as app_main
    app_main()


def cmd_run(_args):
    from perimeter import daemon
    daemon.run(dispatch_enabled=True)


def cmd_test(_args):
    from perimeter import daemon
    daemon.run(dispatch_enabled=False)


def main():
    p = argparse.ArgumentParser(prog="perimeter")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("app", help="desktop app (setup + config + run)")
    sub.add_parser("devices", help="list audio input devices")
    sub.add_parser("listen", help="raw RMS/crest meter")

    c = sub.add_parser("calibrate", help="collect training samples")
    c.add_argument("--zone", help="zone id (lr, rr, lf, rf)")
    c.add_argument("--negative", action="store_true", help="collect the negative class")
    c.add_argument("-n", type=int, default=None, help="number of samples")

    sub.add_parser("train", help="train and save the classifier")
    sub.add_parser("run", help="start the daemon")
    sub.add_parser("test", help="daemon with dispatch disabled")

    args = p.parse_args()
    {
        "app": cmd_app,
        "devices": cmd_devices,
        "listen": cmd_listen,
        "calibrate": cmd_calibrate,
        "train": cmd_train,
        "run": cmd_run,
        "test": cmd_test,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
