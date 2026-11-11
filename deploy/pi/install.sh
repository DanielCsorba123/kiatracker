#!/bin/sh
# Pi hardening for an always-on collector. Run once on the Pi: sudo sh deploy/pi/install.sh
set -eu
cd "$(dirname "$0")"
install -m 0755 wifi-watchdog.sh /usr/local/sbin/wifi-watchdog
install -m 0644 wifi-watchdog.service wifi-watchdog.timer /etc/systemd/system/
install -d /etc/systemd/journald.conf.d
install -m 0644 journald-persistent.conf /etc/systemd/journald.conf.d/zz-persistent.conf
systemctl daemon-reload
systemctl enable --now wifi-watchdog.timer
systemctl restart systemd-journald
journalctl --flush
echo "Installed: Wi-Fi watchdog (every 2 min) and a persistent system log."
