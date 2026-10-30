# Updates the Raspberry Pi and installs the packages QuietDesk needs.
# It asks for the Pi's password once (for sudo).
ssh -t admin@raspberrypi5.local "sudo apt update && sudo apt full-upgrade -y && sudo apt install -y git python3-dev portaudio19-dev alsa-utils python3-lgpio python3-spidev && echo UPDATE-DONE"
