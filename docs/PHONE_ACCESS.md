# Phone access

This page explains how a phone can open the planner, what works in each option, and what is still missing before the
planner works for every phone in every place.

## Summary

- As delivered, the planner runs on one Windows PC. Only that PC can open `http://127.0.0.1:8000/` by default.
- **Same Wi-Fi only:** `scripts\run_lan_windows.bat` lets phones on the same network open the planner over plain HTTP.
  Use it only on a network you trust.
- **Every phone, anywhere:** the planner must be served over HTTPS at a domain name. The Docker and Caddy kit in
  `docs/DEPLOY.md` is written for this. Its image has not been built, and nothing has been run.
- **Android app:** `android/flutter_app` is a starter. It has not been built, and it needs an HTTPS address.
- **Real phones:** nothing has been tested on a real phone. The dashboard was checked in headless Chrome with a Pixel 7
  device profile, which is emulation only.

## Option 1: phones on the same Wi-Fi (plain HTTP)

1. On the PC, open Command Prompt in the planner folder and run `scripts\run_lan_windows.bat`.
2. Read the warnings, then type `YES` and press Enter.
3. Find the PC's address. In Command Prompt, run `ipconfig` and note the IPv4 Address of the Wi-Fi adapter, for example
   `192.168.1.20`.
4. On the phone, connected to the same Wi-Fi, open `http://192.168.1.20:8000/` with that address.
5. If Windows asks whether to allow Python through the firewall, allow it on **private** networks only.
6. When you finish, press Ctrl+C in the command window.

**Expected to work:** timetables, route and stop search, direct journeys, scenarios and comparisons, the sources page and
the administration page. The browser checks ran on `localhost` only, so this option has not been tested over a network.

**What does not work over plain HTTP, and why:**

- **"Near me" stops.** Browsers do not provide the device's location on an insecure address. In that case the dashboard
  tells the user to search by stop name.
- **Installing the planner as an app, and offline use.** Browsers allow service workers and installation only over HTTPS
  or on `localhost`. Over plain HTTP the planner does not register its offline cache, and it cannot be installed.

**Security on this option:**

- Traffic is not encrypted. Other devices on the same network can read it, including the administrator key if you type it
  on the phone.
- The rate limit and the audit log see each phone by its own network address, but the administrator key is still exposed
  on the network.
- Do not use this option on public Wi-Fi, in a hotel, at a café or on a shared office network you do not control.

## Option 2: HTTPS hosting for every phone (kit written, not run)

Reaching every phone needs the planner to be reachable over HTTPS, from the internet or from a private network the phone
is on. The steps are:

1. **A server that runs the planner.** The Docker kit in `docs/DEPLOY.md` runs it in a container with Caddy in front.
   Python 3.13 is the only version tested. Without Docker, run the planner behind a reverse proxy on the same machine,
   with the command in `scripts\run_windows.bat`. If the proxy runs on another machine, the planner must listen on an
   address that machine can reach, and `FORWARDED_ALLOW_IPS` must name the proxy's address. Neither case has been tested.
2. **A domain name and an HTTPS certificate.** `deploy/Caddyfile` asks Caddy to obtain a certificate for your domain.
   That needs a public DNS record that points at the server, with ports 80 and 443 reachable from the internet. A hosting
   platform that provides HTTPS itself is an alternative.
3. **A strong `ADMIN_API_KEY`**, and, if you can, a rule at the proxy that allows `/api/admin/` only from your own
   addresses.
4. **Client addresses behind a proxy.** The planner's own code does not read `X-Forwarded-For`. The uvicorn server does,
   and it trusts that header only from the addresses in `FORWARDED_ALLOW_IPS`. The Docker kit sets this to Caddy's fixed
   address. Any other proxy needs the same setting, or every visitor appears to come from the proxy's address and shares
   one rate limit.
5. **Backups on a schedule**, and a copy kept off the server. The Docker kit has no built-in schedule. See
   `database/README.md`.

The Docker and Caddy files were written and the Compose file was checked, but the image was not built and nothing was run.
Treat this option as untested until you have run it yourself.

## Option 3: the Android app (starter only)

`android/flutter_app` opens the dashboard in a full-screen WebView. The address is set at build time with
`--dart-define=PLANNER_URL=https://...`. Recent Android versions block plain HTTP by default, so the address has to be
HTTPS. The starter has **not been built or compiled**, no APK is included, nothing is signed, and it has not run on a
phone. See `android/README.md` for the build steps and their limits.

## Other phones and browsers

The dashboard is plain HTML, CSS and JavaScript, with no build step, so a modern mobile browser can open it once it is
served over HTTPS. Browsers other than headless Chrome were **not tested**.

## What "every phone" still needs

| Requirement | Status |
|---|---|
| HTTPS hosting with a domain name | Docker and Caddy kit written (`docs/DEPLOY.md`). Not built or run. |
| Client addresses behind a proxy | The Docker kit sets `FORWARDED_ALLOW_IPS` to Caddy's address. Not run. |
| Testing on real phones (Android and iPhone), with at least two browsers each | Not done |
| An Android app built, signed and tested on a device | Not built |
| Official timetable data for 2027 to 2030 | Not available. The planner shows none until an administrator verifies an official source. See `SOURCES.md`. |
