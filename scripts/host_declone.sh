#!/usr/bin/env bash
#
# Give a cloned host an identity of its own.
#
# Usage: sudo host_declone.sh [--show | --confirm]
#
#   --show      Report what is shared and change nothing (the default)
#   --confirm   Change it, then ask for a reboot
#
# A host copied from another host's storage carries that host's identity.
# Four things are per-host, and a copy keeps all four:
#
#   /etc/machine-id                      systemd and D-Bus identity, and
#                                        what NetworkManager derives the
#                                        stable IPv6 interface identifier
#                                        from
#   /etc/ssh/ssh_host_*                  how this host proves who it is
#   /var/lib/NetworkManager/secret_key   the other half of that IPv6
#                                        identifier
#   /var/lib/dbus/machine-id             usually a symlink to the first
#
# Two hosts that share them cannot both be on one network: they take the
# same IPv6 address, mDNS conflicts, and the names trade places.  Sharing
# the SSH host keys is worse than inconvenient: every copy answers as the
# same host, so "known_hosts" cannot tell them apart and a substituted
# host raises no warning.
#
# Changing the hostname and the access point SSID does NOT do this.  Those
# are what an operator sees; these are what the network sees.
#
# Run this BEFORE the host first meets a network that a sibling is on.
#
# It does not change the hostname: that is a decision, not a reset, and
# "hostnamectl set-hostname" is the one command for it.

set -u

MACHINE_ID=/etc/machine-id
DBUS_ID=/var/lib/dbus/machine-id
SECRET_KEY=/var/lib/NetworkManager/secret_key

mode="--show"
if [ $# -gt 0 ]; then
    mode=$1
fi
if [ "$mode" != "--show" ] && [ "$mode" != "--confirm" ]; then
    echo "Usage: $0 [--show | --confirm]" >&2
    exit 2
fi

report() {
    echo "machine-id  $(cat $MACHINE_ID 2>/dev/null || echo 'absent')"
    for key in /etc/ssh/ssh_host_*_key.pub; do
        [ -e "$key" ] || continue
        echo "host key    $(ssh-keygen -lf "$key" 2>/dev/null)"
    done
    # Root owns it, so an unprivileged --show must not report "absent"
    # for a file it simply cannot see
    if [ -r "$SECRET_KEY" ]; then
        echo "secret key  $(stat -c '%y' "$SECRET_KEY" | cut -d. -f1)" \
             "($(stat -c '%s' "$SECRET_KEY") bytes)"
    elif [ "$(id -u)" -ne 0 ]; then
        echo "secret key  not readable without root"
    else
        echo "secret key  absent, which NetworkManager writes again"
    fi
    echo "dbus id     $(readlink -f $DBUS_ID 2>/dev/null || echo 'absent')"
}

echo "== identity now"
report

if [ "$mode" = "--show" ]; then
    echo
    echo "Nothing was changed.  Run with --confirm to give this host an"
    echo "identity of its own.  Record the values above first: they are"
    echo "what another host must NOT also have."
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This needs root: it writes /etc and /var/lib" >&2
    exit 1
fi

echo
echo "== changing"

# The machine identity.  Truncating and re-running the setup is the
# documented way: systemd writes a new one, and D-Bus follows the symlink
: > "$MACHINE_ID"
rm -f "$DBUS_ID"
systemd-machine-id-setup
ln -sf "$MACHINE_ID" "$DBUS_ID"
echo "machine-id  written"

# The host keys.  Removing them and reconfiguring is what the package
# does on a first install, so the key types follow the distribution
rm -f /etc/ssh/ssh_host_*
DEBIAN_FRONTEND=noninteractive dpkg-reconfigure openssh-server >/dev/null 2>&1
echo "host keys   written"

# NetworkManager writes this again at its next start
rm -f "$SECRET_KEY"
echo "secret key  removed, and written again at the next start"

echo
echo "== identity after"
report

cat <<'EOF'

Reboot now.  Until the reboot, NetworkManager still holds the old secret
key in memory and sshd still serves the old host keys.

Afterwards, on every computer that has reached this host before:

    ssh-keygen -R <hostname>        # and for its address, and its .local

The next connection then asks about the new key, which is the point: it
could not ask while every copy shared one.
EOF
