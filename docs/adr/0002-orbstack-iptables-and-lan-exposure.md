# 0002: Accept the OrbStack iptables default, and block LAN exposure

- Status: accepted
- Date: 2026-10-31

## Context

The owner runs Docker through OrbStack on macOS for local development. Every
Docker command prints `WARNING: DOCKER_INSECURE_NO_IPTABLES_RAW is set`.
The setting is not in the OrbStack configuration (`orbctl config show`), nor
in the shell or profile files, so it is set internally by OrbStack.

OrbStack's configuration also had `docker.expose_ports_to_lan: true` and
`machines.expose_ports_to_lan: true`, which make container ports reachable
from other devices on the local network.

## Options considered

1. Remove the variable. Not possible from our side: it is not user-configurable.
2. Accept the warning and reduce exposure elsewhere. Chosen.
3. Stop using OrbStack and switch to Docker Desktop. Not needed: the warning
   does not block any project work.

## Decision

- Accept the OrbStack iptables default for local development. The bot makes
  only outgoing calls (Telegram polling, Claude API, Google APIs) and needs no
  inbound ports.
- Set `docker.expose_ports_to_lan` and `machines.expose_ports_to_lan` to `false`:

  ```bash
  orbctl config set docker.expose_ports_to_lan false
  orbctl config set machines.expose_ports_to_lan false
  ```

## Consequences

- Containers on the laptop cannot be reached from other devices on the network.
  The bot does not need this.
- Container isolation is weaker than with the default rules, which is a
  known and accepted risk for local development on a personal laptop.
- Revisit before Week 15, when the bot moves to the Oracle Always Free VM.
  That host is not an OrbStack machine, so this decision does not apply there,
  but the server's firewall and Docker settings must be reviewed separately.
