# Phone access

This page explains how a phone can open the planner, what works in each option, and what is still missing before the
planner works for every phone in every place.

## Summary

- As delivered, the planner runs on one Windows PC. Only that PC can open `http://127.0.0.1:8000/` by default.
- **Same Wi-Fi only:** `scripts\run_lan_windows.bat` lets phones on the same network open the planner. It uses plain HTTP,
  so use it only on a network you trust.
- **Every phone, anywhere:** the planner has to be hosted on a server behind HTTPS, with a domain name. **That hosting has
  not been built or tested.** No server, domain or certificate was set up.
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

**What works:** timetables, route and stop search, direct journeys, scenarios and comparisons, the sources page and the
administration page.

**What does not work over plain HTTP, and why:**

- **"Near me" stops.** Browsers do not provide the device's location on an insecure address. In that case the dashboard
  tells the user to search by stop name.
- **Offline use and home-screen installation.** Browsers register service workers, and allow installation, only over
  HTTPS or on `localhost`. The planner simply does not register its offline cache there.

**Security on this option:**

- Traffic is not encrypted. Other devices on the same network can read it, including the administrator key if you type it
  on the phone.
- The rate limit and the audit log see each phone by its own network address, but the administrator key is still exposed
  on the network.
- Do not use this option on public Wi-Fi, in a hotel, at a café or on a shared office network you do not control.

## Option 2: HTTPS hosting, needed for every phone (not built)

Reaching every phone needs the planner to be reachable over HTTPS from the internet or from a private network the
phone is on. To build that, you would need:

1. **A server** that runs the planner with Python 3.11 or newer, using the same command as `scripts\run_windows.bat`:
   `python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000`.
2. **A domain name and an HTTPS certificate**, usually from a reverse proxy that handles HTTPS in front of the planner
   (Caddy and nginx both do this), or from a hosting platform that provides HTTPS itself.
3. **A strong `ADMIN_API_KEY`**, and, if you can, a rule at the proxy that allows `/api/admin/` only from your own
   addresses.
4. **A change to the rate limiter before a busy public deployment.** The planner does not read the `X-Forwarded-For`
   header. Behind a proxy, every visitor appears to come from the proxy's address, so they would share one rate limit,
   and the audit log would record the proxy's address rather than the visitor's.
5. **Backups on a schedule**, and a copy kept off the server. See `database/README.md`.

None of these steps was carried out in this build. Treat the HTTPS option as a plan, not as a tested deployment.

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
| HTTPS hosting with a domain name | Not built |
| Rate limiting that works behind a proxy | Not built |
| Testing on real phones (Android and iPhone), with at least two browsers each | Not done |
| An Android app built, signed and tested on a device | Not built |
| Official timetable data for 2027 to 2030 | Not available. The planner shows none until an administrator verifies an official source. See `SOURCES.md`. |
