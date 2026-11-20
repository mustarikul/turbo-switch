#!/usr/bin/python3
"""Turbo Switch - disable Intel Turbo Boost now and/or at every boot."""
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

APP_ID = "io.github.turboswitch"
PSTATE = "/sys/devices/system/cpu/intel_pstate/no_turbo"   # 1 = turbo OFF
BOOST = "/sys/devices/system/cpu/cpufreq/boost"             # 0 = turbo OFF
UNIT = "disable-turbo-boost.service"
UNIT_PATH = f"/etc/systemd/system/{UNIT}"
ENFORCER = "/usr/local/libexec/turbo-switch-enforce"


def detect_backend():
    """Return (path, value_when_disabled, value_when_enabled) or None."""
    import os
    if os.path.exists(PSTATE):
        return PSTATE, "1", "0"
    if os.path.exists(BOOST):
        return BOOST, "0", "1"
    return None


BACKEND = detect_backend()


def read_turbo_disabled():
    if not BACKEND:
        return None
    try:
        with open(BACKEND[0]) as f:
            return f.read().strip() == BACKEND[1]
    except OSError:
        return None


def read_persist_enabled():
    # Old (v1) units lack the watchdog; report them as "off" so one toggle upgrades them.
    try:
        with open(UNIT_PATH) as f:
            if ENFORCER not in f.read():
                return False
        r = subprocess.run(["systemctl", "is-enabled", UNIT],
                           capture_output=True, text=True)
        return r.stdout.strip() == "enabled"
    except OSError:
        return False


def service_active():
    try:
        return subprocess.run(["systemctl", "is-active", "-q", UNIT]).returncode == 0
    except OSError:
        return False


def cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "Unknown CPU"


def run_root(script):
    """Run a shell snippet as root via polkit. Returns (ok, message)."""
    try:
        r = subprocess.run(["pkexec", "/bin/sh", "-c", script],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False, "pkexec (polkit) not found"
    if r.returncode == 0:
        return True, ""
    if r.returncode in (126, 127):
        return False, "Authentication cancelled"
    return False, (r.stderr.strip() or f"Failed (exit {r.returncode})")


def script_persist(enable):
    path, off, on = BACKEND
    if not enable:
        return (f"systemctl disable --now {UNIT} 2>/dev/null; "
                f"rm -f {UNIT_PATH} {ENFORCER}; systemctl daemon-reload; "
                f"echo {on} > {path}")
    return f"""set -e
mkdir -p /usr/local/libexec
cat > {ENFORCER} <<'SCRIPT'
#!/bin/sh
# Keeps CPU turbo boost disabled: retries early at boot and re-applies the
# value whenever something (firmware, power daemon, resume...) flips it back.
F={path}
V={off}
logger -t turbo-switch "enforcing $F=$V"
while true; do
  cur=$(cat "$F" 2>/dev/null)
  if [ "$cur" != "$V" ]; then
    if echo "$V" > "$F" 2>/dev/null; then
      logger -t turbo-switch "value was '$cur', re-applied $V"
    fi
  fi
  sleep 3
done
SCRIPT
chmod 755 {ENFORCER}
cat > {UNIT_PATH} <<'UNITEOF'
[Unit]
Description=Keep CPU Turbo Boost disabled
After=tlp.service power-profiles-daemon.service thermald.service

[Service]
Type=simple
ExecStart={ENFORCER}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNITEOF
chmod 644 {UNIT_PATH}
if command -v restorecon >/dev/null 2>&1; then restorecon -RF /usr/local/libexec {UNIT_PATH} || true; fi
systemctl daemon-reload
systemctl enable --now {UNIT}
"""


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Turbo Switch",
                         default_width=460, default_height=440)
        self.busy = False
        self.updating = False

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        page = Adw.PreferencesPage()
        view.set_content(page)

        status = Adw.PreferencesGroup(title="Status")
        page.add(status)
        self.cpu_row = Adw.ActionRow(title="Processor", subtitle=cpu_model())
        status.add(self.cpu_row)
        self.state_row = Adw.ActionRow(title="Turbo Boost")
        self.state_label = Gtk.Label(css_classes=["heading"])
        self.state_row.add_suffix(self.state_label)
        status.add(self.state_row)

        ctl = Adw.PreferencesGroup(
            description="Changes need administrator authentication.")
        page.add(ctl)
        self.sw = Adw.SwitchRow(
            title="Disable Turbo Boost permanently",
            subtitle="Applies now and on every boot, until you switch it off")
        self.sw.connect("notify::active", self.on_switch)
        ctl.add(self.sw)

        self.refresh()
        GLib.timeout_add_seconds(3, self.tick)

    def tick(self):
        if not self.busy:
            self.refresh()
        return True

    def describe(self, turbo_off, rule, active):
        """Return (label, explanation, is_problem)."""
        if turbo_off and rule and active:
            return "Disabled", "Permanent: re-applied at every boot", False
        if turbo_off and rule:
            return "Disabled", "Permanent rule installed (watchdog not running yet)", False
        if turbo_off:
            return ("Disabled (temporary)",
                    "Resets on reboot. Turn the switch on to keep it.", False)
        if rule:
            return ("Enabled",
                    "The permanent rule is set but not working. "
                    "Switch off, then on again to repair it.", True)
        return "Enabled", "Default CPU behaviour", False

    def refresh(self):
        self.updating = True
        if BACKEND is None:
            self.state_label.set_text("Unsupported")
            self.state_row.set_subtitle("No Intel pstate / boost control found")
            self.sw.set_sensitive(False)
        else:
            turbo_off = read_turbo_disabled()
            rule = read_persist_enabled()
            label, why, bad = self.describe(turbo_off, rule, service_active())
            self.state_label.set_text(label)
            self.state_label.remove_css_class("error")
            if bad:
                self.state_label.add_css_class("error")
            self.state_row.set_subtitle(why)
            self.sw.set_active(rule)
            self.sw.set_sensitive(not self.busy)
        self.updating = False

    def toast(self, msg):
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=3))

    def on_switch(self, sw, _p):
        if self.updating or self.busy:
            return
        want = sw.get_active()
        self.busy = True
        sw.set_sensitive(False)

        def work():
            ok, msg = run_root(script_persist(want))
            GLib.idle_add(done, ok, msg)

        def done(ok, msg):
            self.busy = False
            self.toast(("Turbo Boost disabled permanently" if want
                        else "Turbo Boost restored to default") if ok else msg)
            self.refresh()
            return False

        threading.Thread(target=work, daemon=True).start()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


if __name__ == "__main__":
    App().run(None)
