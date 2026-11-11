#!/bin/sh
# Brings the network back when a Raspberry Pi's onboard Wi-Fi (brcmfmac) stops answering.
#
# The chip can hang with firmware timeouts (dmesg: "brcmf_... -110") while Linux keeps running, so the
# hardware watchdog never fires and the collector silently misses readings until someone power-cycles it.
# Run every 2 minutes by wifi-watchdog.timer:
#   3 failed checks in a row (about 6 minutes)  -> reload the Wi-Fi driver
#   6 failed checks in a row (about 12 minutes) -> reboot, at most once an hour (a router outage must not
#                                                  turn into a reboot loop)
set -u
STATE=/var/lib/wifi-watchdog
mkdir -p "$STATE"

online() {
    gateway=$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')
    if [ -n "$gateway" ] && ping -c 3 -W 3 "$gateway" >/dev/null 2>&1; then return 0; fi
    ping -c 2 -W 3 1.1.1.1 >/dev/null 2>&1
}

if online; then
    if [ -s "$STATE/fails" ]; then logger -t wifi-watchdog "network back"; fi
    rm -f "$STATE/fails"
    exit 0
fi

fails=$(( $(cat "$STATE/fails" 2>/dev/null || echo 0) + 1 ))
echo "$fails" > "$STATE/fails"
logger -t wifi-watchdog "no network (check $fails)"

case "$fails" in
    3)
        logger -t wifi-watchdog "reloading the Wi-Fi driver"
        for module in brcmfmac_cyw brcmfmac_wcc brcmfmac; do modprobe -r "$module" 2>/dev/null; done
        sleep 3
        modprobe brcmfmac
        ;;
    6)
        now=$(date +%s)
        last=$(cat "$STATE/last-reboot" 2>/dev/null || echo 0)
        if [ $(( now - last )) -ge 3600 ]; then
            echo "$now" > "$STATE/last-reboot"
            logger -t wifi-watchdog "still offline after the driver reload; rebooting"
            systemctl reboot
        else
            logger -t wifi-watchdog "rebooted less than an hour ago; trying the driver again instead"
            echo 2 > "$STATE/fails"
        fi
        ;;
esac
