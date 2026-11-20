# Turbo Switch

A tiny GTK4 / libadwaita app (shipped as an AppImage) that **permanently disables
Intel Turbo Boost** on Linux, with one switch and a clear status display.
Built and tested for Fedora Workstation (GNOME).

## Features
- One switch: *Disable Turbo Boost permanently* (applies now **and** on every boot)
- Clear status: Enabled / Disabled (temporary) / Disabled (permanent) / rule not working
- Self-healing: a small watchdog service retries early in boot and re-applies the
  setting if firmware, a power daemon or resume from sleep resets it
- Uses polkit (`pkexec`) for authentication; the GUI itself never runs as root
- Supports `intel_pstate/no_turbo` and falls back to `cpufreq/boost`

## Requirements
Fedora Workstation (or any distro) with `python3`, `python3-gobject`, GTK 4,
libadwaita and polkit. All are installed by default on Fedora Workstation.

## Usage
Download `TurboSwitch-x86_64.AppImage` from the [Releases](../../releases) page:

```bash
chmod +x TurboSwitch-x86_64.AppImage
./TurboSwitch-x86_64.AppImage
```
If you get a FUSE error: `./TurboSwitch-x86_64.AppImage --appimage-extract-and-run`

## What it installs
Turning the switch **on** creates (as root, after authentication):
- `/usr/local/libexec/turbo-switch-enforce`: the watchdog script
- `/etc/systemd/system/disable-turbo-boost.service`: enabled and started

Turning it **off**, or removing manually, deletes both and restores turbo:
```bash
sudo systemctl disable --now disable-turbo-boost.service
sudo rm /etc/systemd/system/disable-turbo-boost.service /usr/local/libexec/turbo-switch-enforce
sudo systemctl daemon-reload
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
```

## Troubleshooting
```bash
cat /sys/devices/system/cpu/intel_pstate/no_turbo      # 1 = turbo disabled
systemctl status disable-turbo-boost.service
journalctl -t turbo-switch -b                          # shows every re-apply
```

## Build from source
```bash
./build.sh        # produces TurboSwitch-x86_64.AppImage
```
Pushing a tag like `v1.0.0` builds the AppImage on GitHub Actions and attaches it
to a release automatically.

## Note
Disabling turbo caps the CPU at its base clock: cooler and quieter, but slower
under load. Use at your own risk.

## License
MIT
