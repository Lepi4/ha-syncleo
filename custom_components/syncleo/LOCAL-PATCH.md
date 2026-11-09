# Local handshake recovery fix

Base: ha-syncleo 0.7.0, with pysyncleo==0.4.1.

`transport.py` is adapted from pysyncleo 0.4.1 under its MIT license
(see PYSYNCLEO-LICENSE.txt). Integration setup and type definitions use this
transport so the fix persists across Home Assistant container updates.

An ACK only confirms delivery. It must not leave CONNECTING waiting forever
when the full handshake reply is lost. A separate 10 second deadline changes
the state to DISCONNECTED, which triggers the existing entity reconnect
scheduler with its 5 to 300 second backoff. New attempts clear stale pending
packets and recreate the encryption state. Explicit disconnect clears pending
session state.

The previous climate and water-heater target-temperature fixes are included
in upstream 0.7.0. This fork does not duplicate them.

Run the offline regressions with Python 3.14.2 or later:

    python -m unittest discover -s tests -v

Tests use a fake UDP transport and synthetic keys. They contact no devices.
A real device power-loss recovery test has not been performed.
