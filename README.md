# Host setup: PipeWire audio for the lva voice assistant

The `lva` container captures the microphone through a PulseAudio socket on the host. On a headless Debian/Ubuntu host, this means installing PipeWire as the audio stack and keeping the user session alive without a logged-in login.

## Install PipeWire

```sh
sudo apt update && sudo apt install -y pipewire wireplumber pipewire-audio-client-libraries libspa-0.2-bluetooth pipewire-audio pipewire-pulse dfu-util pulseaudio-utils
```

Route ALSA through PipeWire (50-pipewire.conf ships with the packages above):

```sh
sudo ln -s /usr/share/alsa/alsa.conf.d/50-pipewire.conf /etc/alsa/conf.d/
```

## Keep the user session alive (systemd linger)

PipeWire runs as a *user* systemd service; without a login session it never starts. Lingering starts the user session at boot, headlessly:

```sh
sudo mkdir -p /var/lib/systemd/linger
sudo touch /var/lib/systemd/linger/$USER
```

## Audio clock at 16 kHz

The voice pipeline expects 16 kHz audio. Create `/etc/pipewire/pipewire.conf.d/linux-voice-assistant.conf`:

```
context.properties = {
    default.clock.rate = 16000
}
```

## udev rule for the USB microphone

The mic (USB `08bb:2902`) needs its ACP profile set on plug. Create `/etc/udev/rules.d/99-pipewire.rules`:

```
ATTRS{idVendor}=="08bb", ATTRS{idProduct}=="2902", ENV{ACP_PROFILE_SET}="default.conf"
```

## Apply changes

```sh
systemctl --user restart pipewire pipewire-pulse wireplumber
sudo udevadm control --reload-rules && sudo udevadm trigger
```